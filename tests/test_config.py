"""Tests for configuration loading and parsing."""

import os
import tempfile
from pathlib import Path

import pytest

from elite_agent.config import Config, load_config, _parse_env_file, _to_bool, _to_int, _to_float, _csv_set


class TestParseEnvFile:
    """Test _parse_env_file function."""

    def test_basic_parsing(self, tmp_path):
        """Test basic KEY=VALUE parsing."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n")
        result = _parse_env_file(str(env_file))
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_ignore_comments(self, tmp_path):
        """Test that comments are ignored."""
        env_file = tmp_path / ".env"
        env_file.write_text("# Comment\nKEY1=value1\n# Another comment\nKEY2=value2\n")
        result = _parse_env_file(str(env_file))
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_ignore_blank_lines(self, tmp_path):
        """Test that blank lines are ignored."""
        env_file = tmp_path / ".env"
        env_file.write_text("KEY1=value1\n\nKEY2=value2\n")
        result = _parse_env_file(str(env_file))
        assert result == {"KEY1": "value1", "KEY2": "value2"}

    def test_strip_quotes(self, tmp_path):
        """Test that surrounding quotes are stripped."""
        env_file = tmp_path / ".env"
        env_file.write_text('KEY1="value1"\nKEY2=\'value2\'\nKEY3=value3\n')
        result = _parse_env_file(str(env_file))
        assert result == {"KEY1": "value1", "KEY2": "value2", "KEY3": "value3"}

    def test_nonexistent_file(self):
        """Test that nonexistent file returns empty dict."""
        result = _parse_env_file("/nonexistent/file/.env")
        assert result == {}

    def test_values_with_equals(self, tmp_path):
        """Test values containing equals signs."""
        env_file = tmp_path / ".env"
        env_file.write_text("URL=https://example.com?key=value\n")
        result = _parse_env_file(str(env_file))
        assert result == {"URL": "https://example.com?key=value"}


class TestConversions:
    """Test conversion functions."""

    def test_to_bool(self):
        """Test _to_bool function."""
        assert _to_bool("1") is True
        assert _to_bool("true") is True
        assert _to_bool("True") is True
        assert _to_bool("TRUE") is True
        assert _to_bool("yes") is True
        assert _to_bool("Yes") is True
        assert _to_bool("on") is True
        assert _to_bool("ON") is True
        assert _to_bool("0") is False
        assert _to_bool("false") is False
        assert _to_bool("no") is False
        assert _to_bool("off") is False

    def test_to_int(self):
        """Test _to_int function."""
        assert _to_int("42") == 42
        assert _to_int("0") == 0
        assert _to_int("-5") == -5

    def test_to_float(self):
        """Test _to_float function."""
        assert _to_float("3.14") == 3.14
        assert _to_float("0.0") == 0.0
        assert _to_float("1") == 1.0

    def test_csv_set(self):
        """Test _csv_set function."""
        assert _csv_set("a,b,c") == {"a", "b", "c"}
        assert _csv_set("A,B,C") == {"a", "b", "c"}
        assert _csv_set(" a , b , c ") == {"a", "b", "c"}
        assert _csv_set("") == set()
        assert _csv_set("   ") == set()
        assert _csv_set("single") == {"single"}


class TestConfigDefaults:
    """Test config defaults."""

    def test_defaults_load_without_files(self):
        """Test that defaults load when no files provided."""
        config = load_config()
        assert config.imap_port == 993
        assert config.smtp_port == 587
        assert config.enabled is True
        assert config.dry_run is True
        assert config.persona_name == "Coach"
        assert config.brain == "olympic"
        assert config.openai_model == "gpt-4-mini"


class TestConfigEnvFileParsing:
    """Test config loading from env file."""

    def test_load_from_env_file(self, tmp_path):
        """Test loading config from env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "IMAP_HOST=imap.example.com\n"
            "IMAP_USER=user@example.com\n"
            "IMAP_PASS=secret123\n"
        )
        config = load_config(env_file=str(env_file))
        assert config.imap_host == "imap.example.com"
        assert config.imap_user == "user@example.com"
        assert config.imap_pass == "secret123"
        # Check defaults for other fields
        assert config.imap_port == 993

    def test_env_file_with_comments(self, tmp_path):
        """Test env file parsing with comments."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "# IMAP Configuration\n"
            "IMAP_HOST=imap.example.com\n"
            "# SMTP Configuration\n"
            "SMTP_HOST=smtp.example.com\n"
        )
        config = load_config(env_file=str(env_file))
        assert config.imap_host == "imap.example.com"
        assert config.smtp_host == "smtp.example.com"


class TestConfigProfileOverride:
    """Test profile file overrides."""

    def test_profile_overrides_env_file(self, tmp_path):
        """Test that profile file overrides env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("EA_PERSONA_NAME=DefaultCoach\nEA_BRAIN=olympic\n")

        profile_file = tmp_path / ".env.dev"
        profile_file.write_text("EA_PERSONA_NAME=DevCoach\n")

        config = load_config(env_file=str(env_file), profile_file=str(profile_file))
        assert config.persona_name == "DevCoach"
        assert config.brain == "olympic"  # From env file


class TestConfigProcessEnvOverride:
    """Test process environment overrides."""

    def test_process_env_overrides_files(self, tmp_path, monkeypatch):
        """Test that process env overrides files."""
        env_file = tmp_path / ".env"
        env_file.write_text("EA_PERSONA_NAME=FileCoach\n")

        monkeypatch.setenv("EA_PERSONA_NAME", "EnvCoach")
        config = load_config(env_file=str(env_file))
        assert config.persona_name == "EnvCoach"

    def test_process_env_overrides_both(self, tmp_path, monkeypatch):
        """Test that process env overrides both files."""
        env_file = tmp_path / ".env"
        env_file.write_text("EA_PERSONA_NAME=FileCoach\n")

        profile_file = tmp_path / ".env.dev"
        profile_file.write_text("EA_PERSONA_NAME=ProfileCoach\n")

        monkeypatch.setenv("EA_PERSONA_NAME", "EnvCoach")
        config = load_config(env_file=str(env_file), profile_file=str(profile_file))
        assert config.persona_name == "EnvCoach"


class TestConfigTypeCoercion:
    """Test configuration type coercion."""

    def test_bool_coercion(self, tmp_path):
        """Test boolean field coercion."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "EA_ENABLED=1\n"
            "EA_DRY_RUN=false\n"
            "EA_WRITE_DRAFTS=yes\n"
            "EA_LOG_LLM_IO=no\n"
        )
        config = load_config(env_file=str(env_file))
        assert config.enabled is True
        assert config.dry_run is False
        assert config.write_drafts is True
        assert config.log_llm_io is False

    def test_int_coercion(self, tmp_path):
        """Test integer field coercion."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "IMAP_PORT=995\n"
            "SMTP_PORT=465\n"
            "EA_MAX_MESSAGES_PER_RUN=50\n"
        )
        config = load_config(env_file=str(env_file))
        assert config.imap_port == 995
        assert config.smtp_port == 465
        assert config.max_messages_per_run == 50

    def test_float_coercion(self, tmp_path):
        """Test float field coercion."""
        env_file = tmp_path / ".env"
        env_file.write_text("EA_MIN_LLM_CONFIDENCE=0.85\n")
        config = load_config(env_file=str(env_file))
        assert config.min_llm_confidence == 0.85

    def test_csv_set_coercion(self, tmp_path):
        """Test CSV set field coercion."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "EA_ALLOW_SENDERS=alice@example.com,bob@example.com\n"
            "EA_SKIP_DOMAINS=spam.com,phishing.io\n"
        )
        config = load_config(env_file=str(env_file))
        assert config.allow_senders == {"alice@example.com", "bob@example.com"}
        assert config.skip_domains == {"spam.com", "phishing.io"}


class TestConfigDryRunDefault:
    """Test that dry_run defaults to True."""

    def test_dry_run_default_true(self):
        """Test that dry_run defaults to True."""
        config = load_config()
        assert config.dry_run is True


class TestConfigRepr:
    """Test config repr with masked secrets."""

    def test_repr_masks_imap_pass(self):
        """Test that IMAP password is masked in repr."""
        config = load_config()
        repr_str = repr(config)
        assert "imap_pass=***MASKED***" in repr_str
        # Make sure the actual password doesn't appear (it should be empty default)
        assert config.imap_pass not in repr_str or config.imap_pass == ""

    def test_repr_masks_smtp_pass(self):
        """Test that SMTP password is masked in repr."""
        config = load_config()
        repr_str = repr(config)
        assert "smtp_pass=***MASKED***" in repr_str

    def test_repr_masks_openai_api_key(self):
        """Test that OpenAI API key is masked in repr."""
        config = load_config()
        repr_str = repr(config)
        assert "openai_api_key=***MASKED***" in repr_str


class TestConfigRequire:
    """Test Config.require() method."""

    def test_require_missing_fields(self):
        """Test that require() raises for missing fields."""
        config = load_config()
        with pytest.raises(ValueError) as exc_info:
            config.require("imap_host", "smtp_host")
        assert "Missing required configuration" in str(exc_info.value)
        assert "imap_host" in str(exc_info.value)
        assert "smtp_host" in str(exc_info.value)

    def test_require_present_fields(self, tmp_path):
        """Test that require() passes for present fields."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "IMAP_HOST=imap.example.com\n"
            "SMTP_HOST=smtp.example.com\n"
        )
        config = load_config(env_file=str(env_file))
        # Should not raise
        config.require("imap_host", "smtp_host")

    def test_require_nonexistent_field(self):
        """Test that require() handles nonexistent fields gracefully."""
        config = load_config()
        with pytest.raises(ValueError):
            config.require("nonexistent_field")
