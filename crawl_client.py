import os
import base64
import logging
import time
import json
import requests
from typing import List, Dict, Any, Optional, Union
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)


def _crawl4ai_request_headers(
    api_token: Optional[str] = None,
    http_user: Optional[str] = None,
    http_password: Optional[str] = None,
) -> Dict[str, str]:
    """Build HTTP headers for Crawl4AI behind an optional reverse-proxy Basic auth.

    - ``Content-Type: application/json``
    - If user + password are set: ``Authorization: Basic ...`` (edge auth, e.g. Traefik/Coolify).
    - If an API key is set: sent as ``x-api-key: <key>`` by default (not
      ``Authorization: Bearer``), so Basic and the service key do not compete
      for the same ``Authorization`` header.

    Key env: ``CRAWL4AI_API_KEY`` or ``CRAWL4AI_API_TOKEN``.
    Optional ``CRAWL4AI_API_KEY_HEADER`` overrides the header name (default ``x-api-key``).
    """
    raw_t = (
        api_token
        if api_token is not None
        else (os.getenv("CRAWL4AI_API_KEY") or os.getenv("CRAWL4AI_API_TOKEN") or "")
    )
    token = raw_t.strip()
    raw_u = http_user if http_user is not None else (os.getenv("CRAWL4AI_USER") or os.getenv("CRAWL4AI_HTTP_USER") or "")
    user = raw_u.strip()
    raw_p = (
        http_password
        if http_password is not None
        else (
            os.getenv("CRAWL4AI_PASSWORD")
            or os.getenv("CRAWL4AI_PASS")
            or os.getenv("CRAWL4AI_HTTP_PASSWORD")
            or ""
        )
    )
    password = raw_p.strip()
    has_basic = bool(user) and bool(password)

    headers: Dict[str, str] = {"Content-Type": "application/json"}

    if has_basic:
        raw = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {raw}"
    if token:
        key_header = (os.getenv("CRAWL4AI_API_KEY_HEADER") or "x-api-key").strip() or "x-api-key"
        headers[key_header] = token
    if not token and not has_basic:
        raise ValueError(
            "Crawl4AI auth: set CRAWL4AI_API_KEY (or CRAWL4AI_API_TOKEN), "
            "and/or CRAWL4AI_USER + CRAWL4AI_PASSWORD (or CRAWL4AI_PASS) for Traefik Basic auth."
        )

    return headers


def _status_token(status: Any) -> str:
    """Normalize TaskStatus or string to a lowercase token (e.g. completed, failed)."""
    if status is None:
        return ""
    s = str(status).strip().lower()
    if "." in s:
        s = s.rsplit(".", 1)[-1]
    return s


def _is_sync_crawl_result(data: Dict[str, Any]) -> bool:
    """Crawl4AI 0.8+ POST /crawl returns the full crawl payload immediately (no task_id)."""
    if not isinstance(data, dict):
        return False
    return data.get("success") is True and isinstance(data.get("results"), list)


class Crawl4AIClient:
    """Client for interacting with the Crawl4AI API."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        http_user: Optional[str] = None,
        http_password: Optional[str] = None,
    ):
        """Initialize the Crawl4AI client.

        Args:
            base_url: The base URL for the Crawl4AI API. Defaults to environment variable.
            api_token: Crawl4AI API key (sent via ``CRAWL4AI_API_KEY_HEADER``, default ``x-api-key``).
                Defaults to ``CRAWL4AI_API_KEY`` / ``CRAWL4AI_API_TOKEN``.
            http_user: Optional Basic auth user for Traefik/Coolify (CRAWL4AI_USER).
            http_password: Optional Basic auth password (CRAWL4AI_PASSWORD / CRAWL4AI_PASS).
        """
        self.base_url = (
            base_url
            or os.getenv("CRAWL4AI_URL")
            or os.getenv("CRAWL4AI_BASE_URL")
        )
        if not self.base_url:
            raise ValueError(
                "Crawl4AI base URL not provided; set CRAWL4AI_URL or CRAWL4AI_BASE_URL."
            )
        self.timeout = int(os.getenv("CRAWL4AI_HTTP_TIMEOUT", "60"))

        raw_tok = (
            api_token
            if api_token is not None
            else (os.getenv("CRAWL4AI_API_KEY") or os.getenv("CRAWL4AI_API_TOKEN") or "")
        ).strip()
        self.api_token = raw_tok or None

        self.headers = _crawl4ai_request_headers(
            api_token=api_token,
            http_user=http_user,
            http_password=http_password,
        )
        auth = self.headers.get("Authorization", "")
        key_header = (os.getenv("CRAWL4AI_API_KEY_HEADER") or "x-api-key").strip() or "x-api-key"
        has_key = key_header in self.headers
        if auth.startswith("Basic"):
            print(
                f"Initialized Crawl4AI client: {self.base_url} "
                f"(Basic auth; {key_header} {'set' if has_key else 'not set'})"
            )
        else:
            print(f"Initialized Crawl4AI client: {self.base_url} ({key_header})")

    def start_crawl(self, urls: Union[str, List[str]], priority: int = 10,
                   extraction_config: Optional[Dict[str, Any]] = None,
                   js_code: Optional[List[str]] = None,
                   wait_for: Optional[str] = None,
                   css_selector: Optional[str] = None,
                   headless: Optional[bool] = None,
                   browser_type: Optional[str] = None,
                   proxy: Optional[str] = None,
                   javascript_enabled: Optional[bool] = None,
                   user_agent: Optional[str] = None,
                   timeout: Optional[int] = None,
                   wait_for_timeout: Optional[int] = None,
                   download_images: Optional[bool] = None,
                   download_videos: Optional[bool] = None,
                   download_files: Optional[bool] = None,
                   follow_redirects: Optional[bool] = None,
                   max_depth: Optional[int] = None,
                   follow_external_links: Optional[bool] = None,
                   include_patterns: Optional[List[str]] = None,
                   exclude_patterns: Optional[List[str]] = None) -> Dict[str, Any]:
        """Start a crawl task.

        Args:
            urls: A single URL or list of URLs to crawl.
            priority: Priority of the crawl task (1-10).
            extraction_config: Configuration for extraction strategy.
            js_code: JavaScript code to execute on the page.
            wait_for: CSS selector to wait for before considering page loaded.
            css_selector: CSS selector for content extraction.
            headless: Whether to run the browser in headless mode.
            browser_type: Type of browser to use (chromium, firefox, webkit).
            proxy: Proxy server to use.
            javascript_enabled: Whether to enable JavaScript.
            user_agent: User agent string to use.
            timeout: Page load timeout in milliseconds.
            wait_for_timeout: Time to wait after page load in milliseconds.
            download_images: Whether to download images.
            download_videos: Whether to download videos.
            download_files: Whether to download files.
            follow_redirects: Whether to follow redirects.
            max_depth: Maximum depth for crawling.
            follow_external_links: Whether to follow external links.
            include_patterns: List of URL patterns to include.
            exclude_patterns: List of URL patterns to exclude.

        Returns:
            Dict containing the task_id and other response data.
        """
        # Ensure urls is a list
        if isinstance(urls, str):
            urls = [urls]

        # Prepare the request payload according to v0.5.0 format
        payload = {
            "urls": urls,
            "priority": priority
        }

        # Add optional parameters if provided
        if extraction_config:
            # Make sure extraction_config has the correct format for v0.5.0
            if "type" not in extraction_config:
                extraction_config["type"] = "basic"
            payload["extraction_config"] = extraction_config
        else:
            # Default extraction config for v0.5.0
            payload["extraction_config"] = {"type": "basic"}

        if js_code:
            payload["js_code"] = js_code
        if wait_for:
            payload["wait_for"] = wait_for
        if css_selector:
            payload["css_selector"] = css_selector

        # Add browser options
        browser_options = {}
        if headless is not None:
            browser_options["headless"] = headless
        if browser_type:
            browser_options["browser_type"] = browser_type
        if proxy:
            browser_options["proxy"] = proxy
        if javascript_enabled is not None:
            browser_options["javascript_enabled"] = javascript_enabled
        if user_agent:
            browser_options["user_agent"] = user_agent

        if browser_options:
            payload["browser_options"] = browser_options

        # Add page navigation options
        navigation_options = {}
        if timeout:
            navigation_options["timeout"] = timeout
        if wait_for_timeout:
            navigation_options["wait_for_timeout"] = wait_for_timeout

        if navigation_options:
            payload["navigation_options"] = navigation_options

        # Add media handling options
        media_options = {}
        if download_images is not None:
            media_options["download_images"] = download_images
        if download_videos is not None:
            media_options["download_videos"] = download_videos
        if download_files is not None:
            media_options["download_files"] = download_files

        if media_options:
            payload["media_options"] = media_options

        # Add link handling options
        link_options = {}
        if follow_redirects is not None:
            link_options["follow_redirects"] = follow_redirects
        if max_depth is not None:
            link_options["max_depth"] = max_depth
        if follow_external_links is not None:
            link_options["follow_external_links"] = follow_external_links
        if include_patterns:
            link_options["include_patterns"] = include_patterns
        if exclude_patterns:
            link_options["exclude_patterns"] = exclude_patterns

        if link_options:
            payload["link_options"] = link_options

        print(f"Starting crawl for URLs: {urls}")
        print(f"Extraction config: {extraction_config}")

        # Make the API request
        try:
            # Try v0.5.0 endpoint format
            endpoint = f"{self.base_url}/crawl"
            print(f"Sending request to: {endpoint}")
            print(f"Payload: {json.dumps(payload, indent=2)}")

            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=self.timeout,
            )

            # Check if the request was successful
            if response.status_code == 200:
                result = response.json()
                if result.get("task_id"):
                    print(f"Async crawl queued, task_id={result.get('task_id')}")
                elif _is_sync_crawl_result(result):
                    n = len(result.get("results") or [])
                    print(f"Synchronous crawl finished ({n} result(s); no task_id — Crawl4AI 0.8+)")
                else:
                    print(f"Crawl4AI POST /crawl response keys: {list(result.keys())}")
                return result
            else:
                error_message = f"Failed to start crawl task: {response.text}"
                print(f"Error: {error_message}")

                # Try with a simpler payload as fallback
                print("Trying with simplified payload...")
                simple_payload = {
                    "urls": urls,
                    "extraction_config": {"type": "basic"}
                }

                response = requests.post(
                    endpoint,
                    headers=self.headers,
                    json=simple_payload,
                    timeout=self.timeout,
                )

                if response.status_code == 200:
                    result = response.json()
                    if result.get("task_id"):
                        print(f"Async crawl queued (simple payload), task_id={result.get('task_id')}")
                    elif _is_sync_crawl_result(result):
                        print(
                            f"Synchronous crawl OK (simple payload), "
                            f"{len(result.get('results') or [])} result(s)"
                        )
                    return result
                else:
                    raise Exception(f"Failed to start crawl task with simplified payload: {response.text}")

        except requests.RequestException as e:
            error_message = f"Request error when starting crawl: {str(e)}"
            print(f"Error: {error_message}")
            raise Exception(error_message)

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get the status of a crawl task.

        Crawl4AI 0.8+ uses GET /crawl/job/{task_id}; older deployments used GET /task/{task_id}.

        Args:
            task_id: The ID of the task to check.

        Returns:
            Dict containing the task status and results if available.
        """
        base = self.base_url.rstrip("/")
        paths = (f"{base}/crawl/job/{task_id}", f"{base}/task/{task_id}")
        last_error = ""
        for endpoint in paths:
            try:
                logger.debug("Checking task status at: %s", endpoint)
                response = requests.get(
                    endpoint,
                    headers=self.headers,
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    return response.json()
                if response.status_code == 404:
                    last_error = response.text
                    continue
                error_message = f"Failed to get task status: {response.text}"
                print(f"Error: {error_message}")
                raise Exception(error_message)
            except requests.RequestException as e:
                last_error = str(e)
                continue
        raise Exception(
            f"Task {task_id} not found at /crawl/job or /task. Last error: {last_error}"
        )

    def wait_for_completion(self, task_id: str, polling_interval: int = 5,
                           timeout: int = 600) -> Dict[str, Any]:
        """Wait for a crawl task to complete.

        Args:
            task_id: The ID of the task to wait for.
            polling_interval: How often to check the task status (in seconds).
            timeout: Maximum time to wait (in seconds).

        Returns:
            Dict containing the final task status and results.
        """
        start_time = time.time()

        while True:
            # Check if we've exceeded the timeout
            if time.time() - start_time > timeout:
                raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

            # Get the current task status
            status_data = self.get_task_status(task_id)

            st = _status_token(status_data.get("status"))
            # Check if the task has completed or failed
            if st == "completed":
                logger.info("Crawl4AI task %s completed", task_id)
                inner = status_data.get("result")
                if isinstance(inner, dict) and "results" in inner:
                    return inner
                if "results" in status_data:
                    return status_data
                return status_data
            if st == "failed":
                error_message = f"Task {task_id} failed: {status_data.get('error', 'Unknown error')}"
                print(f"Error: {error_message}")
                raise Exception(error_message)

            # Wait before checking again
            time.sleep(polling_interval)

            elapsed = time.time() - start_time
            logger.debug("Task %s still running after %.1fs", task_id, elapsed)

    def crawl_and_wait(self, urls: Union[str, List[str]], **kwargs) -> Dict[str, Any]:
        """Start a crawl task and wait for it to complete.

        Args:
            urls: A single URL or list of URLs to crawl.
            **kwargs: Additional arguments to pass to start_crawl.
                - extraction_config: Configuration for extraction strategy.
                - js_code: JavaScript code to execute on the page.
                - wait_for: CSS selector to wait for before considering page loaded.
                - css_selector: CSS selector for content extraction.
                - headless: Whether to run the browser in headless mode.
                - browser_type: Type of browser to use (chromium, firefox, webkit).
                - proxy: Proxy server to use.
                - javascript_enabled: Whether to enable JavaScript.
                - user_agent: User agent string to use.
                - timeout: Page load timeout in milliseconds.
                - wait_for_timeout: Time to wait after page load in milliseconds.
                - download_images: Whether to download images.
                - download_videos: Whether to download videos.
                - download_files: Whether to download files.
                - follow_redirects: Whether to follow redirects.
                - max_depth: Maximum depth for crawling.
                - follow_external_links: Whether to follow external links.
                - include_patterns: List of URL patterns to include.
                - exclude_patterns: List of URL patterns to exclude.

        Returns:
            Dict containing the final task status and results.
        """
        # Start the crawl task
        try:
            task_data = self.start_crawl(urls, **kwargs)

            # Crawl4AI 0.8+: POST /crawl returns { success, results, ... } immediately (no task_id).
            if _is_sync_crawl_result(task_data):
                return task_data

            task_id = task_data.get("task_id")
            if not task_id:
                raise ValueError(
                    "Unexpected Crawl4AI response: expected task_id (async job) or "
                    f"success+results (sync). Keys: {list(task_data.keys())}"
                )

            print(f"Started crawl task with ID: {task_id}")
            return self.wait_for_completion(task_id)
        except Exception as e:
            print(f"Error in crawl_and_wait: {e}")

            # If the error is related to extraction_config, try with a simpler config
            if "extraction_config" in str(e):
                print("Trying with a simpler extraction configuration...")
                if "extraction_config" in kwargs:
                    kwargs["extraction_config"] = {"type": "basic"}
                    return self.crawl_and_wait(urls, **kwargs)

            raise

    def crawl_sitemap(self, sitemap_url: str, priority: int = 10, max_urls: int = 50) -> Dict[str, Any]:
        """Crawl a sitemap using the Crawl4AI API.

        Args:
            sitemap_url: The URL of the sitemap to crawl.
            priority: Priority of the crawl task (1-10).
            max_urls: Maximum number of URLs to crawl from the sitemap.

        Returns:
            Dict containing the task results with individual page content.
        """
        print(f"Starting sitemap crawl for: {sitemap_url}")

        # First, get the sitemap content to extract URLs
        print(f"Fetching sitemap content from: {sitemap_url}")

        # Crawl the sitemap URL first to get its content
        sitemap_result = self.crawl_and_wait(sitemap_url, extraction_config={"type": "basic"})

        # Extract URLs from the sitemap result
        urls = []

        # Check if we have results
        if 'results' in sitemap_result and sitemap_result['results']:
            # Get the first result (the sitemap)
            sitemap_data = sitemap_result['results'][0]

            # Try to parse the HTML as XML
            import xml.etree.ElementTree as ET
            from io import StringIO

            try:
                # Try to parse the HTML as XML
                root = ET.fromstring(sitemap_data['html'])

                # Define the XML namespace
                namespace = {'ns': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

                # Extract URLs from the sitemap
                for url_element in root.findall('.//ns:url/ns:loc', namespace):
                    url = url_element.text.strip()
                    if url not in urls:
                        urls.append(url)
            except Exception as e:
                print(f"Error parsing sitemap XML: {e}")

                # If XML parsing fails, try to extract URLs from links
                if 'links' in sitemap_data and sitemap_data['links']:
                    # Get internal links
                    internal_links = sitemap_data['links'].get('internal', [])
                    for link in internal_links:
                        if 'href' in link and link['href'] not in urls:
                            urls.append(link['href'])

                    # Also check external links (some sitemaps might list them as external)
                    external_links = sitemap_data['links'].get('external', [])
                    for link in external_links:
                        if 'href' in link and link['href'] not in urls:
                            urls.append(link['href'])

        if not urls:
            print("No URLs found in sitemap. Returning the sitemap result directly.")
            return sitemap_result

        print(f"Found {len(urls)} URLs in sitemap")

        # Limit the number of URLs to crawl
        if max_urls > 0 and len(urls) > max_urls:
            print(f"Limiting to {max_urls} URLs for crawling")
            urls = urls[:max_urls]

        # Now crawl each URL found in the sitemap
        print(f"Crawling {len(urls)} URLs from sitemap")

        # Use crawl_and_wait to crawl all URLs
        urls_result = self.crawl_and_wait(urls, extraction_config={"type": "basic"})

        # Combine the results
        combined_result = {
            "sitemap_result": sitemap_result,
            "urls_result": urls_result,
            "urls": urls
        }

        return combined_result
