# Security Design

elite-agent implements defense-in-depth for an LLM-driven email system: untrusted content marking, inbound pattern detection, header risk assessment, outbound policy enforcement, and operational gating.

## Inbound Defenses

### Prompt Injection Prevention

All untrusted email content (subject, body) is wrapped in explicit markers before being included in LLM prompts:

```
BEGIN_UNTRUSTED_EMAIL_BODY
[email subject and body here]
END_UNTRUSTED_EMAIL_BODY
```

This framing helps the LLM distinguish data from instructions and resist prompt-injection attacks that try to override system instructions or leak secrets.

### Attack Pattern Detection

Before any LLM call, the pipeline scans email subject + body for prompt-injection and hacking keywords:

- "ignore all previous instructions" / "disregard prior instructions"
- "reveal system prompt" / "reveal api key" / "reveal secret"
- "bypass safety" / "jailbreak"
- Command execution (`exec(`, `subprocess`, `rm -rf`)
- Script injection (`<script>`, `javascript:`)
- Private key markers (`BEGIN PGP PRIVATE KEY`)

If any pattern matches, the message is **immediately discarded** with an `discard_attack` event logged, before any LLM is invoked. See `elite_agent/security.py:detect_attack_patterns()`.

### Header Risk Flags

The pipeline inspects email headers for spam and phishing signals:

- **`spam_header`:** `X-Spam-Flag: yes` or `X-Spam-Status: yes*`
- **`dmarc_fail`:** `Authentication-Results` contains `dmarc=fail`
- **`spf_and_dkim_fail`:** Both SPF and DKIM fail in auth headers
- **`bulk_list_mail`:** `Precedence: bulk/junk/list` and `List-Unsubscribe` present
- **`phishing_language_with_url`:** Subject contains phishing terms ("verify your account", "gift card", "wire transfer", etc.) AND a URL

If any flag is present, the message is **forced into escalate mode** (held for human review, never auto-replied). See `elite_agent/security.py:detect_header_risk()`.

## Outbound Defenses

### Policy Enforcement

Before sending any reply, the outbound body is checked for violations:

- **No URLs:** Blocks `http://` or `https://` (prevents phishing link injection).
- **No secret-like strings:** Rejects patterns like `api_key:`, `password=`, `secret:=` (prevents accidental secret leaks).
- **Length capped:** Replies truncated to a reasonable length (configurable; default 1000 chars), preferring sentence boundaries.

If any violation is found, the message is **held for review**, not sent. See `elite_agent/security.py:outbound_policy_check()`.

### Body Sanitization

Email bodies are extracted with:
- Character encoding normalization (UTF-8 with replacement for invalid bytes)
- Line ending normalization (CRLF → LF)
- Truncation to a configured limit (default 8000 chars)
- Attachment names extracted but file content never parsed or processed

## Operational Gating

### Dry-Run Default

The agent starts in **dry-run mode** (`EA_DRY_RUN=1`). Drafts are written to `./outbox` but never sent via SMTP. To enable live sending:

```bash
EA_DRY_RUN=0 python3 -m elite_agent run
```

### Sender Allowlist

By default, `EA_REQUIRE_REPLY_ALLOWLIST=1`. Only replies to senders in `EA_ALLOW_SENDERS` (specific emails) or `EA_ALLOW_REPLY_DOMAINS` (domain patterns) are auto-replied. Others are held for review.

### Intent Whitelist

Only intents in `EA_AUTO_REPLY_INTENTS` (e.g., "question", "support", "general") trigger auto-replies. Unknown intents are held.

### Rate Limiting

The agent tracks sends per hour and enforces `EA_MAX_SENDS_PER_HOUR` (default 10). Exceeding this limit holds additional messages for review. State is persisted to `EA_STATE_FILE`.

### Confidence Threshold

LLM interpretation returns a confidence score (0.0–1.0). Messages with confidence below `EA_MIN_LLM_CONFIDENCE` (default 0.6) are held for human review, even if all other gates pass.

## Limitations & Recommendations

**Keyword classifier:** The attack-pattern and risk-flag detection use regex and simple keyword matching. Sophisticated phishing or prompt injection may evade these checks.

**LLM output not guaranteed safe:** Even with all above defenses, the LLM may generate unexpected or unsafe replies. The outbound policy check catches common mistakes (URLs, secrets) but not all failure modes.

**Human review recommended:** For production deployments, route escalated/held messages to a human reviewer (`EA_ESCALATE_EMAIL`) and audit the `EA_AUDIT_FILE` (JSON event log) regularly.

## Audit Logging

All outcomes are logged to `EA_AUDIT_FILE` (default `./state/audit.jsonl`), one JSON event per line:

```json
{"ts": "2024-01-15T14:30:00.123456+00:00", "uid": "123", "message_id": "<...>", "sender": "user@example.com", "subject": "...", "event": "sent"}
{"ts": "2024-01-15T14:30:01.234567+00:00", "uid": "124", "message_id": "<...>", "sender": "attacker@evil.com", "subject": "...", "event": "discard_attack", "patterns": ["reveal api key"]}
{"ts": "2024-01-15T14:30:02.345678+00:00", "uid": "125", "message_id": "<...>", "sender": "partner@example.com", "subject": "...", "event": "escalated"}
```

Events include:
- `sent` – message auto-replied via SMTP
- `drafted` – message drafted but not sent (dry-run or gate not passed)
- `hold` – message held for review (low confidence, gate failure, policy violation)
- `escalated` – message flagged for manual review (risk headers or escalation signal from LLM)
- `discard_attack` – message discarded due to attack pattern match
- `skip_autoreply` – message is itself an auto-reply (avoided reply loop)
- `skip_seen` – message already processed
- `error` – exception during processing

Monitor these logs to detect attack attempts, tune allowlists, and validate agent behavior.

## Storage & Secrets

- **State and audit files** (`state/`, `outbox/`) are **gitignored** and should never be committed.
- **Sensitive config** (`IMAP_PASS`, `SMTP_PASS`, `OPENAI_API_KEY`) should be supplied via environment variables or a `.env` file not checked into version control.
- **Drafts & logs** may contain user email content; handle according to your privacy and data retention policy.

## Data Isolation

- **Attachments never parsed or extracted.** Only headers and text body are processed.
- **External network access:** Only to IMAP/SMTP mail server and OpenAI API. No other outbound connections.
- **No analytics, telemetry, or third-party webhooks** in core; only what you explicitly add.
