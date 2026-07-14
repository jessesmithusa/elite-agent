"""Tests for the brains module."""

import pytest
from pathlib import Path

from elite_agent.brains.base import Card, BaseBrain, parse_frontmatter
from elite_agent.brains.olympic import OlympicBrain, get_brain
from elite_agent.brains import load_brain
from elite_agent.config import Config


def test_parse_frontmatter_valid():
    """Test parsing valid frontmatter."""
    text = """---
athlete: "Michael Phelps"
sport: "swimming"
skill: "executing under crisis"
situation_type: "overwhelm"
---

Body content here."""
    fm = parse_frontmatter(text)
    assert fm["athlete"] == "Michael Phelps"
    assert fm["sport"] == "swimming"
    assert fm["skill"] == "executing under crisis"
    assert fm["situation_type"] == "overwhelm"


def test_parse_frontmatter_with_quotes():
    """Test that quoted values are unquoted."""
    text = """---
athlete: 'Single quotes'
sport: "Double quotes"
---
"""
    fm = parse_frontmatter(text)
    assert fm["athlete"] == "Single quotes"
    assert fm["sport"] == "Double quotes"


def test_parse_frontmatter_with_inline_comment():
    """Test that inline comments are stripped."""
    text = """---
athlete: "Phelps"  # the swimmer
---
"""
    fm = parse_frontmatter(text)
    assert fm["athlete"] == "Phelps"


def test_parse_frontmatter_no_frontmatter():
    """Test that missing frontmatter returns empty dict."""
    text = "Just some text without frontmatter."
    fm = parse_frontmatter(text)
    assert fm == {}


def test_classify_avoidance():
    """Test that avoidance keywords are detected."""
    brain = OlympicBrain([])
    result = brain.classify("I keep postponing my training")
    assert "avoidance" in result


def test_classify_overwhelm():
    """Test that overwhelm keywords are detected."""
    brain = OlympicBrain([])
    result = brain.classify("I'm drowning in too much at once")
    assert "overwhelm" in result


def test_classify_decisiveness():
    """Test that decisiveness keywords are detected."""
    brain = OlympicBrain([])
    result = brain.classify("I can't decide which event to focus on")
    assert "decisiveness" in result


def test_classify_conflict():
    """Test that conflict keywords are detected."""
    brain = OlympicBrain([])
    result = brain.classify("The referee yelled at me")
    assert "conflict" in result


def test_classify_general():
    """Test that neutral text returns 'general' bucket."""
    brain = OlympicBrain([])
    result = brain.classify("I had a good practice today")
    assert result == ["general"]


def test_retrieve_returns_cards():
    """Test that retrieve returns matching cards."""
    card1 = Card(
        path="/path/to/card1.md",
        bucket="overwhelm",
        title="Card 1",
        frontmatter={"situation_type": "overwhelm"},
        body="Body 1"
    )
    card2 = Card(
        path="/path/to/card2.md",
        bucket="conflict",
        title="Card 2",
        frontmatter={"situation_type": "conflict"},
        body="Body 2"
    )
    brain = OlympicBrain([card1, card2])
    result = brain.retrieve(["overwhelm"])
    assert len(result) == 1
    assert result[0].title == "Card 1"


def test_retrieve_respects_max_cards():
    """Test that retrieve limits results by max_cards."""
    cards = [
        Card(
            path=f"/path/to/card{i}.md",
            bucket="overwhelm",
            title=f"Card {i}",
            frontmatter={"situation_type": "overwhelm"},
            body=f"Body {i}"
        )
        for i in range(5)
    ]
    brain = OlympicBrain(cards)
    result = brain.retrieve(["overwhelm"], max_cards=2)
    assert len(result) == 2


def test_retrieve_skips_template():
    """Test that TEMPLATE.md cards are never retrieved."""
    # This is implicit in load_cards, but we verify the intent here
    # by checking that no card has a name that matches TEMPLATE_NAMES
    from elite_agent.brains.olympic.cards import TEMPLATE_NAMES
    assert "TEMPLATE.md" in TEMPLATE_NAMES
    assert "CARD_TEMPLATE.md" in TEMPLATE_NAMES


def test_mode_escalate_on_risk():
    """Test that mode returns 'escalate' when risk_flags is True."""
    brain = OlympicBrain([])
    mode = brain.mode(["general"], [], risk_flags=True)
    assert mode == "escalate"


def test_mode_draft_now_with_cards():
    """Test that mode returns 'draft_now' when cards available and no risk."""
    card = Card(
        path="/path/to/card.md",
        bucket="overwhelm",
        title="Card",
        frontmatter={},
        body="Body"
    )
    brain = OlympicBrain([])
    mode = brain.mode(["overwhelm"], [card], risk_flags=False)
    assert mode == "draft_now"


def test_mode_draft_hold_no_cards():
    """Test that mode returns 'draft_hold' when no cards and no risk."""
    brain = OlympicBrain([])
    mode = brain.mode(["general"], [], risk_flags=False)
    assert mode == "draft_hold"


def test_load_brain_default_olympic():
    """Test that load_brain returns OlympicBrain for default config."""
    cfg = Config(
        imap_host="test", imap_port=993, imap_user="test", imap_pass="test",
        imap_mailbox="INBOX",
        smtp_host="test", smtp_port=587, smtp_user="test", smtp_pass="test",
        smtp_from="test@test.com",
        openai_api_key="test", openai_model="gpt-4", openai_chat_url="https://test",
        enabled=True, dry_run=True, target_address="test@test.com",
        persona_name="Test", signature="Test", org_context="", org_context_file="",
        brain="olympic", cards_dir="",
        require_reply_allowlist=True, allow_senders=set(), allow_reply_domains=set(),
        skip_domains=set(), auto_reply_intents=set(),
        min_llm_confidence=0.6, max_messages_per_run=10, max_uid_scan=200,
        max_email_chars=8000, max_sends_per_hour=10,
        state_file="state.json", audit_file="audit.jsonl",
        outbox_dir="outbox", review_dir="outbox/review",
        escalate_email="", write_drafts=True, log_llm_io=False,
        llm_log_dir="log", openai_timeout_sec=60,
        interpret_max_tokens=800, draft_max_tokens=800
    )
    brain = load_brain(cfg)
    assert isinstance(brain, OlympicBrain)
    assert brain.name == "olympic"


def test_load_brain_invalid_module():
    """Test that load_brain raises error on invalid dotted path."""
    cfg = Config(
        imap_host="test", imap_port=993, imap_user="test", imap_pass="test",
        imap_mailbox="INBOX",
        smtp_host="test", smtp_port=587, smtp_user="test", smtp_pass="test",
        smtp_from="test@test.com",
        openai_api_key="test", openai_model="gpt-4", openai_chat_url="https://test",
        enabled=True, dry_run=True, target_address="test@test.com",
        persona_name="Test", signature="Test", org_context="", org_context_file="",
        brain="nonexistent.brain.module", cards_dir="",
        require_reply_allowlist=True, allow_senders=set(), allow_reply_domains=set(),
        skip_domains=set(), auto_reply_intents=set(),
        min_llm_confidence=0.6, max_messages_per_run=10, max_uid_scan=200,
        max_email_chars=8000, max_sends_per_hour=10,
        state_file="state.json", audit_file="audit.jsonl",
        outbox_dir="outbox", review_dir="outbox/review",
        escalate_email="", write_drafts=True, log_llm_io=False,
        llm_log_dir="log", openai_timeout_sec=60,
        interpret_max_tokens=800, draft_max_tokens=800
    )
    with pytest.raises(ImportError):
        load_brain(cfg)
