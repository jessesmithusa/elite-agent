# Connecting to a Maddy Mail Server

**elite-agent** works with any IMAP/SMTP provider. This guide shows how to set it up with a local [maddy](https://maddy.email/) mail server.

## Prerequisites

- maddy running on your machine or network
- IMAP and submission (SMTP) endpoints exposed (e.g., 127.0.0.1:993 and 127.0.0.1:587)
- Admin access to maddy creds and account commands

## Create an Agent Mailbox

```bash
# Create a password for agent@example.com
maddy creds create agent@example.com

# Create the IMAP account
maddy imap-acct create agent@example.com
```

maddy will prompt for a password; use a strong one. Store it securely (environment variable, `.env` file, secrets manager, etc.).

## Configure .env

In your elite-agent project directory, create `.env` (or edit `.env.example`):

```bash
# IMAP (maddy on 127.0.0.1)
IMAP_HOST=127.0.0.1
IMAP_PORT=993
IMAP_USER=agent@example.com
IMAP_PASS=<password-from-maddy-creds-create>
IMAP_MAILBOX=INBOX

# SMTP (maddy on 127.0.0.1)
SMTP_HOST=127.0.0.1
SMTP_PORT=587
SMTP_USER=agent@example.com
SMTP_PASS=<password-from-maddy-creds-create>
SMTP_FROM=coach@example.com

# LLM
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4-mini

# Agent
EA_TARGET_ADDRESS=coach@example.com
EA_BRAIN=olympic
EA_DRY_RUN=1
```

## TLS Configuration

- **IMAP (port 993):** Implicit SSL. maddy serves it with TLS by default.
- **Submission (port 587):** STARTTLS. maddy upgrades to TLS after initial connection.

elite-agent uses Python's `ssl.create_default_context()` for both, which validates certificates. For local development with self-signed certs, you may need to disable cert verification (not recommended for production):

```python
# In your code, if needed:
import ssl
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE
# Pass context to imaplib.IMAP4_SSL(...) or smtplib.SMTP(..., context=context)
```

## Test Connectivity

```bash
python3 -m elite_agent check
```

This will verify IMAP login, mailbox access, and SMTP connectivity without reading or sending any mail.

## Send Test Mail

To test the agent's routing and drafting:

```bash
# Dry-run (drafts to ./outbox)
python3 -m elite_agent run

# View drafted messages
cat ./outbox/*.json | python3 -m json.tool
```

## Notes

- **maddy is just the reference.** elite-agent also works with Gmail, commercial mail hosts, custom mail servers, or any IMAP/SMTP provider.
- **Permissions:** Ensure the `agent@example.com` account has permission to receive mail (e.g., set up a catchall or mail rules).
- **Spam filtering:** Some mail servers apply aggressive spam filtering. Check maddy logs if mail doesn't arrive:
  ```bash
  # Watch maddy logs
  journalctl -u maddy -f
  ```
