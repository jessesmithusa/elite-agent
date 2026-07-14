"""Olympic brain for coaching email classification."""

from __future__ import annotations

from pathlib import Path

from elite_agent.brains.base import BaseBrain, Card
from elite_agent.brains.olympic.classify import classify
from elite_agent.brains.olympic.cards import load_cards, retrieve


class OlympicBrain(BaseBrain):
    """Olympic-themed brain using public athlete stories for routing."""

    name = "olympic"

    def __init__(self, cards: list[Card]):
        """Initialize with loaded cards."""
        self.cards = cards

    def classify(self, text: str) -> list[str]:
        """Classify text using keyword-based bucketing."""
        return classify(text)

    def retrieve(self, buckets: list[str], max_cards: int = 3) -> list[Card]:
        """Retrieve cards matching the given buckets."""
        return retrieve(self.cards, buckets, max_cards)


def get_brain(cfg) -> OlympicBrain:
    """
    Factory function to create and load the Olympic brain.

    Args:
        cfg: Config object with optional cards_dir field

    Returns:
        OlympicBrain instance with loaded cards
    """
    # Bundled cards directory
    bundled_cards_dir = Path(__file__).parent / "cards"
    dirs = [bundled_cards_dir]

    # Add optional extra cards directory from config
    if hasattr(cfg, "cards_dir") and cfg.cards_dir:
        extra_dir = Path(cfg.cards_dir)
        if extra_dir.exists():
            dirs.append(extra_dir)

    # Load all cards
    cards = load_cards(dirs)

    return OlympicBrain(cards)
