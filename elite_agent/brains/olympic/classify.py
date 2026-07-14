"""Email classification for the olympic brain."""

from __future__ import annotations


BUCKET_KEYWORDS = {
    "avoidance": [
        "later", "putting off", "put it off", "keep postponing", "postponing",
        "postpone", "not sure if", "avoid", "avoiding", "haven't started",
        "procrastinat", "keep delaying", "delaying", "i'll do it eventually",
    ],
    "overwhelm": [
        "too much", "can't keep up", "cant keep up", "drowning", "overwhelmed",
        "overwhelming", "burnt out", "burned out", "so much going on",
        "no time", "exhausted", "can't handle", "cant handle",
    ],
    "decisiveness": [
        "should i", "can't decide", "cant decide", "torn between", "which one",
        "not sure which", "stuck between", "need to decide", "deciding between",
        "what should i do",
    ],
    "conflict": [
        "argue", "argued", "arguing", "fight with", "fought with", "mad at me",
        "coach yelled", "yelled at", "disagreement", "disagree with", "referee",
        "teammate is", "confront", "confrontation",
    ],
}


def classify(text: str) -> list[str]:
    """Map message text to coarse buckets via transparent keyword matching."""
    lowered = text.lower()
    buckets = []
    for bucket, keywords in BUCKET_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            buckets.append(bucket)
    return buckets or ["general"]
