import os
import argparse
import json
from dotenv import load_dotenv
from crawler import WebCrawler
from db_setup import setup_database
from utils import (
    console, print_header, print_success, print_error, 
    print_warning, print_info, print_sites_table, print_search_results
)
from chat import ChatBot

# Load environment variables
load_dotenv()

from app_logging import configure_logging

configure_logging()

def crawl_command(args):
    """Handle the crawl command."""
    crawler = WebCrawler()
    
    # If URL is not provided via command line, use the one from .env
    url = args.url or os.getenv("CRAWL_URL")
    if not url:
        print_error("No URL provided. Please specify a URL via command line or in the .env file.")
        return None
    
    # If sitemap flag is not set, check the CRAWL_TYPE in .env
    is_sitemap = args.sitemap
    if not is_sitemap and not args.url:  # Only check .env if not explicitly set via command line
        crawl_type = os.getenv("CRAWL_TYPE", "url").lower()
        is_sitemap = crawl_type == "sitemap"
    
    # Get site name and description from args or .env
    site_name = args.name or os.getenv("CRAWL_SITE_NAME")
    site_description = args.description or os.getenv("CRAWL_SITE_DESCRIPTION")
    
    # Get max_urls from args or .env
    max_urls = args.max_urls
    if max_urls is None and os.getenv("MAX_URLS"):
        try:
            max_urls = int(os.getenv("MAX_URLS"))
            print_info(f"Using MAX_URLS={max_urls} from .env")
        except ValueError:
            print_warning(f"Invalid MAX_URLS in .env: {os.getenv('MAX_URLS')}")
    
    if is_sitemap:
        print_header(f"Crawling sitemap: {url}")
        site_id = crawler.crawl_sitemap(url, site_name, site_description, max_urls=max_urls)
    else:
        print_header(f"Crawling website: {url}")
        site_id = crawler.crawl_site(url, site_name, site_description)
    
    print_success(f"Crawl completed. Site ID: {site_id}")
    return site_id

def search_command(args):
    """Handle the search command."""
    crawler = WebCrawler()
    
    print_header(f"Searching for: {args.query}")
    results = crawler.search(
        args.query, 
        use_embedding=not args.text_only,
        threshold=args.threshold,
        limit=args.limit
    )
    
    print_search_results(results)
    
    if args.output:
        # Save results to a JSON file
        with open(args.output, 'w') as f:
            json.dump(results, f, indent=2)
        print_success(f"Results saved to {args.output}")

def list_sites_command(args):
    """Handle the list-sites command."""
    from db_client import SupabaseClient
    
    db_client = SupabaseClient()
    
    # Connect to the database
    conn = db_client._get_connection()
    cur = conn.cursor()
    
    # Get all sites with page counts
    # If include_chunks is False, only count parent pages
    if args.include_chunks:
        cur.execute("""
            SELECT s.id, s.name, s.url, s.description, COUNT(p.id) as page_count
            FROM crawl_sites s
            LEFT JOIN crawl_pages p ON s.id = p.site_id
            GROUP BY s.id, s.name, s.url, s.description
            ORDER BY s.id
        """)
    else:
        cur.execute("""
            SELECT s.id, s.name, s.url, s.description, COUNT(p.id) as page_count
            FROM crawl_sites s
            LEFT JOIN crawl_pages p ON s.id = p.site_id AND (p.is_chunk IS NULL OR p.is_chunk = FALSE)
            GROUP BY s.id, s.name, s.url, s.description
            ORDER BY s.id
        """)
    
    sites = cur.fetchall()
    
    print_header(f"Found {len(sites)} sites:")
    
    if sites:
        print_sites_table(sites)
    else:
        print_info("No sites found. Use 'python main.py crawl' to crawl a site.")
    
    conn.close()

def setup_command(args):
    """Handle the setup command."""
    print_header("Setting up the database...")
    setup_database()
    print_success("Database setup completed.")

def chat_command(args):
    """Handle the chat command."""
    print_header("Starting chat interface")
    
    # Get parameters from args or .env
    model = args.model or os.getenv("CHAT_MODEL")
    result_limit = args.limit
    if result_limit is None and os.getenv("CHAT_RESULT_LIMIT"):
        try:
            result_limit = int(os.getenv("CHAT_RESULT_LIMIT"))
        except ValueError:
            print_warning(f"Invalid CHAT_RESULT_LIMIT in .env: {os.getenv('CHAT_RESULT_LIMIT')}")
    
    threshold = args.threshold
    if threshold is None and os.getenv("CHAT_SIMILARITY_THRESHOLD"):
        try:
            threshold = float(os.getenv("CHAT_SIMILARITY_THRESHOLD"))
        except ValueError:
            print_warning(f"Invalid CHAT_SIMILARITY_THRESHOLD in .env: {os.getenv('CHAT_SIMILARITY_THRESHOLD')}")
    
    # Get session ID and user ID from args or .env
    session_id = args.session or os.getenv("CHAT_SESSION_ID")
    user_id = args.user or os.getenv("CHAT_USER_ID")
    profile = args.profile or os.getenv("CHAT_PROFILE")
    profiles_dir = args.profiles_dir or os.getenv("CHAT_PROFILES_DIR", "profiles")
    
    # Get verbose flag from .env if not provided in args
    verbose = False
    if os.getenv("CHAT_VERBOSE", "").lower() == "true":
        verbose = True
    
    # Create a chat interface
    chat_bot = ChatBot(
        model=model,
        result_limit=result_limit,
        similarity_threshold=threshold,
        session_id=session_id,
        user_id=user_id,
        profile=profile,
        profiles_dir=profiles_dir,
        verbose=verbose
    )
    
    # Start the chat loop
    chat_bot.chat_loop()

def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(description="Crawl websites and search using vector embeddings")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Set up the database")
    
    # Crawl command
    crawl_parser = subparsers.add_parser("crawl", help="Crawl a website or sitemap")
    crawl_parser.add_argument("url", nargs="?", help="URL to crawl (optional if set in .env)")
    crawl_parser.add_argument("--name", help="Name for the site (optional)")
    crawl_parser.add_argument("--description", help="Description of the site (optional)")
    crawl_parser.add_argument("--sitemap", action="store_true", help="Treat URL as a sitemap")
    crawl_parser.add_argument("--max-urls", type=int, help="Maximum number of URLs to crawl")
    
    # Search command
    search_parser = subparsers.add_parser("search", help="Search the crawled data")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--text-only", action="store_true", help="Use text search instead of embeddings")
    search_parser.add_argument("--threshold", type=float, default=0.3, help="Similarity threshold (0-1)")
    search_parser.add_argument("--limit", type=int, default=10, help="Maximum number of results")
    search_parser.add_argument("--output", help="Save results to a JSON file")
    
    # List sites command
    list_sites_parser = subparsers.add_parser("list-sites", help="List all crawled sites")
    list_sites_parser.add_argument("--include-chunks", action="store_true", help="Include chunks in page count")
    
    # Chat command
    chat_parser = subparsers.add_parser("chat", help="Start the chat interface")
    chat_parser.add_argument("--model", help="Model to use for chat")
    chat_parser.add_argument("--limit", type=int, help="Maximum number of results")
    chat_parser.add_argument("--threshold", type=float, help="Similarity threshold (0-1)")
    chat_parser.add_argument("--session", help="Session ID")
    chat_parser.add_argument("--user", help="User ID")
    chat_parser.add_argument("--profile", help="Profile to use for chat")
    chat_parser.add_argument("--profiles-dir", help="Profiles directory")
    
    args = parser.parse_args()
    
    if args.command == "setup":
        setup_command(args)
    elif args.command == "crawl":
        crawl_command(args)
    elif args.command == "search":
        search_command(args)
    elif args.command == "list-sites":
        list_sites_command(args)
    elif args.command == "chat":
        chat_command(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 