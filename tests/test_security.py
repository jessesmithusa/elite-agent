"""Tests for elite_agent.security."""

import email
from pathlib import Path

from elite_agent.security import (
    detect_attack_patterns,
    detect_header_risk,
    outbound_policy_check,
    sanitize_outbound_body,
    wrap_untrusted,
)
from elite_agent.sanitize import extract_sanitized_body

FIXTURES = Path(__file__).parent / "fixtures"


def load_msg(name):
    data = (FIXTURES / name).read_bytes()
    return email.message_from_bytes(data)


class TestDetectAttackPatterns:
    def test_clean_text_on_plain_fixture(self):
        msg = load_msg("plain.eml")
        body, _ = extract_sanitized_body(msg, max_chars=8000)
        subject = msg.get("Subject", "")
        hits = detect_attack_patterns(f"{subject}\n{body}")
        assert hits == []

    def test_detects_injection_on_injection_fixture(self):
        msg = load_msg("injection.eml")
        body, _ = extract_sanitized_body(msg, max_chars=8000)
        subject = msg.get("Subject", "")
        hits = detect_attack_patterns(f"{subject}\n{body}")
        assert hits != []

    def test_detects_various_patterns(self):
        assert detect_attack_patterns("please JAILBREAK the model") != []
        assert detect_attack_patterns("run rm -rf / now") != []
        assert detect_attack_patterns("<script>evil()</script>") != []

    def test_empty_text(self):
        assert detect_attack_patterns("") == []
        assert detect_attack_patterns(None) == []


class TestDetectHeaderRisk:
    def test_dmarc_fail_flags(self):
        msg = load_msg("dmarc_fail.eml")
        hits = detect_header_risk(msg)
        assert "dmarc_fail" in hits

    def test_bulk_list_flags(self):
        msg = load_msg("bulk_list.eml")
        hits = detect_header_risk(msg)
        assert "bulk_list_mail" in hits

    def test_clean_plain_message_has_no_risk(self):
        msg = load_msg("plain.eml")
        hits = detect_header_risk(msg)
        assert hits == []


class TestOutboundPolicyCheck:
    def test_blocks_secret_leak(self):
        violations = outbound_policy_check("here is the value: api_key=sk-abc123")
        assert "potential_secret_leak" in violations

    def test_blocks_url(self):
        violations = outbound_policy_check("check this out: https://example.com/page")
        assert "urls_not_allowed_in_auto_reply" in violations

    def test_blocks_empty_body(self):
        violations = outbound_policy_check("   ")
        assert "empty_body" in violations

    def test_clean_body_passes(self):
        violations = outbound_policy_check("Thanks for reaching out, we'll follow up soon.")
        assert violations == []


class TestSanitizeOutboundBody:
    def test_short_body_unchanged(self):
        body = "Thanks for your note."
        assert sanitize_outbound_body(body, max_chars=1000) == body

    def test_long_body_truncated(self):
        body = "word " * 500
        result = sanitize_outbound_body(body, max_chars=100)
        assert len(result) <= 100

    def test_removes_control_chars(self):
        result = sanitize_outbound_body("hello\x00world", max_chars=1000)
        assert "\x00" not in result


class TestWrapUntrusted:
    def test_framing_markers_present(self):
        wrapped = wrap_untrusted("some untrusted content")
        assert "BEGIN_UNTRUSTED_EMAIL_BODY" in wrapped
        assert "END_UNTRUSTED_EMAIL_BODY" in wrapped
        assert "some untrusted content" in wrapped
        begin_idx = wrapped.index("BEGIN_UNTRUSTED_EMAIL_BODY")
        end_idx = wrapped.index("END_UNTRUSTED_EMAIL_BODY")
        assert begin_idx < end_idx

    def test_wraps_empty_text(self):
        wrapped = wrap_untrusted("")
        assert "BEGIN_UNTRUSTED_EMAIL_BODY" in wrapped
        assert "END_UNTRUSTED_EMAIL_BODY" in wrapped
