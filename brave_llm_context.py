"""
Brave Search LLM Context API — pre-extracted web grounding for RAG / chat.

Docs: https://api-dashboard.search.brave.com/documentation/services/llm-context
Auth: header X-Subscription-Token (same value as BRAVE_API_KEY in .env).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_BASE = "https://api.search.brave.com/res/v1/llm/context"
DEFAULT_TIMEOUT = int(os.getenv("BRAVE_HTTP_TIMEOUT", "30"))


def get_brave_api_key() -> str:
    return (os.getenv("BRAVE_API_KEY") or "").strip()


def user_requests_brave_explicit(user_message: Optional[str]) -> bool:
    """
    Heuristic: user asked for web / Brave / online lookup (server-side fetch is triggered separately).
    """
    t = (user_message or "").lower()
    if not t.strip():
        return False
    phrases = (
        "search the web",
        "web search",
        "search online",
        "look up online",
        "look this up online",
        "use brave",
        "brave search",
        "from the web",
        "on the web",
        "wider web",
        "google search",
        "duckduckgo",
        "search the internet",
        "look it up on the",
    )
    if any(p in t for p in phrases):
        return True
    if re.search(r"\bbrave\b", t):
        return True
    # short requests like "brave:" or "web:"
    stripped = t.strip()
    if stripped.startswith("brave ") or stripped.startswith("web "):
        return True
    return False


def fetch_llm_context(
    query: str,
    *,
    country: Optional[str] = None,
    search_lang: Optional[str] = None,
    count: Optional[int] = None,
    maximum_number_of_tokens: Optional[int] = None,
    context_threshold_mode: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    GET /res/v1/llm/context — returns JSON with grounding.generic[] and sources{}.
    Returns None if BRAVE_API_KEY is unset or on HTTP error (caller logs).
    """
    key = get_brave_api_key()
    if not key:
        return None

    q = (query or "").strip()
    if not q:
        return None

    max_snip = int(os.getenv("BRAVE_MAX_SNIPPETS", "50"))
    params: Dict[str, Any] = {
        "q": q[:400],
        "country": (country or os.getenv("BRAVE_COUNTRY", "us")).strip()[:2],
        "search_lang": (search_lang or os.getenv("BRAVE_SEARCH_LANG", "en")).strip(),
        "count": min(50, max(1, int(count or os.getenv("BRAVE_COUNT", "12")))),
        "maximum_number_of_tokens": min(
            32768,
            max(1024, int(maximum_number_of_tokens or os.getenv("BRAVE_MAX_TOKENS", "4096"))),
        ),
        "maximum_number_of_snippets": min(100, max(1, max_snip)),
        "context_threshold_mode": (
            context_threshold_mode or os.getenv("BRAVE_CONTEXT_THRESHOLD_MODE", "balanced")
        ).strip(),
    }

    headers = {
        "X-Subscription-Token": key,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }

    url = (os.getenv("BRAVE_LLM_CONTEXT_URL") or DEFAULT_BASE).strip()
    try:
        r = requests.get(url, headers=headers, params=params, timeout=DEFAULT_TIMEOUT)
        if r.status_code != 200:
            logger.warning("Brave LLM Context HTTP %s: %s", r.status_code, r.text[:500])
            return None
        return r.json()
    except requests.RequestException as exc:
        logger.warning("Brave LLM Context request failed: %s", exc)
        return None


def format_grounding_for_prompt(data: Dict[str, Any], *, max_snippets_total: int = 60) -> str:
    """Flatten grounding.generic (+ optional poi/map) into a system-prompt friendly block."""
    lines: List[str] = []
    grounding = data.get("grounding") or {}
    generic = grounding.get("generic") or []
    if isinstance(generic, list):
        for item in generic:
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            url = item.get("url") or ""
            snippets = item.get("snippets") or []
            if url or title:
                lines.append(f"### {title or url}")
                if url:
                    lines.append(f"Source: {url}")
            if isinstance(snippets, list):
                for snip in snippets:
                    if snip and max_snippets_total > 0:
                        text = str(snip).strip()
                        if len(text) > 1200:
                            text = text[:1200] + "…"
                        lines.append(text)
                        max_snippets_total -= 1
            lines.append("")

    poi = grounding.get("poi")
    if isinstance(poi, dict) and (poi.get("snippets") or poi.get("name")):
        lines.append("### Local (POI)")
        if poi.get("name"):
            lines.append(f"{poi.get('name')} — {poi.get('url', '')}")
        for snip in poi.get("snippets") or []:
            lines.append(str(snip).strip())
        lines.append("")

    for m in grounding.get("map") or []:
        if isinstance(m, dict) and (m.get("title") or m.get("name")):
            title = m.get("title") or m.get("name") or ""
            lines.append(f"### {title}")
            if m.get("url"):
                lines.append(f"Source: {m.get('url')}")
            for snip in m.get("snippets") or []:
                if max_snippets_total > 0:
                    lines.append(str(snip).strip())
                    max_snippets_total -= 1
            lines.append("")

    sources = data.get("sources") or {}
    if isinstance(sources, dict) and sources:
        lines.append("\n---\n**Source index (titles / ages):**")
        for surl, meta in list(sources.items())[:30]:
            if not isinstance(meta, dict):
                continue
            host = meta.get("hostname") or ""
            ttl = meta.get("title") or ""
            age = meta.get("age")
            age_s = ""
            if isinstance(age, list) and age:
                age_s = str(age[0])
            elif age:
                age_s = str(age)
            lines.append(f"- [{host}] {ttl} — {surl}" + (f" ({age_s})" if age_s else ""))

    return "\n".join(lines).strip()


def brave_ui_payload(block: str, brave_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compact data for JSON/chat UI: truncated preview text + source URLs/titles.
    """
    max_chars = max(500, int(os.getenv("BRAVE_UI_PREVIEW_CHARS", "8000")))
    raw = block or ""
    preview = raw[:max_chars]
    if len(raw) > max_chars:
        preview += "…"
    sources: List[Dict[str, str]] = []
    g = (brave_data or {}).get("grounding") or {}
    for item in (g.get("generic") or [])[:15]:
        if isinstance(item, dict):
            u = item.get("url") or ""
            t = (item.get("title") or "")[:400]
            if u or t:
                sources.append({"url": u, "title": t})
    return {"preview": preview, "sources": sources}


def _best_rag_similarity(rag_results: Optional[List[Dict[str, Any]]]) -> float:
    if not rag_results:
        return 0.0
    best = 0.0
    for item in rag_results:
        if isinstance(item, dict):
            try:
                best = max(best, float(item.get("similarity") or 0))
            except (TypeError, ValueError):
                pass
    return best


def should_merge_brave(
    mode: str,
    rag_results: Optional[List[Dict[str, Any]]],
    *,
    weak_threshold: float = 0.35,
    user_message: Optional[str] = None,
) -> bool:
    """
    BRAVE_WEB_CONTEXT:
      off | when_empty | when_weak | always | auto

    ``when_empty`` / ``when_weak``: If the user explicitly asks for Brave/web search (see
    ``user_requests_brave_explicit``), Brave is fetched even when RAG already returned hits
    (otherwise unrelated crawled chunks would block web context).

    ``auto``: Explicit ask, empty RAG, or weak RAG (below ``weak_threshold``).
    """
    m = (mode or "when_empty").strip().lower()
    if m in ("0", "false", "off", "no"):
        return False
    key = bool(get_brave_api_key())
    explicit = user_requests_brave_explicit(user_message)
    if m in ("always", "yes", "true", "1"):
        return key
    # when_empty: skip Brave if RAG has hits — unless the user explicitly asked for web/Brave lookup
    if m in ("when_empty", "empty", "if_empty"):
        if not key:
            return False
        if explicit:
            return True
        return not rag_results or len(rag_results) == 0
    if m in ("when_weak", "weak", "low_signal"):
        if not key:
            return False
        if explicit:
            return True
        if not rag_results:
            return True
        return _best_rag_similarity(rag_results) < weak_threshold
    if m in ("auto", "smart", "hybrid"):
        if not key:
            return False
        if explicit:
            return True
        if not rag_results or len(rag_results) == 0:
            return True
        return _best_rag_similarity(rag_results) < weak_threshold
    if not key:
        return False
    if explicit:
        return True
    return not rag_results or len(rag_results) == 0
