"""Tests for IMAP and SMTP clients."""

import email.message
import smtplib
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from elite_agent.config import Config
from elite_agent.mail.imap_client import ImapClient
from elite_agent.mail.smtp_client import send_reply
from tests.fakes import FakeIMAP, FakeSMTP


@pytest.fixture
def config():
    """Create test configuration."""
    return Config(
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="test@example.com",
        imap_pass="password",
        imap_mailbox="INBOX",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="test@example.com",
        smtp_pass="password",
        smtp_from="sender@example.com",
        openai_api_key="test",
        openai_model="gpt-4",
        openai_chat_url="http://localhost",
        enabled=True,
        dry_run=False,
        target_address="recipient@example.com",
        persona_name="Test",
        signature="Test Signature",
        org_context="",
        org_context_file="",
        brain="test",
        cards_dir="",
        require_reply_allowlist=False,
        allow_senders=set(),
        allow_reply_domains=set(),
        skip_domains=set(),
        auto_reply_intents=set(),
        min_llm_confidence=0.5,
        max_messages_per_run=10,
        max_uid_scan=100,
        max_email_chars=5000,
        max_sends_per_hour=10,
        state_file="/tmp/state.json",
        audit_file="/tmp/audit.jsonl",
        outbox_dir="/tmp/outbox",
        review_dir="/tmp/review",
        escalate_email="",
        write_drafts=True,
        log_llm_io=False,
        llm_log_dir="/tmp/llm",
        openai_timeout_sec=30,
        interpret_max_tokens=500,
        draft_max_tokens=500,
    )


class TestImapClient:
    """Tests for ImapClient."""

    def test_connect(self, config):
        """Test IMAP connection."""
        fake_imap = FakeIMAP()
        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.connect()
            assert fake_imap.logged_in
            assert fake_imap.selected_mailbox == "INBOX"

    def test_targeted_unseen_uids_no_target(self, config):
        """Test searching for unseen UIDs without target."""
        fake_imap = FakeIMAP()
        fake_imap.set_search_response("None UNSEEN", ["1", "2", "3"])

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            uids = client.targeted_unseen_uids("")
            assert uids == [b"1", b"2", b"3"]

    def test_targeted_unseen_uids_with_target(self, config):
        """Test searching for unseen UIDs matching target address."""
        fake_imap = FakeIMAP()
        # Simulate search responses for different header fields
        fake_imap.set_search_response(
            "None UNSEEN HEADER To recipient@example.com",
            ["1", "2"],
        )
        fake_imap.set_search_response(
            "None UNSEEN HEADER Cc recipient@example.com",
            ["2", "3"],
        )
        # Other fields return empty
        for field in ["Delivered-To", "X-Delivered-To", "X-Original-To", "Envelope-To", "X-Resolved-To"]:
            fake_imap.set_search_response(
                f"None UNSEEN HEADER {field} recipient@example.com",
                [],
            )

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            uids = client.targeted_unseen_uids("recipient@example.com")
            # Should deduplicate and sort numerically
            assert set(uids) == {b"1", b"2", b"3"}
            assert uids == [b"1", b"2", b"3"]

    def test_fetch_headers(self, config):
        """Test fetching headers only."""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Test body")

        fake_imap = FakeIMAP()
        fake_imap.set_fetch_response("1", msg.as_bytes())

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            parsed = client.fetch_headers(b"1")
            assert parsed["From"] == "sender@example.com"
            assert parsed["To"] == "recipient@example.com"

    def test_fetch_full(self, config):
        """Test fetching complete message."""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["To"] = "recipient@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Test body")

        fake_imap = FakeIMAP()
        fake_imap.set_fetch_response("1", msg.as_bytes())

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            parsed = client.fetch_full(b"1")
            assert parsed["From"] == "sender@example.com"
            assert parsed["Subject"] == "Test"
            assert "Test body" in parsed.get_content()

    def test_mark_seen(self, config):
        """Test marking message as seen."""
        fake_imap = FakeIMAP()

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            client.mark_seen(b"1")
            assert "\\Seen" in fake_imap.get_stored_flags("1")

    def test_ensure_folder(self, config):
        """Test folder creation."""
        fake_imap = FakeIMAP()

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            client.ensure_folder("[Gmail]/Drafts")
            assert "[Gmail]/Drafts" in fake_imap.created_folders

    def test_ensure_folder_tolerates_no(self, config):
        """Test that ensure_folder tolerates NO response."""
        fake_imap = FakeIMAP()
        # First call to create returns NO (folder exists)
        original_create = fake_imap.create

        def mock_create(name):
            if name in fake_imap.created_folders:
                return "NO", [b"Folder already exists"]
            fake_imap.created_folders.add(name)
            return "OK", [b""]

        fake_imap.create = mock_create

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            # First call succeeds
            client.ensure_folder("[Gmail]/Drafts")
            # Second call gets NO but doesn't raise
            client.ensure_folder("[Gmail]/Drafts")

    def test_append_draft(self, config):
        """Test appending draft with \\Draft flag."""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Draft"
        msg.set_content("Draft body")

        fake_imap = FakeIMAP()
        fake_imap.create = lambda name: ("OK", [b""])

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            with patch("time.time", return_value=1234567890):
                client = ImapClient(config)
                client.imap = fake_imap

                client.append_draft("[Gmail]/Drafts", msg.as_bytes())

                assert "[Gmail]/Drafts" in fake_imap.appended_messages
                messages = fake_imap.appended_messages["[Gmail]/Drafts"]
                assert len(messages) == 1
                flags, data = messages[0]
                assert "\\Draft" in flags

    def test_peek_does_not_mark_seen(self, config):
        """Test that PEEK fetch doesn't mark message as seen."""
        msg = EmailMessage()
        msg["From"] = "sender@example.com"
        msg["Subject"] = "Test"
        msg.set_content("Test")

        fake_imap = FakeIMAP()
        fake_imap.set_fetch_response("1", msg.as_bytes())

        with patch("imaplib.IMAP4_SSL", return_value=fake_imap):
            client = ImapClient(config)
            client.imap = fake_imap

            # Fetch headers and full message
            client.fetch_headers(b"1")
            client.fetch_full(b"1")

            # Should not have \\Seen flag
            assert "\\Seen" not in fake_imap.get_stored_flags("1")


class TestSmtpClient:
    """Tests for SMTP client."""

    def test_send_reply_basic(self, config):
        """Test sending a basic reply."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP", return_value=fake_smtp):
            send_reply(
                config,
                to_addr="sender@example.com",
                subject="Re: Original",
                body="Reply body",
            )

            assert len(fake_smtp.messages) == 1
            msg = fake_smtp.messages[0]
            assert msg["To"] == "sender@example.com"
            assert msg["From"] == "sender@example.com"
            assert msg["Subject"] == "Re: Original"
            assert "Reply body" in msg.get_content()

    def test_send_reply_with_threading(self, config):
        """Test reply with threading headers."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP", return_value=fake_smtp):
            send_reply(
                config,
                to_addr="sender@example.com",
                subject="Re: Original",
                body="Reply body",
                in_reply_to="<original@example.com>",
                references="<original@example.com>",
            )

            msg = fake_smtp.messages[0]
            assert msg["In-Reply-To"] == "<original@example.com>"
            assert msg["References"] == "<original@example.com>"

    def test_send_reply_sets_auto_submitted(self, config):
        """Test that Auto-Submitted header is set."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP", return_value=fake_smtp):
            send_reply(
                config,
                to_addr="sender@example.com",
                subject="Re: Test",
                body="Reply",
            )

            msg = fake_smtp.messages[0]
            assert msg["Auto-Submitted"] == "auto-replied"
            assert msg["X-Auto-Response-Suppress"] == "All"

    def test_send_reply_custom_from(self, config):
        """Test send with custom from address."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP", return_value=fake_smtp):
            send_reply(
                config,
                to_addr="recipient@example.com",
                subject="Test",
                body="Body",
                from_addr="custom@example.com",
            )

            msg = fake_smtp.messages[0]
            assert msg["From"] == "custom@example.com"

    def test_send_reply_smtp_context_manager(self, config):
        """Test that SMTP is used as context manager."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP") as mock_smtp:
            mock_smtp.return_value = fake_smtp
            mock_smtp.return_value.__enter__ = MagicMock(return_value=fake_smtp)
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)

            send_reply(
                config,
                to_addr="test@example.com",
                subject="Test",
                body="Test",
            )

            # SMTP should be instantiated with correct parameters
            mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)

    def test_send_reply_with_login(self, config):
        """Test SMTP with login credentials."""
        fake_smtp = FakeSMTP()

        with patch("smtplib.SMTP", return_value=fake_smtp):
            send_reply(
                config,
                to_addr="test@example.com",
                subject="Test",
                body="Body",
            )

            assert fake_smtp.starttls_called
            assert fake_smtp.logged_in
