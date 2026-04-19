"""
Heuristics to keep vector search from surfacing base64 blobs and similar crawled noise.
"""

from __future__ import annotations

from typing import Any, Dict, List


def is_likely_encoded_garbage_text(text: str) -> bool:
    """
    True when *text* looks like a long base64/pem/minified blob (few spaces, high [A-Za-z0-9+/=] ratio).
    Such content sometimes gets moderate embedding similarity to unrelated short queries.
    """
    if not text:
        return False
    s = text.strip()
    if len(s) < 160:
        return False
    sample = s[:8000]
    n = len(sample)
    if n < 160:
        return False
    ws = sum(1 for c in sample if c.isspace())
    ws_ratio = ws / n
    if ws_ratio > 0.07:
        return False
    ok = sum(1 for c in sample if c.isalnum() or c in "+/=\n\r-_.:")
    if ok / n < 0.89:
        return False
    # Long unbroken runs without word-like breaks
    longest = max((len(p) for p in sample.split()), default=0)
    if longest >= 120 and ws_ratio < 0.03:
        return True
    return False


def should_exclude_from_vector_hits(content: str | None, summary: str | None) -> bool:
    """Exclude a row from semantic hits when long text fields look like encoded noise."""
    for part in (content, summary):
        if part and is_likely_encoded_garbage_text(part):
            return True
    return False


def boost_similarity_for_query_in_fields(
    similarity: float,
    query: str,
    *,
    url: str | None = None,
    title: str | None = None,
    summary: str | None = None,
) -> float:
    """Nudge score up when the query string appears in URL/title/summary (helps username/domain queries)."""
    q = (query or "").strip().lower()
    if len(q) < 2:
        return similarity
    hay = f"{url or ''} {title or ''} {summary or ''}".lower()
    if q in hay:
        return min(1.0, float(similarity) + 0.12)
    return float(similarity)


def rerank_search_results_by_query_terms(query: str, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply lexical boost and re-sort (stable for equal scores)."""
    if not results:
        return results
    boosted: List[Dict[str, Any]] = []
    for r in results:
        rr = dict(r)
        rr["similarity"] = boost_similarity_for_query_in_fields(
            float(rr.get("similarity") or 0),
            query,
            url=rr.get("url"),
            title=rr.get("title"),
            summary=rr.get("summary"),
        )
        boosted.append(rr)
    boosted.sort(key=lambda x: float(x.get("similarity") or 0), reverse=True)
    return boosted
