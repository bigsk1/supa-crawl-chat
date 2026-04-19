"""Decide whether a user message is pure small talk — if so, chat can skip crawl RAG."""

from __future__ import annotations

import re


def is_simple_greeting_message(text: str) -> bool:
    """
    True only for short small-talk where skipping RAG is intended.

    Substantive questions like 'Hey, what can you tell me about OpenClaw?' must return False
    so vector search still runs even though they contain a greeting word.
    """
    clean = (text or "").strip().lower()
    if not clean:
        return False

    words = clean.split()
    n = len(words)
    if n > 6:
        return False
    if "?" in clean and n > 4:
        return False
    if re.search(
        r"\b("
        r"tell me about|can you tell|can you explain|"
        r"what can you|what (is|are)|which|"
        r"how (do|does|can|is|about|much|many)|"
        r"why (is|are|do|does)|"
        r"when (is|are|do|does)|"
        r"where (is|are|do)"
        r")\b",
        clean,
    ):
        return False

    patterns = (
        r"\bhi\b",
        r"\bhello\b",
        r"\bhey\b",
        r"\bgreetings\b",
        r"\bhowdy\b",
        r"\bhola\b",
        r"\bhow\s+are\s+you\b",
        r"\bhow'?s\s+it\s+going\b",
        r"\bwhat'?s\s+up\b",
        r"\bwhat'?s\s+going\s+on\b",
        r"\bsup\b",
        r"\bgood\s+morning\b",
        r"\bgood\s+afternoon\b",
        r"\bgood\s+evening\b",
        r"\bthanks?\b",
        r"\bthank\s+you\b",
        r"\bbye\b",
        r"\bgoodbye\b",
        r"\bsee\s+ya\b",
    )
    return any(re.search(p, clean) for p in patterns)
