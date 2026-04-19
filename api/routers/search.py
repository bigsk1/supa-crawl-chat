from fastapi import APIRouter, Query, HTTPException, status
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import json
from datetime import datetime

# Import from main project
from crawler import WebCrawler

# Create router
router = APIRouter()

# Define models
class SearchResult(BaseModel):
    id: int
    site_id: Optional[int] = None
    site_name: Optional[str] = None
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_length: Optional[int] = None
    content_truncated: Optional[bool] = None
    summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    snippet: Optional[str] = None
    similarity: Optional[float] = None
    context: Optional[str] = None
    is_chunk: Optional[bool] = None
    chunk_index: Optional[int] = None
    parent_id: Optional[int] = None
    parent_title: Optional[str] = None

class SearchResponse(BaseModel):
    results: List[SearchResult]
    count: int
    query: str
    threshold: float
    use_embedding: bool
    dedupe: bool


def _base_url(url: str) -> str:
    return (url or "").split("#chunk-")[0]


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _filter_after(results: List[Dict[str, Any]], after: Optional[datetime]) -> List[Dict[str, Any]]:
    if not after:
        return results
    filtered = []
    for result in results:
        metadata = result.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        crawled_at = _parse_dt(metadata.get("crawled_at"))
        comparison_after = after
        if crawled_at and crawled_at.tzinfo is None and after.tzinfo is not None:
            crawled_at = crawled_at.replace(tzinfo=after.tzinfo)
        if crawled_at and crawled_at.tzinfo is not None and after.tzinfo is None:
            comparison_after = after.replace(tzinfo=crawled_at.tzinfo)
        if crawled_at and crawled_at >= comparison_after:
            filtered.append(result)
    return filtered


def _dedupe_results(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best_by_url: Dict[str, Dict[str, Any]] = {}
    for result in results:
        key = _base_url(result.get("url", ""))
        if not key:
            continue
        current = best_by_url.get(key)
        if current is None:
            best_by_url[key] = result
            continue
        result_score = result.get("similarity") or result.get("rank") or 0
        current_score = current.get("similarity") or current.get("rank") or 0
        if result_score > current_score:
            best_by_url[key] = result
    return sorted(best_by_url.values(), key=lambda item: item.get("similarity") or item.get("rank") or 0, reverse=True)


def _matching_site_ids(crawler: WebCrawler, site_name: Optional[str]) -> Optional[List[int]]:
    if not site_name:
        return None
    needle = site_name.lower()
    return [
        site["id"]
        for site in crawler.db_client.get_all_sites()
        if needle in site.get("name", "").lower() or needle in site.get("url", "").lower()
    ]

@router.get("", response_model=SearchResponse)
async def search(
    query: str = Query(..., description="The search query"),
    threshold: float = Query(0.3, ge=0.0, le=1.0, description="Similarity threshold (0-1)"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    text_only: bool = Query(False, description="Use text search instead of embeddings"),
    site_id: Optional[int] = Query(None, description="Optional site ID to filter results by"),
    site_name: Optional[str] = Query(None, description="Optional site name/url substring to filter results by"),
    after: Optional[datetime] = Query(None, description="Only include results crawled after this ISO timestamp when metadata is available"),
    include_content: bool = Query(False, description="Include result content in the response"),
    content_chars: int = Query(2000, ge=0, le=50000, description="Maximum content characters per result"),
    dedupe: bool = Query(True, description="Return only the best result per source URL")
):
    """
    Search for content using semantic search or text search.

    - **query**: The search query
    - **threshold**: Similarity threshold (0-1)
    - **limit**: Maximum number of results
    - **text_only**: Use text search instead of embeddings
    - **site_id**: Optional site ID to filter results by
    """
    try:
        crawler = WebCrawler()
        target_site_ids = [site_id] if site_id is not None else _matching_site_ids(crawler, site_name)
        if target_site_ids == []:
            results = []
        elif target_site_ids:
            results = []
            per_site_limit = max(limit, 5)
            for target_site_id in target_site_ids:
                results.extend(crawler.search(
                    query=query,
                    use_embedding=not text_only,
                    threshold=threshold,
                    limit=per_site_limit,
                    site_id=target_site_id
                ))
        else:
            results = crawler.search(
                query=query,
                use_embedding=not text_only,
                threshold=threshold,
                limit=limit * 2 if dedupe else limit,
                site_id=None
            )

        results = _filter_after(results, after)
        if dedupe:
            results = _dedupe_results(results)
        results = results[:limit]

        # Convert results to SearchResult model
        search_results = []
        for result in results:
            content = result.get("content")
            content_length = len(content) if content else 0
            if not include_content:
                response_content = None
                content_truncated = content_length > 0
            elif content and len(content) > content_chars:
                response_content = content[:content_chars]
                content_truncated = True
            else:
                response_content = content
                content_truncated = False

            search_results.append(SearchResult(
                id=result.get("id"),
                site_id=result.get("site_id"),
                site_name=result.get("site_name"),
                url=result.get("url"),
                title=result.get("title"),
                content=response_content,
                content_length=content_length,
                content_truncated=content_truncated,
                summary=result.get("summary"),
                metadata=result.get("metadata"),
                snippet=result.get("snippet"),
                similarity=result.get("similarity"),
                context=result.get("context"),
                is_chunk=result.get("is_chunk"),
                chunk_index=result.get("chunk_index"),
                parent_id=result.get("parent_id"),
                parent_title=result.get("parent_title")
            ))

        return SearchResponse(
            results=search_results,
            count=len(search_results),
            query=query,
            threshold=threshold,
            use_embedding=not text_only,
            dedupe=dedupe
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error performing search: {str(e)}"
        )
