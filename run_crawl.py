"""
Script to run a crawl using the configuration from the .env file.
"""

import os
from dotenv import load_dotenv
from crawler import WebCrawler

# Load environment variables
load_dotenv()

from app_logging import configure_logging

configure_logging()

def run_crawl():
    """Run a crawl using the configuration from the .env file."""
    # Get configuration from .env
    url = os.getenv("CRAWL_URL")
    if not url:
        print("Error: CRAWL_URL not found in .env file.")
        return
    
    crawl_type = os.getenv("CRAWL_TYPE", "url").lower()
    site_name = os.getenv("CRAWL_SITE_NAME")
    site_description = os.getenv("CRAWL_SITE_DESCRIPTION")
    
    # Get max_urls from environment if available
    max_urls = None
    if os.getenv("MAX_URLS"):
        try:
            max_urls = int(os.getenv("MAX_URLS"))
            print(f"Using MAX_URLS={max_urls} from .env")
        except ValueError:
            print(f"Warning: Invalid MAX_URLS in .env: {os.getenv('MAX_URLS')}")
    
    # Create a crawler instance
    crawler = WebCrawler()
    
    # Run the crawl
    if crawl_type == "sitemap":
        print(f"Crawling sitemap: {url}")
        site_id = crawler.crawl_sitemap(url, site_name, site_description, max_urls=max_urls)
    else:
        print(f"Crawling website: {url}")
        site_id = crawler.crawl_site(url, site_name, site_description)
    
    print(f"Crawl completed. Site ID: {site_id}")
    return site_id

if __name__ == "__main__":
    run_crawl() 