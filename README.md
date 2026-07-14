# elite-agent

**An email agent that turns unread mail into reviewed replies — safely.**

It watches an IMAP inbox, routes each message through a coaching "brain"
(pluggable buckets + story cards), asks OpenAI to interpret and draft a reply,
and then either holds the draft for your review or sends it — depending on
gates you control. Pure Python stdlib, one `.env` file, dry-run by default.

```bash
git clone <repo-url> && cd elite-agent
cp .env.example .env        # fill IMAP_*, SMTP_*, OPENAI_API_KEY
python3 -m elite_agent check   # verify config + connectivity
python3 -m elite_agent run     # process unseen mail (dry-run: drafts only)
python3 -m elite_agent digest  # list drafts awaiting your review
```

## The state change (and why it's the point)

Every unseen email ends the run in exactly **one** new state:

```
                     ┌────────────► discard_attack   (injection patterns — never reaches the LLM)
                     │
 unseen email ───► screen ───► route + draft ───┬──► drafted    (dry-run: reply saved to ./outbox)
                     │                          ├──► hold       (low confidence / policy violation — saved for review)
                     │                          ├──► escalated  (spam/DMARC/phishing flags — saved to ./outbox/review)
                     └────────► skip_autoreply  └──► sent       (all gates passed, live mode only)
```

**The benefit:** mail stops piling up silently, but nothing irreversible
happens without you. In the old way, unread email just sits there — invisible
work. Here, every message is *forced through* to a terminal state: either a
ready-to-approve draft, a flagged escalation, or a logged discard. `digest`
shows you the 3–5 drafts that need a yes/no instead of an inbox to excavate.
Going live (`EA_DRY_RUN=0`) only ever adds the `sent` state, and only behind
an allowlist, an intent filter, an hourly rate limit, and an outbound policy
check (no URLs, no secret-shaped strings). Every state change is one line in
an audit log (`state/audit.jsonl`), so you can always answer "what did the
agent do and why."

## Routing: buckets → cards → mode

The default **olympic** brain classifies message text into buckets
(avoidance, overwhelm, decisiveness, conflict), retrieves matching athlete
story cards, and picks the mode (`draft_now` / `draft_hold` / `escalate`).
The cards give the LLM concrete, sourced coaching material instead of generic
advice.

- Swap the whole brain: `EA_BRAIN=my.module` (must expose `get_brain(cfg)`).
- Add private cards without forking: `EA_CARDS_DIR=./my-cards`.
- Contribute public cards via PR — see `CONTRIBUTING.md`.

## Docs

- `docs/configuration.md` — every variable, defaults, layering
- `docs/maddy.md` — pointing the agent at a maddy mail server
- `docs/security.md` — prompt-injection defenses, gates, limitations

## License

MIT
