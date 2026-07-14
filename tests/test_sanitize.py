"""Tests for elite_agent.sanitize."""

import email
from pathlib import Path

from elite_agent.sanitize import (
    extract_sanitized_body,
    html_to_text,
    normalize_text,
    sanitize_header_value,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load_msg(name):
    data = (FIXTURES / name).read_bytes()
    return email.message_from_bytes(data)


class TestSanitizeHeaderValue:
    def test_collapses_whitespace(self):
        assert sanitize_header_value("hello    world\t\tagain") == "hello world again"

    def test_strips_control_chars(self):
        assert sanitize_header_value("hello\x00\x01world") == "hello world"

    def test_truncates_to_max_len(self):
        assert sanitize_header_value("a" * 500, max_len=10) == "a" * 10

    def test_empty_value(self):
        assert sanitize_header_value("") == ""
        assert sanitize_header_value(None) == ""


class TestHtmlToText:
    def test_strips_script_content(self):
        html_body = "<html><script>alert('bad')</script><p>Hello</p></html>"
        result = html_to_text(html_body)
        assert "alert" not in result
        assert "bad" not in result
        assert "Hello" in result

    def test_strips_style_content(self):
        html_body = "<style>body{color:red}</style><p>Visible text</p>"
        result = html_to_text(html_body)
        assert "color" not in result
        assert "Visible text" in result

    def test_unescapes_entities(self):
        assert "&" in html_to_text("Fish &amp; Chips")


class TestNormalizeText:
    def test_removes_control_chars(self):
        result = normalize_text("hello\x00world\x01", max_chars=1000)
        assert "\x00" not in result
        assert "\x01" not in result

    def test_truncates_to_max_chars(self):
        result = normalize_text("a" * 5000, max_chars=100)
        assert len(result) == 100

    def test_normalizes_crlf(self):
        result = normalize_text("line1\r\nline2\r\n", max_chars=1000)
        assert "\r" not in result
        assert "line1" in result and "line2" in result

    def test_drops_blank_lines(self):
        result = normalize_text("a\n\n\nb", max_chars=1000)
        assert result == "a\nb"


class TestExtractSanitizedBody:
    def test_plain_text_body(self):
        msg = load_msg("plain.eml")
        body, attachments = extract_sanitized_body(msg, max_chars=8000)
        assert "Tuesday at 10am" in body
        assert attachments == []

    def test_html_body_strips_script(self):
        msg = load_msg("html.eml")
        body, attachments = extract_sanitized_body(msg, max_chars=8000)
        assert "alert" not in body
        assert "should be stripped entirely" not in body
        assert "monthly update" in body
        assert attachments == []

    def test_attachment_discarded_but_name_captured(self):
        msg = load_msg("multipart_attachment.eml")
        body, attachments = extract_sanitized_body(msg, max_chars=8000)
        assert "Please see the attached report" in body
        # The base64 attachment payload must never appear in the body text.
        assert "JVBERi0xLjQK" not in body
        assert attachments == ["report.pdf"]

    def test_max_chars_enforced(self):
        msg = load_msg("plain.eml")
        body, _ = extract_sanitized_body(msg, max_chars=5)
        assert len(body) <= 5
