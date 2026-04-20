"""
Module for enhancing content with titles and summaries using OpenAI.
"""

import os
import json
import asyncio
import tiktoken
from typing import Dict, Any, List, Optional
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class ContentEnhancer:
    """Class for enhancing content with titles and summaries using OpenAI."""
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        """Initialize the content enhancer.
        
        Args:
            api_key: OpenAI API key. Defaults to environment variable.
            model: The OpenAI model to use. Defaults to environment variable.
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_CONTENT_MODEL", "gpt-3.5-turbo")
        
        if not self.api_key:
            raise ValueError("OpenAI API key not provided and not found in environment variables.")
        
        try:
            # Try to initialize the sync client with the standard parameters.
            # Async clients are created per async call so their transports close
            # before asyncio.run() tears down the crawl worker event loop.
            self.client = OpenAI(api_key=self.api_key)
            self._async_client_kwargs: Dict[str, Any] = {"api_key": self.api_key}
        except TypeError as e:
            # If there's an error about unexpected keyword arguments, try a different approach
            if "unexpected keyword argument" in str(e):
                print(f"Warning: {e}. Trying alternative initialization.")
                # Initialize without the problematic parameter
                import httpx
                http_client = httpx.Client()
                self.client = OpenAI(api_key=self.api_key, http_client=http_client)
                self._async_client_kwargs = {"api_key": self.api_key}
            else:
                raise
        
        # Initialize tokenizer
        # gpt-4o-mini uses cl100k_base encoding
        self.tokenizer = tiktoken.get_encoding("cl100k_base")
        
        # Set token limits - gpt-4o-mini has a 16K context window
        self.max_tokens = 15000  # Using 15K to be safe
        
        print(f"Using model {self.model} for title and summary generation")
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text.
        
        Args:
            text: The text to count tokens for.
            
        Returns:
            The number of tokens.
        """
        return len(self.tokenizer.encode(text))
    
    def generate_title_and_summary(self, content: str, url: str) -> Dict[str, str]:
        """Generate a title and summary for content.
        
        Args:
            content: The content to generate a title and summary for.
            url: The URL of the content.
            
        Returns:
            A dictionary with 'title' and 'summary' keys.
        """
        system_prompt = """You are an AI that extracts titles and summaries from web content.
        Return a JSON object with 'title' and 'summary' keys.
        For the title: Extract or derive a descriptive title for this content.
        For the summary: Create a concise summary of the main points in this content.
        Keep both title and summary concise but informative."""
        
        try:
            # Truncate content if it's too long using token-based truncation
            token_count = self.count_tokens(content)
            if token_count > self.max_tokens:
                print(f"Content for {url} exceeds token limit ({token_count} > {self.max_tokens}). Truncating...")
                tokens = self.tokenizer.encode(content)
                truncated_tokens = tokens[:self.max_tokens]
                truncated_content = self.tokenizer.decode(truncated_tokens) + "..."
            else:
                truncated_content = content
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"URL: {url}\n\nContent:\n{truncated_content}"}
                ],
                response_format={"type": "json_object"}
            )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "title": result.get("title", f"Content from {url}"),
                "summary": result.get("summary", "No summary available.")
            }
        except Exception as e:
            print(f"Error generating title and summary: {e}")
            # Return placeholder title and summary when there's an error
            domain = url.split('/')[2] if '//' in url else url.split('/')[0]
            return {
                "title": f"Content from {domain}",
                "summary": "No summary available."
            }
    
    async def generate_title_and_summary_async(self, content: str, url: str) -> Dict[str, str]:
        """Generate a title and summary for content asynchronously.
        
        Args:
            content: The content to generate a title and summary for.
            url: The URL of the content.
            
        Returns:
            A dictionary with 'title' and 'summary' keys.
        """
        system_prompt = """You are an AI that extracts titles and summaries from web content.
        Return a JSON object with 'title' and 'summary' keys.
        For the title: Extract or derive a descriptive title for this content.
        For the summary: Create a concise summary of the main points in this content.
        Keep both title and summary concise but informative."""
        
        try:
            # Truncate content if it's too long using token-based truncation
            token_count = self.count_tokens(content)
            if token_count > self.max_tokens:
                print(f"Content for {url} exceeds token limit ({token_count} > {self.max_tokens}). Truncating...")
                tokens = self.tokenizer.encode(content)
                truncated_tokens = tokens[:self.max_tokens]
                truncated_content = self.tokenizer.decode(truncated_tokens) + "..."
            else:
                truncated_content = content
            
            async with AsyncOpenAI(**self._async_client_kwargs) as async_client:
                response = await async_client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"URL: {url}\n\nContent:\n{truncated_content}"}
                    ],
                    response_format={"type": "json_object"}
                )
            
            result = json.loads(response.choices[0].message.content)
            return {
                "title": result.get("title", f"Content from {url}"),
                "summary": result.get("summary", "No summary available.")
            }
        except Exception as e:
            print(f"Error generating title and summary asynchronously: {e}")
            # Return placeholder title and summary when there's an error
            domain = url.split('/')[2] if '//' in url else url.split('/')[0]
            return {
                "title": f"Content from {domain}",
                "summary": "No summary available."
            }
    
    async def enhance_pages_async(self, pages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Enhance multiple pages with titles and summaries asynchronously.
        
        Args:
            pages: List of page data dictionaries.
            
        Returns:
            The enhanced pages.
        """
        enhanced_pages = []
        
        # Process pages in batches to avoid rate limits
        batch_size = 5
        for i in range(0, len(pages), batch_size):
            batch = pages[i:i+batch_size]
            tasks = []
            
            for page in batch:
                # Only generate title and summary if they're missing
                if (not page.get('title') or not page.get('summary')) and page.get('content'):
                    task = self.generate_title_and_summary_async(page['content'], page['url'])
                    tasks.append(task)
                else:
                    # If title and summary are already present, just add None to maintain order
                    tasks.append(None)
            
            # Wait for all tasks to complete
            results = await asyncio.gather(*[task if task else asyncio.sleep(0) for task in tasks])
            
            # Update pages with results
            for j, (page, result) in enumerate(zip(batch, results)):
                if result:
                    if not page.get('title'):
                        page['title'] = result['title']
                    if not page.get('summary'):
                        page['summary'] = result['summary']
                enhanced_pages.append(page)
            
            # Sleep to avoid rate limits
            if i + batch_size < len(pages):
                await asyncio.sleep(1)
        
        return enhanced_pages
