import os
import time
import json
import re
import asyncio
import xml.etree.ElementTree as ET
import requests
from typing import List, Dict, Any, Optional, Union
from urllib.parse import urlparse
from tqdm import tqdm

from crawl_client import Crawl4AIClient
from embeddings import EmbeddingGenerator
from db_client import SupabaseClient
from content_enhancer import ContentEnhancer
from security_utils import UnsafeURL, validate_fetch_url
from search_quality import rerank_search_results_by_query_terms
from utils import console, print_header, print_success, print_error, print_warning, print_info, get_rich_progress


def _extract_urls_from_text_or_markdown(body: str) -> List[str]:
    """
    When a URL is labeled 'sitemap' but returns plain text or Markdown (e.g. docs llms.txt),
    extract http(s) URLs. XML sitemap parsing is not applicable.
    """
    seen: set[str] = set()
    out: List[str] = []
    for m in re.finditer(r"\[[^\]]*\]\((https?://[^)\s]+)\)", body):
        u = m.group(1).rstrip(").,;")
        if u not in seen:
            seen.add(u)
            out.append(u)
    # Exclude `)` so lines like `](https://...md):` do not swallow the closing `):`
    for m in re.finditer(r"https?://[^\s<>\"\)]+", body):
        u = m.group(0).rstrip(").,;]")
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


class WebCrawler:
    """Main crawler class that ties together crawl4ai, embeddings, and database storage."""

    def __init__(self):
        """Initialize the web crawler with its dependencies."""
        self.crawl_client = Crawl4AIClient()
        self.embedding_generator = EmbeddingGenerator()
        self.db_client = SupabaseClient()
        self.content_enhancer = ContentEnhancer()

    def extract_domain(self, url: str) -> str:
        """Extract the domain name from a URL.

        Args:
            url: The URL to extract the domain from.

        Returns:
            The domain name.
        """
        parsed_url = urlparse(url)
        domain = parsed_url.netloc

        # Remove 'www.' if present
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain

    def generate_site_name(self, url: str) -> str:
        """Generate a site name from a URL.

        Args:
            url: The URL to generate a name from.

        Returns:
            A human-readable site name.
        """
        domain = self.extract_domain(url)

        # Split by dots and dashes
        parts = re.split(r'[.-]', domain)

        # Capitalize each part
        parts = [part.capitalize() for part in parts if part]

        # Join with spaces
        return ' '.join(parts)

    def _extraction_and_crawl_kwargs_from_advanced(
        self, advanced_options: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Build Crawl4AI extraction_config and keyword args for crawl_and_wait/start_crawl."""
        extraction_type = advanced_options.get("extraction_type", "basic") or "basic"
        extraction_config: Dict[str, Any] = {"type": extraction_type}
        if extraction_type == "custom" and "css_selector" in advanced_options:
            extraction_config["css_selector"] = advanced_options["css_selector"]
        crawl_options: Dict[str, Any] = {}
        if "headless" in advanced_options:
            crawl_options["headless"] = advanced_options["headless"]
        if "browser_type" in advanced_options:
            crawl_options["browser_type"] = advanced_options["browser_type"]
        if "proxy" in advanced_options:
            crawl_options["proxy"] = advanced_options["proxy"]
        if "javascript_enabled" in advanced_options:
            crawl_options["javascript_enabled"] = advanced_options["javascript_enabled"]
        if "user_agent" in advanced_options:
            crawl_options["user_agent"] = advanced_options["user_agent"]
        if "timeout" in advanced_options:
            crawl_options["timeout"] = advanced_options["timeout"]
        if "wait_for_selector" in advanced_options:
            crawl_options["wait_for"] = advanced_options["wait_for_selector"]
        if "wait_for_timeout" in advanced_options:
            crawl_options["wait_for_timeout"] = advanced_options["wait_for_timeout"]
        if "download_images" in advanced_options:
            crawl_options["download_images"] = advanced_options["download_images"]
        if "download_videos" in advanced_options:
            crawl_options["download_videos"] = advanced_options["download_videos"]
        if "download_files" in advanced_options:
            crawl_options["download_files"] = advanced_options["download_files"]
        if "follow_redirects" in advanced_options:
            crawl_options["follow_redirects"] = advanced_options["follow_redirects"]
        if "max_depth" in advanced_options:
            crawl_options["max_depth"] = advanced_options["max_depth"]
        if "follow_external_links" in advanced_options:
            crawl_options["follow_external_links"] = advanced_options["follow_external_links"]
        if "include_patterns" in advanced_options:
            crawl_options["include_patterns"] = advanced_options["include_patterns"]
        if "exclude_patterns" in advanced_options:
            crawl_options["exclude_patterns"] = advanced_options["exclude_patterns"]
        return extraction_config, crawl_options

    def process_crawl_results(self, results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Process the results from the crawl4ai API.

        Args:
            results: The results from the crawl4ai API.

        Returns:
            List of processed page data dictionaries.
        """
        # Debug: Print the structure of the results
        print_info("Processing crawl results...")

        # Print a sample of the results structure to help debug
        if 'results' in results:
            print_info(f"Found {len(results['results'])} results")
            if results['results']:
                result = results['results'][0]
                print_info(f"Sample result URL: {result.get('url', 'N/A')}")
                print_info(f"Result keys: {list(result.keys())}")

                # Check for markdown content
                if 'markdown' in result:
                    if isinstance(result['markdown'], dict):
                        print_info(f"Markdown keys: {list(result['markdown'].keys())}")
                    else:
                        print_info(f"Markdown type: {type(result['markdown'])}")
                        print_info(f"Markdown length: {len(str(result['markdown']))}")

                # Check for HTML content
                if 'html' in result:
                    print_info(f"HTML length: {len(result['html'])}")

                # Check for cleaned HTML
                if 'cleaned_html' in result:
                    print_info(f"Cleaned HTML length: {len(result['cleaned_html'])}")

        pages = []

        # Check if results has a 'results' key (v0.5.0 format)
        if 'results' in results:
            print_info(f"Processing {len(results.get('results', []))} results")
            for result in results.get('results', []):
                url = result.get('url', '')

                # Extract content from the result based on CrawlResult structure
                # See: https://docs.crawl4ai.com/api/crawl-result/

                # Try to get markdown content first
                content = None
                if isinstance(result.get('markdown'), dict):
                    # It's a MarkdownGenerationResult object
                    markdown_result = result.get('markdown', {})
                    content = markdown_result.get('raw_markdown')
                    if not content and 'fit_markdown' in markdown_result:
                        content = markdown_result.get('fit_markdown')
                elif isinstance(result.get('markdown'), str):
                    # It's a string
                    content = result.get('markdown')

                # If no markdown, try other content fields
                if not content:
                    content = result.get('extracted_content', '')
                if not content:
                    content = result.get('cleaned_html', '')
                if not content:
                    content = result.get('html', '')

                if not content:
                    print_warning(f"No content found for URL: {url}")
                    continue

                # Get title from metadata or use URL
                title = ''
                if result.get('metadata') and 'title' in result.get('metadata', {}):
                    title = result.get('metadata', {}).get('title', '')
                elif 'title' in result:
                    title = result.get('title', '')

                # Create a page dictionary
                page = {
                    'url': url,
                    'title': title or self.extract_domain(url),
                    'content': content,
                    'summary': '',  # Will be generated later
                    'is_chunk': False,
                    'metadata': {
                        "source": self.extract_domain(url),
                        "url_path": urlparse(url).path,
                        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                    }
                }

                pages.append(page)
                print_info(f"Added page from results: {url} with {len(content)} characters of content")

        # Process pages from the crawl results
        if 'pages' in results:
            print_info(f"Found 'pages' key in crawl results with {len(results.get('pages', {}))} items")
            for url, page_data in results.get('pages', {}).items():
                # Skip pages with no content
                if not page_data.get('content'):
                    print_warning(f"No content found for URL: {url}")
                    continue

                # Create a page dictionary
                page = {
                    'url': url,  # Use the actual URL from the crawl results
                    'title': page_data.get('title', '') or self.extract_domain(url),
                    'content': page_data.get('content', ''),
                    'summary': '',  # Will be generated later
                    'is_chunk': False,
                    'metadata': {
                        "source": self.extract_domain(url),
                        "url_path": urlparse(url).path,
                        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                    }
                }

                pages.append(page)
                print_info(f"Added page from pages: {url}")

        # If we still have no pages, try to extract from the raw result
        if not pages and 'result' in results:
            print_info("No pages found in structured format, trying to extract from raw result")
            result = results.get('result', {})
            url = result.get('url', '')

            # Extract content from the result based on CrawlResult structure
            # See: https://docs.crawl4ai.com/api/crawl-result/

            # Try to get markdown content first
            content = None
            if isinstance(result.get('markdown'), dict):
                # It's a MarkdownGenerationResult object
                markdown_result = result.get('markdown', {})
                content = markdown_result.get('raw_markdown')
                if not content and 'fit_markdown' in markdown_result:
                    content = markdown_result.get('fit_markdown')
            elif isinstance(result.get('markdown'), str):
                # It's a string
                content = result.get('markdown')

            # If no markdown, try other content fields
            if not content:
                content = result.get('extracted_content', '')
            if not content:
                content = result.get('cleaned_html', '')
            if not content:
                content = result.get('html', '')

            if content:
                # Get title from metadata or use URL
                title = ''
                if result.get('metadata') and 'title' in result.get('metadata', {}):
                    title = result.get('metadata', {}).get('title', '')
                elif 'title' in result:
                    title = result.get('title', '')

                # Create a page dictionary
                page = {
                    'url': url,
                    'title': title or self.extract_domain(url),
                    'content': content,
                    'summary': '',  # Will be generated later
                    'is_chunk': False,
                    'metadata': {
                        "source": self.extract_domain(url),
                        "url_path": urlparse(url).path,
                        "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                    }
                }

                pages.append(page)
                print_info(f"Added page from raw result: {url}")

        print_info(f"Total pages processed: {len(pages)}")
        return pages

    def chunk_content(self, page: Dict[str, Any], max_tokens: int = 4000, overlap_tokens: int = 200) -> List[Dict[str, Any]]:
        """Split a page's content into smaller, overlapping chunks based on token count.

        Args:
            page: The page data dictionary.
            max_tokens: Maximum number of tokens per chunk.
            overlap_tokens: Number of tokens to overlap between chunks.

        Returns:
            List of chunked page data dictionaries.
        """
        content = page.get('content', '')
        if not content:
            # No content to chunk
            page['is_chunk'] = False
            return [page]

        total_tokens = self.embedding_generator.count_tokens(content)
        if total_tokens <= max_tokens:
            page['is_chunk'] = False
            page['chunk_index'] = None
            page['metadata'] = {
                **(page.get('metadata') or {}),
                "source": self.extract_domain(page['url']),
                "url_path": urlparse(page['url']).path,
                "chunk_size": total_tokens,
                "chunk_count": 0,
                "has_chunks": False,
                "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            }
            return [page]

        # Use the embedding generator's tokenizer to count tokens
        try:
            # First, try to split by semantic boundaries (headers, paragraphs)
            # This helps preserve the meaning of each chunk

            # Split by headers first (markdown headers)
            header_pattern = r'(#{1,6}\s+.+?\n)'
            header_sections = re.split(header_pattern, content)

            # Group the headers with their content
            sections = []
            current_section = ""

            for i, section in enumerate(header_sections):
                if i % 2 == 0 and current_section:  # Even indices are content after headers
                    sections.append(current_section)
                    current_section = section
                else:
                    current_section += section

            if current_section:
                sections.append(current_section)

            # If no headers were found, split by paragraphs
            if len(sections) <= 1:
                sections = [p for p in content.split('\n\n') if p.strip()]

            # Now create chunks based on token counts
            chunks = []
            chunk_index = 0
            current_chunk = ""
            current_tokens = 0

            for section in sections:
                section_tokens = self.embedding_generator.count_tokens(section)

                # If this section alone exceeds the max tokens, we need to split it further
                if section_tokens > max_tokens:
                    # If we have content in the current chunk, add it first
                    if current_tokens > 0:
                        chunk_page = page.copy()
                        chunk_page['content'] = current_chunk
                        chunk_page['chunk_index'] = chunk_index
                        chunk_page['is_chunk'] = True
                        chunk_page['token_count'] = current_tokens
                        # Create a unique URL for the chunk by adding a fragment
                        chunk_page['url'] = f"{page['url']}#chunk-{chunk_index}"

                        # Create proper metadata
                        chunk_page['metadata'] = {
                            "source": self.extract_domain(page['url']),
                            "url_path": urlparse(page['url']).path,
                            "chunk_size": current_tokens,
                            "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                        }

                        chunks.append(chunk_page)
                        chunk_index += 1
                        current_chunk = ""
                        current_tokens = 0

                    # Now split the large section into smaller pieces
                    tokens = self.embedding_generator.tokenizer.encode(section)
                    for start_idx in range(0, len(tokens), max_tokens - overlap_tokens):
                        end_idx = min(start_idx + max_tokens, len(tokens))
                        chunk_tokens = tokens[start_idx:end_idx]
                        chunk_text = self.embedding_generator.tokenizer.decode(chunk_tokens)

                        chunk_page = page.copy()
                        chunk_page['content'] = chunk_text
                        chunk_page['chunk_index'] = chunk_index
                        chunk_page['is_chunk'] = True
                        chunk_page['token_count'] = len(chunk_tokens)
                        # Create a unique URL for the chunk by adding a fragment
                        chunk_page['url'] = f"{page['url']}#chunk-{chunk_index}"

                        # Create proper metadata
                        chunk_page['metadata'] = {
                            "source": self.extract_domain(page['url']),
                            "url_path": urlparse(page['url']).path,
                            "chunk_size": len(chunk_tokens),
                            "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                        }

                        chunks.append(chunk_page)
                        chunk_index += 1

                        if end_idx >= len(tokens):
                            break
                else:
                    # Check if adding this section would exceed the token limit
                    if current_tokens + section_tokens > max_tokens and current_tokens > 0:
                        # Save the current chunk and start a new one
                        chunk_page = page.copy()
                        chunk_page['content'] = current_chunk
                        chunk_page['chunk_index'] = chunk_index
                        chunk_page['is_chunk'] = True
                        chunk_page['token_count'] = current_tokens
                        # Create a unique URL for the chunk by adding a fragment
                        chunk_page['url'] = f"{page['url']}#chunk-{chunk_index}"

                        # Create proper metadata
                        chunk_page['metadata'] = {
                            "source": self.extract_domain(page['url']),
                            "url_path": urlparse(page['url']).path,
                            "chunk_size": current_tokens,
                            "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                        }

                        chunks.append(chunk_page)
                        chunk_index += 1

                        # Start a new chunk with overlap if possible
                        if current_tokens > overlap_tokens:
                            # Find a good breaking point in the current chunk for overlap
                            overlap_text = current_chunk[-1000:]  # Look at the last 1000 chars for a break point
                            break_points = [
                                overlap_text.rfind('\n\n'),  # Paragraph break
                                overlap_text.rfind('. '),    # Sentence break
                                overlap_text.rfind(', '),    # Clause break
                                overlap_text.rfind(' ')      # Word break
                            ]

                            # Use the first good break point found
                            break_point = next((bp for bp in break_points if bp != -1), -1)

                            if break_point != -1:
                                # Use text after the break point as the start of the new chunk
                                current_chunk = overlap_text[break_point+1:]
                                current_tokens = self.embedding_generator.count_tokens(current_chunk)
                            else:
                                current_chunk = ""
                                current_tokens = 0
                        else:
                            current_chunk = ""
                            current_tokens = 0

                    # Add the section to the current chunk
                    if current_chunk:
                        current_chunk += "\n\n" + section
                    else:
                        current_chunk = section

                    current_tokens = self.embedding_generator.count_tokens(current_chunk)

            # Add the final chunk if there's anything left
            if current_chunk:
                chunk_page = page.copy()
                chunk_page['content'] = current_chunk
                chunk_page['chunk_index'] = chunk_index
                chunk_page['is_chunk'] = True
                chunk_page['token_count'] = current_tokens
                # Create a unique URL for the chunk by adding a fragment
                chunk_page['url'] = f"{page['url']}#chunk-{chunk_index}"

                # Create proper metadata
                chunk_page['metadata'] = {
                    "source": self.extract_domain(page['url']),
                    "url_path": urlparse(page['url']).path,
                    "chunk_size": current_tokens,
                    "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                }

                chunks.append(chunk_page)

            # If the content was small enough to not need chunking, return the original page
            if not chunks:
                # Mark the original page as not a chunk
                page['is_chunk'] = False

                # Set proper metadata for the parent page
                page['metadata'] = {
                    "source": self.extract_domain(page['url']),
                    "url_path": urlparse(page['url']).path,
                    "chunk_size": total_tokens,
                    "chunk_count": 0,
                    "has_chunks": False,
                    "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                }

                return [page]

            # If we have chunks, make sure the parent page is included first
            if chunks:
                # Create a parent page that's not a chunk
                parent_page = page.copy()
                parent_page['is_chunk'] = False
                parent_page['chunk_index'] = None

                # Set proper metadata for the parent page
                parent_page['metadata'] = {
                    "source": self.extract_domain(page['url']),
                    "url_path": urlparse(page['url']).path,
                    "chunk_size": total_tokens,
                    "chunk_count": len(chunks),
                    "has_chunks": True,
                    "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
                }

                print_info(f"Split page '{page.get('title', 'Untitled')}' into {len(chunks)} chunks")

                # Return parent page first, followed by chunks
                return [parent_page] + chunks

            return chunks

        except Exception as e:
            print_error(f"Error chunking content: {e}")
            # Fall back to returning the original page
            page['is_chunk'] = False

            # Set proper metadata for the parent page
            page['metadata'] = {
                "source": self.extract_domain(page['url']),
                "url_path": urlparse(page['url']).path,
                "chunk_size": self.embedding_generator.count_tokens(content) if content else 0,
                "crawled_at": time.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            }

            return [page]

    async def enhance_pages(self, pages: List[Dict[str, Any]], max_tokens_per_chunk: Optional[int] = None) -> List[Dict[str, Any]]:
        """Enhance pages with titles, summaries, and embeddings.

        Args:
            pages: List of page data dictionaries.
            max_tokens_per_chunk: Maximum number of tokens per chunk.

        Returns:
            List of enhanced page data dictionaries.
        """
        if not pages:
            return []

        if max_tokens_per_chunk is None:
            try:
                max_tokens_per_chunk = int(os.getenv("CHUNK_MAX_TOKENS", "900"))
            except ValueError:
                max_tokens_per_chunk = 900

        try:
            overlap_tokens = int(os.getenv("CHUNK_OVERLAP_TOKENS", "120"))
        except ValueError:
            overlap_tokens = 120

        print_header("Enhancing page content...")

        # Generate titles and summaries for pages
        enhanced_pages = []
        for page in pages:
            # Skip if the page has no content
            if not page.get('content'):
                continue

            # Generate title and summary if not already present
            if not page.get('title') or not page.get('summary'):
                try:
                    result = await self.content_enhancer.generate_title_and_summary_async(
                        page.get('content', ''),
                        page.get('url', '')
                    )
                    page['title'] = result['title']
                    page['summary'] = result['summary']
                except Exception as e:
                    print_error(f"Error generating title and summary: {e}")
                    # Use fallbacks if generation fails
                    if not page.get('title'):
                        page['title'] = f"Page from {self.extract_domain(page.get('url', ''))}"
                    if not page.get('summary'):
                        page['summary'] = page.get('content', '')[:200] + '...'

            enhanced_pages.append(page)

        # Chunk content for better LLM interaction
        print_header("Chunking content for better LLM interaction...")
        all_pages = []

        for page in enhanced_pages:
            # Chunk the content
            chunked_pages = self.chunk_content(
                page,
                max_tokens=max_tokens_per_chunk,
                overlap_tokens=overlap_tokens,
            )
            all_pages.extend(chunked_pages)

        # Generate embeddings for all pages
        print_header("Generating embeddings...")

        # Process in batches to avoid overwhelming the embedding API
        batch_size = 10
        total_batches = (len(all_pages) + batch_size - 1) // batch_size

        with get_rich_progress() as progress:
            embedding_task = progress.add_task("Generating embeddings...", total=len(all_pages))

            for i in range(0, len(all_pages), batch_size):
                batch = all_pages[i:i+batch_size]

                # Process each page in the batch
                for page in batch:
                    content = page.get('content', '')
                    if not content:
                        continue

                    if page.get("metadata", {}).get("has_chunks") and not page.get("is_chunk"):
                        page["embedding"] = None
                        progress.update(embedding_task, advance=1)
                        continue

                    try:
                        # Generate embedding
                        embedding = self.embedding_generator.generate_embedding(content)
                        page['embedding'] = embedding
                    except Exception as e:
                        print_error(f"Error generating embedding: {e}")
                        # Use a zero vector as fallback
                        page['embedding'] = [0.0] * 1536

                    # Update progress
                    progress.update(embedding_task, advance=1)

        return all_pages

    def crawl_site(self, url: str, site_name: Optional[str] = None,
                  description: Optional[str] = None, start_only: bool = False,
                  needs_description: bool = False, **advanced_options) -> int:
        """Crawl a site, generate embeddings, and store in the database.

        Args:
            url: The URL to crawl.
            site_name: Optional name for the site. If not provided, one will be generated.
            description: Optional description of the site.
            start_only: If True, only start the crawl and return the site ID without waiting for completion.
            needs_description: If True, force generation of a description even if one exists.
            **advanced_options: Additional options for the crawl.
                - follow_external_links: Whether to follow external links.
                - include_patterns: List of URL patterns to include.
                - exclude_patterns: List of URL patterns to exclude.
                - headless: Whether to run the browser in headless mode.
                - browser_type: Type of browser to use (chromium, firefox, webkit).
                - proxy: Proxy server to use.
                - javascript_enabled: Whether to enable JavaScript.
                - user_agent: User agent string to use.
                - timeout: Page load timeout in milliseconds.
                - wait_for_selector: CSS selector to wait for before considering page loaded.
                - wait_for_timeout: Time to wait after page load in milliseconds.
                - download_images: Whether to download images.
                - download_videos: Whether to download videos.
                - download_files: Whether to download files.
                - follow_redirects: Whether to follow redirects.
                - max_depth: Maximum depth for crawling.
                - extraction_type: Type of extraction to use (basic, article, custom).
                - css_selector: CSS selector for content extraction.

        Returns:
            The site ID in the database.
        """
        # Ensure URL is a string
        url = validate_fetch_url(str(url), purpose="crawl")

        # Generate a site name if not provided
        if not site_name:
            site_name = self.generate_site_name(url)

        print_info(f"Crawling site: {site_name} ({url})")

        # Check if the site already exists
        try:
            existing_site = self.db_client.get_site_by_url(url)
            if existing_site:
                print_warning(f"Site already exists with ID: {existing_site['id']}. Updating existing site.")
                site_id = existing_site['id']

                # If a description was provided, update it
                if description:
                    self.db_client.update_site_description(site_id, description)
                    print_success(f"Updated site description: {description[:100]}...")
                # If needs_description is True or no description exists, we'll generate one later
                elif needs_description or not existing_site.get('description'):
                    description = None  # Mark for generation
                else:
                    # Use the existing description
                    description = existing_site.get('description')
            else:
                # Add the site to the database (description might be None, we'll update it later)
                site_id = self.db_client.add_site(site_name, url, description)
                print_success(f"Added new site with ID: {site_id}")
        except Exception as e:
            print_error(f"Error checking for existing site: {e}")
            # Add the site to the database as a fallback
            site_id = self.db_client.add_site(site_name, url, description)
            print_success(f"Added new site with ID: {site_id}")

        extraction_config, crawl_options = self._extraction_and_crawl_kwargs_from_advanced(advanced_options)

        # Start the crawl
        try:
            if start_only:
                return site_id
            else:
                crawl_results = self.crawl_client.crawl_and_wait(
                    url,
                    extraction_config=extraction_config,
                    **crawl_options
                )

            # Process the results
            pages = self.process_crawl_results(crawl_results)

            if not pages:
                print_warning("No pages found in crawl results.")
                return site_id

            print_info(f"Found {len(pages)} pages.")

            # If no description was provided or needs_description is True, generate one from the homepage content
            if (not description or needs_description) and pages:
                print_info("Generating site description using OpenAI...")
                homepage = next((p for p in pages if p['url'] == url or p['url'] == f"{url}/"), pages[0])

                # Use the content enhancer to generate a description
                description_data = asyncio.run(
                    self.content_enhancer.generate_title_and_summary_async(
                        homepage['content'][:5000], url
                    )
                )
                description = description_data.get('summary', '')

                # Update the site with the generated description
                self.db_client.update_site_description(site_id, description)
                print_success(f"Generated site description with {self.content_enhancer.model}: {description[:100]}...")

            # Enhance pages with titles, summaries, and embeddings
            enhanced_pages = asyncio.run(self.enhance_pages(pages))

            # Store the pages in the database
            page_ids = self.db_client.add_pages(site_id, enhanced_pages, replace_chunks=True)

            print_success(f"Successfully stored {len(page_ids)} pages in the database.")

        except Exception as e:
            print_error(f"Error during crawl: {e}")
            print_info("Crawl failed. Please check the API configuration and try again.")
            return site_id

        return site_id

    def refresh_single_page_at_url(
        self,
        site_id: int,
        page_url: str,
        advanced_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """Fetch one URL via Crawl4AI (max_depth=0, no following links), enhance, merge into the site."""
        page_url = validate_fetch_url(str(page_url), purpose="page refresh")
        site = self.db_client.get_site_by_id(site_id)
        if not site:
            raise ValueError(f"Site {site_id} not found")
        opts = dict(advanced_options or {})
        extraction_config, crawl_options = self._extraction_and_crawl_kwargs_from_advanced(opts)
        crawl_options["max_depth"] = 0
        crawl_options["follow_external_links"] = False
        crawl_results = self.crawl_client.crawl_and_wait(
            page_url,
            extraction_config=extraction_config,
            **crawl_options,
        )
        pages = self.process_crawl_results(crawl_results)
        if not pages:
            raise ValueError("No content returned for this URL")
        enhanced_pages = asyncio.run(self.enhance_pages(pages))
        self.db_client.add_pages(site_id, enhanced_pages, replace_chunks=True)
        n_parent = sum(1 for p in enhanced_pages if not p.get("is_chunk"))
        n_chunk = sum(1 for p in enhanced_pages if p.get("is_chunk"))
        return {"parent_pages": n_parent, "chunks": n_chunk, "stored": len(enhanced_pages)}

    def crawl_sitemap(self, sitemap_url: str, site_name: Optional[str] = None,
                     description: Optional[str] = None, max_urls: Optional[int] = None,
                     start_only: bool = False, needs_description: bool = False, **advanced_options) -> int:
        """Crawl a sitemap, generate embeddings, and store in the database.

        Args:
            sitemap_url: The URL of the sitemap to crawl.
            site_name: Optional name for the site. If not provided, one will be generated.
            description: Optional description of the site.
            max_urls: Maximum number of URLs to crawl from the sitemap. If None, uses the MAX_URLS env var.
            start_only: If True, only start the crawl and return the site ID without waiting for completion.
            needs_description: If True, force generation of a description even if one exists.
            **advanced_options: Additional options for the crawl.
                - follow_external_links: Whether to follow external links.
                - include_patterns: List of URL patterns to include.
                - exclude_patterns: List of URL patterns to exclude.
                - headless: Whether to run the browser in headless mode.
                - browser_type: Type of browser to use (chromium, firefox, webkit).
                - proxy: Proxy server to use.
                - javascript_enabled: Whether to enable JavaScript.
                - user_agent: User agent string to use.
                - timeout: Page load timeout in milliseconds.
                - wait_for_selector: CSS selector to wait for before considering page loaded.
                - wait_for_timeout: Time to wait after page load in milliseconds.
                - download_images: Whether to download images.
                - download_videos: Whether to download videos.
                - download_files: Whether to download files.
                - follow_redirects: Whether to follow redirects.
                - max_depth: Maximum depth for crawling.
                - extraction_type: Type of extraction to use (basic, article, custom).
                - css_selector: CSS selector for content extraction.

        Returns:
            The site ID in the database.
        """
        # Ensure URL is a string
        sitemap_url = validate_fetch_url(str(sitemap_url), purpose="sitemap crawl")

        # Get the maximum URLs to crawl from environment variable or use default
        if max_urls is None:
            try:
                max_urls = int(os.getenv("MAX_URLS", "50"))
            except ValueError:
                max_urls = 50
                print_warning(f"Invalid MAX_URLS in environment, using default: {max_urls}")

        # Generate a site name if not provided
        if not site_name:
            site_name = self.generate_site_name(sitemap_url)

        print_info(f"Crawling sitemap: {site_name} ({sitemap_url})")
        print_info(f"Maximum URLs to crawl: {max_urls}")

        # Check if the site already exists
        try:
            existing_site = self.db_client.get_site_by_url(sitemap_url)
            if existing_site:
                print_warning(f"Site already exists with ID: {existing_site['id']}. Updating existing site.")
                site_id = existing_site['id']

                # If a description was provided, update it
                if description:
                    self.db_client.update_site_description(site_id, description)
                    print_success(f"Updated site description: {description[:100]}...")
                # If needs_description is True or no description exists, we'll generate one later
                elif needs_description or not existing_site.get('description'):
                    description = None  # Mark for generation
                else:
                    # Use the existing description
                    description = existing_site.get('description')
            else:
                # Add the site to the database (description might be None, we'll update it later)
                site_id = self.db_client.add_site(site_name, sitemap_url, description)
                print_success(f"Added new site with ID: {site_id}")
        except Exception as e:
            print_error(f"Error checking for existing site: {e}")
            # Add the site to the database as a fallback
            site_id = self.db_client.add_site(site_name, sitemap_url, description)
            print_success(f"Added new site with ID: {site_id}")

        # If start_only is True, return the site_id without waiting for the crawl to complete
        if start_only:
            return site_id

        try:
            # First, fetch the sitemap XML directly
            print_info(f"Fetching sitemap XML from: {sitemap_url}")
            response = requests.get(sitemap_url, timeout=int(os.getenv("SITEMAP_FETCH_TIMEOUT", "30")))
            response.raise_for_status()  # Raise an exception for HTTP errors

            raw = response.content
            urls: List[str] = []

            try:
                root = ET.fromstring(raw)
            except ET.ParseError:
                text = raw.decode("utf-8", errors="replace")
                urls = _extract_urls_from_text_or_markdown(text)
                if not urls:
                    print_error(
                        "Not valid XML sitemap and no http(s) URLs found in plain text/Markdown. "
                        "Use a real sitemap.xml URL, or for llms.txt-style indexes the file must list links."
                    )
                    return site_id
                print_info(
                    f"Non-XML document (e.g. llms.txt/Markdown); extracted {len(urls)} URL(s) from links and bare URLs."
                )
            else:
                # Standard sitemap XML: urlset with namespace http://www.sitemaps.org/schemas/sitemap/0.9
                namespace = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
                for url_element in root.findall(".//ns:url/ns:loc", namespace):
                    if url_element.text:
                        urls.append(url_element.text.strip())

                # Sitemap index: <sitemap><loc>...</loc></sitemap>
                if not urls:
                    for loc in root.findall(
                        ".//{http://www.sitemaps.org/schemas/sitemap/0.9}sitemap/{http://www.sitemaps.org/schemas/sitemap/0.9}loc"
                    ):
                        if loc.text:
                            urls.append(loc.text.strip())

                if not urls:
                    print_warning(f"No URLs found in sitemap: {sitemap_url}")
                    return site_id

            print_info(f"Found {len(urls)} URLs in sitemap")

            # Limit the number of URLs to crawl based on max_urls
            if max_urls > 0 and len(urls) > max_urls:
                print_warning(f"Limiting to {max_urls} URLs for processing (from {len(urls)} total)")
                urls = urls[:max_urls]

            # Configure extraction based on Crawl4AI v0.5.0 documentation
            extraction_type = advanced_options.get('extraction_type', 'basic')
            extraction_config = {
                "type": extraction_type
            }

            # Add CSS selector if provided and extraction type is custom
            if extraction_type == 'custom' and 'css_selector' in advanced_options:
                extraction_config["css_selector"] = advanced_options['css_selector']

            # Prepare additional crawl options
            crawl_options = {}

            # Browser options
            if 'headless' in advanced_options:
                crawl_options['headless'] = advanced_options['headless']
            if 'browser_type' in advanced_options:
                crawl_options['browser_type'] = advanced_options['browser_type']
            if 'proxy' in advanced_options:
                crawl_options['proxy'] = advanced_options['proxy']
            if 'javascript_enabled' in advanced_options:
                crawl_options['javascript_enabled'] = advanced_options['javascript_enabled']
            if 'user_agent' in advanced_options:
                crawl_options['user_agent'] = advanced_options['user_agent']

            # Page navigation options
            if 'timeout' in advanced_options:
                crawl_options['timeout'] = advanced_options['timeout']
            if 'wait_for_selector' in advanced_options:
                crawl_options['wait_for'] = advanced_options['wait_for_selector']
            if 'wait_for_timeout' in advanced_options:
                crawl_options['wait_for_timeout'] = advanced_options['wait_for_timeout']

            # Media handling options
            if 'download_images' in advanced_options:
                crawl_options['download_images'] = advanced_options['download_images']
            if 'download_videos' in advanced_options:
                crawl_options['download_videos'] = advanced_options['download_videos']
            if 'download_files' in advanced_options:
                crawl_options['download_files'] = advanced_options['download_files']

            # Link handling options
            if 'follow_redirects' in advanced_options:
                crawl_options['follow_redirects'] = advanced_options['follow_redirects']
            if 'max_depth' in advanced_options:
                crawl_options['max_depth'] = advanced_options['max_depth']
            if 'follow_external_links' in advanced_options:
                crawl_options['follow_external_links'] = advanced_options['follow_external_links']
            if 'include_patterns' in advanced_options:
                crawl_options['include_patterns'] = advanced_options['include_patterns']
            if 'exclude_patterns' in advanced_options:
                crawl_options['exclude_patterns'] = advanced_options['exclude_patterns']

            # Crawl each URL found in the sitemap
            all_pages = []
            for url in urls:
                print_info(f"Crawling URL from sitemap: {url}")
                try:
                    # Crawl the individual URL
                    crawl_results = self.crawl_client.crawl_and_wait(
                        url,
                        extraction_config=extraction_config,
                        **crawl_options
                    )

                    # Process the results for this URL
                    pages = self.process_crawl_results(crawl_results)

                    if pages:
                        all_pages.extend(pages)
                        print_info(f"Successfully processed URL: {url}")
                    else:
                        print_warning(f"No content found for URL: {url}")
                except Exception as e:
                    print_error(f"Error crawling URL {url}: {e}")

            if not all_pages:
                print_warning("No pages were successfully crawled from the sitemap.")
                return site_id

            print_info(f"Successfully crawled {len(all_pages)} pages from sitemap.")

            # If no description was provided or needs_description is True, generate one from the first page content
            if (not description or needs_description) and all_pages:
                print_info("Generating site description using OpenAI...")
                # Try to find the main page or use the first page
                main_domain = self.extract_domain(sitemap_url)
                main_page = next(
                    (p for p in all_pages if main_domain in self.extract_domain(p['url'])),
                    all_pages[0]
                )

                # Use the content enhancer to generate a description
                description_data = asyncio.run(
                    self.content_enhancer.generate_title_and_summary_async(
                        main_page['content'][:5000], main_page['url']
                    )
                )
                description = description_data.get('summary', '')

                # Update the site with the generated description
                self.db_client.update_site_description(site_id, description)
                print_success(f"Generated site description with {self.content_enhancer.model}: {description[:100]}...")

            # Enhance pages with titles, summaries, and embeddings
            enhanced_pages = asyncio.run(self.enhance_pages(all_pages))

            # Store the pages in the database
            page_ids = self.db_client.add_pages(site_id, enhanced_pages, replace_chunks=True)

            print_success(f"Successfully stored {len(page_ids)} pages in the database.")

            return site_id

        except Exception as e:
            print_error(f"Error processing sitemap: {e}")
            print_info("Sitemap crawl failed. Please check the API configuration and try again.")
            return site_id

    def search(self, query: str, use_embedding: bool = True,
              threshold: float = 0.5, limit: int = 10, site_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search for pages matching a query.

        Args:
            query: The search query.
            use_embedding: Whether to use vector embeddings for search.
            threshold: Minimum similarity threshold for embedding search.
            limit: Maximum number of results to return.
            site_id: Optional site ID to filter results by.

        Returns:
            List of matching pages.
        """
        if use_embedding:
            try:
                # Generate an embedding for the query
                print_info(f"Generating embedding for query: '{query}'")
                query_embedding = self.embedding_generator.generate_embedding(query)

                if not query_embedding or len(query_embedding) == 0:
                    print_warning("Failed to generate embedding for query, falling back to text search")
                    return self.db_client.search_by_text(query, limit, site_id)

                print_info(f"Generated query embedding of length {len(query_embedding)}")

                # Validate the embedding format
                if not all(isinstance(x, (int, float)) for x in query_embedding):
                    print_warning("Invalid embedding format, falling back to text search")
                    return self.db_client.search_by_text(query, limit, site_id)

                # Use hybrid search that combines vector similarity with text matching
                print_info(f"Using hybrid search with threshold {threshold}...")
                results = self.db_client.hybrid_search(query, query_embedding, threshold, limit, site_id)

                # If no results from hybrid search, fall back to text search
                if not results:
                    print_warning("No results from hybrid search, falling back to text search")
                    results = self.db_client.search_by_text(query, limit, site_id)

                results = rerank_search_results_by_query_terms(query, results)

                # Enhance results with context
                enhanced_results = []
                for result in results:
                    # If this is a chunk, add context about its parent document
                    if result.get('is_chunk'):
                        # Add a snippet of the content (first 200 characters)
                        content = result.get('content', '')
                        result['snippet'] = content[:200] + '...' if len(content) > 200 else content

                        # Add context about which part of the document this is
                        result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                    else:
                        # For non-chunks, still add a snippet
                        content = result.get('content', '')
                        result['snippet'] = content[:200] + '...' if len(content) > 200 else content

                    enhanced_results.append(result)

                # Log the final results for debugging
                print_info(f"Final search results: {len(enhanced_results)} items")
                for i, result in enumerate(enhanced_results[:3]):
                    print_info(f"Result {i+1}: {result.get('title', 'No title')} - Similarity: {result.get('similarity', 0):.4f}")
                    print_info(f"  URL: {result.get('url', 'No URL')}")

                return enhanced_results
            except Exception as e:
                print_error(f"Error in hybrid search, falling back to text search: {e}")
                # Fall back to text search
                print_info("Falling back to text search...")
                return self.db_client.search_by_text(query, limit, site_id)
        else:
            # Use text search
            print_info("Using text search...")
            results = self.db_client.search_by_text(query, limit, site_id)
            results = rerank_search_results_by_query_terms(query, results)

            # Enhance results with context
            enhanced_results = []
            for result in results:
                # If this is a chunk, add context about its parent document
                if result.get('is_chunk'):
                    # Add a snippet of the content (first 200 characters)
                    content = result.get('content', '')
                    result['snippet'] = content[:200] + '...' if len(content) > 200 else content

                    # Add context about which part of the document this is
                    result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                else:
                    # For non-chunks, still add a snippet
                    content = result.get('content', '')
                    result['snippet'] = content[:200] + '...' if len(content) > 200 else content

                enhanced_results.append(result)

            # Log the final results for debugging
            print_info(f"Final text search results: {len(enhanced_results)} items")
            for i, result in enumerate(enhanced_results[:3]):
                print_info(f"Result {i+1}: {result.get('title', 'No title')}")
                print_info(f"  URL: {result.get('url', 'No URL')}")

            return enhanced_results

    def get_site_pages(
        self,
        site_id: int,
        limit: int = 100,
        include_chunks: bool = False,
        offset: int = 0,
        include_content: bool = True,
        content_chars: Optional[int] = None,
        preview_chars: int = 500,
    ) -> List[Dict[str, Any]]:
        """Get pages for a specific site.

        Args:
            site_id: The ID of the site.
            limit: Maximum number of pages to return.
            include_chunks: Whether to include chunked content. If False, only parent pages are returned.

        Returns:
            List of pages for the site.
        """
        return self.db_client.get_pages_by_site_id(
            site_id,
            limit=limit,
            include_chunks=include_chunks,
            offset=offset,
            include_content=include_content,
            content_chars=content_chars,
            preview_chars=preview_chars,
        )
