import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Path, status
from pydantic import BaseModel, Field, field_validator

from crawler import WebCrawler
from security_utils import UnsafeURL, validate_fetch_url


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
    return {
        key: getattr(data, key)
        for key in ADVANCED_OPTION_KEYS
        if hasattr(data, key) and getattr(data, key) is not None
    }


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
) -> None:
    crawler: Optional[WebCrawler] = None
    try:
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
                **options,
            )
        else:
            site_id = crawler.crawl_site(
                url,
                site_name,
                site_description,
                needs_description=needs_description,
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

        crawler = WebCrawler()
        site_id = _ensure_site(crawler, crawl_data)
        job_options = crawl_data.model_dump()
        advanced_options = _advanced_options(crawl_data)
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


@router.get("/status/{site_id}", response_model=Dict[str, Any])
async def crawl_status(site_id: int = Path(..., description="The ID of the site")):
    try:
        crawler = WebCrawler()
        site = crawler.db_client.get_site_by_id(site_id)
        if not site:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site with ID {site_id} not found")

        total_count = crawler.db_client.get_page_count_by_site_id(site_id, include_chunks=True)
        page_count = crawler.db_client.get_page_count_by_site_id(site_id, include_chunks=False)
        chunk_count = total_count - page_count
        latest_job = crawler.db_client.get_latest_crawl_job_by_site_id(site_id)

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
