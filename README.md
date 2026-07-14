# elite-agent

**Modular IMAP-in / SMTP-out email agent for coaching and support.**

Connects to your mail server, classifies incoming messages, routes them to coaching cards via a pluggable brain, interprets intent with OpenAI, drafts replies, and sends or holds them based on safety gates.

## Quickstart

```bash
git clone <repo-url>
cd elite-agent
cp .env.example .env
# Edit .env: fill IMAP_HOST, IMAP_USER, IMAP_PASS, SMTP_HOST, SMTP_FROM, OPENAI_API_KEY
python3 -m elite_agent check    # Verify config and connectivity
python3 -m elite_agent run      # Run one poll/process/reply cycle (dry-run by default)
```

**Drafts land in `./outbox` by default in dry-run mode.** To send live replies:

```bash
# Edit .env: set EA_DRY_RUN=0, add sender domains to EA_ALLOW_REPLY_DOMAINS
python3 -m elite_agent run
```

See `docs/configuration.md` for all configuration variables.

## Architecture

```
IMAP (unseen messages)
    ↓
[Ingest] – extract headers, body, detect attack patterns
    ↓
[Classify] – keyword-based bucket routing (avoidance, overwhelm, etc.)
    ↓
[Retrieve] – load coaching cards for matched buckets
    ↓
[Risk Check] – inspect headers (SPF/DKIM/DMARC, spam flags, phishing language)
    ↓
[Interpret] – two-pass LLM: extract intent, confidence, escalation signal
    ↓
[Draft] – LLM synthesizes coaching context + cards → reply
    ↓
[Policy Check] – outbound: block secrets, URLs, overly long replies
    ↓
[Gates] – dry-run, allowlist, hourly rate limit, intent whitelist
    ↓
[Send or Hold] – SMTP send (live) or save draft (hold/review)
```

## How Routing Works

The **brain** classifies email text into **buckets** (e.g., "avoidance", "overwhelm"), retrieves matching **coaching cards**, and determines a response **mode**:

- `draft_now` – risk-free, cards available, can auto-reply
- `draft_hold` – no cards, send for review
- `escalate` – spam flag, DMARC fail, phishing language → manual review

**Swap brains:** Set `EA_BRAIN=olympic` (default, built-in) or `EA_BRAIN=my.custom.brain` (dynamic import, must implement `get_brain(cfg)`).

**Add cards:** Set `EA_CARDS_DIR=./my-cards` to load `.md` files alongside bundled cards.

## Security Highlights

- **Prompt injection defense:** Untrusted email content wrapped in explicit markers (`BEGIN_UNTRUSTED_EMAIL_BODY`) before LLM prompt.
- **Inbound pattern detection:** Scans subject + body for command injection, jailbreak keywords, private key markers before any LLM call.
- **Header risk flags:** SPF/DKIM/DMARC failures, spam headers, phishing language with URLs force escalation to manual review.
- **Outbound policy:** Blocks URLs and secret-like strings in auto-replies; length-capped; dry-run default.

See `docs/security.md` for implementation details.

## Contributing

**Coaching cards:** Copy `elite_agent/brains/olympic/cards/TEMPLATE.md`, fill frontmatter (situation_type must be avoidance/overwhelm/decisiveness/conflict/general), and write your coaching story. Public athlete figures with cited sources only; no private data. PR must pass `tests/test_cards.py` and `tests/test_no_personal_data.py`.

**Custom brains:** Subpackage under `elite_agent/brains/` exposing `get_brain(cfg) -> BaseBrain`. Keep stdlib-only. Point `EA_BRAIN` at your module path.

## License

MIT
