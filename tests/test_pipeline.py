"""End-to-end pipeline tests using FakeIMAP/FakeSMTP and a fake LLM transport.

No real network or mail server is touched anywhere in this file.
"""

from __future__ import annotations

import email
import email.policy
import io
import json
import os
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import patch

import pytest

from elite_agent import digest as digest_mod
from elite_agent import pipeline
from elite_agent.__main__ import run_checks
from elite_agent.config import load_config
from tests.fakes import FakeIMAP, FakeSMTP

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def make_cfg(tmp_path, **overrides):
    """Build a real Config via load_config(), scoped to a tmp_path sandbox."""
    env = {
        "IMAP_HOST": "imap.example.com",
        "IMAP_PORT": "993",
        "IMAP_USER": "agent@example.com",
        "IMAP_PASS": "secret",
        "IMAP_MAILBOX": "INBOX",
        "SMTP_HOST": "smtp.example.com",
        "SMTP_PORT": "587",
        "SMTP_USER": "agent@example.com",
        "SMTP_PASS": "secret",
        "SMTP_FROM": "coach@example.com",
        "OPENAI_API_KEY": "test-key",
        "OPENAI_MODEL": "test-model",
        "OPENAI_CHAT_URL": "https://example.invalid/v1/chat/completions",
        "EA_ENABLED": "1",
        "EA_DRY_RUN": "1",
        "EA_TARGET_ADDRESS": "coach@example.com",
        "EA_PERSONA_NAME": "Coach",
        "EA_SIGNATURE": "The Team",
        "EA_ORG_CONTEXT": "We help athletes train.",
        "EA_BRAIN": "olympic",
        "EA_REQUIRE_REPLY_ALLOWLIST": "1",
        "EA_ALLOW_SENDERS": "alice@example.com",
        "EA_ALLOW_REPLY_DOMAINS": "",
        "EA_SKIP_DOMAINS": "",
        "EA_AUTO_REPLY_INTENTS": "question,support",
        "EA_MIN_LLM_CONFIDENCE": "0.5",
        "EA_MAX_MESSAGES_PER_RUN": "10",
        "EA_MAX_UID_SCAN": "200",
        "EA_MAX_EMAIL_CHARS": "8000",
        "EA_MAX_SENDS_PER_HOUR": "10",
        "EA_STATE_FILE": str(tmp_path / "state" / "state.json"),
        "EA_AUDIT_FILE": str(tmp_path / "state" / "audit.jsonl"),
        "EA_OUTBOX_DIR": str(tmp_path / "outbox"),
        "EA_REVIEW_DIR": str(tmp_path / "outbox" / "review"),
        "EA_ESCALATE_EMAIL": "",
        "EA_WRITE_DRAFTS": "1",
        "EA_LOG_LLM_IO": "0",
        "EA_LLM_LOG_DIR": str(tmp_path / "state" / "llm"),
        "EA_OPENAI_TIMEOUT_SEC": "5",
        "EA_INTERPRET_MAX_TOKENS": "500",
        "EA_DRAFT_MAX_TOKENS": "500",
    }
    env.update(overrides)

    old = {}
    for k, v in env.items():
        old[k] = os.environ.get(k)
        os.environ[k] = v
    try:
        cfg = load_config()
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    return cfg


class FakeHTTPResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _chat_body(content_obj):
    return {"choices": [{"message": {"content": json.dumps(content_obj)}}]}


def make_llm_transport(interpretation: dict, draft: dict):
    """Return a fake urlopen that answers interpret_email then draft_reply, in order."""
    responses = [interpretation, draft]
    calls = []

    def fake_urlopen(req, timeout=None):
        calls.append(json.loads(req.data.decode("utf-8")))
        payload = responses.pop(0)
        return FakeHTTPResponse(_chat_body(payload))

    return fake_urlopen, calls


def build_message(*, sender, to, subject, body, message_id="<msg1@example.com>"):
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-Id"] = message_id
    msg["Date"] = "Mon, 1 Jan 2026 09:00:00 -0500"
    msg.set_content(body)
    return msg.as_bytes()


def wire_fake_imap(fake_imap, cfg, uid, msg_bytes):
    """Configure FakeIMAP so targeted_unseen_uids(cfg.target_address) returns uid."""
    target = cfg.target_address.strip().lower()
    fake_imap.set_search_response(f"None UNSEEN HEADER To {target}", [uid])
    fake_imap.set_fetch_response(uid, msg_bytes)


# --- Test 1: avoidance-flavored email -> drafted (dry-run) -----------------


def test_run_once_dry_run_drafts_avoidance_email(tmp_path):
    cfg = make_cfg(tmp_path, EA_DRY_RUN="1")

    msg_bytes = build_message(
        sender="Alice Example <alice@example.com>",
        to=cfg.target_address,
        subject="Struggling with training plan",
        body="I keep putting off my training plan and I'm not sure if I'll ever start.",
        message_id="<avoid1@example.com>",
    )

    fake_imap = FakeIMAP()
    wire_fake_imap(fake_imap, cfg, "101", msg_bytes)
    fake_smtp = FakeSMTP()

    interpretation = {
        "intent": "question",
        "urgency": "normal",
        "summary": "Athlete is avoiding their training plan.",
        "should_reply": True,
        "escalate": False,
        "confidence": 0.9,
        "risk_flags": [],
        "needs_clarification": False,
        "clarifying_question": "",
    }
    draft = {"subject": "Re: Struggling with training plan", "body": "Thanks for reaching out. Small steps help."}
    fake_urlopen, calls = make_llm_transport(interpretation, draft)

    with patch("imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("smtplib.SMTP", return_value=fake_smtp), \
         patch("urllib.request.urlopen", fake_urlopen):
        summary = pipeline.run_once(cfg)

    assert summary["counts"] == {"drafted": 1}
    assert summary["total"] == 1
    assert len(calls) == 2  # interpret + draft

    # No live send in dry-run mode.
    assert fake_smtp.messages == []

    # Message marked seen.
    assert "\\Seen" in fake_imap.get_stored_flags("101")

    # Draft JSON written to the outbox with buckets + a matched card.
    outbox_dir = Path(cfg.outbox_dir)
    json_files = list(outbox_dir.glob("*.json"))
    assert len(json_files) == 1
    record = json.loads(json_files[0].read_text())
    assert record["route"]["buckets"] == ["avoidance"]
    assert len(record["route"]["cards"]) >= 1

    # Audit line appended.
    audit_lines = Path(cfg.audit_file).read_text().strip().splitlines()
    assert len(audit_lines) == 1
    assert json.loads(audit_lines[0])["event"] == "drafted"

    # State updated with the message id.
    state = json.loads(Path(cfg.state_file).read_text())
    assert "<avoid1@example.com>" in state["processed_message_ids"]


# --- Test 2: injection fixture -> discard_attack, no LLM call --------------


def test_run_once_discards_injection_attempt(tmp_path):
    cfg = make_cfg(tmp_path)

    fixture_msg = email.message_from_bytes(
        (FIXTURES_DIR / "injection.eml").read_bytes(), policy=email.policy.default
    )
    fixture_msg.replace_header("To", cfg.target_address)
    msg_bytes = fixture_msg.as_bytes()

    fake_imap = FakeIMAP()
    wire_fake_imap(fake_imap, cfg, "202", msg_bytes)
    fake_smtp = FakeSMTP()

    def fail_urlopen(req, timeout=None):
        raise AssertionError("LLM must not be called for an attack-flagged message")

    with patch("imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("smtplib.SMTP", return_value=fake_smtp), \
         patch("urllib.request.urlopen", fail_urlopen):
        summary = pipeline.run_once(cfg)

    assert summary["counts"] == {"discard_attack": 1}
    assert fake_smtp.messages == []
    assert "\\Seen" in fake_imap.get_stored_flags("202")

    audit_lines = Path(cfg.audit_file).read_text().strip().splitlines()
    assert len(audit_lines) == 1
    assert json.loads(audit_lines[0])["event"] == "discard_attack"

    # No draft should be written for a discarded attack message.
    assert list(Path(cfg.outbox_dir).glob("*.json")) == []


# --- Test 3: live send (dry_run=False, allowlisted sender, gates pass) -----


def test_run_once_live_send_when_gates_pass(tmp_path):
    cfg = make_cfg(tmp_path, EA_DRY_RUN="0")

    msg_bytes = build_message(
        sender="Alice Example <alice@example.com>",
        to=cfg.target_address,
        subject="Quick question",
        body="I can't decide whether to push through today's workout or rest, should I train anyway?",
        message_id="<live1@example.com>",
    )

    fake_imap = FakeIMAP()
    wire_fake_imap(fake_imap, cfg, "303", msg_bytes)
    fake_smtp = FakeSMTP()

    interpretation = {
        "intent": "question",
        "urgency": "normal",
        "summary": "Asking about practice time.",
        "should_reply": True,
        "escalate": False,
        "confidence": 0.95,
        "risk_flags": [],
        "needs_clarification": False,
        "clarifying_question": "",
    }
    draft = {"subject": "Re: Quick question", "body": "Practice is at 10am tomorrow, see you there."}
    fake_urlopen, calls = make_llm_transport(interpretation, draft)

    with patch("imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("smtplib.SMTP", return_value=fake_smtp), \
         patch("urllib.request.urlopen", fake_urlopen):
        summary = pipeline.run_once(cfg)

    assert summary["counts"] == {"sent": 1}
    assert len(fake_smtp.messages) == 1
    sent = fake_smtp.messages[0]
    assert sent["To"] == "alice@example.com"
    assert sent["In-Reply-To"] == "<live1@example.com>"

    assert "\\Seen" in fake_imap.get_stored_flags("303")

    state = json.loads(Path(cfg.state_file).read_text())
    assert len(state["sent_reply_timestamps"]) == 1


# --- check subcommand behavior with fakes -----------------------------------


def test_run_checks_all_pass(tmp_path, capsys):
    cfg = make_cfg(tmp_path)

    fake_imap = FakeIMAP()
    fake_smtp = FakeSMTP()

    with patch("imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("smtplib.SMTP", return_value=fake_smtp):
        code = run_checks(cfg)

    out = capsys.readouterr().out
    assert code == 0
    assert "[PASS] config" in out
    assert "[PASS] imap_connect" in out
    assert "[PASS] smtp_connect" in out
    # check must never read or send actual mail.
    assert fake_smtp.messages == []


def test_run_checks_reports_missing_config(tmp_path, capsys):
    cfg = make_cfg(tmp_path, IMAP_HOST="", SMTP_FROM="")

    fake_imap = FakeIMAP()
    fake_smtp = FakeSMTP()

    with patch("imaplib.IMAP4_SSL", return_value=fake_imap), \
         patch("smtplib.SMTP", return_value=fake_smtp):
        code = run_checks(cfg)

    out = capsys.readouterr().out
    assert code == 1
    assert "[FAIL] config" in out


# --- build_digest rendering --------------------------------------------------


def test_build_digest_empty_outbox(tmp_path):
    assert digest_mod.build_digest([str(tmp_path / "does-not-exist")]) == "No pending drafts."


def test_build_digest_renders_drafts_and_skips_llm_subdir(tmp_path):
    outbox = tmp_path / "outbox"
    outbox.mkdir()
    (outbox / "llm").mkdir()

    record = {
        "ts": "2026-01-01T00:00:00+00:00",
        "sender": "alice@example.com",
        "reply_subject": "Re: Hello",
        "body": "This is the drafted reply body text used for the digest preview." * 3,
        "interpretation": {"confidence": 0.82},
        "risk_flags": ["dmarc_fail"],
    }
    (outbox / "draft1.json").write_text(json.dumps(record))
    # Should be skipped: lives under an "llm*" subdirectory.
    (outbox / "llm" / "trace.json").write_text(json.dumps({"sender": "x"}))

    text = digest_mod.build_digest([str(outbox)])
    assert "Pending drafts (1)" in text
    assert "alice@example.com" in text
    assert "Re: Hello" in text
    assert "82%" in text
    assert "dmarc_fail" in text
