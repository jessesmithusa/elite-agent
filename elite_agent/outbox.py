"""Outbox management and message queueing."""

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def save_draft(outbox_dir: Path, draft: Dict[str, Any], eml_bytes: Optional[bytes] = None) -> Path:
    """Save draft email as JSON summary and optional EML file.

    Creates a timestamped pair of files:
    - {timestamp}_uid{uid}_{subject}.json: Metadata and draft details
    - {timestamp}_uid{uid}_{subject}.eml: Raw message (optional)

    Args:
        outbox_dir: Directory to save draft files.
        draft: Dictionary with draft metadata (uid, subject, etc.).
        eml_bytes: Optional raw message bytes (EML format).

    Returns:
        Path to the JSON file created.
    """
    outbox_dir = Path(outbox_dir)
    outbox_dir.mkdir(parents=True, exist_ok=True)

    # Create timestamp and safe filename tokens
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    uid_token = _safe_token(str(draft.get("uid", "")), max_len=24)
    subject_token = _safe_token(str(draft.get("subject", "") or ""), max_len=64)

    base_name = f"{timestamp}_uid{uid_token}_{subject_token}"
    json_path = outbox_dir / f"{base_name}.json"

    # Write JSON summary
    json_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    # Write EML if provided
    if eml_bytes:
        eml_path = outbox_dir / f"{base_name}.eml"
        eml_path.write_bytes(eml_bytes)

    return json_path


def _safe_token(value: str, max_len: int = 80) -> str:
    """Convert string to safe filename token."""
    token = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    token = token.strip("._-")
    if not token:
        token = "item"
    return token[:max_len]


def load_state(path: Path) -> Dict[str, Any]:
    """Load state from JSON file.

    Returns default empty state if file does not exist.

    Args:
        path: Path to state JSON file.

    Returns:
        Dictionary with state (processed_message_ids, processed_uids, etc.).
    """
    path = Path(path)
    if not path.exists():
        return {
            "processed_message_ids": [],
            "processed_uids": [],
            "sent_reply_timestamps": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "processed_message_ids": [],
            "processed_uids": [],
            "sent_reply_timestamps": [],
        }


def save_state(path: Path, state: Dict[str, Any]) -> None:
    """Save state to JSON file, bounded to prevent unbounded growth.

    Keeps:
    - Latest 500 processed_message_ids
    - Latest 500 processed_uids
    - Latest 500 sent_reply_timestamps

    Args:
        path: Path to state JSON file.
        state: State dictionary to save.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Bound state to prevent unbounded growth
    bounded_state = dict(state)
    bounded_state["processed_message_ids"] = state.get("processed_message_ids", [])[-500:]
    bounded_state["processed_uids"] = state.get("processed_uids", [])[-500:]
    bounded_state["sent_reply_timestamps"] = state.get("sent_reply_timestamps", [])[-500:]

    # Ensure timestamp field for tracking
    bounded_state["updated_at"] = datetime.now(timezone.utc).isoformat()

    path.write_text(
        json.dumps(bounded_state, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def append_audit(path: Path, record: Dict[str, Any]) -> None:
    """Append audit event to JSONL file.

    Args:
        path: Path to audit JSONL file.
        record: Event record dictionary.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Add timestamp if not present
    line = dict(record)
    if "ts" not in line:
        line["ts"] = datetime.now(timezone.utc).isoformat()

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=True) + "\n")


def _current_epoch() -> int:
    """Return current Unix timestamp."""
    return int(time.time())


def _prune_send_timestamps(state: Dict[str, Any], now: Optional[int] = None) -> list:
    """Remove send timestamps older than 1 hour.

    Args:
        state: State dictionary (modified in-place).
        now: Optional current timestamp (defaults to current time).

    Returns:
        List of recent timestamps (< 1 hour old).
    """
    current = _current_epoch() if now is None else int(now)
    cutoff = current - 3600  # 1 hour ago

    kept = []
    for raw in state.get("sent_reply_timestamps", []):
        try:
            stamp = int(raw)
        except (ValueError, TypeError):
            continue
        if stamp >= cutoff:
            kept.append(stamp)

    state["sent_reply_timestamps"] = kept
    return kept


def can_send(state: Dict[str, Any], max_per_hour: int) -> bool:
    """Check if under hourly rate limit.

    Args:
        state: State dictionary with send history.
        max_per_hour: Maximum sends allowed per hour (0 = unlimited).

    Returns:
        True if send is allowed, False if rate limit exceeded.
    """
    if max_per_hour <= 0:
        return True

    kept = _prune_send_timestamps(state)
    return len(kept) < max_per_hour


def record_send(state: Dict[str, Any]) -> None:
    """Record successful send in state.

    Updates sent_reply_timestamps with current timestamp.

    Args:
        state: State dictionary (modified in-place).
    """
    now = _current_epoch()
    _prune_send_timestamps(state, now=now)
    state.setdefault("sent_reply_timestamps", []).append(now)
