from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio
import os
import sys
import uvicorn
from dotenv import load_dotenv

# Add the parent directory to the path so we can import from the main project
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Import routers
from api.routers import search, crawl, chat, sites, pages
from api.auth import require_api_key
from db_client import SupabaseClient
from security_utils import UnsafeURL, env_bool, parse_csv_env, validate_fetch_url

# Load environment variables
load_dotenv()

# Custom middleware to handle trailing slashes
class TrailingSlashMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Remove trailing slash if present (except for root path)
        if request.url.path != "/" and request.url.path.endswith("/"):
            # Simply modify the request scope directly
            path_without_slash = request.url.path.rstrip("/")
            print(f"Removing trailing slash: {request.url.path} -> {path_without_slash}")

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
            print(f"Preventing 307 redirect for path: {request.url.path}")
            # Create a new response with the same content but status code 200
            return await call_next(request)

        return response

# Create FastAPI app
app = FastAPI(
    title="Supa-Crawl-Chat API",
    description="API for Supa-Crawl-Chat - A web crawling and semantic search solution with chat capabilities",
    version="1.0.0",
    # Disable automatic redirection for trailing slashes since we handle it in middleware
    redirect_slashes=False,
    dependencies=[Depends(require_api_key)],
)

# Add trailing slash middleware first
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

# Include routers
# print("Registering routers...")
# print(f"Search router: {search.router}")
# print(f"Crawl router: {crawl.router}")
# print(f"Chat router: {chat.router}")
# print(f"Sites router: {sites.router}")
# print(f"Pages router: {pages.router}")

app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(crawl.router, prefix="/api/crawl", tags=["crawl"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(sites.router, prefix="/api/sites", tags=["sites"])
app.include_router(pages.router, prefix="/api/pages", tags=["pages"])

@app.get("/api")
async def root():
    """
    Root endpoint for the API.
    """
    return {
        "message": "Welcome to the Supa-Crawl-Chat API",
        "version": app.version,
        "docs_url": "/docs",
        "redoc_url": "/redoc",
    }

@app.on_event("startup")
async def ensure_runtime_schema():
    try:
        SupabaseClient().ensure_runtime_schema()
    except Exception as exc:
        print(f"Runtime schema check skipped: {exc}")


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
            print(f"Skipping auto-refresh for site {site.get('id')}: {exc}")
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
            print(f"Auto-refresh pass failed: {exc}")
        await asyncio.sleep(interval_seconds)


@app.on_event("startup")
async def start_auto_refresh_loop():
    if not env_bool("AUTO_REFRESH_ENABLED", default=False):
        return
    task = asyncio.create_task(_auto_refresh_loop())
    app.state.auto_refresh_task = task
    print("Auto-refresh scheduler enabled")


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
