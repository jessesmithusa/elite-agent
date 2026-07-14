"""Configuration management for elite-agent."""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Optional


def _to_bool(value: str) -> bool:
    """Convert string to bool. Accepts: 1, true, yes, on (case-insensitive)."""
    return value.lower() in ("1", "true", "yes", "on")


def _to_int(value: str) -> int:
    """Convert string to int."""
    return int(value)


def _to_float(value: str) -> float:
    """Convert string to float."""
    return float(value)


def _csv_set(value: str) -> set[str]:
    """Parse comma-separated values into a lowercase, stripped set."""
    if not value.strip():
        return set()
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def _parse_env_file(path: str) -> dict[str, str]:
    """
    Parse KEY=VALUE environment file.
    Ignores blank lines and comments (lines starting with #).
    Strips optional surrounding quotes from values.
    """
    result = {}
    try:
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Strip optional surrounding quotes
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]
                result[key] = value
    except FileNotFoundError:
        pass
    return result


@dataclass(frozen=True)
class Config:
    """Configuration dataclass for elite-agent."""

    # IMAP configuration
    imap_host: str
    imap_port: int
    imap_user: str
    imap_pass: str
    imap_mailbox: str

    # SMTP configuration
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_pass: str
    smtp_from: str

    # LLM configuration
    openai_api_key: str
    openai_model: str
    openai_chat_url: str

    # Agent behavior
    enabled: bool
    dry_run: bool
    target_address: str
    persona_name: str
    signature: str
    org_context: str
    org_context_file: str
    brain: str
    cards_dir: str
    require_reply_allowlist: bool
    allow_senders: set[str]
    allow_reply_domains: set[str]
    skip_domains: set[str]
    auto_reply_intents: set[str]
    min_llm_confidence: float
    max_messages_per_run: int
    max_uid_scan: int
    max_email_chars: int
    max_sends_per_hour: int
    state_file: str
    audit_file: str
    outbox_dir: str
    review_dir: str
    escalate_email: str
    write_drafts: bool
    log_llm_io: bool
    llm_log_dir: str
    openai_timeout_sec: int
    interpret_max_tokens: int
    draft_max_tokens: int

    def __repr__(self) -> str:
        """Return repr with sensitive fields masked."""
        parts = []
        for fld in fields(self):
            value = getattr(self, fld.name)
            if fld.name in ("imap_pass", "smtp_pass", "openai_api_key"):
                display_value = "***MASKED***"
            else:
                display_value = repr(value)
            parts.append(f"{fld.name}={display_value}")
        return f"Config({', '.join(parts)})"

    def require(self, *names: str) -> None:
        """
        Raise ValueError if any of the named fields are empty/falsy.
        Raises ValueError with a list of missing required fields.
        """
        missing = []
        for name in names:
            try:
                value = getattr(self, name)
                if not value or (isinstance(value, str) and not value.strip()):
                    missing.append(name)
            except AttributeError:
                missing.append(name)

        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")


def load_config(
    env_file: Optional[str] = None, profile_file: Optional[str] = None
) -> Config:
    """
    Load configuration with precedence: process-env > profile_file > env_file > defaults.

    Args:
        env_file: Path to .env file to load (defaults to .env.example).
        profile_file: Path to profile override file (loads after env_file).

    Returns:
        Loaded Config instance.
    """
    # Defaults
    defaults = {
        "imap_host": "",
        "imap_port": 993,
        "imap_user": "",
        "imap_pass": "",
        "imap_mailbox": "INBOX",
        "smtp_host": "",
        "smtp_port": 587,
        "smtp_user": "",
        "smtp_pass": "",
        "smtp_from": "",
        "openai_api_key": "",
        "openai_model": "gpt-4-mini",
        "openai_chat_url": "https://api.openai.com/v1/chat/completions",
        "enabled": True,
        "dry_run": True,
        "target_address": "",
        "persona_name": "Coach",
        "signature": "",
        "org_context": "",
        "org_context_file": "",
        "brain": "olympic",
        "cards_dir": "",
        "require_reply_allowlist": True,
        "allow_senders": "",
        "allow_reply_domains": "",
        "skip_domains": "",
        "auto_reply_intents": "question,support,general",
        "min_llm_confidence": 0.6,
        "max_messages_per_run": 10,
        "max_uid_scan": 200,
        "max_email_chars": 8000,
        "max_sends_per_hour": 10,
        "state_file": "./state/state.json",
        "audit_file": "./state/audit.jsonl",
        "outbox_dir": "./outbox",
        "review_dir": "./outbox/review",
        "escalate_email": "",
        "write_drafts": True,
        "log_llm_io": False,
        "llm_log_dir": "./state/llm",
        "openai_timeout_sec": 60,
        "interpret_max_tokens": 800,
        "draft_max_tokens": 800,
    }

    # Load from env_file
    env_vars = {}
    if env_file:
        env_vars.update(_parse_env_file(env_file))

    # Load from profile_file (overrides env_file)
    if profile_file:
        env_vars.update(_parse_env_file(profile_file))

    # Override with process environment (using EA_ prefix)
    env_mapping = {
        "IMAP_HOST": "imap_host",
        "IMAP_PORT": "imap_port",
        "IMAP_USER": "imap_user",
        "IMAP_PASS": "imap_pass",
        "IMAP_MAILBOX": "imap_mailbox",
        "SMTP_HOST": "smtp_host",
        "SMTP_PORT": "smtp_port",
        "SMTP_USER": "smtp_user",
        "SMTP_PASS": "smtp_pass",
        "SMTP_FROM": "smtp_from",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_MODEL": "openai_model",
        "OPENAI_CHAT_URL": "openai_chat_url",
        "EA_ENABLED": "enabled",
        "EA_DRY_RUN": "dry_run",
        "EA_TARGET_ADDRESS": "target_address",
        "EA_PERSONA_NAME": "persona_name",
        "EA_SIGNATURE": "signature",
        "EA_ORG_CONTEXT": "org_context",
        "EA_ORG_CONTEXT_FILE": "org_context_file",
        "EA_BRAIN": "brain",
        "EA_CARDS_DIR": "cards_dir",
        "EA_REQUIRE_REPLY_ALLOWLIST": "require_reply_allowlist",
        "EA_ALLOW_SENDERS": "allow_senders",
        "EA_ALLOW_REPLY_DOMAINS": "allow_reply_domains",
        "EA_SKIP_DOMAINS": "skip_domains",
        "EA_AUTO_REPLY_INTENTS": "auto_reply_intents",
        "EA_MIN_LLM_CONFIDENCE": "min_llm_confidence",
        "EA_MAX_MESSAGES_PER_RUN": "max_messages_per_run",
        "EA_MAX_UID_SCAN": "max_uid_scan",
        "EA_MAX_EMAIL_CHARS": "max_email_chars",
        "EA_MAX_SENDS_PER_HOUR": "max_sends_per_hour",
        "EA_STATE_FILE": "state_file",
        "EA_AUDIT_FILE": "audit_file",
        "EA_OUTBOX_DIR": "outbox_dir",
        "EA_REVIEW_DIR": "review_dir",
        "EA_ESCALATE_EMAIL": "escalate_email",
        "EA_WRITE_DRAFTS": "write_drafts",
        "EA_LOG_LLM_IO": "log_llm_io",
        "EA_LLM_LOG_DIR": "llm_log_dir",
        "EA_OPENAI_TIMEOUT_SEC": "openai_timeout_sec",
        "EA_INTERPRET_MAX_TOKENS": "interpret_max_tokens",
        "EA_DRAFT_MAX_TOKENS": "draft_max_tokens",
    }

    for env_key, config_key in env_mapping.items():
        if env_key in os.environ:
            env_vars[env_key] = os.environ[env_key]

    # Merge defaults with loaded vars
    config_dict = defaults.copy()
    for env_key, config_key in env_mapping.items():
        if env_key in env_vars:
            config_dict[config_key] = env_vars[env_key]

    # Type conversions
    config_dict["imap_port"] = _to_int(str(config_dict["imap_port"]))
    config_dict["smtp_port"] = _to_int(str(config_dict["smtp_port"]))
    config_dict["enabled"] = _to_bool(str(config_dict["enabled"]))
    config_dict["dry_run"] = _to_bool(str(config_dict["dry_run"]))
    config_dict["require_reply_allowlist"] = _to_bool(
        str(config_dict["require_reply_allowlist"])
    )
    config_dict["write_drafts"] = _to_bool(str(config_dict["write_drafts"]))
    config_dict["log_llm_io"] = _to_bool(str(config_dict["log_llm_io"]))
    config_dict["min_llm_confidence"] = _to_float(str(config_dict["min_llm_confidence"]))
    config_dict["max_messages_per_run"] = _to_int(
        str(config_dict["max_messages_per_run"])
    )
    config_dict["max_uid_scan"] = _to_int(str(config_dict["max_uid_scan"]))
    config_dict["max_email_chars"] = _to_int(str(config_dict["max_email_chars"]))
    config_dict["max_sends_per_hour"] = _to_int(str(config_dict["max_sends_per_hour"]))
    config_dict["openai_timeout_sec"] = _to_int(str(config_dict["openai_timeout_sec"]))
    config_dict["interpret_max_tokens"] = _to_int(
        str(config_dict["interpret_max_tokens"])
    )
    config_dict["draft_max_tokens"] = _to_int(str(config_dict["draft_max_tokens"]))
    config_dict["allow_senders"] = _csv_set(str(config_dict["allow_senders"]))
    config_dict["allow_reply_domains"] = _csv_set(str(config_dict["allow_reply_domains"]))
    config_dict["skip_domains"] = _csv_set(str(config_dict["skip_domains"]))
    config_dict["auto_reply_intents"] = _csv_set(str(config_dict["auto_reply_intents"]))

    return Config(**config_dict)
