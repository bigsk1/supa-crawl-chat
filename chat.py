"""
Chat interface for interacting with crawled data using an LLM.
"""

import os
import argparse
import uuid
import json
import yaml
import glob
import re
from typing import List, Dict, Any, Optional, Tuple, Union, Callable
from dotenv import load_dotenv
from openai import OpenAI
from crawler import WebCrawler
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.prompt import Prompt, Confirm
from rich.table import Table
import datetime
import sys
from rich.progress import Progress, SpinnerColumn, TextColumn
import time

from utils import print_success, print_error, print_warning, print_info

# Create a rich console
console = Console()

# Load environment variables
load_dotenv()

# Create a flag to control verbose output
VERBOSE_OUTPUT = False


def _openai_chat_token_kwargs(model: Optional[str], limit: int) -> Dict[str, int]:
    """Chat Completions: newer models require ``max_completion_tokens`` instead of ``max_tokens``."""
    if os.getenv("OPENAI_PREFER_MAX_COMPLETION_TOKENS", "").lower() in ("1", "true", "yes"):
        return {"max_completion_tokens": limit}
    m = (model or "").lower()
    if m.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": limit}
    return {"max_tokens": limit}

# Override print functions to respect verbose mode
def chat_print_info(text: str):
    """Print info message only if verbose mode is enabled."""
    if VERBOSE_OUTPUT:
        print_info(text)

def chat_print_warning(text: str):
    """Print warning message only if verbose mode is enabled."""
    if VERBOSE_OUTPUT:
        print_warning(text)

def chat_print_error(text: str):
    """Print error message only if verbose mode is enabled."""
    print_error(text)  # Always show errors

def chat_print_success(text: str):
    """Print success message only if verbose mode is enabled."""
    if VERBOSE_OUTPUT:
        print_success(text)


# Replace the original print functions in the modules that need quieter output
import crawler
import db_client
import embeddings

# Store original functions
original_print_info = crawler.print_info
original_print_warning = crawler.print_warning
original_print_error = crawler.print_error
original_print_success = crawler.print_success

def set_quiet_mode():
    """Set quiet mode for the crawler."""
    crawler.print_info = chat_print_info
    crawler.print_warning = chat_print_warning
    crawler.print_error = chat_print_error
    crawler.print_success = chat_print_success

    db_client.print_info = chat_print_info
    db_client.print_warning = chat_print_warning
    db_client.print_error = chat_print_error
    db_client.print_success = chat_print_success

    embeddings.print_info = chat_print_info
    embeddings.print_warning = chat_print_warning
    embeddings.print_error = chat_print_error
    embeddings.print_success = chat_print_success

def restore_verbose_mode():
    """Restore original print functions."""
    crawler.print_info = original_print_info
    crawler.print_warning = original_print_warning
    crawler.print_error = original_print_error
    crawler.print_success = original_print_success

    db_client.print_info = original_print_info
    db_client.print_warning = original_print_warning
    db_client.print_error = original_print_error
    db_client.print_success = original_print_success

    embeddings.print_info = original_print_info
    embeddings.print_warning = original_print_warning
    embeddings.print_error = original_print_error
    embeddings.print_success = original_print_success

# Define default chat profiles (fallback if files not found)
DEFAULT_PROFILES = {
    "default": {
        "name": "default",
        "description": "General-purpose assistant for all sites",
        "system_prompt": "You are a helpful assistant that answers questions based on the provided context. If the answer is not in the context, say you don't know.",
        "search_settings": {
            "sites": [],  # Empty list means search all sites
            "threshold": 0.5,
            "limit": 5
        }
    }
}

def load_profiles_from_directory(profiles_dir="profiles"):
    """Load profile configurations from YAML files in the profiles directory.

    Args:
        profiles_dir: Directory containing profile YAML files.

    Returns:
        Dictionary of profile configurations.
    """
    profiles = {}

    # First, load the default profiles as fallback
    profiles.update(DEFAULT_PROFILES)

    # Check if the profiles directory exists
    if not os.path.exists(profiles_dir):
        console.print(f"[yellow]Profiles directory '{profiles_dir}' not found. Using default profiles.[/yellow]")
        return profiles

    # Find all YAML files in the profiles directory
    profile_files = glob.glob(os.path.join(profiles_dir, "*.yaml"))
    profile_files.extend(glob.glob(os.path.join(profiles_dir, "*.yml")))

    if not profile_files:
        console.print(f"[yellow]No profile files found in '{profiles_dir}'. Using default profiles.[/yellow]")
        return profiles

    # Load each profile file
    for profile_file in profile_files:
        try:
            with open(profile_file, 'r') as f:
                profile_data = yaml.safe_load(f)

            # Validate the profile data
            if not profile_data.get('name'):
                console.print(f"[yellow]Profile file '{profile_file}' missing 'name' field. Skipping.[/yellow]")
                continue

            # Extract the profile name
            profile_name = profile_data['name']

            # Ensure search_settings exists
            if 'search_settings' not in profile_data:
                profile_data['search_settings'] = DEFAULT_PROFILES['default']['search_settings']

            # Add the profile to the dictionary
            profiles[profile_name] = profile_data

        except Exception as e:
            console.print(f"[red]Error loading profile from '{profile_file}': {e}[/red]")

    # Print the number of profiles loaded
    console.print(f"[green]Loaded {len(profiles)} profiles from {profiles_dir}[/green]")

    return profiles

# Load profiles from the profiles directory
# CHAT_PROFILES = load_profiles_from_directory()

class ChatBot:
    """Chat interface for interacting with crawled data using an LLM."""

    def __init__(self, model: Optional[str] = None,
                result_limit: Optional[int] = None,
                similarity_threshold: Optional[float] = None,
                session_id: Optional[str] = None,
                user_id: Optional[str] = None,
                profile: str = "default",
                profiles_dir: str = "profiles",
                verbose: bool = False):
        """Initialize the chat interface.

        Args:
            model: The OpenAI model to use.
            result_limit: Maximum number of search results to return.
            similarity_threshold: Similarity threshold for vector search.
            session_id: Session ID for the conversation.
            user_id: User ID for the conversation.
            profile: Profile to use for the conversation.
            profiles_dir: Directory containing profile YAML files.
            verbose: Whether to show verbose output.
        """
        # Set verbose output flag
        global VERBOSE_OUTPUT
        VERBOSE_OUTPUT = verbose

        # Set quiet mode by default for chat
        set_quiet_mode()

        # Initialize the crawler
        self.crawler = WebCrawler()

        # Set up the OpenAI API key
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")

        # Set up the OpenAI client
        try:
            # Try to initialize the client with the standard parameters
            self.client = OpenAI(api_key=self.api_key)
        except TypeError as e:
            # If there's an error about unexpected keyword arguments, try a different approach
            if "unexpected keyword argument" in str(e):
                print(f"Warning: {e}. Trying alternative initialization.")
                # Initialize without the problematic parameter
                import httpx
                http_client = httpx.Client()
                self.client = OpenAI(api_key=self.api_key, http_client=http_client)
            else:
                raise

        # Set up the model
        self.model = model or os.getenv("CHAT_MODEL", "gpt-4o")

        # Set up the result limit
        self.result_limit = result_limit or int(os.getenv("CHAT_RESULT_LIMIT", "5"))

        # Set up the similarity threshold
        self.similarity_threshold = similarity_threshold or float(os.getenv("CHAT_SIMILARITY_THRESHOLD", "0.5"))

        # Set up the session ID
        if session_id:
            self.session_id = session_id
        else:
            env_session_id = os.getenv("CHAT_SESSION_ID")
            if env_session_id and env_session_id.strip():
                self.session_id = env_session_id
            else:
                self.session_id = str(uuid.uuid4())
                console.print(f"Generated new session ID: {self.session_id}")

        # Set up the user ID
        self.user_id = user_id or os.getenv("CHAT_USER_ID")

        # Load profiles
        self.profiles_dir = profiles_dir or os.getenv("CHAT_PROFILES_DIR", "profiles")
        self.profiles = load_profiles_from_directory(self.profiles_dir)

        # Initialize the database client
        self.db_client = self.crawler.db_client

        # Set up the conversation history table
        self.db_client.setup_conversation_history_table()

        # Set up the conversation history
        self.conversation_history = []
        self.load_conversation_history()

        # Set up the profile (must be done after conversation_history is initialized)
        profile_name = profile or os.getenv("CHAT_PROFILE", "default")
        self.set_profile(profile_name)

        # Print configuration
        console.print(f"Using chat model: {self.model}")
        console.print(f"Result limit: {self.result_limit}")
        console.print(f"Similarity threshold: {self.similarity_threshold}")

        # Get search settings from the profile
        self.search_sites = self.profile.get('search_settings', {}).get('sites', [])
        self.search_threshold = self.profile.get('search_settings', {}).get('threshold', self.similarity_threshold)
        self.search_limit = self.profile.get('search_settings', {}).get('limit', self.result_limit)

        # Print search settings if they differ from the defaults
        if self.search_threshold != self.similarity_threshold:
            console.print(f"[bold blue]Profile search threshold:[/bold blue] [green]{self.search_threshold}[/green]")
        if self.search_limit != self.result_limit:
            console.print(f"[bold blue]Profile search limit:[/bold blue] [green]{self.search_limit}[/green]")
        if self.search_sites:
            console.print(f"[bold blue]Filtering sites:[/bold blue] [green]{', '.join(self.search_sites)}[/green]")

    def load_conversation_history(self):
        """Load conversation history from the database."""
        try:
            # If the crawler is not available, return
            if not self.crawler:
                console.print("[yellow]No database connection, conversation history will not be loaded[/yellow]")
                return

            # Get conversation history from the database
            db_messages = self.crawler.db_client.get_conversation_history(self.session_id)

            # Convert to the format expected by the OpenAI API
            self.conversation_history = []

            # Track user preferences
            all_preferences = []

            for message in db_messages:
                # Add the message to the conversation history
                self.conversation_history.append({
                    "role": message["role"],
                    "content": message["content"],
                    "timestamp": message.get("timestamp", ""),
                    "metadata": message.get("metadata", {})
                })

                # Extract preferences from metadata
                if message["role"] == "user" and message.get("metadata") and "preference" in message["metadata"]:
                    preference = message["metadata"]["preference"]
                    all_preferences.append(preference)

            # Print the number of messages loaded
            if self.conversation_history:
                console.print(f"[bold green]Loaded {len(self.conversation_history)} messages from history[/bold green]")

                # Print a summary of the conversation
                user_messages = [msg for msg in self.conversation_history if msg["role"] == "user"]
                if user_messages:
                    console.print(f"[blue]Previous conversation includes {len(user_messages)} user messages[/blue]")

                    # Show the first and last user message as a preview
                    if len(user_messages) > 1:
                        console.print(f"[blue]First message: '{user_messages[0]['content'][:50]}...'[/blue]")
                        console.print(f"[blue]Last message: '{user_messages[-1]['content'][:50]}...'[/blue]")

                # Consolidate and display user preferences if any were found
                if all_preferences:
                    # Remove duplicates while preserving order
                    unique_preferences = []
                    for pref in all_preferences:
                        if pref not in unique_preferences:
                            unique_preferences.append(pref)

                    # Limit to the most recent 5 preferences
                    if len(unique_preferences) > 5:
                        unique_preferences = unique_preferences[-5:]

                    console.print(f"[green]Remembered user preferences:[/green]")
                    for pref in unique_preferences:
                        console.print(f"[green]- {pref}[/green]")
            else:
                console.print("[yellow]No conversation history found for this session[/yellow]")
        except Exception as e:
            console.print(f"[red]Error loading conversation history: {e}[/red]")
            self.conversation_history = []

    def add_system_message(self, content: str):
        """Add a system message to the conversation history.

        Args:
            content: The message content.
        """
        # Add the message to the conversation history
        message = {
            "role": "system",
            "content": content,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.conversation_history.append(message)

        # If the crawler is not available, return
        if not self.crawler:
            return

        # Save the message to the database
        try:
            self.crawler.db_client.save_message(
                session_id=self.session_id,
                role="system",
                content=content,
                user_id=self.user_id,
                metadata={"profile": self.profile_name}
            )
        except Exception as e:
            console.print(f"[red]Error saving system message to database: {e}[/red]")

    def add_user_message(self, content: str):
        """Add a user message to the conversation history.

        Args:
            content: The message content.
        """
        # Add the message to the conversation history
        message = {
            "role": "user",
            "content": content,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.conversation_history.append(message)

        # If the crawler is not available, return
        if not self.crawler:
            return

        # Base metadata with profile information
        metadata = {"profile": self.profile_name}

        # Check for preference keywords - EXPANDED list
        preference_keywords = [
            # Explicit preferences
            "like", "love", "prefer", "favorite", "enjoy", "hate", "dislike",
            # Additional markers
            "interested in", "fond of", "care about", "passionate about",
            "can't stand", "don't like", "don't care for", "avoid"
        ]

        # Enhanced preference detection
        has_preference = False
        for keyword in preference_keywords:
            if keyword in content.lower():
                has_preference = True
                break

        # If the message might contain a preference, use the LLM to extract it properly
        if has_preference or len(content.split()) >= 10:  # Check longer messages too
            try:
                # Create a more nuanced prompt for the LLM to extract preferences
                prompt = f"""Extract any user preferences from this message: "{content}"

Look for:
1. Direct preferences (like, love, prefer, favorite, enjoy, hate, dislike)
2. Implied preferences (interested in, fond of, passionate about)
3. Important personal details that should be remembered for future conversation
4. Attitudes or opinions expressed about topics

If you find any preferences or important details, format each as "TYPE VALUE" (e.g., "like Python", "hate brussels sprouts", "interested AI", "from Seattle")

For TYPE, use one of: like, love, hate, dislike, prefer, interest, trait, background

If there are no clear preferences or important details, respond with "NONE".
Extract up to 3 key preferences or details, prioritizing the most salient ones.
"""

                # Use a smaller model for this extraction
                extraction_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")

                response = self.client.chat.completions.create(
                    model=extraction_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    **_openai_chat_token_kwargs(extraction_model, 100),
                )

                # Extract the preferences
                extraction_result = response.choices[0].message.content.strip()

                # Only save if it's a valid preference
                if extraction_result and extraction_result != "NONE":
                    # Split multiple preferences (one per line)
                    preferences = [pref.strip() for pref in extraction_result.split('\n') if pref.strip() and pref.strip() != "NONE"]

                    # Store the most important preference in message metadata
                    if preferences:
                        metadata["preference"] = preferences[0]
                        console.print(f"[blue]Extracted primary preference: {preferences[0]}[/blue]")

                    # If we have a user ID, save all preferences to the user_preferences table
                    if self.user_id:
                        for preference in preferences:
                            try:
                                # Get a confidence score based on the clarity of the preference
                                # Direct preferences get higher confidence
                                direct_preference = any(f"{keyword} " in content.lower() for keyword in ["like ", "love ", "hate ", "prefer ", "favorite "])
                                confidence = 0.9 if direct_preference else 0.75

                                # Extract preference type and value
                                parts = preference.split(" ", 1)
                                if len(parts) == 2:
                                    pref_type = parts[0]  # e.g., "like", "hate"
                                    pref_value = parts[1]  # e.g., "corvettes", "brussels sprouts"

                                    # Save the preference to the database
                                    self.crawler.db_client.save_user_preference(
                                        user_id=self.user_id,
                                        preference_type=pref_type,
                                        preference_value=pref_value,
                                        context=content,
                                        confidence=confidence,
                                        source_session=self.session_id
                                    )

                                    console.print(f"[green]Saved preference to database: {pref_type} {pref_value} (confidence: {confidence:.2f})[/green]")
                                else:
                                    console.print(f"[yellow]Could not split preference into type and value: {preference}[/yellow]")
                            except Exception as e:
                                console.print(f"[red]Error saving preference to database: {e}[/red]")
            except Exception as e:
                console.print(f"[dim red]Error extracting preference: {e}[/dim red]")

        # Save to database
        try:
            self.crawler.db_client.save_message(
                session_id=self.session_id,
                role="user",
                content=content,
                user_id=self.user_id,
                metadata=metadata
            )
        except Exception as e:
            console.print(f"[red]Error saving user message to database: {e}[/red]")

    def add_assistant_message(self, content: str):
        """Add an assistant message to the conversation history.

        Args:
            content: The message content.
        """
        # Add the message to the conversation history
        message = {
            "role": "assistant",
            "content": content,
            "timestamp": datetime.datetime.now().isoformat()
        }
        self.conversation_history.append(message)

        # If the crawler is not available, return
        if not self.crawler:
            return

        # Save the message to the database
        try:
            self.crawler.db_client.save_message(
                session_id=self.session_id,
                role="assistant",
                content=content,
                user_id=self.user_id,
                metadata={"profile": self.profile_name}
            )
        except Exception as e:
            console.print(f"[red]Error saving assistant message to database: {e}[/red]")

    def clear_conversation_history(self):
        """Clear the conversation history."""
        # Clear from the database
        self.crawler.db_client.clear_conversation_history(self.session_id)

        # Clear from memory
        self.conversation_history = []

        # Add a system message
        self.add_system_message(self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt']))

        console.print("[bold green]Conversation history cleared[/bold green]")

    def change_profile(self, profile_name: str):
        """Change the chat profile.

        Args:
            profile_name: The name of the profile to use.
        """
        # For backward compatibility, call the new set_profile method
        self.set_profile(profile_name)

    def search_for_context(self, query: str) -> List[Dict[str, Any]]:
        """Search for relevant context based on the query.

        Args:
            query: The user's query.

        Returns:
            A list of search results.
        """
        # Clean and prepare the query
        clean_query = query.strip().lower()
        search_terms = clean_query.split()

        # Check if the query is about an app or application
        is_app_query = False
        if 'app' in clean_query or 'application' in clean_query:
            is_app_query = True
            # Extract the potential app name by removing "app" or "application"
            app_name_parts = []
            for term in search_terms:
                if term not in ['app', 'application', 'the', 'about', 'what', 'is', 'can', 'you', 'tell', 'me']:
                    app_name_parts.append(term)

            # If we found potential app name parts, create an alternative query
            if app_name_parts:
                alt_query = ' '.join(app_name_parts)
                console.print(f"[blue]Detected app query. Also searching for: {alt_query}[/blue]")

                # Try searching with the alternative query first
                try:
                    # Use the crawler's search method with the correct parameters
                    alt_results = self.crawler.search(
                        query=alt_query,
                        use_embedding=True,
                        threshold=max(0.5, self.similarity_threshold - 0.2),  # Lower threshold for broader matches
                        limit=self.result_limit,
                        site_id=None  # Search all sites
                    )

                    if alt_results:
                        console.print(f"[green]Found {len(alt_results)} results for alternative query[/green]")
                        # Mark these as "best" results
                        for result in alt_results:
                            result["is_best_result"] = True
                        return alt_results
                except Exception as e:
                    console.print(f"[red]Error searching for alternative query: {e}[/red]")
                    import traceback
                    traceback.print_exc()

        # Check if the query is very specific (contains hyphens, underscores, or other technical patterns)
        contains_technical_pattern = False
        if '-' in clean_query or '_' in clean_query:
            contains_technical_pattern = True
        elif len(search_terms) <= 3 and not any(q in clean_query for q in ["what", "how", "why", "when", "who", "which"]):
            # Short, non-question query might be a specific entity
            contains_technical_pattern = True

        # Check if the query directly mentions a website by domain name
        contains_domain = False
        domain_name = None

        # Common domain patterns: website.com, website.org, etc.
        domain_pattern = re.compile(r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}')
        domain_matches = domain_pattern.findall(clean_query)

        if domain_matches:
            contains_domain = True
            domain_name = domain_matches[0]
            console.print(f"[blue]Detected domain name: {domain_name}[/blue]")

        # Check if query directly asks about a website or site
        site_query_patterns = [
            r'about (the )?(\w+) (website|site)',
            r'what is (the )?(\w+) (website|site)',
            r'tell me about (the )?(\w+) (website|site)',
            r'information (about|on) (the )?(\w+) (website|site)'
        ]

        site_name = None
        for pattern in site_query_patterns:
            match = re.search(pattern, clean_query)
            if match:
                # Extract the site name from the appropriate group
                for group in match.groups():
                    if group and not any(word in group for word in ['the', 'website', 'site', 'about', 'on']):
                        site_name = group
                        break

                if site_name:
                    console.print(f"[blue]Detected site name: {site_name}[/blue]")
                    break

        # Check if the query contains a URL or GitHub repository reference
        contains_url = 'http://' in clean_query or 'https://' in clean_query
        contains_github = 'github.com' in clean_query
        contains_repo_pattern = bool(re.search(r'[\w\-]+/[\w\-]+', clean_query))  # Pattern like username/repo

        # Extract project names from the query - regardless of whether they're GitHub repos or not
        project_names = []

        # Look for hyphenated terms that might be project names
        hyphenated_terms = re.findall(r'(\w+(?:-\w+)+)', clean_query)
        for term in hyphenated_terms:
            if term not in project_names and len(term) > 3:
                project_names.append(term)
                # Also add the space-separated version
                project_names.append(term.replace('-', ' '))

        # For specific URL or repository queries, try extra search variations
        if contains_url or contains_github or contains_repo_pattern or domain_name or site_name:
            console.print("[yellow]Detected URL or website reference - specializing search...[/yellow]")

            # Try to find direct URL matches
            url_results = self._search_for_urls(query)
            if url_results:
                console.print(f"[green]Found {len(url_results)} URL results[/green]")
                return url_results

            # If no URL results, try a broader search for content
            content_results = self._search_for_best_content(query)
            if content_results:
                console.print(f"[green]Found {len(content_results)} content results for URL/repo query[/green]")
                return content_results

            # If direct queries didn't work, try direct keyword search with site name/domain
            try:
                if domain_name or site_name:
                    site_query = site_name or domain_name
                    console.print(f"[yellow]Trying direct keyword search for site: {site_query}[/yellow]")

                    # Search for the site name in the database
                    keyword_results = self.crawler.db_client.direct_keyword_search(
                        query=site_query,
                        limit=self.search_limit
                    )

                    if keyword_results:
                        console.print(f"[green]Found {len(keyword_results)} results for site: {site_query}[/green]")
                        return keyword_results
            except Exception as e:
                console.print(f"[red]Error in site keyword search: {e}[/red]")

        # If this is likely a query about a specific technical term, try direct keyword search
        if contains_technical_pattern:
            try:
                # Direct search for technical terms
                console.print(f"[yellow]Trying direct keyword search for technical term: {clean_query}[/yellow]")

                # Get site patterns from profile if available
                site_patterns = None
                if self.profile and "site_patterns" in self.profile:
                    site_patterns = self.profile["site_patterns"]
                elif self.profile and "search_settings" in self.profile and "site_patterns" in self.profile["search_settings"]:
                    site_patterns = self.profile["search_settings"]["site_patterns"]

                # Log the site patterns for debugging
                if site_patterns:
                    console.print(f"[blue]Using site patterns from profile: {site_patterns}[/blue]")

                # Try searching with the profile's site patterns first
                if site_patterns:
                    keyword_results = self.crawler.db_client.direct_keyword_search(
                        query=clean_query,
                        limit=self.search_limit,
                        site_patterns=site_patterns
                    )

                    if keyword_results and len(keyword_results) > 0:
                        console.print(f"[green]Found {len(keyword_results)} direct keyword matches with site patterns[/green]")
                        return keyword_results

                # If no results with site patterns, try without
                keyword_results = self.crawler.db_client.direct_keyword_search(
                    query=clean_query,
                    limit=self.search_limit
                )

                if keyword_results and len(keyword_results) > 0:
                    console.print(f"[green]Found {len(keyword_results)} direct keyword matches[/green]")
                    return keyword_results
            except Exception as e:
                console.print(f"[red]Error in direct keyword search: {e}[/red]")

        # Normal search case - try a regular search
        try:
            # Use the main search method
            console.print(f"[yellow]Performing regular search for: {query}[/yellow]")

            # Regular search with the query
            results = self._regular_search(query)

            if results:
                console.print(f"[green]Found {len(results)} results with regular search[/green]")
                return results
        except Exception as e:
            console.print(f"[red]Error in regular search: {e}[/red]")

        # If we got here, no results were found
        console.print("[red]No results found for query[/red]")
        return []

    def _regular_search(self, query: str) -> List[Dict[str, Any]]:
        """Perform a regular search based on the query.

        Args:
            query: The user's query.

        Returns:
            A list of search results.
        """
        # Log the search query for debugging
        console.print(f"[blue]Performing regular search for: {query}[/blue]")

        # If the profile specifies specific sites to search, filter by site name
        if self.search_sites:
            console.print(f"[blue]Filtering search to {len(self.search_sites)} sites...[/blue]")

            # Get all sites
            all_sites = self.crawler.db_client.get_all_sites()

            # Filter sites based on the patterns in the profile
            site_ids = []
            site_names = []
            for site in all_sites:
                site_name = site.get("name", "").lower()
                for pattern in self.search_sites:
                    pattern = pattern.lower()
                    if pattern in site_name or site_name in pattern:
                        site_ids.append(site["id"])
                        site_names.append(site_name)
                        break

            console.print(f"[blue]Found {len(site_ids)} matching sites: {', '.join(site_names)}[/blue]")

            # If we have site IDs, search each site separately
            if site_ids:
                console.print(f"[blue]Searching {len(site_ids)} sites...[/blue]")

                all_results = []
                for i, site_id in enumerate(site_ids):
                    try:
                        console.print(f"[blue]Searching site: {site_names[i]} (ID: {site_id})[/blue]")

                        # Use the crawler's search method for each site
                        site_results = self.crawler.search(
                            query,
                            limit=self.result_limit,
                            threshold=max(0.2, self.similarity_threshold - 0.1),  # Lower threshold slightly for better recall
                            site_id=site_id
                        )

                        all_results.extend(site_results)
                    except Exception as e:
                        console.print(f"[red]Error searching site {site_names[i]} (ID: {site_id}): {e}[/red]")

                # Sort by similarity score and limit to result_limit
                all_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
                all_results = all_results[:self.result_limit]

                if all_results:
                    console.print(f"[green]Found {len(all_results)} results across {len(site_ids)} sites[/green]")
                    return all_results
                else:
                    console.print("[yellow]No results found across specified sites, searching all sites[/yellow]")

        # If no site IDs or no results from site-specific search, do a general search
        console.print(f"[blue]Searching all sites with query: '{query}'[/blue]")

        # Use the crawler's search method for all sites with a slightly lower threshold
        results = self.crawler.search(
            query,
            limit=self.result_limit,
            threshold=max(0.2, self.similarity_threshold - 0.1),  # Lower threshold slightly for better recall
        )

        if results:
            console.print(f"[green]Found {len(results)} results[/green]")
        else:
            # If no results with vector search, try a keyword search
            console.print("[yellow]No results found with semantic search, trying keyword search[/yellow]")
            try:
                keyword_results = self.crawler.search(
                    query=query,
                    use_embedding=False,  # Use text search for keywords
                    threshold=0.5,
                    limit=self.result_limit,
                    site_id=None  # Search all sites
                )

                if keyword_results:
                    console.print(f"[green]Found {len(keyword_results)} keyword results[/green]")
                    return keyword_results
                else:
                    console.print("[red]No results found with keyword search either[/red]")
            except Exception as e:
                console.print(f"[red]Error in keyword search: {e}[/red]")

        return results

    def _search_for_urls(self, query: str) -> List[Dict[str, Any]]:
        """Search for URLs based on the query.

        Args:
            query: The user's query.

        Returns:
            A list of URL results.
        """
        console.print(f"[blue]URL query detected, searching for URLs...[/blue]")

        # Extract domain parts if present
        domain_parts = re.findall(r'[\w\.-]+\.\w+', query)
        domain = domain_parts[0] if domain_parts else None

        if domain:
            console.print(f"[blue]Detected domain: {domain}[/blue]")

            # Use the crawler's search method directly with the domain as the query
            # This will use vector search to find the most relevant results
            try:
                # First try with the domain as the query
                results = self.crawler.search(
                    query=domain,
                    limit=self.result_limit,
                    threshold=0.2,  # Lower threshold for better recall
                )

                if results:
                    console.print(f"[green]Found {len(results)} results for domain: {domain}[/green]")

                    # Mark these as URL results
                    for result in results:
                        result["is_url_result"] = True

                    # Print the top results for debugging
                    console.print("[blue]Top URL results:[/blue]")
                    for i, result in enumerate(results[:3]):
                        console.print(f"[blue]Result {i+1}: {result.get('title', 'No title')} - URL: {result.get('url', 'No URL')} - Similarity: {result.get('similarity', 0):.4f}[/blue]")

                    return results
                else:
                    console.print(f"[yellow]No results found for domain: {domain}, trying with full query[/yellow]")

                    # Try with the full query
                    results = self.crawler.search(
                        query=query,
                        limit=self.result_limit,
                        threshold=0.2,  # Lower threshold for better recall
                    )

                    if results:
                        console.print(f"[green]Found {len(results)} results for query: {query}[/green]")

                        # Mark these as URL results
                        for result in results:
                            result["is_url_result"] = True

                        # Print the top results for debugging
                        console.print("[blue]Top URL results:[/blue]")
                        for i, result in enumerate(results[:3]):
                            console.print(f"[blue]Result {i+1}: {result.get('title', 'No title')} - URL: {result.get('url', 'No URL')} - Similarity: {result.get('similarity', 0):.4f}[/blue]")

                        return results
            except Exception as e:
                console.print(f"[red]Error searching for domain: {e}[/red]")

        # If we get here, either there was no domain or the search failed
        # Fall back to regular search
        console.print("[yellow]No domain detected or search failed, falling back to regular search[/yellow]")
        return self._regular_search(query)

    def _search_for_best_content(self, query: str, lower_threshold: bool = False) -> List[Dict[str, Any]]:
        """Search for the best content based on the query.

        Args:
            query: The user's query.
            lower_threshold: Whether to use a lower similarity threshold for broader matches.

        Returns:
            A list of search results.
        """
        try:
            # Set a lower threshold for broader matches if requested
            similarity_threshold = self.similarity_threshold
            if lower_threshold:
                similarity_threshold = max(0.5, similarity_threshold - 0.2)  # Lower by 0.2 but not below 0.5

            # Get site ID if site patterns are specified
            site_id = None
            if self.profile and "site_patterns" in self.profile:
                site_patterns = self.profile["site_patterns"]
                # Try to find a matching site
                if site_patterns:
                    all_sites = self.crawler.db_client.get_all_sites()
                    for site in all_sites:
                        site_name = site.get("name", "").lower()
                        for pattern in site_patterns:
                            pattern = pattern.lower()
                            if pattern in site_name or site_name in pattern:
                                site_id = site["id"]
                                break
                        if site_id:
                            break

            # Use the crawler's search method with the correct parameters
            top_results = self.crawler.search(
                query=query,
                use_embedding=True,
                threshold=similarity_threshold,
                limit=self.result_limit,
                site_id=site_id
            )

            if top_results:
                console.print(f"[green]Found {len(top_results)} quality pages[/green]")

                # Add a flag to indicate these are "best" results
                for result in top_results:
                    result["is_best_result"] = True

                return top_results
            else:
                console.print("[yellow]No quality pages found, falling back to regular search[/yellow]")
                return self._regular_search(query)
        except Exception as e:
            console.print(f"[red]Error retrieving quality pages: {e}[/red]")
            return self._regular_search(query)

    def format_context(self, results: List[Dict[str, Any]]) -> str:
        """Format the context for the LLM.

        Args:
            results: The search results to format.

        Returns:
            The formatted context.
        """
        if not results:
            return "===== NO RELEVANT DATABASE RESULTS FOUND =====\n\nNo information available in the database for this query. The response will be based on general knowledge."

        # Check if the first result is a URL result
        if results and results[0].get("is_url_result", False):
            # Format URL results
            context = "===== DATABASE SEARCH RESULTS: RELEVANT URLS =====\n\n"

            for i, result in enumerate(results, 1):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                site_name = result.get("site_name", "Unknown site")
                summary = result.get("summary", "")

                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]

                context += f"RESULT {i}: {title}\n"
                context += f"URL: {url}\n"
                context += f"SOURCE: {site_name}\n"
                if summary:
                    context += f"SUMMARY: {summary}\n"
                context += "\n"

            # Add a reminder to include URLs in the response when appropriate
            context += "IMPORTANT: When referencing specific information from these results, include the relevant URLs as formatted links using markdown syntax: [link text](URL).\n\n"

            return context

        # Check if these are "best" results
        if results and results[0].get("is_best_result", False):
            # Format best results
            context = "===== VERIFIED DATABASE SEARCH RESULTS =====\n\n"

            for i, result in enumerate(results, 1):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                site_name = result.get("site_name", "Unknown site")
                summary = result.get("summary", "")
                content = result.get("content", "")

                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]

                context += f"RESULT {i}: {title}\n"
                context += f"URL: {url}\n"
                context += f"SOURCE: {site_name}\n"

                if summary:
                    context += f"SUMMARY: {summary}\n\n"
                elif content:
                    # Create a brief summary from the content if no summary exists
                    brief_content = content[:500] + "..." if len(content) > 500 else content
                    context += f"CONTENT: {brief_content}\n\n"
                else:
                    context += "\n"

            # Add a reminder to include URLs in the response when appropriate
            context += "IMPORTANT: When referencing specific information from these results, include the relevant URLs as formatted links using markdown syntax: [link text](URL).\n\n"

            return context

        # For direct keyword search results, give them special formatting
        if results and any(r.get("match_type") in ["title_exact", "content_exact"] or r.get("is_keyword_result", False) for r in results):
            context = "===== EXACT KEYWORD MATCHES IN DATABASE =====\n\n"

            for i, result in enumerate(results, 1):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                site_name = result.get("site_name", "Unknown site")
                content = result.get("content", "")
                match_type = result.get("match_type", "keyword_match")
                similarity = result.get("similarity", 0)

                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]

                context += f"RESULT {i}: {title}\n"
                context += f"URL: {url}\n"
                context += f"SOURCE: {site_name}\n"
                context += f"MATCH TYPE: {match_type} (relevance: {similarity:.2f})\n\n"

                # Include a reasonable amount of content
                if content:
                    # Limit content length but ensure we get enough context
                    max_length = 1000 if i == 1 else 500  # Give more space to the top result
                    formatted_content = content[:max_length] + "..." if len(content) > max_length else content
                    context += f"CONTENT:\n{formatted_content}\n\n"

                context += "---\n\n"

            # Add a reminder to include URLs in the response when appropriate
            context += "IMPORTANT: When referencing specific information from these results, include the relevant URLs as formatted links using markdown syntax: [link text](URL).\n\n"

            return context

        # Group results by site for regular semantic search results
        results_by_site = {}
        for result in results:
            site_name = result.get("site_name", "Unknown")
            if site_name not in results_by_site:
                results_by_site[site_name] = []
            results_by_site[site_name].append(result)

        context = "===== DATABASE SEARCH RESULTS: RELEVANT INFORMATION =====\n\n"

        result_counter = 0
        for site_name, site_results in results_by_site.items():
            # Sort by similarity score
            site_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

            for result in site_results:
                result_counter += 1
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                content = result.get("content", "")
                similarity = result.get("similarity", 0)

                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]

                # Format the header for each result
                context += f"RESULT {result_counter}: {title}\n"
                context += f"URL: {url}\n"
                context += f"SOURCE: {site_name}\n"
                context += f"RELEVANCE: {similarity:.2f}\n\n"

                # Include the content with reasonable length limits
                if content:
                    max_length = 800 if result_counter <= 3 else 400  # More content for top results
                    formatted_content = content[:max_length] + "..." if len(content) > max_length else content
                    context += f"CONTENT:\n{formatted_content}\n\n"

                # Always add a clear separation between results
                context += "---\n\n"

        # Add a reminder to include URLs in the response when appropriate
        context += "IMPORTANT: When referencing specific information from these results, include the relevant URLs as formatted links using markdown syntax: [link text](URL).\n\n"

        return context

    def get_response(self, query: str) -> str:
        """Get a response from the LLM based on the query and relevant context.

        Args:
            query: The user's query.

        Returns:
            The LLM's response.
        """
        console.print(f"[dim]DEBUG: get_response called with query: '{query}'[/dim]")

        # Clean the query for processing
        clean_query = query.strip().lower()

        # Check for simple greetings first - use exact word matching to avoid false positives
        greeting_patterns = [
            "hi", "hello", "hey", "greetings", "howdy", "hola",
            "how are you", "how's it going", "what's up", "sup",
            "good morning", "good afternoon", "good evening"
        ]

        is_greeting = False
        for greeting in greeting_patterns:
            # Use word boundary matching to avoid matching substrings
            if re.search(r'\b' + greeting + r'\b', clean_query):
                is_greeting = True
                console.print(f"[dim]DEBUG: Detected greeting pattern: '{greeting}'[/dim]")
                break

        # Add the user message to the conversation history
        self.add_user_message(query)

        # Check if this is a follow-up question about something the assistant just mentioned
        is_followup = False
        last_assistant_message = None
        last_user_message = None

        # Get the last few messages to check for follow-up context
        recent_messages = self.conversation_history[-10:] if len(self.conversation_history) > 10 else self.conversation_history

        # Find the last assistant and user messages
        for msg in reversed(recent_messages):
            if msg["role"] == "assistant" and not last_assistant_message:
                last_assistant_message = msg["content"]
            elif msg["role"] == "user" and not last_user_message and msg["content"] != query:
                last_user_message = msg["content"]

            if last_assistant_message and last_user_message:
                break

        # Improved follow-up detection
        if last_assistant_message:
            # Check for common follow-up indicators
            follow_up_indicators = [
                "it", "that", "this", "those", "they", "them", "their", "he", "she",
                "more", "about", "tell me more", "what about", "how about",
                "explain", "elaborate", "why is", "how does", "can you",
                "else", "other", "another", "additional", "further", "anything else",
                "great", "thanks", "thank you", "ok", "okay", "cool", "nice", "good"
            ]

            # Check if the query contains any follow-up indicators
            is_followup = any(indicator in clean_query for indicator in follow_up_indicators)

            # Short queries are likely follow-ups
            if len(clean_query.split()) <= 5:
                is_followup = True

            console.print(f"[dim]DEBUG: Follow-up detection: {is_followup}[/dim]")

        # For greetings, don't do complex processing or context search
        if is_greeting and not is_followup:
            console.print(f"[blue]Detected greeting: '{clean_query}'[/blue]")

            # For greetings, we don't need to search for context
            # Just respond with a friendly greeting
            system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": query}
            ]

            console.print(f"[dim]DEBUG: Sending greeting to LLM with model: {self.model}[/dim]")

            try:
                # Get response from LLM
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.7,
                    **_openai_chat_token_kwargs(self.model, 150),
                )

                response_text = response.choices[0].message.content.strip()
                console.print(f"[dim]DEBUG: Got greeting response: '{response_text[:30]}...'[/dim]")

                # Add the assistant's response to the conversation history
                self.add_assistant_message(response_text)

                return response_text
            except Exception as e:
                console.print(f"[red]Error getting greeting response: {e}[/red]")
                import traceback
                traceback.print_exc()
                response_text = "Hello! How can I help you today?"
                self.add_assistant_message(response_text)
                return response_text

        # Continue with regular processing for non-greeting messages

        # Check for user-specific queries
        user_queries = ["my name", "who am i", "what's my name", "what is my name"]
        is_user_query = any(user_query in clean_query for user_query in user_queries)

        # Check for time-related queries - make this more precise
        time_queries = ["what time", "what is the time", "current time", "tell me the time",
                      "what date", "what is the date", "current date", "tell me the date",
                      "what day is it", "what day of the week", "today's date"]
        # Use more precise matching to avoid false positives
        is_time_query = any(time_query in clean_query for time_query in time_queries) or \
                       (clean_query in ["time", "date", "day", "today"]) or \
                       (clean_query.startswith("what") and clean_query.split()[1:2] == ["time"]) or \
                       (clean_query.startswith("what") and clean_query.split()[1:2] == ["date"])

        # Check for memory-related queries
        memory_queries = ["remember", "said", "told", "mentioned", "earlier", "before", "previous", "last time"]
        preference_queries = ["like", "love", "prefer", "favorite", "enjoy", "hate", "dislike", "my favorite"]

        is_memory_query = any(memory_query in clean_query for memory_query in memory_queries)
        is_preference_query = any(pref_query in clean_query for pref_query in preference_queries)

        # Check for technical patterns like hyphens that might indicate specific terms
        is_technical_pattern = ('-' in clean_query or '_' in clean_query or
                          (len(clean_query.split()) <= 3 and not any(q in clean_query for q in ["what", "how", "why", "when", "who", "which"])))

        # If it's a user-specific query and we have user information
        if is_user_query and self.user_id:
            response_text = f"Your name is {self.user_id}."
            self.add_assistant_message(response_text)
            return response_text

        # If it's a time-related query, provide the current date and time
        if is_time_query:
            now = datetime.datetime.now()
            date_str = now.strftime("%A, %B %d, %Y")
            time_str = now.strftime("%I:%M %p")
            response_text = f"The current date is {date_str} and the time is {time_str}."
            self.add_assistant_message(response_text)
            return response_text

        # Determine if this is likely a query about a technical term or project name
        if is_technical_pattern and not is_greeting:
            console.print(f"[yellow]Detected potential technical term or project name: '{clean_query}'[/yellow]")
            console.print(f"[yellow]Attempting direct keyword search...[/yellow]")

            # Try the direct keyword search first for technical terms
            try:
                # Get site patterns from profile if available
                site_patterns = None
                if self.profile and "site_patterns" in self.profile:
                    site_patterns = self.profile["site_patterns"]
                elif self.profile and "search_settings" in self.profile and "site_patterns" in self.profile["search_settings"]:
                    site_patterns = self.profile["search_settings"]["site_patterns"]

                # Log the site patterns for debugging
                if site_patterns:
                    console.print(f"[blue]Using site patterns from profile: {site_patterns}[/blue]")

                # Perform direct keyword search
                keyword_results = self.crawler.search(
                    query=query,
                    use_embedding=False,  # Use text search for keywords
                    threshold=0.7,
                    limit=self.result_limit,
                    site_id=None  # Search all sites
                )

                if keyword_results:
                    console.print(f"[green]Found {len(keyword_results)} keyword results[/green]")

                    # Mark these as keyword results
                    for result in keyword_results:
                        result["is_keyword_result"] = True

                    # Format the context
                    context_str = self.format_context(keyword_results)

                    # Get response from LLM
                    messages = self._prepare_messages_for_llm(query, context_str, is_followup)
                    response_text = self._get_llm_response(messages)

                    # Add the assistant's response to the conversation history
                    self.add_assistant_message(response_text)

                    return response_text
            except Exception as e:
                console.print(f"[red]Error in keyword search: {e}[/red]")
                import traceback
                traceback.print_exc()
                # Continue with regular search if keyword search fails

        # If this is a follow-up question, try to extract relevant entities from the assistant's last response
        if is_followup and last_assistant_message:
            try:
                # Extract key entities from the last response
                entity_prompt = f"""Extract the most important entities (names, technical terms, concepts) from this text: "{last_assistant_message}"

        Return only the entities as a comma-separated list. Limit to 3-5 most important entities."""

                entity_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": entity_prompt}],
                    temperature=0.3,
                    **_openai_chat_token_kwargs(self.model, 100),
                )

                entities = entity_response.choices[0].message.content.strip()
                console.print(f"[blue]Extracted entities from previous response: {entities}[/blue]")

                # Create an enhanced query combining the original query with the entities
                enhanced_query = f"{query} {entities}"
                console.print(f"[blue]Enhanced query: {enhanced_query}[/blue]")

                # Search with the enhanced query
                results = self.search_for_context(enhanced_query)
            except Exception as e:
                console.print(f"[red]Error enhancing query with entities: {e}[/red]")
                # Fall back to regular search
                results = self.search_for_context(query)
        else:
            # Regular search for non-follow-up questions
            results = self.search_for_context(query)

        # If we still don't have good results for technical terms, try variations
        if is_technical_pattern and (not results or len(results) < 2):
            console.print(f"[yellow]Few or no results for technical term, trying variations...[/yellow]")
            # Try different variations
            variations = [
                query,
                f"what is {query}",
                f"{query} definition",
                f"{query} overview",
                f"{query} features"
            ]

            # Try each variation and collect results
            all_results = []
            for variation in variations:
                var_results = self.search_for_context(variation)
                if var_results:
                    console.print(f"[green]Found {len(var_results)} results for '{variation}'[/green]")
                    # Add this variation as metadata
                    for result in var_results:
                        result["query_variation"] = variation
                    all_results.extend(var_results)

            # If we have results from variations, use those
            if all_results:
                # Deduplicate by URL
                deduplicated = {}
                for result in all_results:
                    url = result.get("url", "")
                    if url and url not in deduplicated:
                        deduplicated[url] = result

                # Sort by similarity
                results = list(deduplicated.values())
                results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

                # Limit to search limit
                results = results[:self.search_limit]
                console.print(f"[green]Found {len(results)} total results after trying variations[/green]")
            else:
                console.print(f"[yellow]No results found for variations, falling back to regular search[/yellow]")
                # If still no results, fall back to the original query
                results = self.search_for_context(query)

        # Format the context
        context = self.format_context(results)

        # Add more detailed logging about search results
        if VERBOSE_OUTPUT:
            result_count = len(results)
            console.print(f"[bold blue]Search returned {result_count} results[/bold blue]")

            # Log the first few results for debugging
            if result_count > 0:
                console.print("[bold blue]Top search results:[/bold blue]")
                for i, result in enumerate(results[:3]):
                    title = result.get("title", "Untitled")
                    url = result.get("url", "No URL")
                    site_name = result.get("site_name", "Unknown site")
                    similarity = result.get("similarity", 0)
                    match_type = result.get("match_type", "semantic")
                    content_preview = result.get("content", "")[:100] + "..." if result.get("content") and len(result.get("content", "")) > 100 else result.get("content", "")
                    console.print(f"[dim blue]Result {i+1}: {title}[/dim blue]")
                    console.print(f"[dim blue]Site: {site_name}[/dim blue]")
                    console.print(f"[dim blue]URL: {url}[/dim blue]")
                    console.print(f"[dim blue]Match type: {match_type}[/dim blue]")
                    console.print(f"[dim blue]Similarity: {similarity:.4f}[/dim blue]")
                    console.print(f"[dim blue]Content preview: {content_preview}[/dim blue]")
                    console.print("---")
            else:
                console.print("[bold red]No search results found![/bold red]")

            # Print context size information
            context_length = len(context.split())
            console.print(f"[dim blue]Search context: {context_length} words[/dim blue]")
            if context_length < 50:
                console.print(f"[dim yellow]WARNING: Search context is very small ({context_length} words). This may affect response quality.[/dim yellow]")

        # Analyze conversation history for relevant information
        conversation_analysis = ""
        if is_memory_query or is_preference_query or "what" in query.lower() or "do i" in query.lower():
            conversation_analysis = self.analyze_conversation_history(query)

        # Get the system prompt from the profile
        system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])

        # Add user information to the system prompt if available
        if self.user_id:
            system_prompt += f"\n\nThe user's name is {self.user_id}."

        # Add current date and time to the system prompt
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        system_prompt += f"\n\nThe current date is {date_str} and the time is {time_str}."

        # Get user preferences from the database
        user_preferences = []
        if self.user_id:
            try:
                # Get preferences from the database with a lower minimum confidence
                db_preferences = self.crawler.db_client.get_user_preferences(
                    user_id=self.user_id,
                    min_confidence=0.65,  # Lowered threshold to capture more preferences
                    active_only=True
                )

                # Format preferences for the system prompt
                for pref in db_preferences:
                    pref_type = pref.get("preference_type", "")
                    pref_value = pref.get("preference_value", "")
                    confidence = pref.get("confidence", 0.0)
                    context = pref.get("context", "")

                    # Update the last_used timestamp for this preference
                    self.crawler.db_client.update_preference_last_used(pref.get("id"))

                    # Add to the list of preferences
                    user_preferences.append({
                        "type": pref_type,
                        "value": pref_value,
                        "confidence": confidence,
                        "context": context
                    })
            except Exception as e:
                console.print(f"[red]Error getting user preferences from database: {e}[/red]")

        # Add user preferences to the system prompt if available
        if user_preferences:
            system_prompt += "\n\nUser Information:"

            # Group preferences by type for better organization
            preference_by_type = {}
            for pref in user_preferences:
                pref_type = pref['type']
                if pref_type not in preference_by_type:
                    preference_by_type[pref_type] = []
                preference_by_type[pref_type].append(pref)

            # Limit the total number of preferences to prevent overwhelming the context
            MAX_PREFERENCES_PER_TYPE = 3
            MAX_TOTAL_PREFERENCES = 8
            total_prefs_added = 0

            # Add preferences by type, limiting the number per type
            for pref_type, prefs in preference_by_type.items():
                # Create a more natural language representation of the preference type
                type_label = pref_type.capitalize()
                if pref_type in ["like", "love"]:
                    system_prompt += f"\n\nThings the user likes:"
                elif pref_type in ["hate", "dislike"]:
                    system_prompt += f"\n\nThings the user dislikes:"
                elif pref_type == "interest":
                    system_prompt += f"\n\nThe user is interested in:"
                elif pref_type == "trait":
                    system_prompt += f"\n\nUser traits:"
                elif pref_type == "background":
                    system_prompt += f"\n\nUser background:"
                else:
                    system_prompt += f"\n\n{type_label}:"

                # Sort by confidence (highest first) and limit per type
                sorted_prefs = sorted(prefs, key=lambda p: p.get('confidence', 0), reverse=True)
                prefs_to_add = sorted_prefs[:MAX_PREFERENCES_PER_TYPE]

                for pref in prefs_to_add:
                    # Create a simple bullet point rather than showing confidence scores
                    system_prompt += f"\n- {pref['value']}"

                    total_prefs_added += 1
                    if total_prefs_added >= MAX_TOTAL_PREFERENCES:
                        break

                if total_prefs_added >= MAX_TOTAL_PREFERENCES:
                    break

            # Add instructions for using preferences
            system_prompt += "\n\nWhen appropriate, reference the user's preferences and background to personalize your responses. Don't force mentioning preferences, but use them to add context and relevance. Balance between addressing their query directly and personalizing based on what you know about them."

        # Create a system message that guides the LLM's behavior
        system_message = f"""You are acting according to this profile: {self.profile_name}

CRITICAL INSTRUCTION: The "DATABASE SEARCH RESULTS" section contains verified information from a database. This is your PRIMARY source of information. Use this information FIRST before relying on other sources, but aim for a conversational, human-like tone in your responses.

{system_prompt}

GUIDELINES FOR RESPONDING:
1. Balance information delivery with conversational tone - be informative but natural
2. For technical terms and project names, always include relevant details from the search results
3. When referencing information from search results, include the full URL as a link: [Title or description](URL)
4. Structure your response with a clear summary first, followed by details
5. If the search included multiple results, synthesize the information rather than listing each source separately

FORMATTING GUIDELINES:
- For technical content or code, use appropriate markdown formatting (```code blocks```)
- Use bullet points or numbered lists for multi-step processes or feature lists
- Bold important terms or concepts using **bold text**
- Include the source URL when providing specific information: [Read more about this](URL)

IMPORTANT: Pay close attention to the conversation history. If the user refers to something they mentioned earlier,
make sure to reference that information in your response. Remember user preferences, likes, dislikes, and any
personal information they've shared during the conversation.

CRITICAL: If the user asks a follow-up question about something you just mentioned in your previous response,
make sure to provide detailed information about that topic. Never claim ignorance about something you just discussed.
Always maintain continuity in the conversation.
"""

        # Create a new list of messages for this specific query
        messages = [
            {"role": "system", "content": system_message},
        ]

        # Add the conversation history (excluding the system message)
        # Use a sliding window approach to avoid token limit issues
        MAX_HISTORY_MESSAGES = 20  # Adjust this value based on your needs

        # Get user and assistant messages, excluding the current query
        history_messages = [
            msg for msg in self.conversation_history
            if msg["role"] != "system" and msg["content"] != query
        ]

        # If we have more messages than the limit, keep only the most recent ones
        if len(history_messages) > MAX_HISTORY_MESSAGES:
            # Always include the first few messages for context
            first_messages = history_messages[:2]
            # And the most recent messages
            recent_messages = history_messages[-(MAX_HISTORY_MESSAGES-2):]
            history_messages = first_messages + recent_messages
            console.print(f"[dim blue]Using {len(history_messages)} messages from conversation history (truncated)[/dim blue]")
        else:
            console.print(f"[dim blue]Using {len(history_messages)} messages from conversation history[/dim blue]")

        # Add the selected history messages
        for message in history_messages:
            messages.append({
                "role": message["role"],
                "content": message["content"]
            })

        # Add the current query
        messages.append({"role": "user", "content": query})

        # If this is a follow-up question, add a special reminder about the previous response
        if is_followup and last_assistant_message:
            messages.append({
                "role": "system",
                "content": f"IMPORTANT: This is a follow-up question about something you mentioned in your previous response. Your previous response was:\n\n{last_assistant_message}\n\nMake sure to provide detailed information about the topic the user is asking about."
            })

        # Add the conversation analysis if available
        if conversation_analysis and conversation_analysis != "No relevant information found.":
            messages.append({
                "role": "system",
                "content": f"Relevant information from conversation history:\n{conversation_analysis}"
            })

        # Add the context from the database search
        messages.append({"role": "system", "content": f"Context from database search:\n{context}"})

        # Get a response from the LLM
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            **_openai_chat_token_kwargs(self.model, 1000),
        )

        # Extract the response text
        response_text = response.choices[0].message.content

        # Add the assistant's response to the conversation history
        self.add_assistant_message(response_text)

        return response_text

    def show_conversation_history(self):
        """Display the conversation history."""
        if not self.conversation_history:
            console.print("[yellow]No conversation history[/yellow]")
            return

        # Create a table for the conversation history
        table = Table(title=f"Conversation History (Session: {self.session_id})")

        table.add_column("Role", style="cyan")
        table.add_column("Content", style="green")
        table.add_column("Timestamp", style="yellow")

        # Add rows for each message
        for message in self.conversation_history:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            timestamp = message.get("timestamp", "")

            # Truncate long messages for display
            if len(content) > 100:
                content = content[:97] + "..."

            table.add_row(
                role,
                content,
                str(timestamp)
            )

        console.print(table)

        # Print information about persistence
        console.print(f"[blue]Conversation is stored with session ID: {self.session_id}[/blue]")
        if self.user_id:
            console.print(f"[blue]User ID: {self.user_id}[/blue]")
        console.print("[blue]To continue this conversation later, use:[/blue]")
        console.print(f"[green]python chat.py --session {self.session_id}{' --user ' + self.user_id if self.user_id else ''}[/green]")

    def show_profiles(self):
        """Show available profiles."""
        table = Table(title="Available Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        table.add_column("Search Sites", style="yellow")

        for name, profile in self.profiles.items():
            # Get the description
            description = profile.get('description', 'No description')

            # Format the search sites
            search_settings = profile.get('search_settings', {})
            search_sites = search_settings.get('sites', [])
            sites_str = ", ".join(search_sites) if search_sites else "All sites"

            table.add_row(
                name,
                description,
                sites_str
            )

        console.print(table)

    def clear_all_conversation_history(self):
        """Clear all conversation history from the database."""
        if not self.crawler:
            console.print("[yellow]No database connection, cannot clear conversation history[/yellow]")
            return

        try:
            if self.crawler.db_client.clear_all_conversation_history():
                console.print("[green]All conversation history has been cleared from the database[/green]")
                # Also clear the in-memory history for the current session
                self.conversation_history = []
                # Add a new system message
                system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])
                if self.user_id:
                    system_prompt += f"\n\nThe user's name is {self.user_id}."
                self.add_system_message(system_prompt)
            else:
                console.print("[red]Failed to clear all conversation history[/red]")
        except Exception as e:
            console.print(f"[red]Error clearing all conversation history: {e}[/red]")

    def chat_loop(self):
        """Run an interactive chat loop."""
        console.print(Panel.fit(
            "[bold cyan]Welcome to the Supa Chat Interface![/bold cyan]\n"
            "Ask questions about the crawled data or use these commands:\n"
            "[bold red]'exit'[/bold red] to quit\n"
            "[bold red]'clear'[/bold red] to clear the current session's conversation history\n"
            "[bold red]'clear all'[/bold red] to clear ALL conversation history from the database\n"
            "[bold red]'history'[/bold red] to view the conversation history\n"
            "[bold red]'profile <name>'[/bold red] to change the chat profile\n"
            "[bold red]'profiles'[/bold red] to list available profiles",
            border_style="blue"
        ))

        # Show session information
        if self.user_id:
            console.print(f"[bold green]Session ID:[/bold green] [blue]{self.session_id}[/blue] - [bold green]User:[/bold green] [blue]{self.user_id}[/blue]")
            console.print("[green]Your conversation history will be saved and can be continued later.[/green]")
        else:
            console.print(f"[bold green]Session ID:[/bold green] [blue]{self.session_id}[/blue]")
            console.print("[yellow]To save your name for future sessions, use --user parameter (e.g., python chat.py --user YourName)[/yellow]")

        try:
            while True:
                try:
                    # Get user input with a timeout
                    query = Prompt.ask("\n[bold green]You[/bold green]")

                    # Skip empty queries
                    if not query.strip():
                        console.print("[yellow]Please enter a question or command.[/yellow]")
                        continue

                    # Check for exit commands
                    if query.lower() in ["exit", "quit", "bye", "goodbye", "q"]:
                        console.print("[green]Exiting chat. Goodbye![/green]")
                        break

                    # Check for clear command
                    if query.lower() == "clear":
                        self.clear_conversation_history()
                        console.print("[green]Conversation history cleared for this session[/green]")
                        continue

                    # Check for clear all command
                    if query.lower() == "clear all":
                        if Confirm.ask("[bold red]Are you sure you want to clear ALL conversation history?[/bold red]"):
                            self.clear_all_conversation_history()
                        console.print("[green]All conversation history cleared[/green]")
                        continue

                    # Check for history command
                    if query.lower() == "history":
                        self.show_conversation_history()
                        continue

                    # Check for profiles command
                    if query.lower() == "profiles":
                        self.show_profiles()
                        continue

                    # Check for profile command
                    if query.lower().startswith("profile "):
                        profile_name = query.split(" ", 1)[1].strip()
                        self.change_profile(profile_name)
                        continue

                    # Check for preferences command
                    if query.lower() == "preferences":
                        if not self.user_id:
                            console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                            console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                        else:
                            # Get preferences from the database
                            try:
                                preferences = self.crawler.db_client.get_user_preferences(
                                    user_id=self.user_id,
                                    min_confidence=0.0,
                                    active_only=True
                                )

                                if not preferences:
                                    console.print("[yellow]No preferences found for this user.[/yellow]")
                                else:
                                    # Create a table for the preferences
                                    table = Table(title=f"Preferences for {self.user_id}")
                                    table.add_column("ID", style="cyan")
                                    table.add_column("Type", style="green")
                                    table.add_column("Value", style="blue")
                                    table.add_column("Confidence", style="yellow")
                                    table.add_column("Context", style="magenta")
                                    table.add_column("Last Used", style="dim")

                                    for pref in preferences:
                                        table.add_row(
                                            str(pref.get("id", "")),
                                            pref.get("preference_type", ""),
                                            pref.get("preference_value", ""),
                                            f"{pref.get('confidence', 0.0):.2f}",
                                            pref.get("context", "")[:50] + ("..." if len(pref.get("context", "")) > 50 else ""),
                                            str(pref.get("last_used", ""))
                                        )

                                    console.print(table)
                            except Exception as e:
                                console.print(f"[red]Error getting preferences: {e}[/red]")
                        continue

                    # Check for add preference command
                    if query.lower().startswith("add preference "):
                        if not self.user_id:
                            console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                            console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                        else:
                            # Parse the preference
                            try:
                                # Format: add preference <type> <value> [confidence]
                                parts = query[14:].strip().split(" ", 2)
                                if len(parts) < 2:
                                    console.print("[yellow]Invalid format. Use: add preference <type> <value> [confidence][/yellow]")
                                    console.print("[yellow]Example: add preference like Python 0.9[/yellow]")
                                else:
                                    pref_type = parts[0]

                                    # Check if confidence is provided
                                    if len(parts) == 3 and parts[2].replace(".", "", 1).isdigit():
                                        pref_value = parts[1]
                                        confidence = float(parts[2])
                                    else:
                                        # If no confidence or not a valid number, combine the rest as the value
                                        pref_value = " ".join(parts[1:])
                                        confidence = 0.9  # Default confidence

                                    # Add the preference
                                    pref_id = self.crawler.db_client.save_user_preference(
                                        user_id=self.user_id,
                                        preference_type=pref_type,
                                        preference_value=pref_value,
                                        context="Manually added via CLI",
                                        confidence=confidence,
                                        source_session=self.session_id,
                                        metadata={"source": "cli_manual_entry"}
                                    )

                                    if pref_id > 0:
                                        console.print(f"[green]Preference added with ID: {pref_id}[/green]")
                                    else:
                                        console.print("[red]Failed to add preference[/red]")
                            except Exception as e:
                                console.print(f"[red]Error adding preference: {e}[/red]")
                        continue

                    # Check for delete preference command
                    if query.lower().startswith("delete preference "):
                        if not self.user_id:
                            console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                            console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                        else:
                            # Parse the preference ID
                            try:
                                pref_id = int(query[17:].strip())

                                # Delete the preference
                                success = self.crawler.db_client.delete_user_preference(pref_id)

                                if success:
                                    console.print(f"[green]Preference with ID {pref_id} deleted[/green]")
                                else:
                                    console.print(f"[red]Failed to delete preference with ID {pref_id}[/red]")
                            except ValueError:
                                console.print("[yellow]Invalid preference ID. Use: delete preference <id>[/yellow]")
                            except Exception as e:
                                console.print(f"[red]Error deleting preference: {e}[/red]")
                        continue

                    # Check for clear preferences command
                    if query.lower() == "clear preferences":
                        if not self.user_id:
                            console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                            console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                        else:
                            if Confirm.ask("[bold red]Are you sure you want to clear ALL preferences for this user?[/bold red]"):
                                try:
                                    success = self.crawler.db_client.clear_user_preferences(self.user_id)

                                    if success:
                                        console.print(f"[green]All preferences cleared for user {self.user_id}[/green]")
                                    else:
                                        console.print("[red]Failed to clear preferences[/red]")
                                except Exception as e:
                                    console.print(f"[red]Error clearing preferences: {e}[/red]")
                        continue

                    # Check for help command
                    if query.lower() in ["help", "?"]:
                        console.print("\n[bold]Available Commands:[/bold]")
                        console.print("  [cyan]exit, quit, bye, goodbye, q[/cyan] - Exit the chat")
                        console.print("  [cyan]clear[/cyan] - Clear conversation history for this session")
                        console.print("  [cyan]clear all[/cyan] - Clear ALL conversation history")
                        console.print("  [cyan]history[/cyan] - View conversation history")
                        console.print("  [cyan]profiles[/cyan] - List available profiles")
                        console.print("  [cyan]profile <name>[/cyan] - Change to a different profile")
                        console.print("  [cyan]preferences[/cyan] - List your preferences")
                        console.print("  [cyan]add preference <type> <value> [confidence][/cyan] - Add a new preference")
                        console.print("  [cyan]delete preference <id>[/cyan] - Delete a preference")
                        console.print("  [cyan]clear preferences[/cyan] - Clear all your preferences")
                        console.print("  [cyan]help, ?[/cyan] - Show this help message")
                        continue

                    # Show thinking indicator
                    with console.status("[bold blue]Thinking...[/bold blue]", spinner="dots"):
                        # Get a response with a timeout
                        try:
                            response = self.get_response(query)
                            console.print(f"[dim]Debug: Got response of length {len(response)}[/dim]")
                        except Exception as e:
                            console.print(f"[red]Error getting response: {e}[/red]")
                            import traceback
                            traceback.print_exc()
                            response = "I'm sorry, I encountered an error while processing your request. Please try again."

                    # Print the response
                    console.print("\n[bold purple]Assistant[/bold purple]")
                    console.print(Panel(Markdown(response), border_style="purple"))

                except KeyboardInterrupt:
                    # Handle Ctrl+C gracefully
                    console.print("\n[yellow]Interrupted by user. Type 'exit' to quit or continue with your next question.[/yellow]")
                    continue
                except Exception as e:
                    console.print(f"\n[red]An error occurred: {e}[/red]")
                    console.print("[yellow]Please try again or type 'exit' to quit.[/yellow]")
                    continue

        except KeyboardInterrupt:
            # Final exit on Ctrl+C
            console.print("\n[bold cyan]Goodbye![/bold cyan]")
        except Exception as e:
            console.print(f"\n[red]Fatal error: {e}[/red]")
        finally:
            # Make sure we always exit cleanly
            console.print("[dim]Chat session ended.[/dim]")

    def analyze_conversation_history(self, query: str) -> str:
        """Analyze the conversation history using an LLM to extract relevant information.

        Args:
            query: The user's current query.

        Returns:
            A summary of relevant information from the conversation history.
        """
        # If there's no conversation history, return an empty string
        if not self.conversation_history or len(self.conversation_history) < 3:
            return ""

        console.print("[blue]Analyzing conversation history with LLM...[/blue]")

        try:
            # Extract preferences from metadata
            preferences = []
            for message in self.conversation_history:
                if message.get("metadata") and "preference" in message.get("metadata", {}):
                    preference = message["metadata"]["preference"]
                    if preference not in preferences:
                        preferences.append(preference)

            # Format the conversation history for the LLM
            history_text = ""

            # Limit the amount of history to analyze to avoid token limits
            max_history_messages = 10
            history_to_analyze = self.conversation_history[-max_history_messages:] if len(self.conversation_history) > max_history_messages else self.conversation_history

            for message in history_to_analyze:
                if message["role"] != "system":  # Skip system messages
                    role = "User" if message["role"] == "user" else "Assistant"
                    # Truncate very long messages
                    content = message["content"]
                    if len(content) > 500:
                        content = content[:500] + "..."
                    history_text += f"{role}: {content}\n\n"

            # Create a prompt for the LLM
            prompt = f"""Analyze the following conversation history and extract relevant information that would help answer the user's current query: "{query}"

Focus on:
1. User preferences (likes, dislikes, favorites)
2. Personal information the user has shared
3. Previous topics discussed that relate to the current query
4. Any commitments or promises made by the assistant

"""

            # Add extracted preferences if available
            if preferences:
                prompt += "Known user preferences from previous messages:\n"
                for pref in preferences:
                    prompt += f"- {pref}\n"
                prompt += "\n"

            prompt += f"""Conversation History:
{history_text}

Provide a concise summary of ONLY the information that is directly relevant to the current query.
Focus especially on preferences and personal information that would help answer the query.
If there is no relevant information, respond with "No relevant information found."
"""

            # Use a smaller, faster model for this analysis
            analysis_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")

            # Get a response from the LLM with a timeout
            response = self.client.chat.completions.create(
                model=analysis_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                **_openai_chat_token_kwargs(analysis_model, 500),
                timeout=10  # 10 second timeout
            )

            # Extract the response text
            analysis = response.choices[0].message.content

            if analysis and analysis != "No relevant information found.":
                console.print(f"[blue]Found relevant information in conversation history[/blue]")

            return analysis
        except Exception as e:
            console.print(f"[red]Error analyzing conversation history: {e}[/red]")
            return "Error analyzing conversation history. Proceeding without historical context."

    def set_profile(self, profile_name: str):
        """Set the profile for the chat interface.

        Args:
            profile_name: The name of the profile to use.
        """
        if profile_name not in self.profiles:
            console.print(f"[yellow]Warning: Profile '{profile_name}' not found, using default profile[/yellow]")
            profile_name = "default"

        self.profile_name = profile_name
        self.profile = self.profiles[profile_name]

        # Update search settings from the profile
        self.search_sites = self.profile.get('search_settings', {}).get('sites', [])
        self.search_threshold = self.profile.get('search_settings', {}).get('threshold', self.similarity_threshold)
        self.search_limit = self.profile.get('search_settings', {}).get('limit', self.result_limit)

        console.print(f"[green]Using profile: {self.profile['name']} - {self.profile['description']}[/green]")

        # If we have a conversation history, add a new system message with the profile's system prompt
        if self.conversation_history:
            # Add user information to the system prompt if available
            system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])
            if self.user_id:
                system_prompt += f"\n\nThe user's name is {self.user_id}."

            # Add a new system message
            self.add_system_message(system_prompt)

    @property
    def current_profile(self):
        """Get the current profile name.

        Returns:
            The name of the current profile.
        """
        return self.profile_name

    def _prepare_messages_for_llm(self, query: str, context_str: str, is_followup: bool = False) -> List[Dict[str, str]]:
        """Prepare messages for the LLM.

        Args:
            query: The user's query.
            context_str: The context string from search results.
            is_followup: Whether this is a follow-up question.

        Returns:
            A list of messages for the LLM.
        """
        # Get the system prompt from the profile
        system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])

        # Add user information to the system prompt if available
        if self.user_id:
            system_prompt += f"\n\nThe user's name is {self.user_id}."

        # Add current date and time to the system prompt
        now = datetime.datetime.now()
        date_str = now.strftime("%A, %B %d, %Y")
        time_str = now.strftime("%I:%M %p")
        system_prompt += f"\n\nThe current date is {date_str} and the time is {time_str}."

        # Create a system message that guides the LLM's behavior
        system_message = f"""You are acting according to this profile: {self.profile_name}

{system_prompt}

When answering, use the provided context and conversation history.
If the answer is in the context, respond based on that information.
If the answer is not in the context but you can infer it from the conversation history, use that information.
If the answer is not in either, acknowledge that you don't have specific information about that topic,
but you can provide general information if relevant.

IMPORTANT: Pay close attention to the conversation history. If the user refers to something they mentioned earlier,
make sure to reference that information in your response. Remember user preferences, likes, dislikes, and any
personal information they've shared during the conversation.

CRITICAL: If the user asks a follow-up question about something you just mentioned in your previous response,
make sure to provide detailed information about that topic. Never claim ignorance about something you just discussed.
Always maintain continuity in the conversation.

When presenting URLs to users, make sure to remove any '#chunk-X' fragments from the URLs to make them cleaner.
For example, change 'https://example.com/page/#chunk-0' to 'https://example.com/page/'.
"""

        # Create a new list of messages for this specific query
        messages = [
            {"role": "system", "content": system_message},
        ]

        # Add the conversation history (excluding the system message)
        # Use a sliding window approach to avoid token limit issues
        MAX_HISTORY_MESSAGES = 20  # Adjust this value based on your needs

        # Get user and assistant messages, excluding the current query
        history_messages = [
            msg for msg in self.conversation_history
            if msg["role"] != "system" and msg["content"] != query
        ]

        # If we have more messages than the limit, keep only the most recent ones
        if len(history_messages) > MAX_HISTORY_MESSAGES:
            # Always include the first few messages for context
            first_messages = history_messages[:2]
            # And the most recent messages
            recent_messages = history_messages[-(MAX_HISTORY_MESSAGES-2):]
            history_messages = first_messages + recent_messages
            console.print(f"[dim blue]Using {len(history_messages)} messages from conversation history (truncated)[/dim blue]")
        else:
            console.print(f"[dim blue]Using {len(history_messages)} messages from conversation history[/dim blue]")

        # Add the selected history messages
        for message in history_messages:
            messages.append({
                "role": message["role"],
                "content": message["content"]
            })

        # Add the current query
        messages.append({"role": "user", "content": query})

        # If this is a follow-up question, add a special reminder about the previous response
        last_assistant_message = None
        if is_followup and len(history_messages) > 0:
            for msg in reversed(history_messages):
                if msg["role"] == "assistant":
                    last_assistant_message = msg["content"]
                    break

            if last_assistant_message:
                messages.append({
                    "role": "system",
                    "content": f"IMPORTANT: This is a follow-up question about something you mentioned in your previous response. Your previous response was:\n\n{last_assistant_message}\n\nMake sure to provide detailed information about the topic the user is asking about."
                })

        # Add the context from the database search
        messages.append({"role": "system", "content": f"DATABASE SEARCH RESULTS:\n{context_str}"})

        return messages

    def _get_llm_response(self, messages: List[Dict[str, str]]) -> str:
        """Get a response from the LLM.

        Args:
            messages: The messages to send to the LLM.

        Returns:
            The LLM's response.
        """
        console.print(f"[dim]DEBUG: _get_llm_response called with {len(messages)} messages[/dim]")

        try:
            # Get a response from the LLM
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                **_openai_chat_token_kwargs(self.model, 1000),
            )

            # Extract the response text
            response_text = response.choices[0].message.content
            console.print(f"[dim]DEBUG: Got LLM response: '{response_text[:30]}...'[/dim]")

            return response_text
        except Exception as e:
            console.print(f"[red]Error getting LLM response: {e}[/red]")
            import traceback
            traceback.print_exc()

            # Provide a fallback response
            return "I'm sorry, I encountered an error while processing your request. Please try again or check your API key configuration."

def main():
    """Main function for the chat interface."""
    parser = argparse.ArgumentParser(description="Chat with crawled data using an LLM")
    parser.add_argument("--model", help="Model to use for chat")
    parser.add_argument("--limit", type=int, help="Maximum number of results")
    parser.add_argument("--threshold", type=float, help="Similarity threshold for vector search")
    parser.add_argument("--session", help="Session ID for the conversation")
    parser.add_argument("--user", help="User ID for the conversation")
    parser.add_argument("--profile", help="Chat profile to use")
    parser.add_argument("--profiles-dir", help="Directory containing profile YAML files")
    parser.add_argument("--new-session", action="store_true", help="Start a new session (ignore saved session ID)")
    parser.add_argument("--verbose", action="store_true", help="Show verbose debug output")
    parser.add_argument("--debug", action="store_true", help="Show extra debug information")
    args = parser.parse_args()

    # If new-session is specified, ignore any saved session ID
    session_id = None if args.new_session else args.session

    # Get verbose flag from .env if not provided in args
    verbose = args.verbose or args.debug
    if not verbose and os.getenv("CHAT_VERBOSE", "").lower() == "true":
        verbose = True

    # Set global verbose flag
    global VERBOSE_OUTPUT
    VERBOSE_OUTPUT = verbose

    try:
        # Create the chat bot
        chat_bot = ChatBot(
            model=args.model,
            result_limit=args.limit,
            similarity_threshold=args.threshold,
            session_id=session_id,
            user_id=args.user,
            profile=args.profile,
            profiles_dir=args.profiles_dir,
            verbose=verbose
        )

        # Print welcome message
        console.print(Panel.fit(
            "[bold green]Welcome to the Supa Chat Interface![/bold green]\n"
            "Ask questions about the crawled data or use these commands:\n"
                "[bold red]'exit'[/bold red] to quit\n"
                "[bold red]'clear'[/bold red] to clear the current session's conversation history\n"
                "[bold red]'clear all'[/bold red] to clear ALL conversation history from the database\n"
                "[bold red]'history'[/bold red] to view the conversation history\n"
                "[bold red]'profile <name>'[/bold red] to change the chat profile\n"
                "[bold red]'profiles'[/bold red] to list available profiles",
                border_style="blue"
        ))

        # Print session ID
        console.print(f"Session ID: {chat_bot.session_id}")

        # Print user ID or instructions to set one
        if chat_bot.user_id:
            console.print(f"User: {chat_bot.user_id}")
        else:
            console.print("To save your name for future sessions, use --user parameter (e.g., python chat.py --user YourName)")

        # Start the chat loop
        try:
            while True:
                # Get user input
                user_input = Prompt.ask("\nYou")

                # Skip empty queries
                if not user_input.strip():
                    console.print("[yellow]Please enter a question or command.[/yellow]")
                    continue

                # Check for exit commands
                if user_input.lower() in ["exit", "quit", "bye", "goodbye", "q"]:
                    console.print("[green]Exiting chat. Goodbye![/green]")
                    break

                # Check for clear command
                if user_input.lower() == "clear":
                    chat_bot.clear_conversation_history()
                    console.print("[green]Conversation history cleared for this session[/green]")
                    continue

                # Check for clear all command
                if user_input.lower() == "clear all":
                    if Confirm.ask("[bold red]Are you sure you want to clear ALL conversation history?[/bold red]"):
                        chat_bot.clear_all_conversation_history()
                        console.print("[green]All conversation history cleared[/green]")
                    continue

                # Check for history command
                if user_input.lower() == "history":
                    chat_bot.show_conversation_history()
                    continue

                # Check for profiles command
                if user_input.lower() == "profiles":
                    chat_bot.show_profiles()
                    continue

                # Check for profile command
                if user_input.lower().startswith("profile "):
                    profile_name = user_input.split(" ", 1)[1].strip()
                    chat_bot.change_profile(profile_name)
                    continue

                # Check for preferences command
                if user_input.lower() == "preferences":
                    if not chat_bot.user_id:
                        console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                        console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                    else:
                        # Get preferences from the database
                        try:
                            preferences = chat_bot.crawler.db_client.get_user_preferences(
                                user_id=chat_bot.user_id,
                                min_confidence=0.0,
                                active_only=True
                            )

                            if not preferences:
                                console.print("[yellow]No preferences found for this user.[/yellow]")
                            else:
                                # Create a table for the preferences
                                table = Table(title=f"Preferences for {chat_bot.user_id}")
                                table.add_column("ID", style="cyan")
                                table.add_column("Type", style="green")
                                table.add_column("Value", style="blue")
                                table.add_column("Confidence", style="yellow")
                                table.add_column("Context", style="magenta")
                                table.add_column("Last Used", style="dim")

                                for pref in preferences:
                                    table.add_row(
                                        str(pref.get("id", "")),
                                        pref.get("preference_type", ""),
                                        pref.get("preference_value", ""),
                                        f"{pref.get('confidence', 0.0):.2f}",
                                        pref.get("context", "")[:50] + ("..." if len(pref.get("context", "")) > 50 else ""),
                                        str(pref.get("last_used", ""))
                                    )

                                console.print(table)
                        except Exception as e:
                            console.print(f"[red]Error getting preferences: {e}[/red]")
                    continue

                # Check for add preference command
                if user_input.lower().startswith("add preference "):
                    if not chat_bot.user_id:
                        console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                        console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                    else:
                        # Parse the preference
                        try:
                            # Format: add preference <type> <value> [confidence]
                            parts = user_input[14:].strip().split(" ", 2)
                            if len(parts) < 2:
                                console.print("[yellow]Invalid format. Use: add preference <type> <value> [confidence][/yellow]")
                                console.print("[yellow]Example: add preference like Python 0.9[/yellow]")
                            else:
                                pref_type = parts[0]

                                # Check if confidence is provided
                                if len(parts) == 3 and parts[2].replace(".", "", 1).isdigit():
                                    pref_value = parts[1]
                                    confidence = float(parts[2])
                                else:
                                    # If no confidence or not a valid number, combine the rest as the value
                                    pref_value = " ".join(parts[1:])
                                    confidence = 0.9  # Default confidence

                                # Add the preference
                                pref_id = chat_bot.crawler.db_client.save_user_preference(
                                    user_id=chat_bot.user_id,
                                    preference_type=pref_type,
                                    preference_value=pref_value,
                                    context="Manually added via CLI",
                                    confidence=confidence,
                                    source_session=chat_bot.session_id,
                                    metadata={"source": "cli_manual_entry"}
                                )

                                if pref_id > 0:
                                    console.print(f"[green]Preference added with ID: {pref_id}[/green]")
                                else:
                                    console.print("[red]Failed to add preference[/red]")
                        except Exception as e:
                            console.print(f"[red]Error adding preference: {e}[/red]")
                    continue

                # Check for delete preference command
                if user_input.lower().startswith("delete preference "):
                    if not chat_bot.user_id:
                        console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                        console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                    else:
                        # Parse the preference ID
                        try:
                            pref_id = int(user_input[17:].strip())

                            # Delete the preference
                            success = chat_bot.crawler.db_client.delete_user_preference(pref_id)

                            if success:
                                console.print(f"[green]Preference with ID {pref_id} deleted[/green]")
                            else:
                                console.print(f"[red]Failed to delete preference with ID {pref_id}[/red]")
                        except ValueError:
                            console.print("[yellow]Invalid preference ID. Use: delete preference <id>[/yellow]")
                        except Exception as e:
                            console.print(f"[red]Error deleting preference: {e}[/red]")
                    continue

                # Check for clear preferences command
                if user_input.lower() == "clear preferences":
                    if not chat_bot.user_id:
                        console.print("[yellow]No user ID provided. Preferences are only stored for identified users.[/yellow]")
                        console.print("[yellow]Restart with --user <name> to use preferences.[/yellow]")
                    else:
                        if Confirm.ask("[bold red]Are you sure you want to clear ALL preferences for this user?[/bold red]"):
                            try:
                                success = chat_bot.crawler.db_client.clear_user_preferences(chat_bot.user_id)

                                if success:
                                    console.print(f"[green]All preferences cleared for user {chat_bot.user_id}[/green]")
                                else:
                                    console.print("[red]Failed to clear preferences[/red]")
                            except Exception as e:
                                console.print(f"[red]Error clearing preferences: {e}[/red]")
                    continue

                # Check for help command
                if user_input.lower() in ["help", "?"]:
                    console.print("\n[bold]Available Commands:[/bold]")
                    console.print("  [cyan]exit, quit, bye, goodbye, q[/cyan] - Exit the chat")
                    console.print("  [cyan]clear[/cyan] - Clear conversation history for this session")
                    console.print("  [cyan]clear all[/cyan] - Clear ALL conversation history")
                    console.print("  [cyan]history[/cyan] - View conversation history")
                    console.print("  [cyan]profiles[/cyan] - List available profiles")
                    console.print("  [cyan]profile <name>[/cyan] - Change to a different profile")
                    console.print("  [cyan]preferences[/cyan] - List your preferences")
                    console.print("  [cyan]add preference <type> <value> [confidence][/cyan] - Add a new preference")
                    console.print("  [cyan]delete preference <id>[/cyan] - Delete a preference")
                    console.print("  [cyan]clear preferences[/cyan] - Clear all your preferences")
                    console.print("  [cyan]help, ?[/cyan] - Show this help message")
                    continue

                # Process the user input
                console.print("Searching all sites...")

                # Show a spinner while processing
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]Thinking...[/bold blue]"),
                    transient=True,
                ) as progress:
                    progress.add_task("thinking", total=None)
                    try:
                        if args.debug:
                            console.print(f"[dim]DEBUG: Sending query to get_response: '{user_input}'[/dim]")
                        response = chat_bot.get_response(user_input)
                        if args.debug:
                            console.print(f"[dim]DEBUG: Got response of length {len(response)}[/dim]")
                    except Exception as e:
                        console.print(f"[red]Error getting response: {e}[/red]")
                        if args.debug:
                            import traceback
                            traceback.print_exc()
                        response = "I'm sorry, I encountered an error while processing your request. Please try again."

                # Print the response
                console.print("\nAssistant", style="bold")
                console.print(Panel(Markdown(response), border_style="green"))

        except KeyboardInterrupt:
            # Handle Ctrl+C gracefully
            console.print("\n[yellow]Interrupted by user. Type 'exit' to quit or continue with your next question.[/yellow]")
    except KeyboardInterrupt:
        console.print("\n[yellow]Chat session interrupted[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        if args.debug:
            import traceback
            traceback.print_exc()

    console.print("[green]Chat session ended[/green]")

if __name__ == "__main__":
    main()
