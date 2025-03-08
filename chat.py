"""
Chat interface for interacting with crawled data using an LLM.
"""

import os
import argparse
import uuid
import json
import yaml
import glob
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from openai import OpenAI
from crawler import WebCrawler
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.prompt import Prompt
from rich.table import Table
import datetime

# Create a rich console
console = Console()

# Load environment variables
load_dotenv()

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
CHAT_PROFILES = load_profiles_from_directory()

class ChatBot:
    """Chat interface for interacting with crawled data using an LLM."""
    
    def __init__(self, model: str = None, result_limit: int = None, similarity_threshold: float = None, 
                session_id: str = None, user_id: str = None, profile: str = None):
        """Initialize the chat interface.
        
        Args:
            model: OpenAI model to use.
            result_limit: Maximum number of results to return.
            similarity_threshold: Similarity threshold for vector search.
            session_id: Session ID for the conversation.
            user_id: User ID for the conversation.
            profile: Chat profile to use.
        """
        # Load environment variables
        load_dotenv()
        
        # Set up the OpenAI client
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Set up the model
        self.model = model or os.getenv("CHAT_MODEL", "gpt-4o")
        
        # Set up the result limit
        self.result_limit = result_limit or int(os.getenv("CHAT_RESULT_LIMIT", "5"))
        
        # Set up the similarity threshold
        self.similarity_threshold = similarity_threshold or float(os.getenv("CHAT_SIMILARITY_THRESHOLD", "0.5"))
        
        # Set up the session ID
        self.session_id = session_id or os.getenv("CHAT_SESSION_ID") or str(uuid.uuid4())
        
        # Set up the user ID
        self.user_id = user_id or os.getenv("CHAT_USER_ID")
        if self.user_id:
            console.print(f"[bold blue]User ID:[/bold blue] [green]{self.user_id}[/green]")
        
        # Set up the profile
        self.profile_name = profile or os.getenv("CHAT_PROFILE", "default")
        if self.profile_name not in CHAT_PROFILES:
            console.print(f"[yellow]Warning: Profile '{self.profile_name}' not found, using default profile[/yellow]")
            self.profile_name = "default"
        
        self.profile = CHAT_PROFILES[self.profile_name]
        
        # Get search settings from the profile
        search_settings = self.profile.get('search_settings', {})
        self.search_sites = search_settings.get('sites', [])
        
        # Override result limit and similarity threshold if specified in the profile
        if 'limit' in search_settings:
            self.result_limit = search_settings['limit']
        if 'threshold' in search_settings:
            self.similarity_threshold = search_settings['threshold']
        
        # Print the current profile and settings
        console.print(f"[bold green]Using profile:[/bold green] [blue]{self.profile_name}[/blue] - {self.profile.get('description', '')}")
        console.print(f"[bold blue]Using chat model:[/bold blue] [green]{self.model}[/green]")
        console.print(f"[bold blue]Result limit:[/bold blue] [green]{self.result_limit}[/green]")
        console.print(f"[bold blue]Similarity threshold:[/bold blue] [green]{self.similarity_threshold}[/green]")
        if self.search_sites:
            console.print(f"[bold blue]Filtering sites:[/bold blue] [green]{', '.join(self.search_sites)}[/green]")
        
        # Set up the crawler
        try:
            self.crawler = WebCrawler()
            
            # Set up the conversation history table
            self.crawler.db_client.setup_conversation_history_table()
        except Exception as e:
            console.print(f"[red]Error initializing crawler: {e}[/red]")
            console.print("[yellow]Running in chat-only mode (no database access)[/yellow]")
            self.crawler = None
        
        # Set up the conversation history
        self.conversation_history = []
        
        # Load the conversation history
        self.load_conversation_history()
        
        # Add a system message with the profile's system prompt
        if not self.conversation_history:
            # Add user information to the system prompt if available
            system_prompt = self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt'])
            if self.user_id:
                system_prompt += f"\n\nThe user's name is {self.user_id}."
            
            self.add_system_message(system_prompt)
    
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
        
        # Check for preference keywords
        preference_keywords = ["like", "love", "prefer", "favorite", "enjoy", "hate", "dislike"]
        has_preference = any(keyword in content.lower() for keyword in preference_keywords)
        
        # If the message might contain a preference, use the LLM to extract it properly
        if has_preference and len(self.conversation_history) >= 2:
            try:
                # Create a prompt for the LLM to extract preferences
                prompt = f"""Extract any clear user preference from this message: "{content}"

If the user expresses a preference (like, love, prefer, favorite, enjoy, hate, dislike), 
extract it in the format: "ACTION OBJECT" (e.g., "like corvettes", "hate brussels sprouts")

Only extract clear, specific preferences. If there's no clear preference, respond with "NONE".
Keep it concise (2-4 words) and focus on the main preference only.
"""
                
                # Use a smaller model for this extraction
                extraction_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
                
                response = self.client.chat.completions.create(
                    model=extraction_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                    max_tokens=50
                )
                
                # Extract the preference
                preference = response.choices[0].message.content.strip()
                
                # Only save if it's a valid preference
                if preference and preference != "NONE":
                    metadata["preference"] = preference
                    console.print(f"[dim blue]Saved preference: {preference}[/dim blue]")
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
        if profile_name not in CHAT_PROFILES:
            console.print(f"[yellow]Warning: Profile '{profile_name}' not found, using default profile[/yellow]")
            profile_name = "default"
        
        self.profile_name = profile_name
        self.profile = CHAT_PROFILES[profile_name]
        
        # Update settings from profile
        search_settings = self.profile.get('search_settings', {})
        self.result_limit = search_settings.get('limit', 5)
        self.similarity_threshold = search_settings.get('threshold', 0.5)
        self.search_sites = search_settings.get('sites', [])
        
        # Add a system message with the new profile
        self.add_system_message(self.profile.get('system_prompt', DEFAULT_PROFILES['default']['system_prompt']))
        
        console.print(f"[bold green]Changed profile to:[/bold green] [blue]{profile_name}[/blue] - {self.profile.get('description', '')}")
        if self.search_sites:
            console.print(f"[bold blue]Filtering sites:[/bold blue] [green]{', '.join(self.search_sites)}[/green]")
    
    def search_for_context(self, query: str) -> List[Dict[str, Any]]:
        """Search for relevant context based on the query.
        
        Args:
            query: The user's query.
            
        Returns:
            A list of relevant documents.
        """
        # If the crawler is not available, return an empty list
        if not self.crawler:
            console.print("[yellow]No database connection, search functionality is disabled[/yellow]")
            return []
        
        # Use the LLM to understand the query intent
        try:
            # Only use this for more complex queries
            if len(query.split()) > 3 and any(word in query.lower() for word in ["best", "top", "recommend", "favorite", "good", "great", "url", "link", "site"]):
                console.print("[blue]Analyzing query intent with LLM...[/blue]")
                
                # Create a prompt for the LLM
                prompt = f"""Analyze this search query and determine the best search strategy:

Query: "{query}"

Choose ONE of these search strategies:
1. REGULAR_SEARCH - Standard semantic search for information
2. URL_SEARCH - The user is specifically asking for URLs or links
3. BEST_CONTENT - The user is asking for the best/top/recommended content

Respond with ONLY the strategy name (e.g., "REGULAR_SEARCH").
"""
                
                # Use a smaller model for this analysis
                analysis_model = os.getenv("CHAT_MODEL", "gpt-4o-mini")
                
                response = self.client.chat.completions.create(
                    model=analysis_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=20
                )
                
                # Extract the strategy
                strategy = response.choices[0].message.content.strip()
                console.print(f"[blue]Query intent: {strategy}[/blue]")
            else:
                # For simple queries, use regular search
                strategy = "REGULAR_SEARCH"
        except Exception as e:
            console.print(f"[red]Error analyzing query intent: {e}[/red]")
            strategy = "REGULAR_SEARCH"
        
        # Execute the appropriate search strategy
        if strategy == "URL_SEARCH":
            return self._search_for_urls(query)
        elif strategy == "BEST_CONTENT":
            return self._search_for_best_content(query)
        else:  # REGULAR_SEARCH
            return self._regular_search(query)
    
    def _search_for_urls(self, query: str) -> List[Dict[str, Any]]:
        """Search for URLs based on the query.
        
        Args:
            query: The user's query.
            
        Returns:
            A list of URL results.
        """
        console.print(f"[blue]URL query detected, searching for URLs...[/blue]")
        
        all_urls = []
        
        # If we have specific sites in the profile, search those
        if self.search_sites:
            for site_pattern in self.search_sites:
                try:
                    urls = self.crawler.db_client.get_urls_by_site_name(site_pattern, limit=self.result_limit)
                    all_urls.extend(urls)
                except Exception as e:
                    console.print(f"[red]Error getting URLs for site pattern '{site_pattern}': {e}[/red]")
        else:
            # Get URLs from all sites
            try:
                all_sites = self.crawler.db_client.get_all_sites()
                for site in all_sites:
                    urls = self.crawler.db_client.get_urls_by_site_name(site["name"], limit=5)
                    all_urls.extend(urls)
            except Exception as e:
                console.print(f"[red]Error getting URLs from all sites: {e}[/red]")
        
        # Sort by ID (most recent first) and limit to result_limit
        all_urls.sort(key=lambda x: x.get("id", 0), reverse=True)
        all_urls = all_urls[:self.result_limit]
        
        # Add a flag to indicate these are URL results
        for url in all_urls:
            url["is_url_result"] = True
        
        if all_urls:
            console.print(f"[green]Found {len(all_urls)} URLs[/green]")
        else:
            console.print("[yellow]No URLs found, falling back to regular search[/yellow]")
            return self._regular_search(query)
            
        return all_urls
    
    def _search_for_best_content(self, query: str) -> List[Dict[str, Any]]:
        """Search for the best content based on the query.
        
        Args:
            query: The user's query.
            
        Returns:
            A list of the best content results.
        """
        console.print(f"[blue]Best content query detected, retrieving quality content...[/blue]")
        
        # Get all sites or filter by profile
        site_ids = []
        if self.search_sites:
            # Get all sites
            all_sites = self.crawler.db_client.get_all_sites()
            
            # Filter sites based on the patterns in the profile
            for site in all_sites:
                site_name = site.get("name", "").lower()
                for pattern in self.search_sites:
                    pattern = pattern.lower()
                    if pattern in site_name or site_name in pattern:
                        site_ids.append(site["id"])
                        break
        
        try:
            # Get pages with titles and summaries, sorted by quality indicators
            quality_pages = []
            
            # For each site (or all sites if no filter)
            if site_ids:
                for site_id in site_ids:
                    # Get pages for this site
                    pages = self.crawler.db_client.get_pages_by_site_id(
                        site_id=site_id, 
                        limit=20,  # Get more pages to select from
                        include_chunks=False  # Only get parent pages
                    )
                    quality_pages.extend(pages)
            else:
                # Get pages from all sites
                all_sites = self.crawler.db_client.get_all_sites()
                for site in all_sites:
                    pages = self.crawler.db_client.get_pages_by_site_id(
                        site_id=site["id"], 
                        limit=10,  # Get more pages to select from
                        include_chunks=False  # Only get parent pages
                    )
                    quality_pages.extend(pages)
            
            # Filter pages that have titles and summaries
            quality_pages = [p for p in quality_pages if p.get("title") and p.get("summary")]
            
            # Sort by a quality heuristic (here we're using content length as a simple proxy)
            # In a real system, you might use more sophisticated metrics
            quality_pages.sort(key=lambda x: len(x.get("content", "")), reverse=True)
            
            # Take the top results
            top_results = quality_pages[:self.result_limit]
            
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
    
    def _regular_search(self, query: str) -> List[Dict[str, Any]]:
        """Perform a regular search based on the query.
        
        Args:
            query: The user's query.
            
        Returns:
            A list of search results.
        """
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
                            threshold=self.similarity_threshold,
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
        console.print("[blue]Searching all sites...[/blue]")
        
        # Use the crawler's search method for all sites
        results = self.crawler.search(
            query, 
            limit=self.result_limit,
            threshold=self.similarity_threshold
        )
        
        if results:
            console.print(f"[green]Found {len(results)} results[/green]")
        else:
            console.print("[red]No results found[/red]")
            
        return results
    
    def format_context(self, results: List[Dict[str, Any]]) -> str:
        """Format search results into a context string for the LLM.
        
        Args:
            results: The search results.
            
        Returns:
            A formatted context string.
        """
        if not results:
            return "No relevant information found."
            
        # Check if the first result is a URL result
        if results and results[0].get("is_url_result", False):
            # Format URL results
            context = "Here are some URLs that might be relevant to your query:\n\n"
            
            for i, result in enumerate(results, 1):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                site_name = result.get("site_name", "Unknown site")
                summary = result.get("summary", "")
                
                context += f"{i}. {title}\n"
                context += f"   URL: {url}\n"
                context += f"   Site: {site_name}\n"
                if summary:
                    context += f"   Summary: {summary}\n"
                context += "\n"
            
            return context
            
        # Check if these are "best" results
        if results and results[0].get("is_best_result", False):
            # Format best results
            context = "Here are some of the best articles from the database:\n\n"
            
            for i, result in enumerate(results, 1):
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                site_name = result.get("site_name", "Unknown site")
                summary = result.get("summary", "")
                content = result.get("content", "")
                
                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]
                
                context += f"{i}. {title}\n"
                context += f"   URL: {url}\n"
                context += f"   Site: {site_name}\n"
                
                if summary:
                    context += f"   Summary: {summary}\n"
                elif content:
                    # Create a brief summary from the content if no summary exists
                    brief_content = content[:300] + "..." if len(content) > 300 else content
                    context += f"   Content preview: {brief_content}\n"
                
                context += "\n"
            
            return context
        
        # Group results by site
        results_by_site = {}
        for result in results:
            site_name = result.get("site_name", "Unknown")
            if site_name not in results_by_site:
                results_by_site[site_name] = []
            results_by_site[site_name].append(result)
        
        # Format the context
        context = ""
        for site_name, site_results in results_by_site.items():
            # Sort by similarity score
            site_results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
            
            context += f"Information from {site_name}:\n\n"
            
            for result in site_results:
                title = result.get("title", "Untitled")
                url = result.get("url", "")
                content = result.get("content", "")
                
                # Clean up the URL by removing chunk fragments
                if "#chunk-" in url:
                    url = url.split("#chunk-")[0]
                
                context += f"Document: {title}\n"
                context += f"URL: {url}\n"
                context += f"Content: {content}\n\n"
        
        return context
    
    def get_response(self, query: str) -> str:
        """Get a response from the LLM based on the query and relevant context.
        
        Args:
            query: The user's query.
            
        Returns:
            The LLM's response.
        """
        # Check for user-specific queries
        user_queries = ["my name", "who am i", "what's my name", "what is my name"]
        is_user_query = any(user_query in query.lower() for user_query in user_queries)
        
        # Check for time-related queries
        time_queries = ["time", "date", "day", "month", "year", "today", "current time", "current date", "what time", "what day"]
        is_time_query = any(time_query in query.lower() for time_query in time_queries)
        
        # Check for memory-related queries
        memory_queries = ["remember", "said", "told", "mentioned", "earlier", "before", "previous", "last time"]
        preference_queries = ["like", "love", "prefer", "favorite", "enjoy", "hate", "dislike", "my favorite"]
        
        is_memory_query = any(memory_query in query.lower() for memory_query in memory_queries)
        is_preference_query = any(pref_query in query.lower() for pref_query in preference_queries)
        
        # Add the user message to the conversation history
        self.add_user_message(query)
        
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
        
        # Search for relevant context from the database
        results = self.search_for_context(query)
        
        # Format the context
        context = self.format_context(results)
        
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
        
        # Extract user preferences from conversation history
        preferences = []
        for message in self.conversation_history:
            if message.get("metadata") and "preference" in message.get("metadata", {}):
                preference = message["metadata"]["preference"]
                if preference not in preferences:
                    preferences.append(preference)
        
        # Add user preferences to the system prompt if available
        if preferences:
            system_prompt += "\n\nUser preferences from previous conversations:"
            for preference in preferences:
                system_prompt += f"\n- {preference}"
        
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
            max_tokens=1000
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
        """Display available chat profiles."""
        table = Table(title="Available Chat Profiles")
        
        table.add_column("Name", style="cyan")
        table.add_column("Description", style="green")
        table.add_column("Search Sites", style="yellow")
        
        for name, profile in CHAT_PROFILES.items():
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
    
    def chat_loop(self):
        """Run an interactive chat loop."""
        console.print(Panel.fit(
            "[bold cyan]Welcome to the Crawl4AI Chat Interface![/bold cyan]\n"
            "Ask questions about the crawled data or use these commands:\n"
            "[bold red]'exit'[/bold red] to quit\n"
            "[bold red]'clear'[/bold red] to clear the conversation history\n"
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
        
        while True:
            # Get user input
            query = Prompt.ask("\n[bold green]You[/bold green]")
            
            # Check if the user wants to exit
            if query.lower() in ['exit', 'quit', 'bye']:
                console.print(Panel("[bold cyan]Goodbye![/bold cyan]", border_style="blue"))
                break
            
            # Check if the user wants to clear the conversation history
            if query.lower() == 'clear':
                self.clear_conversation_history()
                continue
            
            # Check if the user wants to view the conversation history
            if query.lower() == 'history':
                self.show_conversation_history()
                continue
            
            # Check if the user wants to list available profiles
            if query.lower() == 'profiles':
                self.show_profiles()
                continue
            
            # Check if the user wants to change the profile
            if query.lower().startswith('profile '):
                profile_name = query.lower().split('profile ')[1].strip()
                self.change_profile(profile_name)
                continue
            
            # Show thinking indicator
            with console.status("[bold blue]Thinking...[/bold blue]", spinner="dots"):
                # Get a response
                response = self.get_response(query)
            
            # Print the response
            console.print("\n[bold purple]Assistant[/bold purple]")
            console.print(Panel(Markdown(response), border_style="purple"))

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
        
        # Extract preferences from metadata
        preferences = []
        for message in self.conversation_history:
            if message.get("metadata") and "preference" in message.get("metadata", {}):
                preference = message["metadata"]["preference"]
                if preference not in preferences:
                    preferences.append(preference)
        
        # Format the conversation history for the LLM
        history_text = ""
        for message in self.conversation_history:
            if message["role"] != "system":  # Skip system messages
                role = "User" if message["role"] == "user" else "Assistant"
                history_text += f"{role}: {message['content']}\n\n"
        
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
        
        try:
            # Get a response from the LLM
            response = self.client.chat.completions.create(
                model=analysis_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500
            )
            
            # Extract the response text
            analysis = response.choices[0].message.content
            
            if analysis and analysis != "No relevant information found.":
                console.print(f"[blue]Found relevant information in conversation history[/blue]")
            
            return analysis
        except Exception as e:
            console.print(f"[red]Error analyzing conversation history: {e}[/red]")
            return ""

def main():
    """Run the chat interface."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Chat with the Crawl4AI database.')
    parser.add_argument('--model', type=str, help='OpenAI model to use')
    parser.add_argument('--limit', type=int, help='Maximum number of results to return')
    parser.add_argument('--threshold', type=float, help='Similarity threshold for vector search')
    parser.add_argument('--session', type=str, help='Session ID for the conversation (to continue a previous session)')
    parser.add_argument('--user', type=str, help='User ID for the conversation (e.g., your name)')
    parser.add_argument('--profile', type=str, help='Chat profile to use')
    parser.add_argument('--profiles-dir', type=str, help='Directory containing profile YAML files')
    parser.add_argument('--new-session', action='store_true', help='Start a new session (ignore saved session ID)')
    args = parser.parse_args()
    
    # Load profiles from the specified directory or the default directory
    profiles_dir = args.profiles_dir or os.getenv("CHAT_PROFILES_DIR", "profiles")
    
    # Only load profiles once and store in global variable
    global CHAT_PROFILES
    if not CHAT_PROFILES:
        CHAT_PROFILES = load_profiles_from_directory(profiles_dir)
        # Print the number of profiles loaded
        console.print(f"Loaded {len(CHAT_PROFILES)} profiles from {profiles_dir}")
    
    # Use the provided session ID or get it from the environment variable or generate a new one
    session_id = args.session or os.getenv("CHAT_SESSION_ID")
    
    # If we still don't have a session ID or new session is requested, generate a new one
    if not session_id or args.new_session:
        session_id = str(uuid.uuid4())
        console.print(f"[blue]Generated new session ID: {session_id}[/blue]")
    
    # Create a chat interface
    chat = ChatBot(
        model=args.model,
        result_limit=args.limit,
        similarity_threshold=args.threshold,
        session_id=session_id,
        user_id=args.user,
        profile=args.profile
    )
    
    # Print session continuation information if a session ID was provided
    if args.session:
        console.print(f"[bold green]Continuing session:[/bold green] [blue]{session_id}[/blue]")
        if args.user:
            console.print(f"[bold green]User:[/bold green] [blue]{args.user}[/blue]")
        console.print("[green]Your conversation history has been loaded.[/green]")
    
    # Run the chat loop
    chat.chat_loop()

if __name__ == "__main__":
    main() 