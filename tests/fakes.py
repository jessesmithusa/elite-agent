"""Fake IMAP and SMTP implementations for testing."""

import email.message
import email.policy
import imaplib
import smtplib
from email.parser import BytesParser
from typing import Any, Dict, List, Optional, Tuple


class FakeIMAP:
    """Scriptable fake IMAP4_SSL for testing."""

    def __init__(self, host: str = "", port: int = 993):
        """Initialize fake IMAP.

        Args:
            host: IMAP server hostname (ignored).
            port: IMAP port (ignored).
        """
        self.host = host
        self.port = port
        self.logged_in = False
        self.selected_mailbox: Optional[str] = None

        # Scriptable responses: search queries can be configured to return specific UIDs
        self.search_responses: Dict[str, List[str]] = {}
        # Scriptable fetch responses: UID -> bytes
        self.fetch_responses: Dict[str, bytes] = {}
        # Stores: UID -> flags
        self.stored_flags: Dict[str, set] = {}
        # Created folders
        self.created_folders: set = set()
        # Appended messages: folder -> list of (flags, message_bytes)
        self.appended_messages: Dict[str, List[Tuple[str, bytes]]] = {}

    def login(self, user: str, passwd: str) -> Tuple[str, List]:
        """Authenticate."""
        self.logged_in = True
        return "OK", [b""]

    def select(self, mailbox: str, readonly: bool = False) -> Tuple[str, List]:
        """Select mailbox."""
        self.selected_mailbox = mailbox
        return "OK", [b"1"]

    def create(self, name: str) -> Tuple[str, List]:
        """Create folder (always succeeds with OK or NO if already exists)."""
        self.created_folders.add(name)
        # Simulate "folder already exists" with NO response if called twice
        if name in self.created_folders:
            return "NO", [b"Folder already exists"]
        return "OK", [b""]

    def uid(self, command: str, *args: Any) -> Tuple[str, List]:
        """Handle UID commands: search, fetch, store."""
        if command == "search":
            # uid search [UNSEEN] [HEADER field value]
            search_key = self._build_search_key(args)
            if search_key in self.search_responses:
                uids = " ".join(self.search_responses[search_key])
                return "OK", [uids.encode("utf-8")]
            return "OK", [b""]

        elif command == "fetch":
            # uid fetch UID (BODY.PEEK[HEADER] | BODY.PEEK[])
            uid = args[0]
            if uid in self.fetch_responses:
                data = self.fetch_responses[uid]
                # Return IMAP-style fetch response: (uid_response, message_bytes)
                return "OK", [(f"{uid} (BODY.PEEK[] {data})".encode("utf-8"), data)]
            return "OK", [b""]

        elif command == "store":
            # uid store UID +FLAGS (\Seen)
            uid = args[0]
            self.stored_flags.setdefault(uid, set()).add("\\Seen")
            return "OK", [b""]

        return "OK", [b""]

    def append(self, mailbox: str, flags: str, date_time: str, message: bytes) -> Tuple[str, List]:
        """Append message to folder."""
        self.appended_messages.setdefault(mailbox, []).append((flags, message))
        return "OK", [b""]

    def close(self) -> Tuple[str, List]:
        """Close connection."""
        return "OK", [b""]

    def _build_search_key(self, args: tuple) -> str:
        """Build a search key for matching responses."""
        return " ".join(str(a) for a in args)

    # Test helpers
    def set_search_response(self, query_key: str, uids: List[str]) -> None:
        """Configure response for a search query."""
        self.search_responses[query_key] = uids

    def set_fetch_response(self, uid: str, message_bytes: bytes) -> None:
        """Configure response for a fetch."""
        self.fetch_responses[uid] = message_bytes

    def get_stored_flags(self, uid: str) -> set:
        """Get flags stored for a UID."""
        return self.stored_flags.get(uid, set())


class FakeSMTP:
    """Scriptable fake SMTP for testing."""

    def __init__(self, host: str = "", port: int = 587, timeout: int = 30):
        """Initialize fake SMTP.

        Args:
            host: SMTP server hostname (ignored).
            port: SMTP port (ignored).
            timeout: Connection timeout (ignored).
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.messages: List[email.message.EmailMessage] = []
        self.logged_in = False
        self.starttls_called = False

    def ehlo(self) -> Tuple[int, List]:
        """Say hello."""
        return (250, [b"OK"])

    def starttls(self, context: Any = None) -> Tuple[int, List]:
        """Upgrade to TLS."""
        self.starttls_called = True
        return (220, [b"Ready to start TLS"])

    def login(self, user: str, password: str) -> Tuple[int, List]:
        """Authenticate."""
        self.logged_in = True
        return (235, [b"OK"])

    def send_message(self, msg: email.message.EmailMessage) -> None:
        """Send message."""
        self.messages.append(msg)

    def close(self) -> None:
        """Close connection."""
        pass

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        """Context manager exit."""
        self.close()
        return False

    # Test helpers
    def get_sent_messages(self) -> List[email.message.EmailMessage]:
        """Get all sent messages."""
        return self.messages
