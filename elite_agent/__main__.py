"""CLI entry point for elite-agent.

Subcommands:
    run     - run one poll/process/reply cycle and print a JSON summary.
    digest  - print a text digest of pending drafts in the outbox.
    check   - verify config + IMAP/SMTP connectivity without reading or
              sending any mail; exits non-zero if any check fails.
"""

from __future__ import annotations

import argparse
import imaplib
import json
import smtplib
import ssl
import sys
from typing import Optional, Sequence

from elite_agent.config import Config, load_config
from elite_agent.digest import build_digest
from elite_agent.pipeline import run_once

CHECK_TIMEOUT_SEC = 10

REQUIRED_FIELDS = (
    "imap_host",
    "imap_user",
    "imap_pass",
    "smtp_host",
    "smtp_from",
    "openai_api_key",
    "target_address",
)


def _report(name: str, passed: bool, detail: str = "") -> bool:
    status = "PASS" if passed else "FAIL"
    suffix = f" - {detail}" if detail else ""
    print(f"[{status}] {name}{suffix}")
    return passed


def run_checks(cfg: Config) -> int:
    """Verify configuration and connectivity. Never reads or sends mail.

    Returns a process exit code (0 = all checks passed).
    """
    all_ok = True

    try:
        cfg.require(*REQUIRED_FIELDS)
        all_ok &= _report("config", True)
    except ValueError as exc:
        all_ok &= _report("config", False, str(exc))

    try:
        imap = imaplib.IMAP4_SSL(cfg.imap_host, cfg.imap_port)
        imap.login(cfg.imap_user, cfg.imap_pass)
        status, _data = imap.select(cfg.imap_mailbox, readonly=True)
        try:
            imap.logout()
        except Exception:
            pass
        all_ok &= _report("imap_connect", status == "OK")
    except Exception as exc:  # noqa: BLE001 - surfaced as a FAIL line, not a crash
        all_ok &= _report("imap_connect", False, str(exc))

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=CHECK_TIMEOUT_SEC) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
        all_ok &= _report("smtp_connect", True)
    except Exception as exc:  # noqa: BLE001
        all_ok &= _report("smtp_connect", False, str(exc))

    return 0 if all_ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="elite-agent", description="Modular IMAP-in / SMTP-out email agent.")
    parser.add_argument("--env", default=None, help="Path to .env file (defaults to .env.example).")
    parser.add_argument("--profile", default=None, help="Path to profile override file, loaded after --env.")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="Run one poll/process/reply cycle.")
    sub.add_parser("digest", help="Print a digest of pending drafts.")
    sub.add_parser("check", help="Verify config and IMAP/SMTP connectivity.")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = load_config(env_file=args.env, profile_file=args.profile)

    if args.command == "run":
        summary = run_once(cfg)
        print(json.dumps(summary, indent=2))
        return 0

    if args.command == "digest":
        print(build_digest([cfg.outbox_dir]))
        return 0

    if args.command == "check":
        return run_checks(cfg)

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
