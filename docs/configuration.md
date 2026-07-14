# Configuration Reference

All configuration variables, their defaults, and meanings. Grouped by category.

**Loading precedence** (highest to lowest): process environment (with prefix, e.g., `IMAP_HOST`) → `--profile` file → `--env` file → built-in defaults.

## Mail Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `IMAP_HOST` | `` | IMAP server hostname (e.g., `imap.example.com`, `your-mail-host`) |
| `IMAP_PORT` | `993` | IMAP port (typically 993 for SSL) |
| `IMAP_USER` | `` | IMAP login username (e.g., `your_email@example.com`) |
| `IMAP_PASS` | `` | IMAP password |
| `IMAP_MAILBOX` | `INBOX` | Mailbox name to poll (e.g., `INBOX`, `Custom Folder`) |
| `SMTP_HOST` | `` | SMTP server hostname (e.g., `smtp.example.com`) |
| `SMTP_PORT` | `587` | SMTP port (typically 587 for STARTTLS, 25 or 465 for others) |
| `SMTP_USER` | `` | SMTP login username (often same as IMAP user) |
| `SMTP_PASS` | `` | SMTP password (often same as IMAP password) |
| `SMTP_FROM` | `` | Sender address for outgoing replies (e.g., `coach@example.com`) |

## LLM Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `OPENAI_API_KEY` | `` | OpenAI API key (required; starts with `sk-`) |
| `OPENAI_MODEL` | `gpt-4-mini` | Model ID (e.g., `gpt-4-mini`, `gpt-4`) |
| `OPENAI_CHAT_URL` | `https://api.openai.com/v1/chat/completions` | OpenAI chat completions endpoint URL |

## Agent Behavior

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_ENABLED` | `1` | Enable/disable the agent entirely (1 = true, 0 = false) |
| `EA_DRY_RUN` | `1` | Dry-run mode: draft to `./outbox`, don't send via SMTP (1 = true, 0 = false) |
| `EA_TARGET_ADDRESS` | `` | Email address the agent watches for (e.g., `coach@example.com`) |
| `EA_PERSONA_NAME` | `Coach` | Agent persona name; used in LLM prompts |
| `EA_SIGNATURE` | `` | Email signature appended to replies (optional) |
| `EA_ORG_CONTEXT` | `` | Organization/team context string for LLM (e.g., "Team X coaching guidelines") |
| `EA_ORG_CONTEXT_FILE` | `` | Path to a file containing org context (if `EA_ORG_CONTEXT` is empty, read from this file) |

## Brain & Routing

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_BRAIN` | `olympic` | Brain module name (`olympic` for built-in, or a dotted Python path) |
| `EA_CARDS_DIR` | `` | Extra coaching cards directory (appended to bundled cards) |

## Gating & Allowlist

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_REQUIRE_REPLY_ALLOWLIST` | `1` | Require sender domain/email in allowlist before auto-reply (1 = true, 0 = false) |
| `EA_ALLOW_SENDERS` | `` | Comma-separated list of allowed sender emails (e.g., `user1@example.com, user2@example.com`) |
| `EA_ALLOW_REPLY_DOMAINS` | `` | Comma-separated list of allowed reply domains (e.g., `example.com, partner.org`) |
| `EA_SKIP_DOMAINS` | `` | Comma-separated list of domains to skip entirely (e.g., `spam.com, noreply.example.com`) |
| `EA_AUTO_REPLY_INTENTS` | `question,support,general` | Comma-separated intents allowed to auto-reply (e.g., `question, support`) |
| `EA_MIN_LLM_CONFIDENCE` | `0.6` | Minimum LLM confidence (0.0–1.0) to auto-reply; lower confidence drafts are held for review |

## Rate Limiting & Message Processing

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_MAX_MESSAGES_PER_RUN` | `10` | Max messages to process in one `run` cycle (0 = no limit) |
| `EA_MAX_UID_SCAN` | `200` | Max UIDs to scan from IMAP (0 = no limit; scans from most recent backwards) |
| `EA_MAX_EMAIL_CHARS` | `8000` | Max characters to extract from email body |
| `EA_MAX_SENDS_PER_HOUR` | `10` | Max SMTP sends allowed per hour (enforced via state file) |

## Storage & Output

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_STATE_FILE` | `./state/state.json` | Path to state file (tracks processed message IDs, send rate) |
| `EA_AUDIT_FILE` | `./state/audit.jsonl` | Path to audit log (one JSON event per line) |
| `EA_OUTBOX_DIR` | `./outbox` | Directory to write draft/sent messages (live & dry-run) |
| `EA_REVIEW_DIR` | `./outbox/review` | Subdirectory for escalated/held messages |
| `EA_WRITE_DRAFTS` | `1` | Write all decisions to draft files (1 = true, 0 = false) |

## Escalation & Review

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_ESCALATE_EMAIL` | `` | Optional email address to forward escalated messages to (e.g., `reviewer@example.com`) |

## LLM Logging & Performance

| Variable | Default | Meaning |
|----------|---------|---------|
| `EA_LOG_LLM_IO` | `0` | Log LLM request/response to disk (1 = true, 0 = false) |
| `EA_LLM_LOG_DIR` | `./state/llm` | Directory to write LLM logs (used if `EA_LOG_LLM_IO=1`) |
| `EA_OPENAI_TIMEOUT_SEC` | `60` | HTTP timeout for OpenAI API calls (seconds) |
| `EA_INTERPRET_MAX_TOKENS` | `800` | Max tokens for interpret LLM call (extract intent, confidence) |
| `EA_DRAFT_MAX_TOKENS` | `800` | Max tokens for draft LLM call (synthesize reply) |

## CLI

Pass `--env <path>` to load from a custom `.env` file instead of `.env.example`:

```bash
python3 -m elite_agent --env .env.production run
```

Pass `--profile <path>` to overlay a second config file (applied after `--env`, so it wins):

```bash
python3 -m elite_agent --env .env --profile .env.local run
```

Process environment variables override all files:

```bash
IMAP_HOST=imap.example.com python3 -m elite_agent run
```
