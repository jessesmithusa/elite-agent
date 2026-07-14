"""Base brain interface and classes."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# Frontmatter block: a literal "---" line at the very top of the file,
# key: value pairs, then a closing "---" line. Parsed with stdlib only.
FRONTMATTER_RE = re.compile(r"\A\s*^---\s*\n(.*?)\n^---\s*$", re.DOTALL | re.MULTILINE)


def parse_frontmatter(text: str) -> dict:
    """Return a dict of frontmatter fields, or {} if the file has none/unparsable."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    block = m.group(1)
    fields = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        # Strip trailing inline comments like:  key: value  # comment
        if "#" in value:
            value = value.split("#", 1)[0].strip()
        # Strip surrounding quotes ("..." or '...').
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key] = value
    return fields


@dataclass
class Card:
    """A coaching card with metadata and content."""
    path: str
    bucket: str
    title: str
    frontmatter: dict
    body: str


@dataclass
class RouteResult:
    """Result of routing a message through the brain."""
    buckets: list[str]
    cards: list[Card]
    mode: str
    context_text: str
    metadata: dict = field(default_factory=dict)


class BaseBrain:
    """Abstract base class for coaching brains."""

    name = "base"

    def classify(self, text: str) -> list[str]:
        """Classify text into coaching buckets. Subclasses must override."""
        raise NotImplementedError(f"{self.name} brain does not implement classify()")

    def retrieve(self, buckets: list[str], max_cards: int = 3) -> list[Card]:
        """Retrieve coaching cards for the given buckets. Subclasses must override."""
        raise NotImplementedError(f"{self.name} brain does not implement retrieve()")

    def mode(self, buckets: list[str], cards: list[Card], risk_flags: bool) -> str:
        """
        Determine response mode based on routing context.

        Returns:
          "escalate" if risk_flags is True (has risks)
          "draft_now" if cards are available (low risk, can draft)
          "draft_hold" if no cards available (need manual review)
        """
        if risk_flags:
            return "escalate"
        elif cards:
            return "draft_now"
        else:
            return "draft_hold"

    def route(self, subject: str, body: str, risk_flags: bool = False) -> RouteResult:
        """
        Route incoming message to cards and response mode.

        Args:
            subject: Email subject line
            body: Email body
            risk_flags: Whether the message has risk indicators

        Returns:
            RouteResult with buckets, cards, mode, and context
        """
        text = f"{subject} {body}".strip()
        if not text:
            return RouteResult(
                buckets=["general"],
                cards=[],
                mode="draft_hold",
                context_text="",
                metadata={}
            )

        buckets = self.classify(text) or ["general"]
        cards = self.retrieve(buckets)
        response_mode = self.mode(buckets, cards, risk_flags)

        # Build context_text: compact block showing each card's content
        context_lines = []
        for card in cards:
            # Truncate body to first 600 chars
            body_preview = card.body[:600]
            context_lines.append(f"### {card.title}\n{body_preview}")
        context_text = "\n\n".join(context_lines)

        return RouteResult(
            buckets=buckets,
            cards=cards,
            mode=response_mode,
            context_text=context_text,
            metadata={}
        )
