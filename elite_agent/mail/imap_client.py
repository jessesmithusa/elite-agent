"""IMAP client for email ingestion."""

import email.message
import email.policy
import imaplib
import logging
from email.parser import BytesParser
from typing import Optional, List

from elite_agent.config import Config


# Header fields to search when looking for targeted emails
TARGET_HEADER_FIELDS = [
    "To",
    "Cc",
    "Delivered-To",
    "X-Delivered-To",
    "X-Original-To",
    "Envelope-To",
    "X-Resolved-To",
]


def _decode_uid_search(data: tuple) -> List[str]:
    """Decode IMAP UID SEARCH response into a list of UID strings."""
    return [u.decode("utf-8") for u in (data[0] or b"").split() if u]


def _extract_fetch_bytes(fetched: tuple) -> Optional[bytes]:
    """Extract message bytes from an IMAP FETCH response structure."""
    if not fetched:
        return None
    for item in fetched:
        if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
            return bytes(item[1])
    return None


class ImapClient:
    """IMAP client for email operations."""

    def __init__(self, cfg: Config, logger: Optional[logging.Logger] = None):
        """Initialize with configuration.

        Args:
            cfg: Config object with imap_host, imap_port, imap_user, imap_pass, imap_mailbox.
            logger: Optional logger instance.
        """
        self.cfg = cfg
        self.logger = logger or logging.getLogger(__name__)
        self.imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self) -> None:
        """Connect and authenticate to IMAP server."""
        self.imap = imaplib.IMAP4_SSL(self.cfg.imap_host, self.cfg.imap_port)
        self.imap.login(self.cfg.imap_user, self.cfg.imap_pass)
        status, _ = self.imap.select(self.cfg.imap_mailbox)
        if status != "OK":
            raise RuntimeError(f"Failed to select mailbox: {self.cfg.imap_mailbox}")

    def targeted_unseen_uids(self, target_address: str) -> List[bytes]:
        """Search for unseen UIDs in target address fields.

        Searches across multiple header fields (To, Cc, Delivered-To, etc.)
        for unseen messages matching the target address. Falls back to plain
        UNSEEN search if no target is specified.

        Args:
            target_address: Target email address (comma-separated for multiple).

        Returns:
            List of UIDs as bytes, sorted by numeric value.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        targets = [x.strip().lower() for x in (target_address or "").split(",") if x.strip()]

        if not targets:
            # No specific target: search all unseen
            status, data = self.imap.uid("search", None, "UNSEEN")
            if status != "OK":
                raise RuntimeError("IMAP search UNSEEN failed")
            uids = _decode_uid_search(data)
            # Return as bytes for consistency with API
            return [uid.encode("utf-8") for uid in uids]

        # Targeted search across header fields
        seen: set[str] = set()
        for target in targets:
            for header_name in TARGET_HEADER_FIELDS:
                status, data = self.imap.uid("search", None, "UNSEEN", "HEADER", header_name, target)
                if status != "OK":
                    self.logger.warning(
                        "IMAP target search failed header=%s target=%s",
                        header_name,
                        target,
                    )
                    continue
                for uid in _decode_uid_search(data):
                    seen.add(uid)

        # Sort numerically and return as bytes
        sorted_uids = sorted(seen, key=lambda item: int(item))
        return [uid.encode("utf-8") for uid in sorted_uids]

    def fetch_headers(self, uid: bytes) -> email.message.Message:
        """Fetch and parse message headers only.

        Uses BODY.PEEK[HEADER] to avoid marking message as seen.

        Args:
            uid: Message UID (as bytes).

        Returns:
            Parsed email message object.

        Raises:
            RuntimeError: If fetch fails.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else uid
        status, fetched = self.imap.uid("fetch", uid_str, "(BODY.PEEK[HEADER])")

        if status != "OK":
            raise RuntimeError(f"Failed to fetch headers for UID {uid_str}")

        header_bytes = _extract_fetch_bytes(fetched)
        if not header_bytes:
            raise RuntimeError(f"No header data for UID {uid_str}")

        return BytesParser(policy=email.policy.default).parsebytes(header_bytes)

    def fetch_full(self, uid: bytes) -> email.message.Message:
        """Fetch and parse complete message.

        Uses BODY.PEEK[] to avoid marking message as seen.

        Args:
            uid: Message UID (as bytes).

        Returns:
            Parsed email message object.

        Raises:
            RuntimeError: If fetch fails.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else uid
        status, fetched = self.imap.uid("fetch", uid_str, "(BODY.PEEK[])")

        if status != "OK":
            raise RuntimeError(f"Failed to fetch message for UID {uid_str}")

        msg_bytes = _extract_fetch_bytes(fetched)
        if not msg_bytes:
            raise RuntimeError(f"No message data for UID {uid_str}")

        return BytesParser(policy=email.policy.default).parsebytes(msg_bytes)

    def mark_seen(self, uid: bytes) -> None:
        """Mark message as seen.

        Args:
            uid: Message UID (as bytes).

        Raises:
            RuntimeError: If operation fails.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        uid_str = uid.decode("utf-8") if isinstance(uid, bytes) else uid
        status, _ = self.imap.uid("store", uid_str, "+FLAGS", "(\\Seen)")

        if status != "OK":
            raise RuntimeError(f"Failed to mark UID {uid_str} as seen")

    def ensure_folder(self, name: str) -> None:
        """Create folder if it does not exist.

        Tolerates NO response from CREATE (folder already exists on many providers).

        Args:
            name: Folder name (e.g., "[Gmail]/Drafts").

        Raises:
            RuntimeError: If folder creation fails with unexpected status.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        status, _ = self.imap.create(name)
        if status not in {"OK", "NO"}:
            raise RuntimeError(f"Unable to create/check IMAP folder: {name}")

    def append_draft(self, folder: str, message_bytes: bytes) -> None:
        """Append draft message to folder with \\Draft flag.

        Args:
            folder: Target folder name.
            message_bytes: Raw message bytes.

        Raises:
            RuntimeError: If append fails.
        """
        if not self.imap:
            raise RuntimeError("Not connected to IMAP server")

        import time

        self.ensure_folder(folder)
        status, _ = self.imap.append(
            folder,
            "(\\Draft)",
            imaplib.Time2Internaldate(time.time()),
            message_bytes,
        )

        if status != "OK":
            raise RuntimeError(f"Failed to append draft to {folder}")

    def close(self) -> None:
        """Close IMAP connection."""
        if self.imap:
            try:
                self.imap.close()
            except Exception:
                pass
            self.imap = None

    def __del__(self):
        """Ensure connection is closed on object deletion."""
        self.close()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
