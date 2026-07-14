"""Card-based responses for the olympic brain."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from elite_agent.brains.base import Card, parse_frontmatter


# Excluded basenames: templates should never be retrieved as coaching cards.
TEMPLATE_NAMES = {"TEMPLATE.md", "CARD_TEMPLATE.md"}


def load_cards(dirs: list[Path]) -> list[Card]:
    """
    Load coaching cards from directories.

    Args:
        dirs: List of Path objects to search for *.md files

    Returns:
        List of Card objects with parsed metadata and content
    """
    cards = []

    for directory in dirs:
        if not directory.exists():
            continue

        for md_file in sorted(directory.rglob("*.md")):
            if md_file.name in TEMPLATE_NAMES:
                continue

            try:
                content = md_file.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue

            frontmatter = parse_frontmatter(content)
            if not frontmatter:
                continue  # no frontmatter -> not a retrievable card

            # Extract body (everything after frontmatter)
            m = re.match(r"\A\s*^---\s*\n.*?\n^---\s*\n", content, re.DOTALL | re.MULTILINE)
            if m:
                body = content[m.end():].strip()
            else:
                body = content

            # Title from frontmatter 'athlete' + 'skill', or fallback to filename
            athlete = frontmatter.get("athlete", "")
            skill = frontmatter.get("skill", "")
            if athlete and skill:
                title = f"{athlete}: {skill}"
            else:
                title = md_file.stem.replace("-", " ").title()

            card = Card(
                path=str(md_file),
                bucket="",  # Will be set during retrieval
                title=title,
                frontmatter=frontmatter,
                body=body
            )
            cards.append(card)

    return cards


def retrieve(cards: list[Card], buckets: list[str], max_cards: int = 3) -> list[Card]:
    """
    Retrieve cards matching the given buckets.

    Args:
        cards: List of all available cards
        buckets: List of bucket names to match (e.g., ["avoidance", "conflict"])
        max_cards: Maximum number of cards to return

    Returns:
        List of matching Card objects (up to max_cards)
    """
    matched = []
    wanted = {b.lower() for b in buckets}

    for card in cards:
        situation_type = card.frontmatter.get("situation_type", "")
        # situation_type may be a single bucket or (rarely) a list-ish string;
        # split defensively on common separators.
        card_buckets = {
            s.strip().lower()
            for s in re.split(r"[,/|]", situation_type)
            if s.strip()
        }

        if card_buckets & wanted:
            matched_bucket = next(iter(card_buckets & wanted))
            # Update the card's bucket to reflect the matched one
            card.bucket = matched_bucket
            matched.append(card)

            if len(matched) >= max_cards:
                break

    return matched[:max_cards]
