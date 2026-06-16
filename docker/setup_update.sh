#!/bin/bash

# Create necessary directories
mkdir -p volumes/{db/data,db/init,api,shm}

# Ensure .env file exists and is not empty
if [ ! -s ".env" ]; then
  echo "Error: .env file is missing or empty. Please create it with the necessary environment variables."
  exit 1
fi

# Create the authentication roles script first (00-auth-roles.sql)
cat > volumes/db/init/001-auth-roles.sql << 'EOL'
-- Create all the necessary roles for Supabase and PostgREST
DO $$
BEGIN
  -- Create admin roles
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_admin') THEN
    CREATE ROLE supabase_admin WITH LOGIN SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS;
    RAISE NOTICE 'Created supabase_admin role';
  END IF;
  
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
    CREATE ROLE supabase_storage_admin WITH LOGIN;
    RAISE NOTICE 'Created supabase_storage_admin role';
  END IF;

  -- Grant privileges
  GRANT ALL PRIVILEGES ON DATABASE postgres TO supabase_admin;

  RAISE NOTICE 'All roles created and configured successfully';
END
$$;
EOL

# Create password setup script (99-set-passwords.sql)
cat > volumes/db/init/99-set-passwords.sql << 'EOL'
-- Set passwords for all database roles
DO $$
DECLARE
    postgres_password TEXT;
BEGIN
    -- Try to get the POSTGRES_PASSWORD environment variable
    BEGIN
        postgres_password := current_setting('postgres.password');
    EXCEPTION WHEN OTHERS THEN
        -- If there's an error, try a different approach
        BEGIN
            postgres_password := current_setting('env.POSTGRES_PASSWORD');
        EXCEPTION WHEN OTHERS THEN
            -- If still not found, use default
            postgres_password := 'StrongPassword123!';
            RAISE WARNING 'POSTGRES_PASSWORD environment variable not set, using default password';
        END;
    END;
    
    -- Set password for supabase_admin
    EXECUTE format('ALTER ROLE supabase_admin WITH PASSWORD %L', postgres_password);
    RAISE NOTICE 'Set password for supabase_admin';
    
    -- Set password for authenticator
    EXECUTE format('ALTER ROLE authenticator WITH PASSWORD %L', postgres_password);
    RAISE NOTICE 'Set password for authenticator';
    
    -- Set password for postgres (superuser)
    EXECUTE format('ALTER ROLE postgres WITH PASSWORD %L', postgres_password);
    RAISE NOTICE 'Set password for postgres';
    
    IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'supabase_storage_admin') THEN
        EXECUTE format('ALTER ROLE supabase_storage_admin WITH PASSWORD %L', postgres_password);
        RAISE NOTICE 'Set password for supabase_storage_admin';
    END IF;
    
    RAISE NOTICE 'All passwords set successfully';
END
$$;
EOL

# Download Supabase initialization scripts for the database
echo "Downloading Supabase initialization scripts..."
curl -s https://raw.githubusercontent.com/supabase/postgres/develop/migrations/db/init-scripts/00000000000000-initial-schema.sql > volumes/db/init/001-initial-schema.sql
curl -s https://raw.githubusercontent.com/supabase/postgres/develop/migrations/db/init-scripts/00000000000001-auth-schema.sql > volumes/db/init/01-auth-schema.sql
curl -s https://raw.githubusercontent.com/supabase/postgres/develop/migrations/db/init-scripts/00000000000003-post-setup.sql > volumes/db/init/03-post-setup.sql

# Create database initialization script for our app tables
cat > volumes/db/init/04-app-tables.sql << 'EOL'
-- Create the tables for our app
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.crawl_sites (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS public.crawl_pages (
    id SERIAL PRIMARY KEY,
    site_id INTEGER REFERENCES public.crawl_sites(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    title TEXT,
    content TEXT,
    summary TEXT,
    embedding VECTOR(1536),
    metadata JSONB,
    is_chunk BOOLEAN DEFAULT FALSE,
    chunk_index INTEGER,
    parent_id INTEGER REFERENCES public.crawl_pages(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(url, site_id, is_chunk, chunk_index)
);

CREATE TABLE IF NOT EXISTS public.chat_conversations (
    id SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB
);

-- Create user_preferences table for enhanced memory system
CREATE TABLE IF NOT EXISTS public.user_preferences (
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

-- Create indexes for user_preferences
CREATE INDEX IF NOT EXISTS idx_user_preferences_user_id ON user_preferences(user_id);
CREATE INDEX IF NOT EXISTS idx_user_preferences_type ON user_preferences(preference_type);
CREATE INDEX IF NOT EXISTS idx_user_preferences_last_used ON user_preferences(last_used);
CREATE INDEX IF NOT EXISTS idx_user_preferences_confidence ON user_preferences(confidence);

-- Create function to merge preference contexts
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

-- Create function to update user preference
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

-- Create function to get user preferences
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
EOL

# Create Kong configuration
cat > volumes/api/kong.yml << 'EOL'
_format_version: "2.1"
_transform: true

services:
  - name: api-service
    url: http://api:8001
    routes:
      - name: api-route
        paths:
          - /api
        strip_path: false
        preserve_host: true
    plugins:
      - name: cors
        config:
          origins:
            - "*"
          methods:
            - GET
            - POST
            - PUT
            - DELETE
            - OPTIONS
          headers:
            - Accept
            - Accept-Version
            - Content-Length
            - Content-MD5
            - Content-Type
            - Date
            - X-Auth-Token
          credentials: true
          max_age: 3600
          preflight_continue: false

  - name: rest-service
    url: http://rest:3000
    routes:
      - name: rest-route
        paths:
          - /rest
EOL

echo "Setup completed successfully!"
echo "You can now run 'docker-compose -f full-stack-compose.yml up -d' to start the services." 
