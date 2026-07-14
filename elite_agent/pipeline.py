"""Email processing pipeline: IMAP ingest -> brain routing -> LLM draft -> SMTP reply.

``run_once`` is the entry point invoked by the CLI (and cron). It connects to
IMAP, finds unseen messages addressed to the target address, and hands each
one to :func:`process_one_message`, which decides -- and records -- exactly
one outcome per message:

    sent | drafted | hold | escalated | discard_attack |
    skip_autoreply | skip_seen | error
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parseaddr
from pathlib import Path
from typing import Any, Dict, List, Optional

from elite_agent.brains import load_brain
from elite_agent.config import Config
from elite_agent.llm import draft_reply, interpret_email
from elite_agent.mail.imap_client import ImapClient
from elite_agent.mail.smtp_client import send_reply
from elite_agent.outbox import append_audit, can_send, load_state, record_send, save_draft, save_state
from elite_agent.sanitize import extract_sanitized_body, sanitize_header_value
from elite_agent.security import detect_attack_patterns, detect_header_risk, outbound_policy_check

logger = logging.getLogger(__name__)

_NOREPLY_LOCAL_PREFIXES = ("noreply", "no-reply", "donotreply", "do-not-reply")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _header_lower(msg: Any, key: str) -> str:
    return sanitize_header_value(msg.get(key, ""), max_len=500).lower()


def _is_autoreply(msg: Any, sender_email: str) -> bool:
    """Heuristics for messages that are themselves automated (avoid reply loops)."""
    auto_submitted = _header_lower(msg, "Auto-Submitted")
    precedence = _header_lower(msg, "Precedence")
    suppress = _header_lower(msg, "X-Auto-Response-Suppress")

    if auto_submitted and auto_submitted != "no":
        return True
    if precedence in {"bulk", "junk", "list", "auto_reply", "auto-reply"}:
        return True
    if "all" in suppress:
        return True

    local = (sender_email or "").split("@", 1)[0].lower()
    if local.startswith(_NOREPLY_LOCAL_PREFIXES):
        return True
    if "mailer-daemon" in (sender_email or "") or "postmaster" in (sender_email or ""):
        return True
    return False


def _sender_allowed(cfg: Config, sender_email: str, domain: str) -> bool:
    if not cfg.require_reply_allowlist:
        return True
    if sender_email and sender_email in cfg.allow_senders:
        return True
    if domain and cfg.allow_reply_domains and domain in cfg.allow_reply_domains:
        return True
    return False


def _mark_processed(state: Dict[str, Any], dedupe_key: str, uid_str: str) -> None:
    state.setdefault("processed_message_ids", []).append(dedupe_key)
    state.setdefault("processed_uids", []).append(uid_str)


def process_one_message(
    cfg: Config,
    imap: ImapClient,
    state: Dict[str, Any],
    uid: bytes,
    brain: Any,
) -> str:
    """Process a single message and return its outcome string."""
    uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else str(uid)

    headers_msg = imap.fetch_headers(uid)

    message_id = sanitize_header_value(headers_msg.get("Message-Id", ""), max_len=500)
    _sender_name, sender_email = parseaddr(headers_msg.get("From", ""))
    sender_email = (sender_email or "").strip().lower()
    subject = sanitize_header_value(headers_msg.get("Subject", ""), max_len=300)
    domain = sender_email.rpartition("@")[2].lower() if sender_email else ""

    dedupe_key = message_id or f"uid:{uid_str}"
    audit_base = {
        "uid": uid_str,
        "message_id": message_id,
        "sender": sender_email,
        "subject": subject,
    }

    if dedupe_key in state.get("processed_message_ids", []):
        imap.mark_seen(uid)
        append_audit(Path(cfg.audit_file), dict(audit_base, event="skip_seen"))
        return "skip_seen"

    if _is_autoreply(headers_msg, sender_email):
        _mark_processed(state, dedupe_key, uid_str)
        imap.mark_seen(uid)
        append_audit(Path(cfg.audit_file), dict(audit_base, event="skip_autoreply"))
        return "skip_autoreply"

    full_msg = imap.fetch_full(uid)
    body, attachment_names = extract_sanitized_body(full_msg, cfg.max_email_chars)

    attack_hits = detect_attack_patterns(f"{subject}\n{body}")
    if attack_hits:
        _mark_processed(state, dedupe_key, uid_str)
        imap.mark_seen(uid)
        append_audit(
            Path(cfg.audit_file),
            dict(audit_base, event="discard_attack", patterns=attack_hits),
        )
        return "discard_attack"

    risk_flags: List[str] = detect_header_risk(full_msg)

    route = brain.route(subject, body, bool(risk_flags))

    interpretation = interpret_email(cfg, route.context_text, subject, sender_email, body)
    draft = draft_reply(cfg, route.context_text, interpretation, subject, sender_email, body)

    draft_record: Dict[str, Any] = {
        "ts": _now_iso(),
        "uid": uid_str,
        "message_id": message_id,
        "sender": sender_email,
        "subject": subject,
        "reply_subject": draft["subject"],
        "body": draft["body"],
        "attachment_names": attachment_names,
        "interpretation": interpretation,
        "risk_flags": risk_flags,
        "route": {
            "buckets": route.buckets,
            "mode": route.mode,
            "cards": [card.title for card in route.cards],
        },
    }

    escalate = route.mode == "escalate" or bool(interpretation.get("escalate"))
    should_reply = bool(interpretation.get("should_reply"))
    confidence = float(interpretation.get("confidence", 0.0))

    if escalate:
        if cfg.escalate_email:
            draft_record["escalate_email"] = cfg.escalate_email
        if cfg.write_drafts:
            save_draft(Path(cfg.review_dir), draft_record)
        _mark_processed(state, dedupe_key, uid_str)
        imap.mark_seen(uid)
        append_audit(Path(cfg.audit_file), dict(audit_base, event="escalated"))
        return "escalated"

    if not should_reply or confidence < cfg.min_llm_confidence:
        if cfg.write_drafts:
            save_draft(Path(cfg.review_dir), draft_record)
        _mark_processed(state, dedupe_key, uid_str)
        imap.mark_seen(uid)
        append_audit(
            Path(cfg.audit_file),
            dict(audit_base, event="hold", reason="low_confidence_or_no_reply", confidence=confidence),
        )
        return "hold"

    if cfg.write_drafts:
        save_draft(Path(cfg.outbox_dir), draft_record)

    gates_pass = (
        _sender_allowed(cfg, sender_email, domain)
        and domain not in cfg.skip_domains
        and interpretation.get("intent") in cfg.auto_reply_intents
        and can_send(state, cfg.max_sends_per_hour)
        and route.mode == "draft_now"
    )

    if gates_pass and not cfg.dry_run:
        violations = outbound_policy_check(draft["body"])
        if violations:
            _mark_processed(state, dedupe_key, uid_str)
            imap.mark_seen(uid)
            append_audit(
                Path(cfg.audit_file),
                dict(audit_base, event="hold", reason="outbound_policy_violation", violations=violations),
            )
            return "hold"

        send_reply(
            cfg,
            to_addr=sender_email,
            subject=draft["subject"],
            body=draft["body"],
            in_reply_to=message_id or None,
            references=message_id or None,
        )
        record_send(state)
        _mark_processed(state, dedupe_key, uid_str)
        imap.mark_seen(uid)
        append_audit(Path(cfg.audit_file), dict(audit_base, event="sent"))
        return "sent"

    _mark_processed(state, dedupe_key, uid_str)
    imap.mark_seen(uid)

    if gates_pass and cfg.dry_run:
        append_audit(Path(cfg.audit_file), dict(audit_base, event="drafted", reason="dry_run"))
        return "drafted"

    append_audit(Path(cfg.audit_file), dict(audit_base, event="hold", reason="gate_not_passed"))
    return "hold"


def run_once(cfg: Config) -> Dict[str, Any]:
    """Run one poll/process/reply cycle. Returns a summary dict of outcome counts."""
    if not cfg.enabled:
        return {"status": "skipped", "reason": "disabled", "counts": {}, "total": 0}

    state_path = Path(cfg.state_file)
    state = load_state(state_path)
    counts: Dict[str, int] = {}

    imap = ImapClient(cfg)
    try:
        imap.connect()

        brain = load_brain(cfg)

        uids = imap.targeted_unseen_uids(cfg.target_address)
        if cfg.max_uid_scan > 0:
            uids = uids[-cfg.max_uid_scan :]
        if cfg.max_messages_per_run > 0:
            uids = uids[: cfg.max_messages_per_run]

        for uid in uids:
            uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else str(uid)
            try:
                outcome = process_one_message(cfg, imap, state, uid, brain)
            except Exception as exc:  # noqa: BLE001 - keep the run alive across bad messages
                outcome = "error"
                logger.exception("Error processing uid=%s", uid_str)
                append_audit(
                    Path(cfg.audit_file),
                    {"event": "error", "uid": uid_str, "reason": str(exc)},
                )
            counts[outcome] = counts.get(outcome, 0) + 1
    finally:
        imap.close()

    save_state(state_path, state)

    return {"status": "ok", "counts": counts, "total": sum(counts.values())}
