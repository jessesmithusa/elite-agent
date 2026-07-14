"""Security and authorization utilities.

Covers three concerns for an LLM-driven email agent:
- inbound prompt-injection / attack pattern detection over subject+body text
- inbound header-based risk signals (spam flags, auth failures, bulk mail,
  phishing language paired with URLs)
- outbound policy enforcement (block secret-looking leaks and URLs,
  truncate long replies) plus a framing helper that marks untrusted
  content when it is embedded in an LLM prompt.
"""

from __future__ import annotations

import email.message
import re
from typing import List

from elite_agent.sanitize import normalize_text, sanitize_header_value

# --- Inbound attack pattern detection -------------------------------------

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"ignore\s+developer\s+instructions",
    r"disregard\s+(all\s+)?(prior|previous)\s+instructions",
    r"reveal\s+(system\s+prompt|prompt|api\s*key|secret|password)",
    r"system\s+prompt",
    r"bypass\s+(safety|policy|guard)",
    r"jailbreak",
    r"\bexec\(",
    r"\bsubprocess\b",
    r"\brm\s+-rf\b",
    r"<script\b",
    r"javascript:",
    r"BEGIN\s+PGP\s+PRIVATE\s+KEY",
]

_INJECTION_RE = [re.compile(pat, re.IGNORECASE) for pat in INJECTION_PATTERNS]


def detect_attack_patterns(text: str) -> List[str]:
    """
    Scan text (subject + body, or any untrusted text) for prompt-injection
    or hacking indicators. Returns the list of matched pattern strings
    (empty list means no hits).
    """
    text = text or ""
    hits: List[str] = []
    for pattern, compiled in zip(INJECTION_PATTERNS, _INJECTION_RE):
        if compiled.search(text):
            hits.append(pattern)
    return hits


# --- Inbound header risk detection ----------------------------------------


def _header_lower(msg: email.message.Message, key: str) -> str:
    return sanitize_header_value(msg.get(key, ""), max_len=500).lower()


_PHISHING_TERMS = [
    "verify your account",
    "confirm your password",
    "password will expire",
    "gift card",
    "wire transfer",
    "crypto wallet",
    "login immediately",
]
_URL_RE = re.compile(r"https?://", re.IGNORECASE)


def detect_header_risk(msg: email.message.Message) -> List[str]:
    """
    Detect spam/phishing risk signals from raw email headers (and, where
    relevant, header-adjacent body language). Returns a list of risk
    labels (empty list means no risk detected).
    """
    hits: List[str] = []

    spam_flag = _header_lower(msg, "X-Spam-Flag")
    spam_status = _header_lower(msg, "X-Spam-Status")
    auth_results = " ".join(
        sanitize_header_value(v, max_len=500) for v in msg.get_all("Authentication-Results", [])
    ).lower()
    list_unsubscribe = _header_lower(msg, "List-Unsubscribe")
    precedence = _header_lower(msg, "Precedence")

    if spam_flag == "yes" or spam_status.startswith("yes"):
        hits.append("spam_header")
    if "dmarc=fail" in auth_results:
        hits.append("dmarc_fail")
    if "spf=fail" in auth_results and "dkim=fail" in auth_results:
        hits.append("spf_and_dkim_fail")
    if precedence in {"bulk", "junk", "list"} and list_unsubscribe:
        hits.append("bulk_list_mail")

    # Phishing language combined with a URL is a strong signal; check both
    # subject and body-like text via the Subject header (the message body
    # itself should be checked by the caller if desired).
    subject = _header_lower(msg, "Subject")
    if any(term in subject for term in _PHISHING_TERMS) and _URL_RE.search(subject):
        hits.append("phishing_language_with_url")

    return hits


# --- Outbound policy enforcement -------------------------------------------

SECRET_LEAK_RE = re.compile(
    r"(api[_ -]?key|secret|password|token)\s*[:=]", re.IGNORECASE
)
URL_RE = re.compile(r"https?://", re.IGNORECASE)


def outbound_policy_check(body: str) -> List[str]:
    """
    Check an outbound reply body against policy. Returns a list of
    violation reasons; an empty list means the body is OK to send.
    """
    body = body or ""
    violations: List[str] = []
    if not body.strip():
        violations.append("empty_body")
        return violations
    if SECRET_LEAK_RE.search(body):
        violations.append("potential_secret_leak")
    if URL_RE.search(body):
        violations.append("urls_not_allowed_in_auto_reply")
    return violations


def sanitize_outbound_body(body: str, max_chars: int = 1000) -> str:
    """Normalize and truncate an outbound reply body to a bounded length,
    preferring to cut at a sentence/line boundary."""
    normalized = normalize_text(body or "", max_chars=max(max_chars, 1400))
    if len(normalized) <= max_chars:
        return normalized
    cut = normalized[:max_chars]
    boundary = max(cut.rfind("\n"), cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    if boundary > int(max_chars * 0.65):
        return cut[: boundary + 1].strip()
    return cut.rsplit(" ", 1)[0].strip()


# --- Untrusted content framing ----------------------------------------------

_UNTRUSTED_BEGIN = "BEGIN_UNTRUSTED_EMAIL_BODY"
_UNTRUSTED_END = "END_UNTRUSTED_EMAIL_BODY"


def wrap_untrusted(text: str) -> str:
    """Frame untrusted text with explicit begin/end markers for inclusion
    in an LLM prompt, so the model can distinguish data from instructions."""
    return "\n".join([_UNTRUSTED_BEGIN, text or "", _UNTRUSTED_END])
