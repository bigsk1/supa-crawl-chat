import datetime
import logging
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urldefrag

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Path, Request, status
from pydantic import BaseModel, Field, field_validator

from app_logging import attach_crawl_job_logger, detach_crawl_job_logger, get_audit_logger, get_logger
from api.supa_auth import get_client_ip
from crawler import WebCrawler
from db_client import SupabaseClient
from security_utils import UnsafeURL, env_bool, validate_fetch_url


logger = get_logger(__name__)
audit = get_audit_logger()


router = APIRouter()


class CrawlRequest(BaseModel):
    url: str
    site_name: Optional[str] = None
    site_description: Optional[str] = None
    is_sitemap: bool = False
    max_urls: Optional[int] = None
    follow_external_links: Optional[bool] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None

    headless: Optional[bool] = None
    browser_type: Optional[str] = None
    proxy: Optional[str] = None
    javascript_enabled: Optional[bool] = None
    user_agent: Optional[str] = None

    timeout: Optional[int] = None
    wait_for_selector: Optional[str] = None
    wait_for_timeout: Optional[int] = None

    download_images: Optional[bool] = None
    download_videos: Optional[bool] = None
    download_files: Optional[bool] = None

    follow_redirects: Optional[bool] = None
    max_depth: Optional[int] = None

    extraction_type: Optional[str] = None
    css_selector: Optional[str] = None

    @field_validator("url")
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return value

    @field_validator("browser_type")
    def validate_browser_type(cls, value: Optional[str]) -> Optional[str]:
        if value and value not in ["chromium", "firefox", "webkit"]:
            raise ValueError("Browser type must be one of: chromium, firefox, webkit")
        return value

    @field_validator("extraction_type")
    def validate_extraction_type(cls, value: Optional[str]) -> Optional[str]:
        if value and value not in ["basic", "article", "custom"]:
            raise ValueError("Extraction type must be one of: basic, article, custom")
        return value


class RefreshRequest(BaseModel):
    is_sitemap: Optional[bool] = None
    max_urls: Optional[int] = None
    follow_external_links: Optional[bool] = None
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = None


class RefreshStaleRequest(BaseModel):
    stale_after_days: int = Field(30, ge=1, le=3650)
    batch_limit: int = Field(5, ge=1, le=50)
    max_urls: Optional[int] = Field(None, ge=1, le=10000)


class CrawlResponse(BaseModel):
    site_id: int
    site_name: str
    url: str
    message: str
    status: str
    job_id: Optional[int] = None
    next_steps: Dict[str, str]


ADVANCED_OPTION_KEYS = [
    "follow_external_links",
    "include_patterns",
    "exclude_patterns",
    "headless",
    "browser_type",
    "proxy",
    "javascript_enabled",
    "user_agent",
    "timeout",
    "wait_for_selector",
    "wait_for_timeout",
    "download_images",
    "download_videos",
    "download_files",
    "follow_redirects",
    "max_depth",
    "extraction_type",
    "css_selector",
]


def _advanced_options(data: Any) -> Dict[str, Any]:
    options = {
        key: getattr(data, key)
        for key in ADVANCED_OPTION_KEYS
        if hasattr(data, key) and getattr(data, key) is not None
    }
    if options.get("follow_external_links") and not env_bool("CRAWL_ALLOW_EXTERNAL_LINKS", default=False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "follow_external_links is disabled by crawl safety policy. "
                "Set CRAWL_ALLOW_EXTERNAL_LINKS=true only for trusted deployments."
            ),
        )
    if options.get("follow_redirects") and not env_bool("CRAWL_ALLOW_REDIRECTS", default=False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "follow_redirects is disabled by crawl safety policy. "
                "Set CRAWL_ALLOW_REDIRECTS=true only for trusted deployments."
            ),
        )
    if options.get("proxy") and not env_bool("CRAWL_ALLOW_CUSTOM_PROXY", default=False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Custom crawl proxies are disabled by crawl safety policy. "
                "Set CRAWL_ALLOW_CUSTOM_PROXY=true only for trusted deployments."
            ),
        )
    if options.get("download_files") and not env_bool("CRAWL_ALLOW_FILE_DOWNLOADS", default=False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "download_files is disabled by crawl safety policy. "
                "Set CRAWL_ALLOW_FILE_DOWNLOADS=true only for trusted deployments."
            ),
        )
    return options


def _next_steps(site_id: int) -> Dict[str, str]:
    return {
        "check_status": f"GET /api/crawl/status/{site_id}",
        "view_pages": f"GET /api/sites/{site_id}/pages",
        "search_content": f"GET /api/search/?query=your_query&site_id={site_id}",
    }


def _guess_is_sitemap(url: str) -> bool:
    lower_url = url.lower()
    return lower_url.endswith(".xml") or "sitemap" in lower_url


def _ensure_site(crawler: WebCrawler, crawl_data: CrawlRequest) -> int:
    existing_site = crawler.db_client.get_site_by_url(crawl_data.url)
    if existing_site:
        site_id = existing_site["id"]
        if crawl_data.site_description:
            crawler.db_client.update_site_description(site_id, crawl_data.site_description)
        elif not existing_site.get("description"):
            crawler.db_client.update_site_description(
                site_id,
                "AI is generating a description... (refresh in a moment)",
            )
        return site_id

    description = crawl_data.site_description or "AI is generating a description... (refresh in a moment)"
    return crawler.db_client.add_site(
        crawl_data.site_name or crawler.generate_site_name(crawl_data.url),
        crawl_data.url,
        description,
    )


def crawl_in_background(
    url: str,
    site_name: Optional[str],
    site_description: Optional[str],
    is_sitemap: bool,
    max_urls: Optional[int],
    advanced_options: Optional[Dict[str, Any]] = None,
    job_id: Optional[int] = None,
    queue_site_id: Optional[int] = None,
) -> None:
    """
    queue_site_id is the site row when the job was queued (for log filenames and tracing).
    """
    crawler: Optional[WebCrawler] = None
    jlog: Optional[logging.Logger] = None
    jfh: Optional[logging.Handler] = None
    try:
        if job_id:
            jlog, jfh, crawl_log_path = attach_crawl_job_logger(job_id, queue_site_id)
            jlog.info(
                "crawl_started job_id=%s queue_site_id=%s url=%s is_sitemap=%s log_file=%s",
                job_id,
                queue_site_id,
                url,
                is_sitemap,
                crawl_log_path,
            )

        crawler = WebCrawler()
        if job_id:
            crawler.db_client.update_crawl_job(job_id, status="running", error=None)

        existing_site = crawler.db_client.get_site_by_url(url)
        needs_description = bool(
            existing_site
            and not site_description
            and (
                not existing_site.get("description")
                or existing_site.get("description") == "AI is generating a description... (refresh in a moment)"
            )
        )

        options = advanced_options or {}
        if is_sitemap:
            site_id = crawler.crawl_sitemap(
                url,
                site_name,
                site_description,
                max_urls=max_urls,
                needs_description=needs_description,
                raise_on_error=True,
                **options,
            )
        else:
            site_id = crawler.crawl_site(
                url,
                site_name,
                site_description,
                needs_description=needs_description,
                raise_on_error=True,
                max_urls=max_urls,
                **options,
            )

        total_count = crawler.db_client.get_page_count_by_site_id(site_id, include_chunks=True)
        page_count = crawler.db_client.get_page_count_by_site_id(site_id, include_chunks=False)
        chunk_count = total_count - page_count

        if job_id:
            crawler.db_client.update_crawl_job(
                job_id,
                status="completed",
                pages_found=page_count,
                pages_crawled=page_count,
                chunks_created=chunk_count,
                finished_at=datetime.datetime.now(datetime.timezone.utc),
            )

        site_row = crawler.db_client.get_site_by_id(site_id) or {}
        finished_utc = datetime.datetime.now(datetime.timezone.utc)
        if jlog:
            jlog.info(
                "crawl_completed job_id=%s site_id=%s pages=%s chunks=%s "
                "site_updated_at_db=%s finished_utc=%s",
                job_id,
                site_id,
                page_count,
                chunk_count,
                site_row.get("updated_at"),
                finished_utc.isoformat(),
            )

        print("\n" + "=" * 80)
        print("CRAWL COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"Site ID: {site_id}")
        print(f"Pages crawled: {page_count}")
        print(f"Total chunks: {chunk_count}")
        print(f"To check status: GET /api/crawl/status/{site_id}")
        print(f"To view pages: GET /api/sites/{site_id}/pages")
        print(f"To search content: GET /api/search/?query=your_query&site_id={site_id}")
        print("=" * 80 + "\n")
    except Exception as exc:
        if jlog:
            jlog.exception("crawl_failed job_id=%s site_id_hint=%s", job_id, queue_site_id)
        print(f"Error in background crawl task: {exc}")
        if job_id:
            try:
                db_client = crawler.db_client if crawler else WebCrawler().db_client
                db_client.update_crawl_job(
                    job_id,
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.datetime.now(datetime.timezone.utc),
                )
            except Exception:
                pass
    finally:
        if jlog is not None and jfh is not None:
            detach_crawl_job_logger(jlog, jfh)


def _resolve_single_page_refresh_url(
    db: SupabaseClient, site_id: int, page_id: int
) -> Tuple[str, Optional[int]]:
    """Return (validated fetch URL, parent page id when *page_id* is a chunk)."""
    page = db.get_page_by_id(page_id)
    if not page or page.get("site_id") != site_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Page not found for this site",
        )
    if page.get("is_chunk"):
        parent_id = page.get("parent_id")
        if not parent_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Chunk row has no parent_id",
            )
        parent = db.get_page_by_id(int(parent_id))
        if not parent or parent.get("site_id") != site_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid parent page for chunk",
            )
        raw = parent.get("url") or ""
        base, _ = urldefrag(str(raw))
        try:
            return validate_fetch_url(base, purpose="single page refresh"), int(parent_id)
        except UnsafeURL as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raw = page.get("url") or ""
    base, _ = urldefrag(str(raw))
    try:
        return validate_fetch_url(base, purpose="single page refresh"), None
    except UnsafeURL as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def single_page_crawl_in_background(
    site_id: int,
    page_id: int,
    refresh_url: str,
    job_id: Optional[int],
    advanced_options: Optional[Dict[str, Any]] = None,
) -> None:
    """Background worker: crawl one URL and merge into *site_id* (same job row as full-site crawls)."""
    crawler: Optional[WebCrawler] = None
    jlog: Optional[logging.Logger] = None
    jfh: Optional[logging.Handler] = None
    try:
        if job_id:
            jlog, jfh, crawl_log_path = attach_crawl_job_logger(job_id, site_id)
            jlog.info(
                "single_page_crawl_started job_id=%s site_id=%s page_id=%s url=%s log_file=%s",
                job_id,
                site_id,
                page_id,
                refresh_url,
                crawl_log_path,
            )

        crawler = WebCrawler()
        if job_id:
            crawler.db_client.update_crawl_job(job_id, status="running", error=None)

        stats = crawler.refresh_single_page_at_url(
            site_id, refresh_url, advanced_options=advanced_options or {}
        )
        parent_n = int(stats.get("parent_pages", 0))
        chunk_n = int(stats.get("chunks", 0))

        if job_id:
            crawler.db_client.update_crawl_job(
                job_id,
                status="completed",
                pages_found=parent_n,
                pages_crawled=parent_n,
                chunks_created=chunk_n,
                finished_at=datetime.datetime.now(datetime.timezone.utc),
            )

        site_row = crawler.db_client.get_site_by_id(site_id) or {}
        if jlog:
            jlog.info(
                "single_page_crawl_completed job_id=%s site_id=%s page_id=%s parents=%s chunks=%s site_updated_at_db=%s",
                job_id,
                site_id,
                page_id,
                parent_n,
                chunk_n,
                site_row.get("updated_at"),
            )
    except Exception as exc:
        if jlog:
            jlog.exception(
                "single_page_crawl_failed job_id=%s site_id=%s page_id=%s",
                job_id,
                site_id,
                page_id,
            )
        logger.exception("single_page_crawl_failed: %s", exc)
        if job_id:
            try:
                db_client = crawler.db_client if crawler else WebCrawler().db_client
                db_client.update_crawl_job(
                    job_id,
                    status="failed",
                    error=str(exc),
                    finished_at=datetime.datetime.now(datetime.timezone.utc),
                )
            except Exception:
                pass
    finally:
        if jlog is not None and jfh is not None:
            detach_crawl_job_logger(jlog, jfh)


@router.post("", response_model=CrawlResponse)
async def crawl(
    background_tasks: BackgroundTasks,
    crawl_data: CrawlRequest = Body(...),
):
    try:
        try:
            crawl_data.url = validate_fetch_url(crawl_data.url, purpose="crawl")
        except UnsafeURL as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        advanced_options = _advanced_options(crawl_data)
        crawler = WebCrawler()
        site_id = _ensure_site(crawler, crawl_data)
        job_options = crawl_data.model_dump()
        job_id = crawler.db_client.create_crawl_job(site_id, crawl_data.url, job_options)

        background_tasks.add_task(
            crawl_in_background,
            crawl_data.url,
            crawl_data.site_name,
            crawl_data.site_description,
            crawl_data.is_sitemap,
            crawl_data.max_urls,
            advanced_options,
            job_id,
            site_id,
        )

        site = crawler.db_client.get_site_by_id(site_id) or {}
        return CrawlResponse(
            site_id=site_id,
            site_name=site.get("name", ""),
            url=site.get("url", crawl_data.url),
            message="Crawl started successfully",
            status="in_progress",
            job_id=job_id,
            next_steps=_next_steps(site_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting crawl: {exc}",
        )


@router.get("/activity", response_model=Dict[str, Any])
async def crawl_activity_board():
    """
    Single response for the Crawl page: all sites with latest job + page counts.
    Avoids N+1 GET /crawl/status requests from the browser.
    """
    try:
        db_client = SupabaseClient()
        sites = db_client.get_all_sites()
        jobs_by_site = db_client.get_latest_crawl_job_per_site()
        counts_by_site = db_client.get_crawl_page_counts_by_site()
        rows: List[Dict[str, Any]] = []
        for site in sites:
            sid = int(site["id"])
            job = jobs_by_site.get(sid)
            c = counts_by_site.get(sid, {"parent": 0, "total": 0})
            parent = int(c["parent"])
            total = int(c["total"])
            chunk = max(0, total - parent)
            status_val = (job.get("status") if job else None) or "completed"
            rows.append(
                {
                    "site_id": sid,
                    "site_name": site.get("name", ""),
                    "url": site.get("url", ""),
                    "created_at": site.get("created_at", ""),
                    "updated_at": site.get("updated_at", ""),
                    "page_count": parent,
                    "chunk_count": chunk,
                    "total_count": total,
                    "status": status_val,
                    "job": job,
                    "next_steps": _next_steps(sid),
                }
            )
        return {"sites": rows, "count": len(rows)}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error building crawl activity: {exc}",
        )


@router.get("/status/{site_id}", response_model=Dict[str, Any])
async def crawl_status(site_id: int = Path(..., description="The ID of the site")):
    try:
        # DB only — avoid constructing WebCrawler (Crawl4AI + embeddings) on every poll.
        db_client = SupabaseClient()
        site = db_client.get_site_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site with ID {site_id} not found")

        total_count = db_client.get_page_count_by_site_id(site_id, include_chunks=True)
        page_count = db_client.get_page_count_by_site_id(site_id, include_chunks=False)
        chunk_count = total_count - page_count
        latest_job = db_client.get_latest_crawl_job_by_site_id(site_id)

        return {
            "site_id": site_id,
            "site_name": site.get("name", ""),
            "url": site.get("url", ""),
            "page_count": page_count,
            "chunk_count": chunk_count,
            "total_count": total_count,
            "status": latest_job.get("status") if latest_job else "completed",
            "job": latest_job,
            "created_at": site.get("created_at", ""),
            "updated_at": site.get("updated_at", ""),
            "next_steps": _next_steps(site_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting crawl status: {exc}",
        )


@router.post("/refresh/{site_id}/pages/{page_id}", response_model=CrawlResponse)
async def refresh_single_page(
    background_tasks: BackgroundTasks,
    request: Request,
    site_id: int = Path(..., description="The ID of the site"),
    page_id: int = Path(..., description="Parent page ID, or a chunk ID (recrawls the parent URL)"),
    refresh_data: RefreshRequest = Body(default_factory=RefreshRequest),
):
    """
    Re-fetch one page URL via Crawl4AI (no site-wide link crawl) and merge into this site.
    """
    try:
        crawler = WebCrawler()
        db = crawler.db_client
        site = db.get_site_by_id(site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site with ID {site_id} not found",
            )

        refresh_url, _parent_for_chunk = _resolve_single_page_refresh_url(db, site_id, page_id)
        advanced_options = _advanced_options(refresh_data)
        job_options = refresh_data.model_dump()
        job_options.update({"refresh": True, "single_page": True, "page_id": page_id})
        job_id = db.create_crawl_job(site_id, refresh_url, job_options)

        background_tasks.add_task(
            single_page_crawl_in_background,
            site_id,
            page_id,
            refresh_url,
            job_id,
            advanced_options,
        )

        ip = get_client_ip(request) or "unknown"
        audit.info(
            "page_recrawl_queued site_id=%s page_id=%s url=%r client_ip=%s job_id=%s",
            site_id,
            page_id,
            refresh_url,
            ip,
            job_id,
        )
        logger.info(
            "page_recrawl_queued site_id=%s page_id=%s url=%r client_ip=%s job_id=%s",
            site_id,
            page_id,
            refresh_url,
            ip,
            job_id,
        )

        return CrawlResponse(
            site_id=site_id,
            site_name=site.get("name", ""),
            url=refresh_url,
            message="Single-page refresh started",
            status="in_progress",
            job_id=job_id,
            next_steps=_next_steps(site_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error starting single-page refresh: {exc}",
        )


@router.post("/refresh/{site_id}", response_model=CrawlResponse)
async def refresh_site(
    background_tasks: BackgroundTasks,
    site_id: int = Path(..., description="The ID of the site to refresh"),
    refresh_data: RefreshRequest = Body(default_factory=RefreshRequest),
):
    try:
        crawler = WebCrawler()
        site = crawler.db_client.get_site_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site with ID {site_id} not found")

        url = validate_fetch_url(site["url"], purpose="refresh crawl")
        is_sitemap = refresh_data.is_sitemap
        if is_sitemap is None:
            is_sitemap = _guess_is_sitemap(url)

        advanced_options = _advanced_options(refresh_data)
        job_options = refresh_data.model_dump()
        job_options.update({"refresh": True, "is_sitemap": is_sitemap})
        job_id = crawler.db_client.create_crawl_job(site_id, url, job_options)

        background_tasks.add_task(
            crawl_in_background,
            url,
            site.get("name"),
            site.get("description"),
            is_sitemap,
            refresh_data.max_urls,
            advanced_options,
            job_id,
            site_id,
        )

        return CrawlResponse(
            site_id=site_id,
            site_name=site.get("name", ""),
            url=url,
            message="Refresh crawl started successfully",
            status="in_progress",
            job_id=job_id,
            next_steps=_next_steps(site_id),
        )
    except HTTPException:
        raise
    except UnsafeURL as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing site: {exc}",
        )


@router.post("/refresh-stale", response_model=Dict[str, Any])
async def refresh_stale_sites(
    background_tasks: BackgroundTasks,
    refresh_data: RefreshStaleRequest = Body(default_factory=RefreshStaleRequest),
):
    """
    Queue refresh jobs for stale sites that do not already have active jobs.
    """
    try:
        crawler = WebCrawler()
        due_sites = crawler.db_client.get_sites_due_for_refresh(
            stale_after_days=refresh_data.stale_after_days,
            limit=refresh_data.batch_limit,
        )

        queued: List[Dict[str, Any]] = []
        skipped: List[Dict[str, str]] = []

        for site in due_sites:
            try:
                url = validate_fetch_url(site["url"], purpose="stale refresh")
            except UnsafeURL as exc:
                skipped.append({"site_id": str(site.get("id")), "reason": str(exc)})
                continue

            is_sitemap = _guess_is_sitemap(url)
            job_options = {
                "refresh": True,
                "auto_stale_refresh": True,
                "stale_after_days": refresh_data.stale_after_days,
                "is_sitemap": is_sitemap,
                "max_urls": refresh_data.max_urls,
            }
            job_id = crawler.db_client.create_crawl_job(site["id"], url, job_options)
            background_tasks.add_task(
                crawl_in_background,
                url,
                site.get("name"),
                site.get("description"),
                is_sitemap,
                refresh_data.max_urls,
                {},
                job_id,
                site["id"],
            )
            queued.append(
                {
                    "site_id": site["id"],
                    "site_name": site.get("name", ""),
                    "url": url,
                    "job_id": job_id,
                    "last_crawled_at": site.get("last_crawled_at"),
                }
            )

        return {
            "queued_count": len(queued),
            "skipped_count": len(skipped),
            "queued": queued,
            "skipped": skipped,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error refreshing stale sites: {exc}",
        )
