"""Email and text sanitization utilities.

These helpers turn raw, untrusted email content (headers, HTML bodies,
multipart MIME structures) into plain, bounded text that is safe to log,
store, and hand to a downstream LLM. Attachments are never parsed - only
their filenames are captured for context.
"""

from __future__ import annotations

import email.message
import html
import re
from typing import List, Tuple

# Control characters (excluding \n and \t, which normalize_text handles
# separately) that should never appear in normalized text.
CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WHITESPACE_RE = re.compile(r"[ \t]+")
TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style).*?>.*?</\1>")


def sanitize_header_value(value: str, max_len: int = 256) -> str:
    """Collapse whitespace/control characters in a header value and cap its length."""
    value = value or ""
    value = CTRL_RE.sub(" ", value)
    value = WHITESPACE_RE.sub(" ", value).strip()
    return value[:max_len]


def html_to_text(html_body: str) -> str:
    """Strip HTML down to plain text, removing script/style content entirely."""
    cleaned = SCRIPT_STYLE_RE.sub(" ", html_body or "")
    cleaned = TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = CTRL_RE.sub(" ", cleaned)
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def normalize_text(text: str, max_chars: int) -> str:
    """Normalize line endings/whitespace, drop control chars, and cap length."""
    text = text or ""
    text = text.replace("\r", "\n")
    text = CTRL_RE.sub(" ", text)
    lines = [WHITESPACE_RE.sub(" ", ln).strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln)
    return text[:max_chars]


def decode_part_payload(part: email.message.Message) -> str:
    """Decode a MIME part's payload to text, tolerating unknown/bad charsets."""
    payload = part.get_payload(decode=True)
    if payload is None:
        raw = part.get_payload() or ""
        if isinstance(raw, str):
            return raw
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except Exception:
        return payload.decode("utf-8", errors="replace")


def extract_sanitized_body(
    msg: email.message.Message, max_chars: int
) -> Tuple[str, List[str]]:
    """
    Extract a sanitized, bounded plain-text body from an email message.

    Returns (body, attachment_names).

    Security behavior:
    - Attachments are discarded and never parsed; only their filenames
      (sanitized) are retained.
    - Only text/plain and text/html parts contribute to the body.
    - HTML parts have script/style content removed before tag stripping.
    """
    chunks: List[str] = []
    attachment_names: List[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue

            filename = part.get_filename()
            disposition = (part.get_content_disposition() or "").lower()
            maintype = part.get_content_maintype()
            ctype = part.get_content_type()

            if disposition == "attachment" or filename:
                attachment_names.append(
                    sanitize_header_value(filename or "attachment", 200)
                )
                continue

            if maintype != "text":
                continue

            body = decode_part_payload(part)
            if ctype == "text/html":
                body = html_to_text(body)
            chunks.append(body)
    else:
        ctype = msg.get_content_type()
        body = decode_part_payload(msg)
        if ctype == "text/html":
            body = html_to_text(body)
        chunks.append(body)

    text = "\n\n".join(chunks)
    text = normalize_text(text, max_chars=max_chars)
    return text, attachment_names
