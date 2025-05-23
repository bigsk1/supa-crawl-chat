import os
import json
from typing import List, Dict, Any, Optional, Tuple, Union
import psycopg2
from psycopg2.extras import execute_values, Json
from dotenv import load_dotenv
from utils import print_info, print_warning, print_error, print_success
from db_setup import db_params  # Import the db_params from db_setup.py
import re

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
            
            print_info(f"Performing text search for: '{query}'")
            
            # Extract domain names from the query
            domain_pattern = re.compile(r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z0-9][-a-zA-Z0-9]*')
            domains = domain_pattern.findall(query.lower())
            
            # If we found domain names in the query, prioritize those
            if domains:
                domain_list = ', '.join([f"'{domain}'" for domain in domains])
                print_info(f"Found domains in query: {domain_list}, prioritizing these domains")
                
                # Prepare the site filter
                site_filter = ""
                params = [query]
                
                if site_id is not None:
                    # Ensure site_id is an integer
                    try:
                        site_id = int(site_id)
                        site_filter = "AND p.site_id = %s"
                        params.append(site_id)
                    except (ValueError, TypeError):
                        print_error(f"Invalid site_id: {site_id}, must be an integer")
                
                # Add the limit parameter
                params.append(limit * 2)  # Get more results initially
                
                # Search using PostgreSQL full-text search with domain prioritization
                search_query = f"""
                SELECT 
                    p.id, p.site_id, s.name as site_name, p.url, p.title, 
                    p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                    p.parent_id, parent.title as parent_title,
                    ts_rank_cd(to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')), 
                              plainto_tsquery('english', %s)) AS rank
                FROM 
                    crawl_pages p
                    JOIN crawl_sites s ON p.site_id = s.id
                    LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                WHERE 
                    to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')) @@ plainto_tsquery('english', %s)
                    {site_filter}
                    AND (
                        {' OR '.join([f"p.url LIKE '%{domain}%'" for domain in domains])}
                    )
                ORDER BY 
                    rank DESC,
                    p.is_chunk ASC
                LIMIT %s
                """
                
                # Add the query again for ts_rank_cd
                params.insert(0, query)
                
                cur.execute(search_query, params)
                
                # Convert results to dictionaries
                columns = [desc[0] for desc in cur.description]
                all_results = []
                
                for row in cur.fetchall():
                    result = dict(zip(columns, row))
                    # Convert any JSON fields from string to dict
                    if result.get('metadata') and isinstance(result['metadata'], str):
                        result['metadata'] = json.loads(result['metadata'])
                    
                    # Add context about chunking
                    if result.get('is_chunk'):
                        result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                    
                    all_results.append(result)
                
                print_info(f"Domain-specific search found {len(all_results)} results")
                
                # Log some results for debugging
                for i, result in enumerate(all_results[:3]):
                    print_info(f"Result {i+1}: {result.get('title', 'No title')} - Rank: {result.get('rank', 0)}")
                    print_info(f"  URL: {result.get('url', 'No URL')}")
                
                return all_results[:limit]
            
            # Regular search for other queries
            # Prepare the site filter
            site_filter = ""
            params = [query]
            
            if site_id is not None:
                # Ensure site_id is an integer
                try:
                    site_id = int(site_id)
                    site_filter = "AND p.site_id = %s"
                    params.append(site_id)
                except (ValueError, TypeError):
                    print_error(f"Invalid site_id: {site_id}, must be an integer")
            
            # Add the limit parameter
            params.append(limit * 2)  # Get more results initially
            
            # Try different search approaches
            # First, try exact title match
            title_query = f"""
            SELECT 
                p.id, p.site_id, s.name as site_name, p.url, p.title, 
                p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                p.parent_id, parent.title as parent_title,
                1.0 AS rank
            FROM 
                crawl_pages p
                JOIN crawl_sites s ON p.site_id = s.id
                LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
            WHERE 
                p.title ILIKE %s
                {site_filter}
            ORDER BY 
                p.is_chunk ASC
            LIMIT %s
            """
            
            title_params = ['%' + query + '%']
            if site_id is not None:
                title_params.append(site_id)
            title_params.append(limit)
            
            cur.execute(title_query, title_params)
            title_results = []
            
            columns = [desc[0] for desc in cur.description]
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                # Convert any JSON fields from string to dict
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                
                # Add context about chunking
                if result.get('is_chunk'):
                    result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                
                title_results.append(result)
            
            if title_results:
                print_info(f"Found {len(title_results)} results with title match")
                # Log some results for debugging
                for i, result in enumerate(title_results[:3]):
                    print_info(f"Title match {i+1}: {result.get('title', 'No title')}")
                    print_info(f"  URL: {result.get('url', 'No URL')}")
                
                return title_results[:limit]
            
            # If no title matches, try full-text search
            # Search using PostgreSQL full-text search with ranking
            search_query = f"""
            SELECT 
                p.id, p.site_id, s.name as site_name, p.url, p.title, 
                p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                p.parent_id, parent.title as parent_title,
                ts_rank_cd(to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')), 
                          plainto_tsquery('english', %s)) AS rank
            FROM 
                crawl_pages p
                JOIN crawl_sites s ON p.site_id = s.id
                LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
            WHERE 
                to_tsvector('english', COALESCE(p.title, '') || ' ' || COALESCE(p.content, '')) @@ plainto_tsquery('english', %s)
                {site_filter}
            ORDER BY 
                rank DESC,
                p.is_chunk ASC
            LIMIT %s
            """
            
            # Add the query again for ts_rank_cd
            params.insert(0, query)
            
            cur.execute(search_query, params)
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            all_results = []
            
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                # Convert any JSON fields from string to dict
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                
                # Add context about chunking
                if result.get('is_chunk'):
                    result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                
                all_results.append(result)
            
            print_info(f"Full-text search found {len(all_results)} results")
            
            # If no results from full-text search, try a more relaxed search
            if not all_results:
                print_warning("No results from full-text search, trying ILIKE search")
                
                # Try a more relaxed search with ILIKE
                ilike_query = f"""
                SELECT 
                    p.id, p.site_id, s.name as site_name, p.url, p.title, 
                    p.content, p.summary, p.metadata, p.is_chunk, p.chunk_index,
                    p.parent_id, parent.title as parent_title,
                    0.5 AS rank
                FROM 
                    crawl_pages p
                    JOIN crawl_sites s ON p.site_id = s.id
                    LEFT JOIN crawl_pages parent ON p.parent_id = parent.id
                WHERE 
                    (p.title ILIKE %s OR p.content ILIKE %s)
                    {site_filter}
                ORDER BY 
                    p.is_chunk ASC
                LIMIT %s
                """
                
                ilike_params = ['%' + query + '%', '%' + query + '%']
                if site_id is not None:
                    ilike_params.append(site_id)
                ilike_params.append(limit)
                
                cur.execute(ilike_query, ilike_params)
                
                columns = [desc[0] for desc in cur.description]
                for row in cur.fetchall():
                    result = dict(zip(columns, row))
                    # Convert any JSON fields from string to dict
                    if result.get('metadata') and isinstance(result['metadata'], str):
                        result['metadata'] = json.loads(result['metadata'])
                    
                    # Add context about chunking
                    if result.get('is_chunk'):
                        result['context'] = f"From: {result.get('parent_title') or 'Parent Document'} (Part {result.get('chunk_index', 0) + 1})"
                    
                    all_results.append(result)
                
                print_info(f"ILIKE search found {len(all_results)} results")
            
            # Log some results for debugging
            for i, result in enumerate(all_results[:3]):
                print_info(f"Result {i+1}: {result.get('title', 'No title')} - Rank: {result.get('rank', 0)}")
                print_info(f"  URL: {result.get('url', 'No URL')}")
            
            return all_results[:limit]
            
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
            print_info(f"Searching with embedding of length: {len(embedding)}")
            print_info(f"Similarity threshold: {threshold}")
            
            # Ensure site_id is an integer if provided
            if site_id is not None:
                try:
                    site_id = int(site_id)
                except (ValueError, TypeError):
                    print_error(f"Invalid site_id: {site_id}, must be an integer")
                    site_id = None
            
            # First, check if any embeddings exist in the database
            site_filter = ""
            params = []
            
            if site_id is not None:
                site_filter = "AND site_id = %s"
                params.append(site_id)
            
            cur.execute(f"SELECT COUNT(*) FROM crawl_pages WHERE embedding IS NOT NULL {site_filter}", params)
            count = cur.fetchone()[0]
            print_info(f"Found {count} pages with embeddings in the database")
            
            if count == 0:
                print_warning("No embeddings found in database, falling back to text search")
                return []
            
            # Check if pgvector extension is installed
            try:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                pgvector_installed = cur.fetchone() is not None
                
                if not pgvector_installed:
                    print_error("pgvector extension is not installed in the database")
                    return []
                
                # Check the type of the embedding column
                cur.execute("SELECT pg_typeof(embedding) FROM crawl_pages WHERE embedding IS NOT NULL LIMIT 1")
                embedding_type = cur.fetchone()[0]
                print_info(f"Embedding column type: {embedding_type}")
                
                # Check if the type is actually 'vector'
                if embedding_type != 'vector':
                    print_error(f"Embedding column is not of type 'vector' but '{embedding_type}'. Vector search may not work.")
                    return []
                
            except Exception as e:
                print_error(f"Error checking database configuration: {e}")
                return []
            
            # Format the embedding as a string with square brackets for pgvector
            embedding_str = f"[{','.join(str(x) for x in embedding)}]"
            
            # Try to perform a vector similarity search
            try:
                # Get the top results regardless of threshold initially
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
                        1 - (p.embedding <=> %s::vector) DESC
                    LIMIT %s
                    """
                    params = [embedding_str, site_id, embedding_str, limit * 2]  # Get more results initially
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
                        1 - (p.embedding <=> %s::vector) DESC
                    LIMIT %s
                    """
                    params = [embedding_str, embedding_str, limit * 2]  # Get more results initially
                
                print_info(f"Executing vector search query...")
                cur.execute(search_query, params)
                
                # Get all results first for debugging
                all_rows = cur.fetchall()
                print_info(f"Vector search found {len(all_rows)} total results")
                
                # Show similarity distribution for debugging
                if all_rows:
                    similarities = [row[12] for row in all_rows]
                    min_sim = min(similarities)
                    max_sim = max(similarities)
                    avg_sim = sum(similarities) / len(similarities)
                    print_info(f"Similarity range: {min_sim:.4f} to {max_sim:.4f}, average: {avg_sim:.4f}")
                
                # Filter results by threshold
                results = []
                for row in all_rows:
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
                
                # Log the similarity scores for debugging
                if results:
                    print_info(f"Vector search found {len(results)} results above threshold {threshold}")
                    for i, result in enumerate(results[:3]):
                        print_info(f"Result {i+1}: {result.get('title', 'No title')} - Similarity: {result.get('similarity', 0):.4f}")
                else:
                    print_warning(f"Vector search found {len(all_rows)} results, but none above threshold {threshold}")
                    # Show the top results anyway for debugging
                    for i, row in enumerate(all_rows[:3]):
                        similarity = row[12]
                        title = row[4] or "Untitled"
                        print_info(f"Top result {i+1}: {title} - Similarity: {similarity:.4f} (below threshold {threshold})")
                
                return results
                
            except Exception as e:
                print_error(f"Error in vector search: {e}")
                return []
                
        except Exception as e:
            print_error(f"Error in search_by_embedding: {e}")
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
            
            # First try vector search with a lower threshold to get more results
            print_info(f"Performing vector search with threshold {threshold}...")
            vector_threshold = max(threshold * 0.7, 0.2)  # Lower threshold for vector search, but not below 0.2
            print_info(f"Adjusted vector threshold to {vector_threshold}")
            vector_results = self.search_by_embedding(embedding, vector_threshold, limit * 2, site_id)
            
            if vector_results:
                print_info(f"Vector search found {len(vector_results)} results")
                
                # Log the top results for debugging
                for i, result in enumerate(vector_results[:3]):
                    print_info(f"Top vector result {i+1}: {result.get('title', 'No title')} - Similarity: {result.get('similarity', 0):.4f}")
                
                # Return vector results if we found enough
                if len(vector_results) >= limit:
                    return vector_results[:limit]
            else:
                print_warning("Vector search found no results")
            
            # Also try text search
            print_info("Performing text search...")
            text_results = self.search_by_text(query, limit * 2, site_id)
            
            if text_results:
                print_info(f"Text search found {len(text_results)} results")
                
                # Add similarity scores to text results
                for result in text_results:
                    result['similarity'] = 0.65  # Increased default similarity for text results
                    result['vector_score'] = 0.0
                    result['text_score'] = 0.65  # Increased text score
                
                # If we have no vector results, return text results
                if not vector_results:
                    return text_results[:limit]
            else:
                print_warning("Text search found no results")
                
                # If both searches failed, return empty list
                if not vector_results:
                    return []
            
            # Combine results from both searches
            print_info("Combining vector and text search results...")
            
            # Create a dictionary to track unique results by URL
            combined_results = {}
            
            # Add vector results to the combined results
            for result in vector_results:
                url = result.get('url', '')
                if url:
                    result['vector_score'] = result.get('similarity', 0)
                    result['text_score'] = 0.0
                    combined_results[url] = result
            
            # Add text results to the combined results, merging with vector results if needed
            for result in text_results:
                url = result.get('url', '')
                if url:
                    if url in combined_results:
                        # Update existing result with text score
                        combined_results[url]['text_score'] = 0.65  # Increased text score
                        # Recalculate combined similarity score (weighted average with higher weight for text)
                        vector_score = combined_results[url].get('vector_score', 0)
                        # Give text matches more weight in the combined score
                        combined_results[url]['similarity'] = max(vector_score, 0.65)  # Use max instead of average to prioritize matches
                    else:
                        # Add new result
                        result['vector_score'] = 0.0
                        result['text_score'] = 0.65  # Increased text score
                        result['similarity'] = 0.65
                        combined_results[url] = result
            
            # Convert dictionary to list and sort by similarity
            results = list(combined_results.values())
            results.sort(key=lambda x: x.get('similarity', 0), reverse=True)
            
            print_info(f"Combined search found {len(results)} results")
            
            # Return the top results
            return results[:limit]
            
        except Exception as e:
            print_error(f"Error in hybrid search: {e}")
            # Fall back to text search
            return self.search_by_text(query, limit, site_id)
        finally:
            if conn:
                conn.close()
    
    def get_site_by_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Get a site by URL.
        
        Args:
            url: The URL of the site to get.
            
        Returns:
            The site, or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the site
            cur.execute(
                """
                SELECT id, name, url, description, created_at, updated_at 
                FROM crawl_sites 
                WHERE url = %s
                """,
                (url,)
            )
            
            # Get the result
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'url': row[2],
                    'description': row[3],
                    'created_at': row[4],
                    'updated_at': row[5]
                }
            
            return None
        finally:
            if conn:
                conn.close()
    
    def get_site_by_id(self, site_id: int) -> Optional[Dict[str, Any]]:
        """Get a site by ID.
        
        Args:
            site_id: The ID of the site to get.
            
        Returns:
            The site, or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the site
            cur.execute(
                """
                SELECT id, name, url, description, created_at, updated_at 
                FROM crawl_sites 
                WHERE id = %s
                """,
                (site_id,)
            )
            
            # Get the result
            row = cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'url': row[2],
                    'description': row[3],
                    'created_at': row[4],
                    'updated_at': row[5]
                }
            
            return None
        finally:
            if conn:
                conn.close()
    
    def get_page_count_by_site_id(self, site_id: int, include_chunks: bool = False) -> int:
        """Get the number of pages for a specific site.
        
        Args:
            site_id: The ID of the site.
            include_chunks: Whether to include chunks in the count.
            
        Returns:
            The number of pages.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            if include_chunks:
                # Count all pages including chunks
                cur.execute(
                    "SELECT COUNT(*) FROM crawl_pages WHERE site_id = %s",
                    (site_id,)
                )
            else:
                # Count only parent pages (not chunks)
                cur.execute(
                    "SELECT COUNT(*) FROM crawl_pages WHERE site_id = %s AND is_chunk = FALSE",
                    (site_id,)
                )
            
            result = cur.fetchone()
            return result[0] if result else 0
            
        except Exception as e:
            print_error(f"Error getting page count by site ID: {e}")
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
                    p.created_at, p.updated_at,
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
                    id, site_id, url, title, content, summary, metadata,
                    created_at, updated_at,
                    is_chunk, chunk_index, parent_id
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
                page_dict = dict(zip(columns, row))
                
                # Convert datetime objects to strings
                if 'created_at' in page_dict and page_dict['created_at'] is not None:
                    if not isinstance(page_dict['created_at'], str):
                        page_dict['created_at'] = page_dict['created_at'].isoformat()
                
                if 'updated_at' in page_dict and page_dict['updated_at'] is not None:
                    if not isinstance(page_dict['updated_at'], str):
                        page_dict['updated_at'] = page_dict['updated_at'].isoformat()
                
                results.append(page_dict)
            
            return results
        except Exception as e:
            print(f"Error getting pages for site {site_id}: {e}")
            return []
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
                SELECT id, name, url, description, created_at, updated_at 
                FROM crawl_sites
                ORDER BY created_at DESC
                """
            )
            
            # Convert results to dictionaries
            sites = []
            for row in cur.fetchall():
                sites.append({
                    'id': row[0],
                    'name': row[1],
                    'url': row[2],
                    'description': row[3],
                    'created_at': row[4],
                    'updated_at': row[5]
                })
            
            return sites
            
        except Exception as e:
            print_error(f"Error getting all sites: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def get_urls_by_site_name(self, site_name_pattern: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get URLs from sites matching a name pattern.
        
        Args:
            site_name_pattern: Pattern to match against site names.
            limit: Maximum number of results to return.
            
        Returns:
            List of pages with their URLs.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Find site IDs matching the pattern
            site_query = """
            SELECT id, name 
            FROM crawl_sites 
            WHERE name ILIKE %s
            """
            cur.execute(site_query, [f'%{site_name_pattern}%'])
            sites = cur.fetchall()
            
            if not sites:
                print_info(f"No sites found matching pattern: {site_name_pattern}")
                return []
            
            site_ids = [site[0] for site in sites]
            site_names = [site[1] for site in sites]
            print_info(f"Found {len(sites)} sites matching pattern: {', '.join(site_names)}")
            
            # Get URLs from these sites
            placeholders = ', '.join(['%s'] * len(site_ids))
            url_query = f"""
            SELECT 
                p.id, p.site_id, s.name as site_name, p.url, p.title, 
                p.summary
            FROM 
                crawl_pages p
                JOIN crawl_sites s ON p.site_id = s.id
            WHERE 
                p.site_id IN ({placeholders})
                AND p.is_chunk = FALSE
            ORDER BY 
                p.id DESC
            LIMIT %s
            """
            
            params = site_ids + [limit]
            cur.execute(url_query, params)
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            results = []
            
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                results.append(result)
            
            print_info(f"Found {len(results)} URLs from sites matching pattern: {site_name_pattern}")
            return results
            
        except Exception as e:
            print_error(f"Error getting URLs by site name: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def clear_all_conversation_history(self) -> bool:
        """Clear all conversation history from the database.
        
        Returns:
            True if successful, False otherwise.
        """
        try:
            with self._get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM chat_conversations")
                    conn.commit()
                    return True
        except Exception as e:
            print(f"Error clearing all conversation history: {e}")
            return False
    
    def get_page_by_id(self, page_id: int) -> Optional[Dict[str, Any]]:
        """Get a page by ID.
        
        Args:
            page_id: The ID of the page to get.
            
        Returns:
            The page with full content, or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the page with all fields including content
            query = """
            SELECT 
                id, site_id, url, title, content, summary, 
                metadata, is_chunk, chunk_index, parent_id,
                created_at, updated_at
            FROM 
                crawl_pages
            WHERE 
                id = %s
            """
            
            cur.execute(query, (page_id,))
            
            # Get the result
            row = cur.fetchone()
            if not row:
                return None
                
            # Convert to dictionary
            columns = [desc[0] for desc in cur.description]
            result = dict(zip(columns, row))
            
            # Convert any JSON fields from string to dict
            if result.get('metadata') and isinstance(result['metadata'], str):
                result['metadata'] = json.loads(result['metadata'])
            
            # Convert datetime objects to strings
            if result.get('created_at') and not isinstance(result['created_at'], str):
                result['created_at'] = str(result['created_at'])
            if result.get('updated_at') and not isinstance(result['updated_at'], str):
                result['updated_at'] = str(result['updated_at'])
                
            return result
            
        except Exception as e:
            print_error(f"Error getting page by ID: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_chunks_by_parent_id(self, parent_id: int) -> List[Dict[str, Any]]:
        """Get all chunks for a specific parent page.
        
        Args:
            parent_id: The ID of the parent page.
            
        Returns:
            List of chunks for the parent page.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get all chunks for this parent
            query = """
            SELECT 
                id, site_id, url, title, content, summary, 
                metadata, is_chunk, chunk_index, parent_id,
                created_at, updated_at
            FROM 
                crawl_pages
            WHERE 
                parent_id = %s
            ORDER BY
                chunk_index
            """
            
            cur.execute(query, (parent_id,))
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            results = []
            
            for row in cur.fetchall():
                result = dict(zip(columns, row))
                # Convert any JSON fields from string to dict
                if result.get('metadata') and isinstance(result['metadata'], str):
                    result['metadata'] = json.loads(result['metadata'])
                
                # Convert datetime objects to strings
                if result.get('created_at') and not isinstance(result['created_at'], str):
                    result['created_at'] = str(result['created_at'])
                if result.get('updated_at') and not isinstance(result['updated_at'], str):
                    result['updated_at'] = str(result['updated_at'])
                
                results.append(result)
            
            return results
            
        except Exception as e:
            print_error(f"Error getting chunks by parent ID: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    # User Preferences Methods
    
    def save_user_preference(self, user_id: str, preference_type: str, preference_value: str, 
                            context: Optional[str] = None, confidence: float = 0.8,
                            source_session: Optional[str] = None, 
                            metadata: Optional[Dict[str, Any]] = None) -> int:
        """Save or update a user preference.
        
        Args:
            user_id: The user ID.
            preference_type: The type of preference (e.g., 'like', 'dislike', 'trait').
            preference_value: The value of the preference.
            context: Optional context for the preference.
            confidence: Confidence score (0-1) for the preference.
            source_session: Optional session ID where the preference was detected.
            metadata: Optional additional metadata.
            
        Returns:
            The ID of the preference.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Use the database function to update or insert the preference
            cur.execute(
                """
                SELECT * FROM update_user_preference(
                    %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    user_id,
                    preference_type,
                    preference_value,
                    context,
                    confidence,
                    source_session,
                    Json(metadata) if metadata else None
                )
            )
            
            # Get the result
            result = cur.fetchone()
            conn.commit()
            
            # Return the ID
            return result[0] if result else -1
            
        except Exception as e:
            print_error(f"Error saving user preference: {e}")
            if conn:
                conn.rollback()
            return -1
        finally:
            if conn:
                conn.close()
    
    def get_user_preferences(self, user_id: str, min_confidence: float = 0.0, 
                            active_only: bool = True) -> List[Dict[str, Any]]:
        """Get preferences for a user.
        
        Args:
            user_id: The user ID.
            min_confidence: Minimum confidence score (0-1) for preferences to return.
            active_only: Whether to return only active preferences.
            
        Returns:
            List of user preferences.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Use the database function to get preferences
            cur.execute(
                """
                SELECT * FROM get_user_preferences(%s, %s, %s)
                """,
                (user_id, min_confidence, active_only)
            )
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            preferences = []
            
            for row in cur.fetchall():
                preference = dict(zip(columns, row))
                
                # Convert metadata from JSON to dict if it exists
                if preference.get('metadata') and isinstance(preference['metadata'], str):
                    preference['metadata'] = json.loads(preference['metadata'])
                
                preferences.append(preference)
            
            return preferences
            
        except Exception as e:
            print_error(f"Error getting user preferences: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def deactivate_user_preference(self, preference_id: int) -> bool:
        """Deactivate a user preference.
        
        Args:
            preference_id: The ID of the preference to deactivate.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Update the preference
            cur.execute(
                """
                UPDATE user_preferences
                SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (preference_id,)
            )
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error deactivating user preference: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def activate_user_preference(self, preference_id: int) -> bool:
        """Activate a user preference.
        
        Args:
            preference_id: The ID of the preference to activate.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Update the preference
            cur.execute(
                """
                UPDATE user_preferences
                SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (preference_id,)
            )
            
            conn.commit()
            return cur.rowcount > 0
        except Exception as e:
            print(f"Error activating user preference: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def delete_user_preference(self, preference_id: int) -> bool:
        """Delete a user preference.
        
        Args:
            preference_id: The ID of the preference to delete.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Delete the preference
            cur.execute(
                """
                DELETE FROM user_preferences
                WHERE id = %s
                """,
                (preference_id,)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            print_error(f"Error deleting user preference: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_preference_by_id(self, preference_id: int) -> Optional[Dict[str, Any]]:
        """Get a preference by ID.
        
        Args:
            preference_id: The ID of the preference to get.
            
        Returns:
            The preference, or None if not found.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the preference
            cur.execute(
                """
                SELECT 
                    id, user_id, preference_type, preference_value, 
                    context, confidence, created_at, updated_at,
                    last_used, source_session, is_active, metadata
                FROM user_preferences
                WHERE id = %s
                """,
                (preference_id,)
            )
            
            # Get the result
            row = cur.fetchone()
            if not row:
                return None
                
            # Convert to dictionary
            columns = [desc[0] for desc in cur.description]
            preference = dict(zip(columns, row))
            
            # Convert metadata from JSON to dict if it exists
            if preference.get('metadata') and isinstance(preference['metadata'], str):
                preference['metadata'] = json.loads(preference['metadata'])
            
            # Convert datetime objects to strings
            for date_field in ['created_at', 'updated_at', 'last_used']:
                if preference.get(date_field) and not isinstance(preference[date_field], str):
                    preference[date_field] = str(preference[date_field])
                
            return preference
            
        except Exception as e:
            print_error(f"Error getting preference by ID: {e}")
            return None
        finally:
            if conn:
                conn.close()
    
    def update_preference_last_used(self, preference_id: int) -> bool:
        """Update the last_used timestamp for a preference.
        
        Args:
            preference_id: The ID of the preference to update.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Update the preference
            cur.execute(
                """
                UPDATE user_preferences
                SET last_used = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (preference_id,)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            print_error(f"Error updating preference last_used: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def get_preferences_by_type(self, user_id: str, preference_type: str, 
                               min_confidence: float = 0.0) -> List[Dict[str, Any]]:
        """Get preferences of a specific type for a user.
        
        Args:
            user_id: The user ID.
            preference_type: The type of preference to get.
            min_confidence: Minimum confidence score (0-1) for preferences to return.
            
        Returns:
            List of user preferences of the specified type.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Get the preferences
            cur.execute(
                """
                SELECT 
                    id, preference_type, preference_value, context, 
                    confidence, last_used, metadata
                FROM user_preferences
                WHERE 
                    user_id = %s 
                    AND preference_type = %s
                    AND confidence >= %s
                    AND is_active = TRUE
                ORDER BY confidence DESC, last_used DESC
                """,
                (user_id, preference_type, min_confidence)
            )
            
            # Convert results to dictionaries
            columns = [desc[0] for desc in cur.description]
            preferences = []
            
            for row in cur.fetchall():
                preference = dict(zip(columns, row))
                
                # Convert metadata from JSON to dict if it exists
                if preference.get('metadata') and isinstance(preference['metadata'], str):
                    preference['metadata'] = json.loads(preference['metadata'])
                
                preferences.append(preference)
            
            return preferences
            
        except Exception as e:
            print_error(f"Error getting preferences by type: {e}")
            return []
        finally:
            if conn:
                conn.close()
    
    def clear_user_preferences(self, user_id: str) -> bool:
        """Clear all preferences for a user.
        
        Args:
            user_id: The user ID.
            
        Returns:
            True if successful, False otherwise.
        """
        conn = None
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            
            # Delete the preferences
            cur.execute(
                """
                DELETE FROM user_preferences
                WHERE user_id = %s
                """,
                (user_id,)
            )
            
            conn.commit()
            return True
            
        except Exception as e:
            print_error(f"Error clearing user preferences: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def direct_keyword_search(self, query, limit=5, site_patterns=None):
        """
        Performs a direct keyword search focused on finding specific technical terms or project names.
        This is optimized for finding exact matches to specific terms in titles and content.
        
        Args:
            query: The search query (specific term, project name, etc.)
            limit: Maximum number of results to return
            site_patterns: List of site name patterns to filter by
            
        Returns:
            List of matching results
        """
        try:
            # Get a new connection for this operation
            conn = self._get_connection()
            
            # Create a cursor from the connection
            with conn.cursor() as cur:
                # Clean the query for SQL safety - replace quote characters and escape special chars
                clean_query = query.strip().lower().replace("'", "''")
                
                # Create site filter if provided
                site_filter = ""
                site_params = []
                
                if site_patterns and len(site_patterns) > 0:
                    site_conditions = []
                    for i, pattern in enumerate(site_patterns):
                        site_conditions.append(f"s.name ILIKE %s")
                        site_params.append(f"%{pattern}%")
                    site_filter = f"AND ({' OR '.join(site_conditions)})"
                
                # Check if the query looks like a domain name
                is_domain_name = bool(re.search(r'([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}', clean_query))
                
                # Different query approach for domain names vs. regular terms
                if is_domain_name:
                    print_info(f"Query appears to be a domain name: {clean_query}")
                    
                    # Try to match against site names in the database
                    site_query = f"""
                    SELECT 
                        id, name, url, description 
                    FROM crawl_sites 
                    WHERE 
                        name ILIKE %s OR 
                        url ILIKE %s
                    LIMIT 5
                    """
                    
                    cur.execute(site_query, [f"%{clean_query}%", f"%{clean_query}%"])
                    site_matches = cur.fetchall()
                    print_info(f"Found {len(site_matches)} matching sites")
                    
                    if site_matches:
                        # Get site IDs for found sites
                        site_ids = [site[0] for site in site_matches]
                        site_names = {site[0]: site[1] for site in site_matches}
                        
                        # Build a query to get pages from these sites
                        pages_query = f"""
                        SELECT 
                            p.id, 
                            p.url, 
                            p.title,
                            p.site_id,
                            p.content,
                            s.name as site_name,
                            p.summary,
                            1.0 as similarity,
                            'site_match' as match_type
                        FROM crawl_pages p
                        JOIN crawl_sites s ON p.site_id = s.id
                        WHERE 
                            p.site_id IN ({','.join([str(id) for id in site_ids])})
                        ORDER BY p.id DESC
                        LIMIT {limit}
                        """
                        
                        cur.execute(pages_query)
                        result = cur.fetchall()
                        print_info(f"Found {len(result)} pages from matching sites")
                        
                        # Convert to list of dictionaries
                        results = []
                        columns = [desc[0] for desc in cur.description]
                        
                        for row in result:
                            item = dict(zip(columns, row))
                            
                            # Mark as a direct keyword result
                            item["is_keyword_result"] = True
                            item["is_site_result"] = True
                            
                            # Ensure all required keys are present
                            for key in ["url", "title", "content", "site_name", "similarity"]:
                                if key not in item or item[key] is None:
                                    item[key] = "" if key != "similarity" else 0.0
                            
                            # Add site information
                            site_id = item.get("site_id")
                            if site_id and site_id in site_names:
                                item["site_name"] = site_names[site_id]
                            
                            results.append(item)
                        
                        return results
                
                # Build parameter list for regular search
                params = [f"%{clean_query}%", f"%{clean_query}%"]
                params.extend(site_params)
                params.extend(site_params)  # Add again for the second query
                
                # Use parameterized query to prevent SQL injection
                sql = f"""
                WITH page_matches AS (
                    -- Search for exact title matches first (highest priority)
                    SELECT 
                        p.id, 
                        p.url, 
                        p.title,
                        p.site_id,
                        p.content,
                        s.name as site_name,
                        p.summary,
                        1.0 as similarity,
                        'title_exact' as match_type
                    FROM crawl_pages p
                    JOIN crawl_sites s ON p.site_id = s.id
                    WHERE 
                        LOWER(p.title) LIKE %s
                        {site_filter}
                    
                    UNION
                    
                    -- Then search for exact content matches
                    SELECT 
                        p.id, 
                        p.url, 
                        p.title,
                        p.site_id,
                        p.content,
                        s.name as site_name,
                        p.summary,
                        0.9 as similarity,
                        'content_exact' as match_type
                    FROM crawl_pages p
                    JOIN crawl_sites s ON p.site_id = s.id
                    WHERE 
                        LOWER(p.content) LIKE %s
                        {site_filter}
                )
                
                SELECT * FROM page_matches
                ORDER BY similarity DESC, id DESC
                LIMIT {limit};
                """
                
                print_info(f"Executing direct keyword search for: {clean_query}")
                
                # Execute the query with parameters
                cur.execute(sql, params)
                result = cur.fetchall()
                print_info(f"Found {len(result)} direct keyword matches")
                
                # Convert to list of dictionaries
                results = []
                columns = [desc[0] for desc in cur.description]
                
                for row in result:
                    item = dict(zip(columns, row))
                    
                    # Mark as a direct keyword result
                    item["is_keyword_result"] = True
                    
                    # Ensure all required keys are present
                    for key in ["url", "title", "content", "site_name", "similarity"]:
                        if key not in item or item[key] is None:
                            item[key] = "" if key != "similarity" else 0.0
                    
                    results.append(item)
                
                return results
                
        except Exception as e:
            print_error(f"Error in direct_keyword_search: {e}")
            import traceback
            print_error(traceback.format_exc())
            return []
            
        finally:
            # Close the connection properly
            if 'conn' in locals() and conn:
                conn.close() 