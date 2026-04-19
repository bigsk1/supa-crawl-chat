import os
import re
import psycopg2
from urllib.parse import urlparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Parse database connection parameters from environment variables
def get_db_params():
    """Get database connection parameters from environment variables."""
    # Check if a PostgreSQL connection string is provided
    db_url = os.getenv('SUPABASE_URL')

    if db_url and db_url.startswith('postgresql://'):
        # Parse PostgreSQL connection string
        # Format: postgresql://user:password@host:port/database
        pattern = r'postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)'
        match = re.match(pattern, db_url)

        if match:
            user, password, host, port, database = match.groups()
            return {
                'host': host,
                'port': int(port),
                'database': database,
                'user': user,
                'password': password
            }

    # Check if a full URL is provided (backward compatibility)
    supabase_url = os.getenv('SUPABASE_URL')

    if supabase_url:
        # Parse the URL if it's a full URL with protocol
        if supabase_url.startswith('http://') or supabase_url.startswith('https://'):
            parsed_url = urlparse(supabase_url)
            host = parsed_url.hostname
            port = parsed_url.port or 5432  # Default PostgreSQL port
        else:
            # Handle case where URL is just host:port without protocol
            parts = supabase_url.split(':')
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 5432

        # Use DB_USER if provided, otherwise fall back to SUPABASE_KEY
        user = os.getenv('DB_USER') or os.getenv('SUPABASE_KEY', 'postgres')

        return {
            'host': host,
            'port': port,
            'database': os.getenv('SUPABASE_DB', 'postgres'),
            'user': user,
            'password': os.getenv('SUPABASE_PASSWORD', 'postgres')
        }
    else:
        # Use individual components if no URL is provided (local development)
        return {
            'host': os.getenv('SUPABASE_HOST', '192.168.70.90'),
            'port': int(os.getenv('SUPABASE_PORT', '54322')),
            'database': os.getenv('SUPABASE_DB', 'postgres'),
            'user': os.getenv('DB_USER') or os.getenv('SUPABASE_KEY', 'postgres'),
            'password': os.getenv('SUPABASE_PASSWORD', 'postgres')
        }

# Get database connection parameters
db_params = get_db_params()

# SQL statements to set up the database
setup_statements = [
    # Enable the vector extension
    "CREATE EXTENSION IF NOT EXISTS vector;",

    # Create a table for crawled sites
    """
    CREATE TABLE IF NOT EXISTS crawl_sites (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        url TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    # Create a table for crawled pages with vector embeddings
    """
    CREATE TABLE IF NOT EXISTS crawl_pages (
        id SERIAL PRIMARY KEY,
        site_id INTEGER REFERENCES crawl_sites(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        title TEXT,
        content TEXT,
	        summary TEXT,
	        embedding vector(1536),
	        metadata JSONB,
	        content_hash TEXT,
	        is_chunk BOOLEAN DEFAULT FALSE,
        chunk_index INTEGER,
        parent_id INTEGER REFERENCES crawl_pages(id) ON DELETE CASCADE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """,

    # Create user_preferences table for enhanced memory system
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        id SERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        preference_type TEXT NOT NULL,
        preference_value TEXT NOT NULL,
        context TEXT,
        confidence FLOAT CHECK (confidence >= 0 AND confidence <= 1),
        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        last_used TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        source_session TEXT,
        is_active BOOLEAN DEFAULT TRUE,
        metadata JSONB
    );
    """,

    # Create indexes for user_preferences
    """
    CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
    CREATE INDEX IF NOT EXISTS idx_user_preferences_type ON user_preferences(preference_type);
    CREATE INDEX IF NOT EXISTS idx_user_preferences_last_used ON user_preferences(last_used);
    CREATE INDEX IF NOT EXISTS idx_user_preferences_confidence ON user_preferences(confidence);
    """,

    # Create function to merge preference contexts
    """
    CREATE OR REPLACE FUNCTION merge_preference_contexts(old_context TEXT, new_context TEXT)
    RETURNS TEXT
    LANGUAGE plpgsql
    AS $$
    BEGIN
        IF old_context IS NULL THEN
            RETURN new_context;
        ELSIF new_context IS NULL THEN
            RETURN old_context;
        ELSE
            RETURN old_context || ' | ' || new_context;
        END IF;
    END;
    $$;
    """,

    # Create function to update user preference
    """
    CREATE OR REPLACE FUNCTION update_user_preference(
        p_user_id TEXT,
        p_preference_type TEXT,
        p_preference_value TEXT,
        p_context TEXT,
        p_confidence FLOAT,
        p_source_session TEXT,
        p_metadata JSONB
    )
    RETURNS user_preferences
    LANGUAGE plpgsql
    AS $$
    DECLARE
        v_preference user_preferences;
    BEGIN
        -- Try to update existing preference
        UPDATE user_preferences
        SET
            confidence = GREATEST(confidence, p_confidence),
            context = merge_preference_contexts(context, p_context),
            last_used = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            metadata = COALESCE(metadata, '{}'::jsonb) || COALESCE(p_metadata, '{}'::jsonb)
        WHERE
            user_id = p_user_id
            AND preference_type = p_preference_type
            AND preference_value = p_preference_value
        RETURNING * INTO v_preference;

        -- If no row was updated, insert new preference
        IF v_preference IS NULL THEN
            INSERT INTO user_preferences (
                user_id,
                preference_type,
                preference_value,
                context,
                confidence,
                source_session,
                metadata
            )
            VALUES (
                p_user_id,
                p_preference_type,
                p_preference_value,
                p_context,
                p_confidence,
                p_source_session,
                p_metadata
            )
            RETURNING * INTO v_preference;
        END IF;

        RETURN v_preference;
    END;
    $$;
    """,

    # Create function to get user preferences
    """
    CREATE OR REPLACE FUNCTION get_user_preferences(
        p_user_id TEXT,
        p_min_confidence FLOAT DEFAULT 0.0,
        p_active_only BOOLEAN DEFAULT TRUE
    )
    RETURNS TABLE (
        id INTEGER,
        user_id TEXT,
        preference_type TEXT,
        preference_value TEXT,
        context TEXT,
        confidence FLOAT,
        created_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE,
        last_used TIMESTAMP WITH TIME ZONE,
        source_session TEXT,
        is_active BOOLEAN,
        metadata JSONB
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT
            up.id,
            up.user_id,
            up.preference_type,
            up.preference_value,
            up.context,
            up.confidence,
            up.created_at,
            up.updated_at,
            up.last_used,
            up.source_session,
            up.is_active,
            up.metadata
        FROM user_preferences up
        WHERE
            up.user_id = p_user_id
            AND up.confidence >= p_min_confidence
            AND (NOT p_active_only OR up.is_active = TRUE)
        ORDER BY up.confidence DESC, up.last_used DESC;
    END;
    $$;
    """,

    # Create function for similarity search
    """
    CREATE OR REPLACE FUNCTION match_page_embeddings(
        query_embedding VECTOR(1536),
        match_threshold FLOAT,
        match_count INT
    )
    RETURNS TABLE (
        id INTEGER,
        site_id INTEGER,
        url TEXT,
        title TEXT,
        content TEXT,
        summary TEXT,
        similarity FLOAT
    )
    LANGUAGE plpgsql
    AS $$
    BEGIN
        RETURN QUERY
        SELECT
            crawl_pages.id,
            crawl_pages.site_id,
            crawl_pages.url,
            crawl_pages.title,
            crawl_pages.content,
            crawl_pages.summary,
            1 - (crawl_pages.embedding <=> query_embedding) AS similarity
        FROM crawl_pages
        WHERE 1 - (crawl_pages.embedding <=> query_embedding) > match_threshold
        ORDER BY crawl_pages.embedding <=> query_embedding
        LIMIT match_count;
    END;
    $$;
    """,

    # Create an index for faster vector searches
    """
    CREATE INDEX IF NOT EXISTS crawl_pages_embedding_idx ON crawl_pages
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
    """,

    # Add indexes for better performance
    """
	    CREATE INDEX IF NOT EXISTS idx_pages_site_id ON crawl_pages(site_id);
	    CREATE INDEX IF NOT EXISTS idx_pages_url ON crawl_pages(url);
	    CREATE INDEX IF NOT EXISTS idx_pages_parent_id ON crawl_pages(parent_id);
	    CREATE INDEX IF NOT EXISTS idx_pages_is_chunk ON crawl_pages(is_chunk);
	    CREATE INDEX IF NOT EXISTS idx_pages_content_hash ON crawl_pages(content_hash);
	    """,

    # Create crawl job tracking table for durable crawl status
    """
    CREATE TABLE IF NOT EXISTS crawl_jobs (
        id SERIAL PRIMARY KEY,
        site_id INTEGER REFERENCES crawl_sites(id) ON DELETE CASCADE,
        url TEXT NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'queued',
        options JSONB,
        crawl4ai_task_id TEXT,
        pages_found INTEGER DEFAULT 0,
        pages_crawled INTEGER DEFAULT 0,
        chunks_created INTEGER DEFAULT 0,
        error TEXT,
        started_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP WITH TIME ZONE,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_site_id ON crawl_jobs(site_id);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_status ON crawl_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_crawl_jobs_updated_at ON crawl_jobs(updated_at DESC);
    """,

    # Create a function to update the updated_at timestamp
    """
    CREATE OR REPLACE FUNCTION update_updated_at_column()
    RETURNS TRIGGER AS $$
    BEGIN
        NEW.updated_at = CURRENT_TIMESTAMP;
        RETURN NEW;
    END;
    $$ language 'plpgsql'
    """,

    # Create triggers to update the updated_at column
    """
    DROP TRIGGER IF EXISTS update_sites_updated_at ON crawl_sites;
    CREATE TRIGGER update_sites_updated_at
    BEFORE UPDATE ON crawl_sites
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column()
    """,

    """
    DROP TRIGGER IF EXISTS update_pages_updated_at ON crawl_pages;
    CREATE TRIGGER update_pages_updated_at
    BEFORE UPDATE ON crawl_pages
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column()
    """,

    """
    DROP TRIGGER IF EXISTS update_preferences_updated_at ON user_preferences;
    CREATE TRIGGER update_preferences_updated_at
    BEFORE UPDATE ON user_preferences
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column()
    """
]

def setup_database():
    """Set up the database with the required tables and extensions."""
    conn = None
    try:
        # Connect to the database
        conn = psycopg2.connect(**db_params)
        conn.autocommit = True
        cur = conn.cursor()

        # Check if the vector extension is available
        try:
            cur.execute("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
            vector_available = cur.fetchone() is not None

            if not vector_available:
                print("WARNING: The 'vector' extension is not available in this PostgreSQL installation.")
                print("Vector search functionality will not work without it.")
                print("You may need to install the pgvector extension in your PostgreSQL instance.")
                print("For more information, visit: https://github.com/pgvector/pgvector")

                # Continue with setup but skip the vector extension
                setup_statements_no_vector = [stmt for stmt in setup_statements if "CREATE EXTENSION" not in stmt]

                # Modify the crawl_pages table to use TEXT instead of vector if needed
                for i, stmt in enumerate(setup_statements_no_vector):
                    if "CREATE TABLE IF NOT EXISTS crawl_pages" in stmt:
                        # Replace vector type with TEXT
                        setup_statements_no_vector[i] = re.sub(
                            r'embedding vector\(1536\)',
                            'embedding TEXT',
                            stmt
                        )

                # Execute the modified statements
                for statement in setup_statements_no_vector:
                    try:
                        cur.execute(statement)
                        print(f"Executed: {statement[:60]}...")
                    except Exception as e:
                        print(f"Error executing statement: {e}")
                        print(f"Statement: {statement}")

                print("Database setup completed with limited functionality (no vector search).")
                return
        except Exception as e:
            print(f"Error checking for vector extension: {e}")
            # Continue with normal setup

        # Execute all setup statements
        for statement in setup_statements:
            try:
                cur.execute(statement)
                print(f"Executed: {statement[:60]}...")
            except Exception as e:
                print(f"Error executing statement: {e}")
                print(f"Statement: {statement}")

        # Create indexes for better performance
        try:
            # Index for site_id in crawl_pages
            cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_pages_site_id ON crawl_pages(site_id);")

            # Index for parent_id in crawl_pages
            cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_pages_parent_id ON crawl_pages(parent_id);")

            # Index for is_chunk in crawl_pages
            cur.execute("CREATE INDEX IF NOT EXISTS idx_crawl_pages_is_chunk ON crawl_pages(is_chunk);")

            # Create a unique index on the URL to prevent duplicates
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_crawl_pages_url ON crawl_pages(url);")

            print("Created indexes for better performance.")
        except Exception as e:
            print(f"Error creating indexes: {e}")

        # Set up the conversation history table
        try:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_conversations (
                id SERIAL PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                user_id VARCHAR(255),
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                metadata JSONB
            );
            """)

            # Create indexes for the conversation history table
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_conversations_session_id ON chat_conversations(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_id ON chat_conversations(user_id);")

            print("✓ Conversation history table set up successfully")
        except Exception as e:
            print(f"Error setting up conversation history table: {e}")

        print("Database setup completed successfully.")

    except Exception as e:
        print(f"Error setting up database: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_database()
