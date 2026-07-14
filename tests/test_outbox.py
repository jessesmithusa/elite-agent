"""Tests for outbox management."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from elite_agent.outbox import (
    append_audit,
    can_send,
    load_state,
    record_send,
    save_draft,
    save_state,
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestSaveDraft:
    """Tests for save_draft."""

    def test_save_draft_json_only(self, temp_dir):
        """Test saving draft as JSON only."""
        draft = {
            "uid": "123",
            "subject": "Test Subject",
            "to": "recipient@example.com",
            "from": "sender@example.com",
        }

        result = save_draft(temp_dir, draft)

        assert result.exists()
        assert result.suffix == ".json"
        assert "uid123" in result.name
        assert "test_subject" in result.name.lower()

        # Verify content
        content = json.loads(result.read_text())
        assert content["uid"] == "123"
        assert content["subject"] == "Test Subject"

    def test_save_draft_with_eml(self, temp_dir):
        """Test saving draft with JSON and EML files."""
        draft = {
            "uid": "456",
            "subject": "Draft Test",
            "to": "test@example.com",
        }
        eml_bytes = b"From: sender@example.com\nTo: test@example.com\n\nBody"

        result = save_draft(temp_dir, draft, eml_bytes)

        # Check JSON exists
        assert result.exists()
        assert result.suffix == ".json"

        # Check EML exists with same basename
        eml_path = result.parent / (result.stem + ".eml")
        assert eml_path.exists()
        assert eml_path.read_bytes() == eml_bytes

    def test_save_draft_sanitizes_filename(self, temp_dir):
        """Test that unsafe characters are replaced in filename."""
        draft = {
            "uid": "789",
            "subject": "Test/With\\Unsafe:Chars?*",
            "to": "test@example.com",
        }

        result = save_draft(temp_dir, draft)

        # Filename should not contain unsafe characters
        assert "/" not in result.name
        assert "\\" not in result.name
        assert ":" not in result.name
        assert "?" not in result.name
        assert "*" not in result.name

    def test_save_draft_creates_directory(self, temp_dir):
        """Test that save_draft creates missing directories."""
        nested_dir = temp_dir / "sub" / "dir" / "outbox"
        draft = {"uid": "123", "subject": "Test"}

        result = save_draft(nested_dir, draft)

        assert nested_dir.exists()
        assert result.parent == nested_dir


class TestStateManagement:
    """Tests for state load/save."""

    def test_load_state_nonexistent_file(self, temp_dir):
        """Test loading state from nonexistent file."""
        state_file = temp_dir / "state.json"
        state = load_state(state_file)

        assert state["processed_message_ids"] == []
        assert state["processed_uids"] == []
        assert state["sent_reply_timestamps"] == []

    def test_load_state_existing_file(self, temp_dir):
        """Test loading state from existing file."""
        state_file = temp_dir / "state.json"
        original_state = {
            "processed_message_ids": ["msg1", "msg2"],
            "processed_uids": ["1", "2"],
        }
        state_file.write_text(json.dumps(original_state))

        state = load_state(state_file)

        assert state["processed_message_ids"] == ["msg1", "msg2"]
        assert state["processed_uids"] == ["1", "2"]

    def test_load_state_corrupted_file(self, temp_dir):
        """Test loading state from corrupted file returns defaults."""
        state_file = temp_dir / "state.json"
        state_file.write_text("not valid json")

        state = load_state(state_file)

        assert state["processed_message_ids"] == []
        assert state["processed_uids"] == []

    def test_save_state_creates_directory(self, temp_dir):
        """Test that save_state creates missing directories."""
        state_file = temp_dir / "sub" / "dir" / "state.json"
        state = {"processed_message_ids": ["msg1"]}

        save_state(state_file, state)

        assert state_file.parent.exists()
        assert state_file.exists()

    def test_save_state_bounds_lists(self, temp_dir):
        """Test that save_state bounds processed lists to 500 items."""
        state_file = temp_dir / "state.json"
        state = {
            "processed_message_ids": [f"msg{i}" for i in range(600)],
            "processed_uids": [f"{i}" for i in range(600)],
            "sent_reply_timestamps": list(range(600)),
        }

        save_state(state_file, state)

        # Load and verify bounded
        loaded = json.loads(state_file.read_text())
        assert len(loaded["processed_message_ids"]) == 500
        assert len(loaded["processed_uids"]) == 500
        assert len(loaded["sent_reply_timestamps"]) == 500

    def test_save_state_keeps_latest(self, temp_dir):
        """Test that save_state keeps the latest items when bounding."""
        state_file = temp_dir / "state.json"
        state = {
            "processed_message_ids": [f"msg{i}" for i in range(600)],
        }

        save_state(state_file, state)

        loaded = json.loads(state_file.read_text())
        # Should keep msg100-msg599 (latest 500)
        assert loaded["processed_message_ids"][0] == "msg100"
        assert loaded["processed_message_ids"][-1] == "msg599"

    def test_save_state_sets_timestamp(self, temp_dir):
        """Test that save_state adds updated_at timestamp."""
        state_file = temp_dir / "state.json"
        state = {"processed_message_ids": []}

        save_state(state_file, state)

        loaded = json.loads(state_file.read_text())
        assert "updated_at" in loaded
        assert len(loaded["updated_at"]) > 0


class TestAudit:
    """Tests for audit logging."""

    def test_append_audit_creates_file(self, temp_dir):
        """Test that append_audit creates file if missing."""
        audit_file = temp_dir / "audit.jsonl"
        record = {"event": "test", "uid": "123"}

        append_audit(audit_file, record)

        assert audit_file.exists()

    def test_append_audit_adds_timestamp(self, temp_dir):
        """Test that append_audit adds ts if missing."""
        audit_file = temp_dir / "audit.jsonl"
        record = {"event": "test"}

        append_audit(audit_file, record)

        lines = audit_file.read_text().strip().split("\n")
        parsed = json.loads(lines[0])
        assert "ts" in parsed
        assert parsed["event"] == "test"

    def test_append_audit_appends_lines(self, temp_dir):
        """Test that multiple calls append new lines."""
        audit_file = temp_dir / "audit.jsonl"

        append_audit(audit_file, {"event": "event1"})
        append_audit(audit_file, {"event": "event2"})
        append_audit(audit_file, {"event": "event3"})

        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_append_audit_creates_directory(self, temp_dir):
        """Test that append_audit creates missing directories."""
        audit_file = temp_dir / "sub" / "dir" / "audit.jsonl"
        record = {"event": "test"}

        append_audit(audit_file, record)

        assert audit_file.parent.exists()
        assert audit_file.exists()


class TestRateLimiting:
    """Tests for hourly rate limiting."""

    def test_can_send_unlimited(self):
        """Test that max_per_hour=0 means unlimited."""
        state = {"sent_reply_timestamps": []}
        assert can_send(state, max_per_hour=0)

    def test_can_send_under_limit(self):
        """Test can_send when under limit."""
        now = int(time.time())
        state = {
            "sent_reply_timestamps": [now - 1800, now - 1200],  # 30min, 20min ago
        }
        assert can_send(state, max_per_hour=10)

    def test_can_send_at_limit(self):
        """Test can_send when at limit."""
        now = int(time.time())
        timestamps = [now - 60 * i for i in range(10)]  # 10 sends in last hour
        state = {"sent_reply_timestamps": timestamps}
        assert not can_send(state, max_per_hour=10)

    def test_can_send_prunes_old_timestamps(self):
        """Test that can_send prunes timestamps older than 1 hour."""
        now = int(time.time())
        state = {
            "sent_reply_timestamps": [
                now - 7200,  # 2 hours ago (should be pruned)
                now - 1800,  # 30 min ago (should be kept)
                now - 600,   # 10 min ago (should be kept)
            ]
        }
        can_send(state, max_per_hour=10)
        # After pruning, should have 2 timestamps
        assert len(state["sent_reply_timestamps"]) == 2

    def test_can_send_negative_limit(self):
        """Test that negative limit is treated as unlimited."""
        state = {"sent_reply_timestamps": list(range(100))}
        assert can_send(state, max_per_hour=-1)


class TestRecordSend:
    """Tests for recording sends."""

    def test_record_send_adds_timestamp(self):
        """Test that record_send adds current timestamp."""
        state = {"sent_reply_timestamps": []}
        now = int(time.time())

        record_send(state)

        assert len(state["sent_reply_timestamps"]) == 1
        # Timestamp should be close to now (within 1 second)
        recorded = state["sent_reply_timestamps"][0]
        assert abs(recorded - now) < 2

    def test_record_send_multiple_times(self):
        """Test recording multiple sends."""
        state = {"sent_reply_timestamps": []}

        for i in range(3):
            record_send(state)

        assert len(state["sent_reply_timestamps"]) == 3

    def test_record_send_prunes_old(self):
        """Test that record_send prunes old timestamps."""
        now = int(time.time())
        old_timestamp = now - 7200  # 2 hours ago (will be pruned)
        recent_timestamp = now - 1800  # 30 min ago (will be kept)
        state = {
            "sent_reply_timestamps": [old_timestamp, recent_timestamp]
        }

        record_send(state)

        # Old timestamp should be pruned, recent one + new one kept
        assert len(state["sent_reply_timestamps"]) == 2  # 1 recent + 1 new
        # Old timestamp should not be in the list
        assert old_timestamp not in state["sent_reply_timestamps"]

    def test_record_send_with_mock_time(self):
        """Test record_send with mocked time."""
        state = {"sent_reply_timestamps": []}
        mock_now = 1000000

        with patch("elite_agent.outbox._current_epoch", return_value=mock_now):
            record_send(state)

        assert mock_now in state["sent_reply_timestamps"]


class TestIntegration:
    """Integration tests for state operations."""

    def test_state_roundtrip(self, temp_dir):
        """Test saving and loading state preserves data."""
        state_file = temp_dir / "state.json"
        original_state = {
            "processed_message_ids": ["msg1", "msg2"],
            "processed_uids": ["1", "2"],
            "sent_reply_timestamps": [1000, 2000],
        }

        save_state(state_file, original_state)
        loaded_state = load_state(state_file)

        assert loaded_state["processed_message_ids"] == ["msg1", "msg2"]
        assert loaded_state["processed_uids"] == ["1", "2"]
        assert loaded_state["sent_reply_timestamps"] == [1000, 2000]

    def test_rate_limit_workflow(self, temp_dir):
        """Test complete rate limit check and record workflow."""
        state = load_state(temp_dir / "state.json")
        max_per_hour = 5

        # Record 4 sends
        for _ in range(4):
            assert can_send(state, max_per_hour)
            record_send(state)

        # 5th send should succeed (at limit)
        assert can_send(state, max_per_hour)
        record_send(state)

        # 6th send should fail (over limit)
        assert not can_send(state, max_per_hour)
