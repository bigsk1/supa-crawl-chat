from fastapi import APIRouter, Query, HTTPException, status, Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Import from main project
from crawler import WebCrawler
from db_client import SupabaseClient

# Create router
router = APIRouter()

# Define models
class Site(BaseModel):
    id: int
    name: str
    url: str
    description: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    page_count: Optional[int] = None
    last_crawled_at: Optional[str] = None
    crawl_job_status: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, site_dict):
        """Create a Site from a dictionary, converting datetime to string if needed."""
        if 'created_at' in site_dict and site_dict['created_at'] is not None:
            if not isinstance(site_dict['created_at'], str):
                site_dict['created_at'] = str(site_dict['created_at'])
        if 'updated_at' in site_dict and site_dict['updated_at'] is not None:
            if not isinstance(site_dict['updated_at'], str):
                site_dict['updated_at'] = str(site_dict['updated_at'])
        if 'last_crawled_at' in site_dict and site_dict['last_crawled_at'] is not None:
            if not isinstance(site_dict['last_crawled_at'], str):
                site_dict['last_crawled_at'] = str(site_dict['last_crawled_at'])
        return cls(**site_dict)


def _enrich_site_crawl_meta(db_client: SupabaseClient, site_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort last crawl time from crawl_jobs; complements site.updated_at."""
    site_id = site_dict["id"]
    job = db_client.get_latest_crawl_job_by_site_id(site_id)
    last_crawled_at: Optional[str] = None
    crawl_job_status: Optional[str] = None

    def _iso(val: Any) -> Optional[str]:
        if val is None:
            return None
        return val if isinstance(val, str) else str(val)

    if job:
        st = job.get("status")
        crawl_job_status = str(st) if st is not None else None
        fin = job.get("finished_at")
        if fin:
            last_crawled_at = _iso(fin)
        elif crawl_job_status in ("running", "queued"):
            last_crawled_at = _iso(job.get("started_at")) or _iso(job.get("updated_at"))
        if last_crawled_at is None:
            last_crawled_at = _iso(job.get("updated_at")) or _iso(site_dict.get("updated_at"))
    else:
        last_crawled_at = _iso(site_dict.get("updated_at") or site_dict.get("created_at"))

    out = dict(site_dict)
    out["last_crawled_at"] = last_crawled_at
    out["crawl_job_status"] = crawl_job_status
    return out

class SiteList(BaseModel):
    sites: List[Site]
    count: int

class Page(BaseModel):
    id: int
    site_id: Optional[int] = None
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_length: Optional[int] = None
    content_truncated: Optional[bool] = None
    summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_chunk: bool = False
    chunk_index: Optional[int] = None
    parent_id: Optional[int] = None
    parent_title: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def from_dict(cls, page_dict):
        """Create a Page from a dictionary, converting datetime to string if needed."""
        if 'created_at' in page_dict and page_dict['created_at'] is not None:
            if not isinstance(page_dict['created_at'], str):
                page_dict['created_at'] = str(page_dict['created_at'])
        if 'updated_at' in page_dict and page_dict['updated_at'] is not None:
            if not isinstance(page_dict['updated_at'], str):
                page_dict['updated_at'] = str(page_dict['updated_at'])
        return cls(**page_dict)

class PageList(BaseModel):
    pages: List[Page]
    count: int
    site_id: int
    site_name: str

@router.get("", response_model=SiteList)
async def list_sites(
    include_chunks: bool = Query(False, description="Include chunks in page count")
):
    """
    List all crawled sites.

    - **include_chunks**: Whether to include chunks in the page count
    """
    try:
        db_client = SupabaseClient()
        sites = db_client.get_all_sites()

        # Get page count for each site
        site_list = []
        for site in sites:
            page_count = db_client.get_page_count_by_site_id(site["id"], include_chunks=include_chunks)
            site_data = site.copy()
            site_data["page_count"] = page_count
            site_list.append(Site.from_dict(site_data))

        return SiteList(
            sites=site_list,
            count=len(site_list)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error listing sites: {str(e)}"
        )

@router.get("/{site_id}", response_model=Site)
async def get_site(
    site_id: int = Path(..., description="The ID of the site"),
    include_chunks: bool = Query(False, description="Include chunks in page count")
):
    """
    Get a site by ID.

    - **site_id**: The ID of the site
    - **include_chunks**: Whether to include chunks in the page count
    """
    try:
        db_client = SupabaseClient()
        site = db_client.get_site_by_id(site_id)

        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site with ID {site_id} not found"
            )

        # Get page count
        page_count = db_client.get_page_count_by_site_id(site_id, include_chunks=include_chunks)

        site_data = site.copy()
        site_data["page_count"] = page_count
        site_data = _enrich_site_crawl_meta(db_client, site_data)
        return Site.from_dict(site_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting site: {str(e)}"
        )

@router.get("/{site_id}/pages", response_model=PageList)
async def get_site_pages(
    site_id: int = Path(..., description="The ID of the site"),
    include_chunks: bool = Query(False, description="Include chunks in the results"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of pages to return"),
    offset: int = Query(0, ge=0, description="Number of pages to skip"),
    include_content: bool = Query(False, description="Include page content in the listing"),
    content_chars: int = Query(1000, ge=0, le=20000, description="Maximum content characters per page when include_content=true")
):
    """
    Get pages for a specific site.

    - **site_id**: The ID of the site
    - **include_chunks**: Whether to include chunks in the results
    - **limit**: Maximum number of pages to return
    """
    try:
        # Get pages
        crawler = WebCrawler()
        pages = crawler.get_site_pages(
            site_id,
            limit=limit,
            include_chunks=include_chunks,
            offset=offset,
            include_content=include_content,
            content_chars=content_chars,
        )

        # Get site name
        db_client = SupabaseClient()
        site = db_client.get_site_by_id(site_id)
        if not site:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Site with ID {site_id} not found"
            )

        # Convert to Page model
        page_list = []
        for page in pages:
            page_list.append(Page.from_dict(page))

        return PageList(
            pages=page_list,
            count=len(page_list),
            site_id=site_id,
            site_name=site["name"]
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting site pages: {str(e)}"
        )
