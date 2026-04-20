"""Conservative cleanup for crawled text before indexing."""

from __future__ import annotations

import os
import re
from typing import Any, Dict

from search_quality import is_likely_encoded_garbage_text


LONG_ENCODED_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9+/=])([A-Za-z0-9+/=]{240,})(?![A-Za-z0-9+/=])")
DATA_URI_RE = re.compile(
    r"data:[a-z0-9.+-]+/[a-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]{240,}",
    re.IGNORECASE,
)
FENCED_BLOCK_RE = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)```", re.DOTALL)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _max_content_chars() -> int:
    try:
        return max(10_000, int(os.getenv("CRAWL_MAX_CONTENT_CHARS", "250000")))
    except ValueError:
        return 250_000


def _encoded_placeholder(kind: str) -> str:
    return f"[removed {kind} during crawl indexing]"


def _clean_fenced_block(match: re.Match[str]) -> str:
    language = match.group(1) or ""
    body = match.group(2) or ""
    if is_likely_encoded_garbage_text(body):
        return _encoded_placeholder(f"encoded fenced block{f' ({language})' if language else ''}")
    return match.group(0)


def clean_crawled_content(content: str) -> Dict[str, Any]:
    """Return cleaned text and metadata about removed crawl noise.

    This keeps normal docs/code snippets intact, but removes the most common
    retrieval poison: huge base64/data-URI/Pem-like blobs that can dominate
    embeddings and keyword indexes.
    """

    original = content or ""
    cleaned = CONTROL_CHAR_RE.sub("", original)

    stats: Dict[str, Any] = {
        "original_length": len(original),
        "removed_data_uri_count": 0,
        "removed_encoded_token_count": 0,
        "removed_encoded_fence_count": 0,
        "truncated": False,
        "quality_flags": [],
    }

    def data_uri_repl(_: re.Match[str]) -> str:
        stats["removed_data_uri_count"] += 1
        return _encoded_placeholder("base64 data URI")

    cleaned = DATA_URI_RE.sub(data_uri_repl, cleaned)

    def fence_repl(match: re.Match[str]) -> str:
        replacement = _clean_fenced_block(match)
        if replacement != match.group(0):
            stats["removed_encoded_fence_count"] += 1
        return replacement

    cleaned = FENCED_BLOCK_RE.sub(fence_repl, cleaned)

    def token_repl(match: re.Match[str]) -> str:
        token = match.group(1) or ""
        if is_likely_encoded_garbage_text(token):
            stats["removed_encoded_token_count"] += 1
            return _encoded_placeholder("encoded blob")
        return token

    cleaned = LONG_ENCODED_TOKEN_RE.sub(token_repl, cleaned)

    if is_likely_encoded_garbage_text(cleaned):
        stats["quality_flags"].append("encoded_garbage_document")

    max_chars = _max_content_chars()
    if len(cleaned) > max_chars:
        cleaned = cleaned[:max_chars] + "\n\n[truncated during crawl indexing]"
        stats["truncated"] = True

    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned).strip()
    stats["cleaned_length"] = len(cleaned)

    removed_any = any(
        int(stats[key]) > 0
        for key in (
            "removed_data_uri_count",
            "removed_encoded_token_count",
            "removed_encoded_fence_count",
        )
    )
    if removed_any:
        stats["quality_flags"].append("encoded_noise_removed")
    if stats["truncated"]:
        stats["quality_flags"].append("content_truncated")

    return {"content": cleaned, "metadata": stats}

