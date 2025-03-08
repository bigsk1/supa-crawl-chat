import os
import json
from typing import List, Dict, Any, Optional, Tuple, Union
import psycopg2
from psycopg2.extras import execute_values, Json
from dotenv import load_dotenv
from utils import print_info, print_warning, print_error, print_success
from db_setup import db_params  # Import the db_params from db_setup.py

# Load environment variables
load_dotenv()

class SupabaseClient:
    """Client for interacting with the Supabase database."""
    
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                database: Optional[str] = None, user: Optional[str] = None,
                password: Optional[str] = None):
        """Initialize the Supabase client.
        
        Args:
            host: Database host. Defaults to environment variable.
            port: Database port. Defaults to environment variable.
            database: Database name. Defaults to environment variable.
            user: Database user. Defaults to environment variable.
            password: Database password. Defaults to environment variable.
        """
        # Use the provided parameters or the ones from db_params
        self.db_params = {
            'host': host or db_params['host'],
            'port': port or db_params['port'],
            'database': database or db_params['database'],
            'user': user or db_params['user'],
            'password': password or db_params['password']
        }
    
    def _get_connection(self):
        """Get a connection to the database."""
        return psycopg2.connect(**self.db_params)
    
    def add_site(self, name: str, url: str, description: Optional[str] = None) -> int:
        """Add a new site to the database.
        
        Args:
            name: The name of the site.
            url: The URL of the site.
            description: Optional description of the site.
            
        Returns:
            The ID of the newly created site.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Check if the site already exists
            cur.execute("SELECT id FROM crawl_sites WHERE url = %s", (url,))
            existing = cur.fetchone()
            
            if existing:
                # Update the existing site
                cur.execute(
                    "UPDATE crawl_sites SET name = %s, description = %s WHERE id = %s RETURNING id",
                    (name, description, existing[0])
                )
                site_id = cur.fetchone()[0]
                print_info(f"Updated existing site with ID: {site_id}")
            else:
                # Insert the new site
                cur.execute(
                    "INSERT INTO crawl_sites (name, url, description) VALUES (%s, %s, %s) RETURNING id",
                    (name, url, description)
                )
                site_id = cur.fetchone()[0]
                print_success(f"Added new site with ID: {site_id}")
            
            conn.commit()
            return site_id
            
        except Exception as e:
            if conn:
                conn.rollback()
            print_error(f"Error adding site: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def add_pages(self, site_id: int, pages: List[Dict[str, Any]]) -> List[int]:
        """Add pages to the database.
        
        Args:
            site_id: The ID of the site.
            pages: List of page data dictionaries.
            
        Returns:
            List of page IDs.
        """
        if not pages:
            return []
        
        # Separate parent pages and chunks
        parent_pages = [p for p in pages if not p.get('is_chunk', False)]
        chunk_pages = [p for p in pages if p.get('is_chunk', False)]
        
        print_info(f"Processing {len(parent_pages)} parent pages and {len(chunk_pages)} chunks")
        
        # Dictionary to store URL to ID mapping for parent pages
        parent_url_to_id = {}
        page_ids = []
        
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cur:
                    # First, process all parent pages
                    for page in parent_pages:
                        url = page.get('url', '')
                        title = page.get('title', '')
                        content = page.get('content', '')
                        summary = page.get('summary', '')
                        embedding = page.get('embedding', [])
                        metadata = page.get('metadata', {})
                        
                        # Debug embedding information
                        if embedding:
                            print_info(f"Parent page embedding length: {len(embedding)}")
                        else:
                            print_warning(f"No embedding for parent page: {url}")
                        
                        # Ensure embedding is properly formatted for pgvector
                        if embedding and isinstance(embedding, list):
                            # Format the embedding as a string with square brackets for pgvector
                            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                        else:
                            embedding_str = None
                            print_warning(f"Invalid embedding format for parent page: {url}")
                        
                        # Check if the page already exists
                        cur.execute(
                            """
                            SELECT id FROM crawl_pages 
                            WHERE url = %s AND (is_chunk IS NULL OR is_chunk = FALSE)
                            """, 
                            (url,)
                        )
                        existing = cur.fetchone()
                        
                        if existing:
                            # Update existing page
                            page_id = existing[0]
                            cur.execute(
                                """
                                UPDATE crawl_pages 
                                SET title = %s, content = %s, summary = %s, embedding = %s, 
                                    metadata = %s, is_chunk = FALSE, chunk_index = NULL, parent_id = NULL
                                WHERE id = %s
                                """,
                                (title, content, summary, embedding_str, json.dumps(metadata) if metadata else None, page_id)
                            )
                            print_info(f"Updated existing page: {url} (ID: {page_id})")
                        else:
                            # Insert new page
                            cur.execute(
                                """
                                INSERT INTO crawl_pages 
                                (site_id, url, title, content, summary, embedding, metadata, is_chunk, chunk_index, parent_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, NULL, NULL)
                                RETURNING id
                                """,
                                (site_id, url, title, content, summary, embedding_str, json.dumps(metadata) if metadata else None)
                            )
                            page_id = cur.fetchone()[0]
                            print_info(f"Added new page: {url} (ID: {page_id})")
                        
                        # Store the page ID
                        page_ids.append(page_id)
                        
                        # Store the URL to ID mapping for parent pages
                        parent_url_to_id[url] = page_id
                    
                    # Commit the parent pages to ensure they're available for the chunks
                    conn.commit()
                    
                    # Now process all chunks
                    for chunk in chunk_pages:
                        url = chunk.get('url', '')
                        title = chunk.get('title', '')
                        content = chunk.get('content', '')
                        summary = chunk.get('summary', '')
                        embedding = chunk.get('embedding', [])
                        chunk_index = chunk.get('chunk_index', 0)
                        metadata = chunk.get('metadata', {})
                        
                        # Debug embedding information
                        if embedding:
                            print_info(f"Chunk embedding length: {len(embedding)}")
                        else:
                            print_warning(f"No embedding for chunk: {url}")
                        
                        # Ensure embedding is properly formatted for pgvector
                        if embedding and isinstance(embedding, list):
                            # Format the embedding as a string with square brackets for pgvector
                            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
                        else:
                            embedding_str = None
                            print_warning(f"Invalid embedding format for chunk: {url}")
                        
                        # Extract the parent URL from the chunk URL (remove the fragment)
                        parent_url = url.split('#')[0] if '#' in url else url
                        
                        # Get the parent ID from the mapping
                        parent_id = parent_url_to_id.get(parent_url)
                        
                        if not parent_id:
                            print_warning(f"Parent page not found for chunk: {url}")
                            continue
                        
                        # Check if the chunk already exists
                        cur.execute(
                            """
                            SELECT id FROM crawl_pages 
                            WHERE url = %s AND is_chunk = TRUE AND chunk_index = %s
                            """, 
                            (url, chunk_index)
                        )
                        existing = cur.fetchone()
                        
                        if existing:
                            # Update existing chunk
                            chunk_id = existing[0]
                            cur.execute(
                                """
                                UPDATE crawl_pages 
                                SET title = %s, content = %s, summary = %s, embedding = %s, 
                                    metadata = %s, parent_id = %s
                                WHERE id = %s
                                """,
                                (title, content, summary, embedding_str, json.dumps(metadata) if metadata else None, parent_id, chunk_id)
                            )
                            print_info(f"Updated existing chunk: {url} (chunk {chunk_index}, ID: {chunk_id})")
                        else:
                            # Insert new chunk
                            cur.execute(
                                """
                                INSERT INTO crawl_pages 
                                (site_id, url, title, content, summary, embedding, metadata, is_chunk, chunk_index, parent_id)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s)
                                RETURNING id
                                """,
                                (site_id, url, title, content, summary, embedding_str, json.dumps(metadata) if metadata else None, chunk_index, parent_id)
                            )
                            chunk_id = cur.fetchone()[0]
                            print_info(f"Added new chunk: {url} (chunk {chunk_index}, ID: {chunk_id})")
                        
                        # Store the chunk ID
                        page_ids.append(chunk_id)
                    
                    # Commit the chunks
                    conn.commit()
                    
                    print_success(f"Successfully stored {len(page_ids)} pages")
                    return page_ids
                    
        except Exception as e:
            print_error(f"Error adding pages: {e}")
            return []
    
    def search_by_text(self, query: str, limit: int = 10, site_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search pages by text content.
        
        Args:
            query: The search query.
            limit: Maximum number of results to return.
            site_id: Optional site ID to filter results by.
            
        Returns:
            List of matching pages.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Extract domain names from the query
            import re
            domain_pattern = re.compile(r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z0-9][-a-zA-Z0-9]*')
            domains = domain_pattern.findall(query.lower())
            
            # If we found domain names in the query, prioritize those
            if domains:
                domain = domains[0]
                print_info(f"Found domain in query: {domain}, using domain-specific search")
                
                # Prepare the site filter
                site_filter = ""
                domain_pattern = f'%{domain}%'
                
                if site_id is not None:
                    site_filter = "AND p.site_id = %s"
                    params = [domain_pattern, domain_pattern, domain_pattern, site_id, limit]
                else:
                    params = [domain_pattern, domain_pattern, domain_pattern, limit]
                
                # Use a simple ILIKE query with priority for URLs containing the domain
                search_query = f"""
                SELECT 
                    p.id, p.site_id, s.name as site_name, p.url, p.title, 
                    p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                    p.parent_id, parent.title as parent_title
                FROM 
                    crawl_pages p
                    JOIN crawl_sites s ON p.site_id = s.id
                    LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                WHERE 
                    (p.url ILIKE %s OR p.title ILIKE %s OR p.content ILIKE %s)
                    {site_filter}
                ORDER BY 
                    p.is_chunk DESC
                LIMIT %s
                """
                
                cur.execute(search_query, params)
                
                # Convert results to dictionaries
                columns = [desc[0] for desc in cur.description]
                results = []
                
                for row in cur.fetchall():
                    result = dict(zip(columns, row))
                    # Convert any JSON fields from string to dict
                    if result.get('metadata') and isinstance(result['metadata'], str):
                        result['metadata'] = json.loads(result['metadata'])
                    
                    # Add context about chunking
                    if result.get('is_chunk'):
                        result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                    
                    results.append(result)
                
                print_info(f"Domain-specific search found {len(results)} results")
                return results
            
            # Regular search for other queries
            # Prepare the site filter
            site_filter = ""
            params = [query, limit]
            
            if site_id is not None:
                site_filter = "AND p.site_id = %s"
                params.insert(1, site_id)  # Insert site_id before limit
            
            # Search using PostgreSQL full-text search
            search_query = f"""
            SELECT 
                p.id, p.site_id, s.name as site_name, p.url, p.title, 
                p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                p.parent_id, parent.title as parent_title
            FROM 
                crawl_pages p
                JOIN crawl_sites s ON p.site_id = s.id
                LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
            WHERE 
                to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')) @@ plainto_tsquery('english', %s)
                {site_filter}
            ORDER BY 
                ts_rank_cd(to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')), 
                          plainto_tsquery('english', %s)) DESC,
                p.is_chunk DESC
            LIMIT %s
            """
            
            # Add the query again for ts_rank_cd
            params.insert(1, query)
            
            cur.execute(search_query, params)
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            results = []
            
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                # Convert any JSON fields from string to dict
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                
                # Add context about chunking
                if result.get('is_chunk'):
                    result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                
                results.append(result)
            
            print_info(f"Text search found {len(results)} results")
            return results
            
        except Exception as e:
            print_error(f"Error searching by text: {e}")
            # Return empty results instead of raising an exception
            return []
        finally:
            if conn:
                conn.close()
    
    def search_by_embedding(self, embedding: List[float], 
                           threshold: float = 0.5, 
                           limit: int = 10,
                           site_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Search pages by vector similarity.
        
        Args:
            embedding: The query embedding vector.
            threshold: Minimum similarity threshold (0-1).
            limit: Maximum number of results to return.
            site_id: Optional site ID to filter results by.
            
        Returns:
            List of matching pages.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Debug information
            print(f"Searching with embedding of length: {len(embedding)}")
            print(f"Similarity threshold: {threshold}")
            
            # First, check if any embeddings exist in the database
            site_filter = ""
            params = []
            
            if site_id is not None:
                site_filter = "AND site_id = %s"
                params.append(site_id)
            
            cur.execute(f"SELECT COUNT(*) FROM crawl_pages WHERE embedding IS NOT NULL {site_filter}", params)
            count = cur.fetchone()[0]
            print(f"Found {count} pages with embeddings in the database")
            
            if count == 0:
                print("No embeddings found in database, falling back to text search")
                return []
            
            # Check if pgvector extension is installed
            try:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                pgvector_installed = cur.fetchone() is not None
                
                if not pgvector_installed:
                    print("pgvector extension is not installed in the database")
                    return []
                
                # Check the type of the embedding column
                cur.execute("SELECT pg_typeof(embedding) FROM crawl_pages WHERE embedding IS NOT NULL LIMIT 1")
                embedding_type = cur.fetchone()[0]
                print(f"Embedding column type: {embedding_type}")
                
                # Check if the type is actually 'vector'
                if embedding_type != 'vector':
                    print(f"Embedding column is not of type 'vector' but '{embedding_type}'. Vector search may not work.")
                    return []
                
            except Exception as e:
                print(f"Error checking database configuration: {e}")
                return []
            
            # Format the embedding as a string with square brackets for pgvector
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
            
            # Prepare the site filter for the main query
            site_filter = ""
            params = []
            
            # Try to perform a vector similarity search that prioritizes chunks
            try:
                # Get the top results regardless of threshold
                if site_id is not None:
                    search_query = """
                    SELECT 
                        p.id, p.site_id, s.name as site_name, p.url, p.title, 
                        p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                        p.parent_id, parent.title as parent_title,
                        1 - (p.embedding <=> %s::vector) as similarity
                    FROM 
                        crawl_pages p
                        JOIN crawl_sites s ON p.site_id = s.id
                        LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                    WHERE 
                        p.embedding IS NOT NULL
                        AND p.site_id = %s
                    ORDER BY 
                        1 - (p.embedding <=> %s::vector) DESC,
                        p.is_chunk DESC
                    LIMIT %s
                    """
                    params = [embedding_str, site_id, embedding_str, limit]
                else:
                    search_query = """
                    SELECT 
                        p.id, p.site_id, s.name as site_name, p.url, p.title, 
                        p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                        p.parent_id, parent.title as parent_title,
                        1 - (p.embedding <=> %s::vector) as similarity
                    FROM 
                        crawl_pages p
                        JOIN crawl_sites s ON p.site_id = s.id
                        LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                    WHERE 
                        p.embedding IS NOT NULL
                    ORDER BY 
                        1 - (p.embedding <=> %s::vector) DESC,
                        p.is_chunk DESC
                    LIMIT %s
                    """
                    params = [embedding_str, embedding_str, limit]
                
                cur.execute(search_query, params)
                
                # Filter results by threshold
                results = []
                for row in cur.fetchall():
                    result = {
                        "id": row[0],
                        "site_id": row[1],
                        "site_name": row[2],
                        "url": row[3],
                        "title": row[4] or "Untitled",
                        "content": row[5],
                        "summary": row[6],
                        "metadata": row[7] or {},
                        "is_chunk": row[8],
                        "chunk_index": row[9],
                        "parent_id": row[10],
                        "parent_title": row[11],
                        "similarity": row[12]
                    }
                    
                    # Only include results above the threshold
                    if result["similarity"] >= threshold:
                        results.append(result)
                
                return results
                
            except Exception as e:
                print(f"Error in vector search: {e}")
                return []
                
        except Exception as e:
            print(f"Error in search_by_embedding: {e}")
            return []
            
        finally:
            if conn:
                conn.close()
    
    def hybrid_search(self, query: str, embedding: List[float], 
                      threshold: float = 0.5, limit: int = 10, site_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Perform a hybrid search using both vector similarity and text matching.
        
        This combines the strengths of semantic search (finding related concepts)
        with keyword search (finding specific terms).
        
        Args:
            query: The text query for keyword search.
            embedding: The query embedding for vector search.
            threshold: Minimum similarity threshold (0-1).
            limit: Maximum number of results to return.
            site_id: Optional site ID to filter results by.
            
        Returns:
            List of matching pages with combined scores.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # First try the vector search as a fallback
            try:
                print_info("Trying vector search first...")
                vector_results = self.search_by_embedding(embedding, threshold, limit, site_id)
                if vector_results:
                    print_info(f"Vector search found {len(vector_results)} results")
                    return vector_results
            except Exception as e:
                print_error(f"Vector search failed: {e}")
            
            # If vector search fails or returns no results, try text search
            print_info("Trying text search...")
            text_results = self.search_by_text(query, limit, site_id)
            
            # Add similarity scores to text results
            for result in text_results:
                result['similarity'] = 0.5  # Default similarity score
                result['vector_score'] = 0.0
                result['text_score'] = 0.5
            
            print_info(f"Text search found {len(text_results)} results")
            return text_results
            
        except Exception as e:
            print_error(f"Error in hybrid search: {e}")
            # Fall back to text search
            return self.search_by_text(query, limit, site_id)
        finally:
            if conn:
                conn.close()
    
    def get_site_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get a site by its URL.
        
        Args:
            url: The URL of the site.
            
        Returns:
            Site data or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            cur.execute(
                "SELECT id, name, url, description FROM crawl_sites WHERE url = %s",
                (url,)
            )
            
            result = cur.fetchone()
            if not result:
                return None
            
            return {
                'id': result[0],
                'name': result[1],
                'url': result[2],
                'description': result[3]
            }
            
        except Exception as e:
            print_error(f"Error getting site by URL: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_pages_by_site_id(self, site_id: int, limit: int = 100, include_chunks: bool = False) -> List[Dict[str, Any]]:
        """Get pages for a specific site.
        
        Args:
            site_id: The ID of the site.
            limit: Maximum number of pages to return.
            include_chunks: Whether to include chunked content. If False, only parent pages are returned.
            
        Returns:
            List of pages for the site.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Build the query based on whether to include chunks
            if include_chunks:
                query = """
                SELECT 
                    p.id, p.site_id, p.url, p.title, p.content, p.summary, 
                    p.metadata, p.is_chunk, p.chunk_index, p.parent_id,
                    parent.title as parent_title
                FROM 
                    crawl_pages p
                    LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                WHERE 
                    p.site_id = %s
                ORDER BY 
                    p.url, p.is_chunk, p.chunk_index
                LIMIT %s
                """
            else:
                query = """
                SELECT 
                    id, site_id, url, title, content, summary, metadata
                FROM 
                    crawl_pages
                WHERE 
                    site_id = %s AND
                    (is_chunk IS NULL OR is_chunk = FALSE)
                ORDER BY 
                    url
                LIMIT %s
                """
            
            cur.execute(query, (site_id, limit))
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            results = []
            
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                # Convert any JSON fields from string to dict
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)
            
            return results
            
        except Exception as e:
            print_error(f"Error getting pages by site ID: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def update_site_description(self, site_id: int, description: str) -> bool:
        """Update the description of a site.
        
        Args:
            site_id: The ID of the site to update.
            description: The new description.
            
        Returns:
            True if the update was successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            update_query = """
            UPDATE crawl_sites
            SET description = %s
            WHERE id = %s
            """
            
            cur.execute(update_query, (description, site_id))
            conn.commit()
            
            return True
            
        except Exception as e:
            if conn:
                conn.rollback()
            print_error(f"Error updating site description: {e}")
            return False
        finally:
            if conn:
                conn.close()
    
    def setup_conversation_history_table(self):
        """Set up the conversation history table if it doesn't exist."""
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Create the conversation history table if it doesn't exist
            cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB
            )
            """)
            
            # Create an index on session_id for faster lookups
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conversations_session_id 
            ON chat_conversations(session_id)
            """)
            
            # Create an index on user_id for faster lookups
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_id 
            ON chat_conversations(user_id)
            """)
            
            # Create an index on timestamp for faster sorting
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_conversations_timestamp 
            ON chat_conversations(timestamp)
            """)
            
            conn.commit()
            print_success("Conversation history table set up successfully")
            
        except Exception as e:
            print_error(f"Error setting up conversation history table: {e}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()
    
    def save_message(self, session_id: str, role: str, content: str, user_id: Optional[str] = None, 
                    metadata: Optional[Dict[str, Any]] = None) -> int:
        """Save a message to the conversation history.
        
        Args:
            session_id: The session ID for the conversation.
            role: The role of the message sender (e.g., 'user', 'assistant', 'system').
            content: The message content.
            user_id: Optional user ID for the conversation.
            metadata: Optional metadata for the message.
            
        Returns:
            The ID of the newly created message.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Insert the message
            cur.execute(
                """
                INSERT INTO chat_conversations 
                (session_id, user_id, role, content, metadata)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    session_id, 
                    user_id, 
                    role, 
                    content, 
                    json.dumps(metadata) if metadata else None
                )
            )
            
            message_id = cur.fetchone()[0]
            conn.commit()
            
            return message_id
            
        except Exception as e:
            print_error(f"Error saving message: {e}")
            if conn:
                conn.rollback()
            return -1
        finally:
            if conn:
                conn.close()
    
    def get_conversation_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get the conversation history for a session.
        
        Args:
            session_id: The session ID for the conversation.
            limit: Maximum number of messages to return.
            
        Returns:
            List of messages in the conversation.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the conversation history
            cur.execute(
                """
                SELECT id, session_id, user_id, timestamp, role, content, metadata
                FROM chat_conversations
                WHERE session_id = %s
                ORDER BY timestamp ASC
                LIMIT %s
                """,
                (session_id, limit)
            )
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            messages = []
            
            for row in cur.fetchall():
                message = dict(zip(columns, row))
                
                # Convert metadata from JSON string to dict if it exists
                if message.get('metadata') and isinstance(message['metadata'], str):
                    message['metadata'] = json.loads(message['metadata'])
                
                messages.append(message)
            
            return messages
            
        except Exception as e:
            print_error(f"Error getting conversation history: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def clear_conversation_history(self, session_id: str) -> bool:
        """Clear the conversation history for a session.
        
        Args:
            session_id: The session ID for the conversation.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Delete the conversation history
            cur.execute(
                """
                DELETE FROM chat_conversations
                WHERE session_id = %s
                """,
                (session_id,)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            print_error(f"Error clearing conversation history: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all sites.
        
        Returns:
            List of all sites.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get all sites
            cur.execute(
                """
                SELECT id, name, url, description 
                FROM crawl_sites
                ORDER BY name
                """
            )
            
            # Convert results to dictionaries
            sites = []
            for row in cur.fetchall():
                sites.append({
                    'id': row[0],
                    'name': row[1],
                    'url': row[2],
                    'description': row[3]
                })
            
            return sites
            
        except Exception as e:
            print_error(f"Error getting all sites: {e}")
            return []
        finally:
            if conn:
                conn.close() 