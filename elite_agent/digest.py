"""Email digest and summarization.

Scans one or more outbox directories for saved draft ``*.json`` files
(written by :func:`elite_agent.outbox.save_draft`) and renders a compact,
numbered, human-readable text summary -- newest first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Union


def _iter_draft_files(outbox_dir: Path) -> Iterable[Path]:
    """Yield *.json draft files under outbox_dir, skipping llm* subdirs."""
    if not outbox_dir.exists():
        return
    for json_file in sorted(outbox_dir.rglob("*.json")):
        if any(part.startswith("llm") for part in json_file.relative_to(outbox_dir).parts[:-1]):
            continue
        yield json_file


def _load_draft(json_file: Path) -> Union[Dict[str, Any], None]:
    try:
        data = json.loads(json_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None

    interpretation = data.get("interpretation") or {}
    return {
        "path": str(json_file),
        "ts": data.get("ts") or "?",
        "sender": data.get("sender") or data.get("from") or "?",
        "subject": data.get("reply_subject") or data.get("subject") or "?",
        "body": str(data.get("body") or "")[:200],
        "confidence": float(interpretation.get("confidence", data.get("confidence", 0)) or 0),
        "risk_flags": list(data.get("risk_flags") or interpretation.get("risk_flags") or []),
    }


def collect_drafts(outbox_dirs: Sequence[Union[str, Path]]) -> List[Dict[str, Any]]:
    """Collect and normalize draft records from one or more outbox directories."""
    drafts: List[Dict[str, Any]] = []
    for outbox in outbox_dirs:
        outbox_dir = Path(outbox)
        for json_file in _iter_draft_files(outbox_dir):
            draft = _load_draft(json_file)
            if draft is not None:
                drafts.append(draft)
    drafts.sort(key=lambda d: d["ts"], reverse=True)
    return drafts


def build_digest(outbox_dirs: Sequence[Union[str, Path]]) -> str:
    """Render a compact numbered text digest of pending drafts across outbox_dirs."""
    drafts = collect_drafts(outbox_dirs)

    if not drafts:
        return "No pending drafts."

    lines = [f"Pending drafts ({len(drafts)}):", ""]
    for i, draft in enumerate(drafts, 1):
        risk_str = f" risk={','.join(draft['risk_flags'][:3])}" if draft["risk_flags"] else ""
        lines.append(f"[{i}] {draft['ts']}")
        lines.append(f"    From: {draft['sender']}")
        lines.append(f"    Subject: {draft['subject']}")
        lines.append(f"    Confidence: {draft['confidence']:.0%}{risk_str}")
        lines.append(f"    {draft['body']}")
        lines.append("")

    return "\n".join(lines).rstrip("\n")


def main(argv: Union[Sequence[str], None] = None) -> int:
    """CLI entry point for `python -m elite_agent digest` / standalone use."""
    parser = argparse.ArgumentParser(description="Print a digest of pending elite-agent drafts.")
    parser.add_argument(
        "--outbox-dir",
        action="append",
        dest="outbox_dirs",
        default=None,
        help="Outbox directory to scan (repeatable). Defaults to cfg.outbox_dir.",
    )
    args = parser.parse_args(argv)

    outbox_dirs = args.outbox_dirs
    if not outbox_dirs:
        from elite_agent.config import load_config

        cfg = load_config()
        outbox_dirs = [cfg.outbox_dir]

    print(build_digest(outbox_dirs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
