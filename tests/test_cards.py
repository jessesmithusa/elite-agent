"""Tests for card files and structure."""

from pathlib import Path

from elite_agent.brains.base import parse_frontmatter
from elite_agent.brains.olympic.cards import TEMPLATE_NAMES


def test_all_cards_have_valid_frontmatter():
    """Test that every non-template card has parseable frontmatter."""
    cards_dir = Path(__file__).parent.parent / "elite_agent" / "brains" / "olympic" / "cards"

    assert cards_dir.exists(), f"Cards directory not found: {cards_dir}"

    card_files = sorted(cards_dir.glob("*.md"))
    assert len(card_files) > 0, f"No markdown files found in {cards_dir}"

    for card_file in card_files:
        # Skip templates
        if card_file.name in TEMPLATE_NAMES:
            continue

        content = card_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        assert fm, f"{card_file.name}: no frontmatter found"


def test_all_cards_have_situation_type():
    """Test that every card has a situation_type field."""
    cards_dir = Path(__file__).parent.parent / "elite_agent" / "brains" / "olympic" / "cards"

    valid_types = {"avoidance", "overwhelm", "decisiveness", "conflict", "general"}

    for card_file in sorted(cards_dir.glob("*.md")):
        if card_file.name in TEMPLATE_NAMES:
            continue

        content = card_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        assert "situation_type" in fm, f"{card_file.name}: missing situation_type"

        situation_type = fm["situation_type"].strip().lower()
        assert situation_type in valid_types, \
            f"{card_file.name}: situation_type '{situation_type}' not in {valid_types}"


def test_all_cards_have_athlete_and_sport():
    """Test that every card has athlete and sport fields."""
    cards_dir = Path(__file__).parent.parent / "elite_agent" / "brains" / "olympic" / "cards"

    for card_file in sorted(cards_dir.glob("*.md")):
        if card_file.name in TEMPLATE_NAMES:
            continue

        content = card_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)

        assert "athlete" in fm and fm["athlete"].strip(), \
            f"{card_file.name}: missing or empty athlete field"
        assert "sport" in fm and fm["sport"].strip(), \
            f"{card_file.name}: missing or empty sport field"


def test_bundled_cards_present():
    """Test that the 4 bundled cards are present."""
    cards_dir = Path(__file__).parent.parent / "elite_agent" / "brains" / "olympic" / "cards"

    required_cards = {
        "phelps-beijing-goggles.md",
        "biles-tokyo-withdrawal.md",
        "agassi-open-avoidance.md",
        "sale-pelletier-judging.md",
    }

    present_files = {f.name for f in cards_dir.glob("*.md")}

    for card in required_cards:
        assert card in present_files, f"Missing bundled card: {card}"


def test_template_file_excluded():
    """Test that TEMPLATE.md exists but is not treated as a card."""
    cards_dir = Path(__file__).parent.parent / "elite_agent" / "brains" / "olympic" / "cards"

    template_file = cards_dir / "TEMPLATE.md"
    assert template_file.exists(), "TEMPLATE.md should exist"

    # Verify it's in the exclusion list
    assert "TEMPLATE.md" in TEMPLATE_NAMES
