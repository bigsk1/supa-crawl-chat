from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import os
import sys
import time
import uvicorn
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from the main project
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Import routers
from api.routers import search, crawl, chat, sites, pages, auth_webui
from api.supa_auth import check_query_rate_limit, require_supa_request_auth
from db_client import SupabaseClient
from security_utils import UnsafeURL, env_bool, parse_csv_env, validate_fetch_url

# Paths to skip in api_http lines (high frequency or static)
_API_ACCESS_LOG_SKIP = frozenset(
    {
        "/api/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }
)


class ApiAccessLogMiddleware(BaseHTTPMiddleware):
    """One line per request in app.log: method path status ms (toggle with API_ACCESS_LOG)."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _API_ACCESS_LOG_SKIP or not env_bool("API_ACCESS_LOG", default=True):
            return await call_next(request)
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "api_http %s %s -> %s %sms",
            request.method,
            path,
            getattr(response, "status_code", "?"),
            ms,
        )
        return response


class QueryRateLimitMiddleware(BaseHTTPMiddleware):
    """In-process rate limit for GET /api/query only (QUERY_RATE_LIMIT_PER_MINUTE)."""

    async def dispatch(self, request: Request, call_next):
        if request.method == "GET" and request.url.path == "/api/query":
            check_query_rate_limit(request)
        return await call_next(request)


# Load environment variables
load_dotenv()

from app_logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Custom middleware to handle trailing slashes
class TrailingSlashMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Remove trailing slash if present (except for root path)
        if request.url.path != "/" and request.url.path.endswith("/"):
            # Simply modify the request scope directly
            path_without_slash = request.url.path.rstrip("/")
            logger.debug("Removing trailing slash: %s -> %s", request.url.path, path_without_slash)

            # Modify the request path in the scope
            request.scope["path"] = path_without_slash
            request.scope["raw_path"] = path_without_slash.encode()

            # Update the URL in the scope to avoid redirect
            if "url" in request.scope:
                url_parts = list(request.scope["url"])
                url_parts[2] = path_without_slash  # Update the path component
                request.scope["url"] = tuple(url_parts)

        # Continue processing the request
        response = await call_next(request)

        # Ensure we don't return 307 redirects for trailing slashes
        if response.status_code == 307 and response.headers.get("location", "").endswith("/"):
            logger.debug("Preventing 307 redirect for path: %s", request.url.path)
            # Create a new response with the same content but status code 200
            return await call_next(request)

        return response

# Optional Bearer / legacy keys / WebUI JWT (see api/supa_auth.py). /api/health stays public.
_supa_auth_dep = [Depends(require_supa_request_auth)]

app = FastAPI(
    title="Supa-Crawl-Chat API",
    description="API for Supa-Crawl-Chat - A web crawling and semantic search solution with chat capabilities",
    version="1.0.0",
    # Disable automatic redirection for trailing slashes since we handle it in middleware
    redirect_slashes=False,
)

# Innermost (just before routes): rate limit sees path after TrailingSlashMiddleware
app.add_middleware(QueryRateLimitMiddleware)
app.add_middleware(TrailingSlashMiddleware)

cors_origins = list(parse_csv_env("API_CORS_ORIGINS"))
if not cors_origins:
    cors_origins = ["*"]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(ApiAccessLogMiddleware)

# WebUI login + auth status (no Bearer required)
app.include_router(auth_webui.router, prefix="/api/auth", tags=["auth"])

# Include routers
# print("Registering routers...")
# print(f"Search router: {search.router}")
# print(f"Crawl router: {crawl.router}")
# print(f"Chat router: {chat.router}")
# print(f"Sites router: {sites.router}")
# print(f"Pages router: {pages.router}")

app.include_router(search.router, prefix="/api/search", tags=["search"], dependencies=_supa_auth_dep)
# Alias for tools / local clients that expect GET .../query?query=...
app.include_router(
    search.router,
    prefix="/api/query",
    tags=["search"],
    include_in_schema=False,
    dependencies=_supa_auth_dep,
)
app.include_router(crawl.router, prefix="/api/crawl", tags=["crawl"], dependencies=_supa_auth_dep)
app.include_router(chat.router, prefix="/api/chat", tags=["chat"], dependencies=_supa_auth_dep)
app.include_router(sites.router, prefix="/api/sites", tags=["sites"], dependencies=_supa_auth_dep)
app.include_router(pages.router, prefix="/api/pages", tags=["pages"], dependencies=_supa_auth_dep)

@app.get("/api")
async def root():
    """
    Root endpoint: service info and a stable map of HTTP routes so clients can drive the same
    features as the web UI (discoverability without scraping OpenAPI).
    """
    return {
        "message": "Welcome to the Supa-Crawl-Chat API",
        "version": app.version,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "openapi_url": "/openapi.json",
        "capabilities": {
            "crawl": {
                "base": "/api/crawl",
                "routes": [
                    {"method": "POST", "path": "/api/crawl", "note": "Start crawl (body: url, site_name, …)"},
                    {"method": "GET", "path": "/api/crawl/status/{site_id}", "note": "Crawl / site progress"},
                    {"method": "POST", "path": "/api/crawl/refresh/{site_id}/pages/{page_id}", "note": "Re-fetch one page URL only"},
                    {"method": "POST", "path": "/api/crawl/refresh/{site_id}", "note": "Re-crawl existing site"},
                    {"method": "POST", "path": "/api/crawl/refresh-stale", "note": "Batch refresh stale sites (operator)"},
                ],
            },
            "sites": {
                "base": "/api/sites",
                "routes": [
                    {"method": "GET", "path": "/api/sites", "note": "List sites"},
                    {"method": "GET", "path": "/api/sites/{site_id}", "note": "Site detail"},
                    {"method": "GET", "path": "/api/sites/{site_id}/pages", "note": "Pages for site (include_chunks)"},
                ],
            },
            "pages": {
                "base": "/api/pages",
                "routes": [
                    {"method": "GET", "path": "/api/pages/{page_id}", "note": "Single page (content_chars, full)"},
                    {"method": "GET", "path": "/api/pages/{page_id}/chunks", "note": "Chunks for parent page"},
                    {"method": "DELETE", "path": "/api/pages/{page_id}", "note": "Delete one page or chunk row"},
                    {"method": "POST", "path": "/api/pages/maintenance/deduplicate", "note": "Chunk cleanup (operator)"},
                ],
            },
            "search": {
                "base": "/api/search",
                "routes": [
                    {"method": "GET", "path": "/api/search", "note": "Semantic / text search (required query param: query)"},
                    {"method": "GET", "path": "/api/query", "note": "Same handler as /api/search (alias for tools)"},
                ],
            },
            "chat": {
                "base": "/api/chat",
                "routes": [
                    {"method": "POST", "path": "/api/chat", "note": "Chat + RAG + optional Brave; server uses .env (CHAT_MAX_COMPLETION_TOKENS, CHAT_MODEL, BRAVE_*). Body: message, session_id, user_id, profile"},
                    {"method": "GET", "path": "/api/chat/profiles", "note": "List chat profiles"},
                    {"method": "POST", "path": "/api/chat/profiles/{profile_name}", "note": "Set active profile"},
                    {"method": "GET", "path": "/api/chat/history", "note": "Conversation history"},
                    {"method": "DELETE", "path": "/api/chat/history", "note": "Clear history"},
                    {"method": "GET", "path": "/api/chat/preferences", "note": "User preferences (user_id)"},
                    {"method": "POST", "path": "/api/chat/preferences", "note": "Create preference"},
                    {"method": "DELETE", "path": "/api/chat/preferences/{preference_id}", "note": "Delete preference"},
                    {"method": "PUT", "path": "/api/chat/preferences/{preference_id}/deactivate", "note": "Soft-delete"},
                    {"method": "PUT", "path": "/api/chat/preferences/{preference_id}/activate", "note": "Reactivate"},
                    {"method": "DELETE", "path": "/api/chat/preferences", "note": "Clear all for user"},
                ],
            },
        },
    }

@app.on_event("startup")
async def ensure_runtime_schema():
    try:
        SupabaseClient().ensure_runtime_schema()
    except Exception as exc:
        logger.warning("Runtime schema check skipped: %s", exc)


def _auto_refresh_once() -> None:
    db_client = SupabaseClient()
    stale_after_days = int(os.getenv("AUTO_REFRESH_STALE_AFTER_DAYS", "30"))
    batch_limit = int(os.getenv("AUTO_REFRESH_BATCH_LIMIT", "3"))
    max_urls_raw = os.getenv("AUTO_REFRESH_MAX_URLS", "").strip()
    max_urls = int(max_urls_raw) if max_urls_raw else None

    due_sites = db_client.get_sites_due_for_refresh(
        stale_after_days=stale_after_days,
        limit=batch_limit,
    )
    if not due_sites:
        return

    for site in due_sites:
        try:
            url = validate_fetch_url(site["url"], purpose="auto refresh")
        except UnsafeURL as exc:
            logger.warning("Skipping auto-refresh for site %s: %s", site.get("id"), exc)
            continue

        lower_url = url.lower()
        is_sitemap = lower_url.endswith(".xml") or "sitemap" in lower_url
        job_id = db_client.create_crawl_job(
            site["id"],
            url,
            {
                "refresh": True,
                "auto_refresh": True,
                "stale_after_days": stale_after_days,
                "max_urls": max_urls,
                "is_sitemap": is_sitemap,
            },
        )
        crawl.crawl_in_background(
            url,
            site.get("name"),
            site.get("description"),
            is_sitemap,
            max_urls,
            {},
            job_id,
            site.get("id"),
        )


async def _auto_refresh_loop() -> None:
    startup_delay = int(os.getenv("AUTO_REFRESH_STARTUP_DELAY_SECONDS", "30"))
    interval_hours = float(os.getenv("AUTO_REFRESH_INTERVAL_HOURS", "24"))
    interval_seconds = max(300.0, interval_hours * 3600.0)

    await asyncio.sleep(max(0, startup_delay))
    while True:
        try:
            await asyncio.to_thread(_auto_refresh_once)
        except Exception as exc:
            logger.exception("Auto-refresh pass failed: %s", exc)
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def start_auto_refresh_loop():
    if not env_bool("AUTO_REFRESH_ENABLED", default=False):
        return
    task = asyncio.create_task(_auto_refresh_loop())
    app.state.auto_refresh_task = task
    logger.info("Auto-refresh scheduler enabled")


@app.on_event("shutdown")
async def stop_auto_refresh_loop():
    task = getattr(app.state, "auto_refresh_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


@app.get("/api/health")
async def health():
    try:
        return SupabaseClient().get_health_stats()
    except Exception as exc:
        return {
            "status": "degraded",
            "error": str(exc),
        }

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.getenv("API_PORT", 8001))

    # Run the API server
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
