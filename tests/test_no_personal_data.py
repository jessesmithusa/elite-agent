"""Test that the repository does not contain personal/sensitive data."""

import codecs
import os
from pathlib import Path


def test_no_personal_data():
    """
    Verify that the repo tree contains no banned personal/sensitive strings.
    This test is critical for ensuring the codebase can be shared safely.

    Banned strings are stored ROT13-encoded to avoid triggering the check itself.
    """
    # ROT13-encoded banned strings (decode with codecs.decode(..., 'rot_13'))
    banned_rot13 = [
        "wrffr",
        "zpypbq",
        "wfc ngyrgrf",
        "wfcnggyrgrf",
        "fgbxrq",
        "pbebaqnqb",
        "lbhegevor",
        "snfgznvy",
        "108.61.214.57",
        "byzcvpnvpbpnpu",
        "/ine/nccf",
    ]
    banned_strings = {codecs.decode(s, "rot_13") if s != "108.61.214.57" else s
                      for s in banned_rot13}

    # Directories to skip
    skip_dirs = {".git", "state", "outbox", "__pycache__", ".pytest_cache", "dist", "build", "*.egg-info"}

    repo_root = Path(__file__).parent.parent
    this_test_file = Path(__file__).resolve()

    for root, dirs, files in os.walk(repo_root):
        # Modify dirs in-place to skip certain directories
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.endswith(".egg-info")]

        for filename in files:
            # Skip binary files and common non-text formats
            if filename.endswith((".pyc", ".so", ".pyd", ".bin", ".png", ".jpg", ".gif", ".pdf")):
                continue

            filepath = Path(root) / filename
            # Skip this test file itself (it needs to contain banned strings to test them)
            if filepath.resolve() == this_test_file:
                continue
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().lower()

                    for banned in banned_strings:
                        banned_lower = banned.lower()
                        assert (
                            banned_lower not in content
                        ), f"Found banned string '{banned}' in {filepath}"
            except (IsADirectoryError, PermissionError):
                # Skip directories and permission-denied files
                continue
