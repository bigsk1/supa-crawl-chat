[![Python application](https://github.com/bigsk1/supa-crawl-chat/actions/workflows/python-app.yml/badge.svg)](https://github.com/bigsk1/supa-crawl-chat/actions/workflows/python-app.yml)
![Docker support](https://img.shields.io/badge/docker-supported-blue)
[![License](https://img.shields.io/github/license/bigsk1/supa-crawl-chat)](https://github.com/bigsk1/supa-crawl-chat/blob/main/LICENSE)

# 🚀 Supa-Crawl-Chat

Introducing Supa-Crawl-Chat: A Comprehensive Web Crawling, Semantic Search, and AI-Driven Chat Solution with Supabase & Crawl4AI.

Seamlessly crawl websites, transform content into vector embeddings, and enable advanced semantic search. Supa-Crawl-Chat utilizes Supabase for reliable data storage and incorporates AI-powered chat with long-term memory features.

![crawl](https://imagedelivery.net/WfhVb8dSNAAvdXUdMfBuPQ/cbbb5f3b-d089-49a1-704f-c2ebd6bcef00/public)


## ✨ Key Features

- 🕷️ **High-Performance Web Crawling**
  - Harness the power of Crawl4AI to efficiently index websites and sitemaps with configurable depth and scope
  - Advanced crawling algorithms adapt to different website structures and content types for optimal data extraction
  - Seamless handling of JavaScript-rendered content and dynamic websites

- 🔍 **Advanced Semantic Search Engine**
  - Leverage cutting-edge vector similarity and OpenAI embeddings for context-aware search capabilities
  - Achieve up to 95% more relevant search results compared to traditional keyword-based approaches
  - Fine-tuned ranking algorithms that understand semantic relationships between concepts

- 📝 **AI-Powered Content Intelligence**
  - Transform raw web content into structured, actionable data using terminal or UI.
  - Generate human-quality titles, summaries, and site descriptions with remarkable accuracy
  - Automatic content categorization and entity extraction for enhanced data organization

- 📊 **Interactive Data Visualization**
  - Explore your data ecosystem through an intuitive Streamlit-based interface
  - Real-time analytics and insights into your content repository
  - Customizable dashboards for monitoring crawl performance and content metrics

- 🐳 **Scalable Deployment Architecture**
  - Deploy with confidence using our Docker configurations:
    - **Lightweight**: App-only deployment for integration with existing infrastructure
    - **Standard**: App + Crawl4AI for complete content processing capabilities
    - **Full-Stack**: End-to-end solution with App + Crawl4AI + Supabase for maximum autonomy

- 🌐 **Comprehensive API Ecosystem**
  - RESTful API with interactive OpenAPI docs (`/docs`); integration guide: **[docs/API.md](docs/API.md)**
  - Optional authentication: `SUPA_API_AUTH` / `SUPA_API_KEY`, legacy `SCC_API_KEYS` / `API_KEYS`, and optional WebUI password + JWT (`WEBUI_PASSWORD`)
  - Crawl URL validation (SSRF mitigation) with optional private-network overrides for trusted deployments


## Prerequisites

- Python 3.10+
- Node 18+
- A running Crawl4AI instance (self-hosted or provided)
- A Supabase instance (self-hosted or provided)
- OpenAI API key for generating embeddings, content summaries and chat
- Docker (optional)

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/bigsk1/supa-crawl-chat.git
   cd supa-crawl-chat
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Changed directory to frontend and install dependencies:

   ```bash
   cd frontend
   ```

   ```bash
   npm install
   ```


4. Create a `.env` file with your configuration:
<details>
<summary>Click to expand</summary>

```env
# Crawl4AI Configuration
# Locally ran in docker or external service - easily setup with docker compose
CRAWL4AI_API_TOKEN=your_crawl4ai_api_token

# Local Docker
# CRAWL4AI_BASE_URL=http://crawl4ai:11235 
# External Service 
CRAWL4AI_BASE_URL=your_crawl4ai_base_url 

# Supabase Configuration
SUPABASE_URL=your_supabase_host:port
# Database credentials
SUPABASE_DB=postgres
SUPABASE_KEY=postgres
SUPABASE_PASSWORD=postgres

# OpenAI Configuration
OPENAI_API_KEY=sk-proj-
# Model to use for embeddings
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
# Model to use for title and summary generation and chat analysis
OPENAI_CONTENT_MODEL=gpt-4o-mini

# Crawl Configuration
# Set to 'url' for regular website or 'sitemap' for sitemap crawling, will crawl child pages from the sitemap
CRAWL_TYPE=url
# URL to crawl (can be a website URL or sitemap URL)
CRAWL_URL=https://example.com
# Maximum number of URLs to crawl from a sitemap (set to 0 for unlimited)
MAX_URLS=30
# Optional name for the site (if not provided, one will be generated)
CRAWL_SITE_NAME=
# Optional description for the site (if not provided, one will be generated)
CRAWL_SITE_DESCRIPTION=

# Chat Configuration
# Model to use for the chat interface
CHAT_MODEL=gpt-4o
# Number of results to retrieve for each query
CHAT_RESULT_LIMIT=5
# Similarity threshold for vector search (0-1)
CHAT_SIMILARITY_THRESHOLD=0.4
# Default session ID (if not provided, a new one will be generated) you can use a random string
CHAT_SESSION_ID=
# Default user ID (optional, name, user, i.e. larry)
CHAT_USER_ID=
# Default chat profile (default, pydantic, technical, concise, scifi, pirate, supabase_expert, medieval, etc.)
CHAT_PROFILE=default
# Directory containing profile YAML files
CHAT_PROFILES_DIR=profiles
# Verbose mode (true, false) - enable to see more during chat
CHAT_VERBOSE=false
```

</details>


## Running the Frontend and Backend


To run the backend API and the frontend UI, follow these steps:

1. **Start the Backend API**:
   Open a terminal and navigate to the root directory of the project. Then run:
   ```bash
   python run_api.py
   ```

2. **Start the Frontend UI**:
   Open a separate terminal, navigate to the `frontend` directory, and run:
   ```bash
   npm run dev
   ```

3. **Access the Web UI**:
   Open your web browser and go to:
   ```
   http://localhost:3001/
   ```

This will start the backend API on port 8001 and the frontend dev server on port 3001 (see `frontend/vite.config.ts`).

### Logging

The backend uses a **rotating application log** by default: `log/app.log` (configure `APP_LOG_DIR`, `LOG_FILE`, `LOG_LEVEL`, and rotation via `.env`; see `.env.example`). HTTP access lines (`api_http METHOD /path -> status ms`), chat traces, and other services share that file. **Important operator actions** (for example site delete) are also written to **`log/audit.log`** by default (`AUDIT_LOG_FILE`, `AUDIT_LOG_*` rotation, `AUDIT_LOG_ENABLED=false` to disable). There is no separate `log/api/` directory. Set `API_ACCESS_LOG=false` to turn off per-request `api_http` lines; `/api/health`, `/docs`, `/redoc`, and `/openapi.json` are skipped to reduce noise. Optional per-crawl detail logs may appear under `log/crawl/` when crawls run.

 If you need a complete solution - crawl4ai with or without a local Supabase all in Docker see [Docker Deployment](#docker-deployment) section of the README

 ---

![Image](https://github.com/user-attachments/assets/a56cf708-dfe5-4aa7-a854-0685867cee18)

<details open>
<summary>Click to close or open images</summary>

- Crawl a url or sitemap
![Image](https://github.com/user-attachments/assets/9155d59e-303e-484f-96de-1a7a917eeefe)
---

- Chat with your docs!
![Image](https://github.com/user-attachments/assets/86b26bf1-15e9-4cc9-9cba-6a666c2d0646)
---

- Manage your sites
![Image](https://github.com/user-attachments/assets/f106ebd6-96a8-448d-b871-eaa9038169f9)
---

- Search your crawled pages - view chunks
![Image](https://github.com/user-attachments/assets/6b0defc7-d0c9-405b-bbf4-1c8045e6f206)
---

- View your sites - parent pages and chunks
![Image](https://github.com/user-attachments/assets/4c1a0b52-953e-4dc8-b7a9-4a62ecb56c93)
---

- Get detailed info - view whats in the db, view raw, render in md or fetch url live!
![Image](https://github.com/user-attachments/assets/4042e241-23ca-4009-b629-a362dac74f7a)
---

- As you chat the AI will add preferences based on your conversation and remeber them or you can add manually
![Image](https://github.com/user-attachments/assets/5836dfa8-3b09-406e-a5d9-392114d07b99)
---

- Dedicated User Guide
![Image](https://github.com/user-attachments/assets/b6e00fb5-e55a-4f8a-8019-16a73ce347df)

</details>



## Database Connection Options

The project supports two ways to connect to your Supabase database:

1. **Single URL** (Option 1): Use this for both local and remote connections. The URL can be specified with or without protocol.
   ```
   # With protocol (for remote instances)
   SUPABASE_URL=https://your-project.supabase.co:5432
   
   # Without protocol (for local instances)
   SUPABASE_URL=192.168.xx.xx:54322
   ```

You'll need to provide the database credentials:

   ```env
   SUPABASE_DB=postgres
   SUPABASE_KEY=postgres
   SUPABASE_PASSWORD=postgres
   ```

### Content Chunking for LLM Interaction

<details>
<summary>Click to expand</summary>
The system automatically breaks down large content into smaller, more manageable chunks for better LLM interaction and more precise search results. This provides several benefits:

1. **Improved Search Precision**: Instead of matching against entire pages, the system can find the specific chunk that best answers a query.

2. **Efficient Token Usage**: When interacting with LLMs, only the relevant chunks are sent, reducing token usage and costs.

3. **Better Context Management**: Each chunk maintains a reference to its parent page, preserving the full context.

4. **Automatic Token Limit Handling**: Content is automatically chunked to stay within the token limits of the embedding model (8,192 tokens for text-embedding-3-small).
</details>

### How Chunking Works

<details>
<summary>Click to expand chunking details</summary>

The system uses a sophisticated semantic chunking strategy:

1. **Semantic Boundary Detection**: Content is first split along natural semantic boundaries:
   - Markdown headers (e.g., `# Section Title`)
   - Paragraph breaks
   - This preserves the meaning and context of each chunk

2. **Token-Based Sizing**: Each section is then analyzed to ensure it fits within token limits:
   - Sections that fit are kept together
   - Sections that exceed limits are further split with token-based chunking
   - A 200-token overlap is maintained between chunks for context continuity

3. **Smart Overlap**: When creating overlaps between chunks, the system looks for natural break points:
   - Paragraph breaks
   - Sentence endings
   - Clause breaks
   - Word boundaries

4. **Metadata Preservation**: Each chunk maintains references to:
   - Its parent document
   - Its position in the sequence (chunk index)
   - Its token count

This approach ensures that chunks are not only sized appropriately for LLMs but also maintain semantic coherence, making them more useful for search and retrieval.
</details>

### Configuring Chunking

<details>
<summary>Click to expand chunking configuration</summary>

Chunk size and overlap are configured via environment variables (see `.env.example`):

```env
CHUNK_MAX_TOKENS=900
CHUNK_OVERLAP_TOKENS=120
```

These feed the crawler’s chunking pipeline so you can tune token usage and overlap without editing code. Values should stay within the embedding model’s context limit (for example 8,192 tokens for `text-embedding-3-small`).
</details>

## Testing the Setup

Before using the crawler, you can test your setup:

1. Test the database connection:
   ```
   python tests/test_db_connection.py
   ```

2. Test the Crawl4AI API:
   ```
   python tests/test_crawl_api.py
   ```

3. Run the Python test suite (install dev dependencies first):
   ```bash
   pip install -r requirements-dev.txt
   pytest
   ```

   This includes tests for crawl API behavior, URL validation (`security_utils`), and chunking helpers.

## Usage

### Setting up the database

Before using the crawler, you need to set up the database:

```
python main.py setup
```

This will create the necessary tables and extensions in your Supabase database.

## Terminal


<details>
<summary>Click to expand images of terminal</summary>

![Image](https://github.com/user-attachments/assets/bd49c8df-4f45-4981-bd29-64fadf29a0e0)
![Image](https://github.com/user-attachments/assets/c3071ef4-c516-43f9-8496-b49ddc59a55e)

![Image](https://github.com/user-attachments/assets/7aa1d142-4a70-4d86-a17d-860ab633ae3f)

</details>


### Crawling a website with args

<details>
<summary>Click to expand website crawling options</summary>

You can crawl a website in two ways:

1. Using the command-line interface:
   ```
   python main.py crawl https://example.com --name "Example Site" --description "An example website"
   ```

   To crawl a sitemap:
   ```
   python main.py crawl https://example.com/sitemap.xml --sitemap --name "Example Site"
   ```

   You can limit the number of URLs to crawl from the sitemap:
   ```
   python main.py crawl https://example.com/sitemap.xml --sitemap --max-urls 20
   ```

   Note: If you don't provide a description, the system will automatically generate one based on the content of the homepage or main page.

2. Using the `.env` file configuration: ( recommended )
   
   First, update the `.env` file with your crawl settings:
   ```
   CRAWL_TYPE=url  # or 'sitemap' for sitemap crawling
   CRAWL_URL=https://example.com
   CRAWL_SITE_NAME=Example Site
   CRAWL_SITE_DESCRIPTION=An example website  # Optional - will be auto-generated if empty
   ```

   Then run:
   ```
   python run_crawl.py
   ```
</details>


### Title and Summary Generation

The crawler automatically generates titles and summaries for crawled content using OpenAI. You can configure the model used for this in the `.env` file:

```
OPENAI_CONTENT_MODEL=gpt-4o-mini
```

#### Updating Existing Content

<details>
<summary>Click to expand content updating options</summary>

If you have existing pages without titles or summaries, or if you want to regenerate them with a different model, you can use the `update_content.py` script:

```
# Update all sites
python update_content.py

# Update a specific site
python update_content.py --site-id 1

# Limit the number of pages to update
python update_content.py --limit 50

# Force update all pages, even if they already have titles and summaries
python update_content.py --force
```
</details>

### Searching the crawled content

<details>
<summary>Click to expand search options</summary>

To search the crawled content using semantic search:

```
python main.py search "your search query"
```

To use text-based search instead of semantic search:

```
python main.py search "your search query" --text-only
```

![Image](https://github.com/user-attachments/assets/806c80ae-1fbf-4680-990e-9d2b9b3bbaa8)

To adjust the similarity threshold and limit the number of results:

```
python main.py search "your search query" --threshold 0.8 --limit 2
```

To save the search results to a file:

```
python main.py search "your search query" --output results.json
```
</details>

### Listing crawled sites

To list all the sites that have been crawled:

```
python main.py list-sites
```

![Image](https://github.com/user-attachments/assets/c7fce24d-50e8-447e-8900-15ffcb56ce92)

By default, this only counts parent pages (not chunks). To include chunks in the page count:

```
python main.py list-sites --include-chunks
```

### Working with Chunks

<details>
<summary>Click to expand details on working with chunks</summary>

When retrieving or searching content, you can control whether chunks are included:

```python
# Get pages for a site (parent pages only)
pages = crawler.get_site_pages(site_id, limit=100)

# Get pages for a site including chunks
pages_with_chunks = crawler.get_site_pages(site_id, limit=100, include_chunks=True)
```

When searching, chunks are automatically included and prioritized for more precise results. Each chunk includes context about its parent document:

```
python main.py search "your search query"
```

The search results will include:
- The content snippet that matched your query
- Which document it came from
- Which part of the document it represents (e.g., "Part 2 of 5")

This makes it easier to understand the context of each search result, even when it's a small chunk of a larger document.
</details>

---
### Using the chat interface in terminal

![Image](https://github.com/user-attachments/assets/34d79a96-2d60-4221-a1f7-3a8582129855)


The project includes a chat interface in the terminal that uses an LLM to answer questions based on the crawled data. The chat interface now supports persistent conversation history, allowing the LLM to remember previous interactions even after restarting the application.

You can start the terminal chat interface using either the dedicated script or the main CLI:

```bash
# Using the dedicated script
python chat.py

# Using the main CLI
python main.py chat
```

#### Chat Interface Options

<details>
<summary>Click to expand chat interface options</summary>

You can customize the chat interface with various options:

```bash
# Specify a different OpenAI model
python main.py chat --model gpt-4

# Set the maximum number of search results to retrieve when chatting
python main.py chat --limit 10

# Adjust the similarity threshold for vector search (0-1)
python main.py chat --threshold 0.6

# Use a specific session ID for persistent conversations
python main.py chat --session my-chat-session

# Associate the conversation with a specific user
python main.py chat --user John

# Enable verbose debug output
python main.py chat --verbose

# Combined
python main.py chat --model gpt-4 --limit 15 --threshold 0.3 --session 12123111111 --user John --verbose
```
</details>

#### Search Functionality

<details>
<summary>Click to expand search functionality details</summary>

The chat interface uses a sophisticated hybrid search approach that combines vector similarity with text matching:

1. **Vector Search**: Uses OpenAI's embeddings to find semantically similar content
2. **Text Search**: Enhances results with keyword matching for better precision
3. **Hybrid Approach**: Combines both methods to provide the most relevant results

This approach ensures that even when vector similarity might not find exact matches, the text search component can still retrieve relevant information. The system automatically adjusts the search strategy based on the query type and available content.
</details>

#### Persistent Conversation History

<details>
<summary>Click to expand conversation history details</summary>

The chat interface stores all conversation history in the database, allowing the LLM to remember previous interactions. This enables more natural and contextual conversations over time.

Key features:
- **Session-based conversations**: Each conversation gets a unique session ID
- **User identification**: Optionally associate conversations with specific users
- **Conversation continuity**: Continue conversations where you left off, even after restarting
- **Chat commands**:
  - Type `clear` to clear the conversation history
  - Type `history` to view the conversation history
  - Type `exit` or `bye` or `exit` to quit the chat interface

**Important**: To maintain the same conversation across multiple chat sessions, you must use the same session ID. The session ID is displayed when you start the chat interface. You can specify it before starting a new chat session:

```bash
# Start a new chat session
python chat.py --user Joe
# Note the session ID displayed (e.g., "Session ID: a24b6b72-e526-4a09-b662-0f85e82f78a7")

# Later, continue the same conversation by specifying the session ID
python chat.py --user Joe --session a24b6b72-e526-4a09-b662-0f85e82f78a7
```

You can also set a default session ID in your `.env` file:

```
CHAT_SESSION_ID=your-session-id
```

This way, the chat interface will always use the same session ID unless you explicitly specify a different one with the `--session` parameter.
</details>

#### User Preferences and Memory

<details>
<summary>Click to expand user preferences and memory details</summary>

The chat interface can remember user preferences and information shared during conversations, as long as you use the same session ID. For example:
- If you tell the assistant "I like Corvettes" in one session
- Then in a later session (using the same session ID), ask "What cars do I like?"
- The assistant will remember and respond with "You like Corvettes"

This memory persistence works by:
1. Storing all messages in the database with the session ID
2. Analyzing conversation history when relevant questions are asked
3. Extracting user preferences and information from previous messages

To get the most out of this feature, always use the same session ID and user ID when you want the assistant to remember previous conversations.

#### Managing User Preferences via CLI

The chat interface includes several commands for managing user preferences directly from the command line:

**Viewing Preferences**
```
preferences
```
Displays a table of all active preferences for the current user, including ID, type, value, confidence, context, and last used timestamp.

**Adding Preferences**
```
add preference <type> <value> [confidence]
```
Manually adds a new preference for the current user. If confidence is not specified, it defaults to 0.9.

Examples:
```
add preference like Python
add preference expertise JavaScript 0.85
add preference goal "Learn machine learning"
```

**Deleting Preferences**
```
delete preference <id>
```
Deletes a specific preference by ID.

**Clearing All Preferences**
```
clear preferences
```
Deletes all preferences for the current user after confirmation.

**Important**: Preference commands are only available when a user ID is provided (using `--user` when starting the chat). For more detailed information about the user preference system, see the [preferences documentation](docs/preferences.md).
</details>

### Chat Profiles

<details>
<summary>Click to expand chat profiles details</summary>

The chat interface supports different profiles that customize the behavior of the assistant. Each profile has its own system prompt, search settings, and site filtering capabilities. So ideally crawl the sitemap for a doc site and then use or create a profile with an additional system prompt to be an expert about those docs.

Built-in profiles:
- **default**: General-purpose assistant that searches all sites
- **pydantic**: Specialized for Pydantic documentation, focusing on technical details and code examples
- **technical**: Provides detailed technical explanations with step-by-step instructions
- **concise**: Gives brief, to-the-point answers without unnecessary details


You can switch profiles during a chat session:
```
profile pydantic
```

Or start with a specific profile:
```bash
python main.py chat --profile technical
```

You can also view all available profiles:
```
profiles
```
</details>

#### How Site Filtering Works

<details>
<summary>Click to expand site filtering details</summary>

The `sites` array in each profile's `search_settings` controls which sites the assistant searches through when answering questions:

```yaml
search_settings:
  sites: ["pydantic"]  # Only search in sites with "pydantic" in the name
  threshold: 0.6
  limit: 8
```

Here's how the filtering works:

1. **Empty array (`sites: []`)**: Searches across ALL sites in the database
2. **Site patterns**: Filters to only include sites where the site name contains any of the specified patterns
3. **Pattern matching**: Uses case-insensitive partial matching, so `"bigsk1"` would match site names like "Bigsk1 Com", "bigsk1.com", etc.
4. **Multiple patterns**: You can include multiple patterns to search across several related sites

The filtering process:
- When a user asks a question, the system looks at the current profile's `sites` setting
- It queries the `crawl_sites` table to find site IDs where the name contains any of the patterns
- It then only searches for content in pages associated with those site IDs
- This allows profiles to focus on specific content sources, making responses more relevant
</details>

You can switch profiles during a chat session:
```
profile pydantic
```

Or start with a specific profile:
```bash
python main.py chat --profile technical
```

You can also view all available profiles:
```
profiles
```

#### Custom Profiles

<details>
<summary>Click to expand custom profiles details</summary>

You can create your own custom profiles by adding YAML files to the `profiles` directory. Each profile file should include:

- `name`: The name of the profile (used to select it)
- `description`: A brief description of the profile
- `system_prompt`: The system prompt that defines the assistant's behavior
- `search_settings`: Configuration for search behavior
  - `sites`: List of site name patterns to filter by (empty list means search all sites)
  - `threshold`: Similarity threshold for vector search (0-1)
  - `limit`: Maximum number of results to return

Example profile file (`profiles/custom_expert.yaml`):
```yaml
name: custom_expert
description: Custom expert for specific documentation
system_prompt: |
  You are an expert on [specific topic].
  
  Your expertise includes:
  - [Area of expertise 1]
  - [Area of expertise 2]
  - [Area of expertise 3]
  
  When answering questions:
  - [Instruction 1]
  - [Instruction 2]
  - [Instruction 3]

search_settings:
  sites: ["site1", "site2"]  # Only search in sites containing these terms
  threshold: 0.6  # Higher threshold for more precise matches
  limit: 8  # Number of results to return
```

You can specify a custom profiles directory:
```bash
python main.py chat --profiles-dir my_profiles
```
</details>

#### Configuration via .env

<details>
<summary>Click to expand .env configuration details</summary>

You can set default values for the chat interface in your `.env` file:

```
# Chat Configuration
CHAT_MODEL=gpt-4o
CHAT_RESULT_LIMIT=5
CHAT_SIMILARITY_THRESHOLD=0.5
CHAT_SESSION_ID=default-session
CHAT_USER_ID=default-user
CHAT_PROFILE=default
CHAT_PROFILES_DIR=profiles
CHAT_VERBOSE=false
```

This allows you to maintain consistent settings and continue the same conversation across multiple sessions.
</details>

### Resetting the database

<details>
<summary>Click to expand Resetting the database</summary>
If you want to start fresh and delete all data or recreate the tables, you can use the `reset_database.py` script:

```
python tests/reset_database.py
```

This script provides two options:
1. Delete all data (keep tables) - This will delete all data from the tables but keep the table structure.
2. Drop and recreate tables - This will drop the tables and recreate them, effectively starting from scratch.
</details>

### Programmatic usage

You can also use the crawler programmatically in your own Python code. See `tests/example.py` for a demonstration.

## Project Structure

<details>
<summary>Click to expand Project Structure</summary>

### Backend

- `main.py`: Main script with command-line interface
- `crawler.py`: Main crawler class that ties everything together
- `crawl_client.py`: Client for interacting with the Crawl4AI API
- `embeddings.py`: Module for generating OpenAI embeddings
- `content_enhancer.py`: Module for generating titles and summaries using OpenAI
- `db_client.py`: Client for interacting with the Supabase database
- `db_setup.py`: Script for setting up the database
- `chat.py`: Chat interface for interacting with crawled data using an LLM
- `run_api.py`: Script to run the API
- `run_crawl.py`: Script to run a crawl using the configuration from the `.env` file
- `update_content.py`: Script to update existing pages with titles and summaries
- `utils.py`: Utility functions for the CLI
- `requirements.txt`: List of dependencies for the backend
- `.env.example`: Example environment file for the backend
- `api/`: Directory containing the FastAPI implementation
  - `main.py`: FastAPI application entry point (optional API key dependency, CORS, auto-refresh hooks)
  - `auth.py`: Optional `SCC_API_KEYS` / `API_KEYS` validation
  - `routers/`: Directory containing API route definitions
    - `crawl.py`: Endpoints for crawling websites and sitemaps
    - `search.py`: Endpoints for searching crawled content
    - `sites.py`: Endpoints for managing and retrieving site information
    - `chat.py`: Endpoints for interacting with the chat interface
    - `pages.py`: Endpoints for managing and retrieving page information
  - `README.md`: Comprehensive API documentation
- `security_utils.py`: URL validation for crawl/fetch targets and shared env parsing helpers
- `requirements-dev.txt`: Dev dependencies (e.g. `pytest`) layered on `requirements.txt`
- `docker/`: Directory containing Docker-related files
  - `Dockerfile`: Docker image definition for the backend application
  - `frontend.Dockerfile`: Docker image definition for the frontend application
  - `docker-compose.yml`: Docker Compose configuration for the API service only
  - `crawl4ai-docker-compose.yml`: Docker Compose configuration for integrated API and Crawl4AI services
  - `full-stack-compose.yml`: Docker Compose configuration for the complete stack (API, Crawl4AI, Supabase, Frontend)
  - `setup.sh`: Script to set up the full stack environment
  - `reset.sh`: Script to reset the full stack environment
  - `status.sh`: Script to check the status of the full stack environment
  - `.env`: Environment variables for Docker deployment
  - `.env.example`: Example environment file for Docker deployment
  - `full-stack/`: Documentation and utilities for the full stack setup
    - `README.md`: Documentation for the full stack setup
    - `ENV_GUIDE.md`: Guide for configuring environment variables
    - `check_db_connections.sh`: Script to verify database connections
  - `volumes/`: Directory for Docker volumes
  - `.dockerignore`: Specifies files to exclude from Docker builds
- `supabase_explorer/`: Directory containing the Supabase Explorer Streamlit app
  - `supabase_explorer.py`: Interactive Streamlit app for database exploration
  - `supabase_queries.md`: Collection of useful SQL queries
  - `database_explorer_readme.md`: Documentation for the Supabase Explorer
- `profiles/`: Directory containing chat profile configurations
  - Various YAML files defining different chat personalities and behaviors
- `tests/`: Directory containing test scripts
  - `example.py`: Example script demonstrating programmatic usage
  - `test_db_connection.py`: Script to test the database connection
  - `test_crawl_api.py`: Script to test the Crawl4AI API
  - `test_security_utils.py`, `test_crawler_chunking.py`: Pytest coverage for URL rules and chunking
  - `smoke_api.py`: Optional smoke checks against a running API
  - `reset_database.py`: Script to delete tables or reset the database

### Frontend

- `frontend/`: Directory containing the React-based web UI
  - `src/`: Source code for the frontend application
    - `api/`: API client for communicating with the backend
      - `apiService.ts`: Service for making API requests
      - `apiWrapper.ts`: Wrapper for API endpoints with type definitions
    - `components/`: Reusable UI components
      - `Layout.tsx`: Main layout component with Sidebar and Navbar
      - `Navbar.tsx`: Top navigation bar
      - `Sidebar.tsx`: Side navigation menu
      - `NotificationCenter.tsx`: Notification system for user alerts
      - `PageListItem.tsx`: Component for displaying page items in lists
      - `UserProfileModal.tsx`: Modal for user profile management
      - `ui/`: Shadcn UI component library
        - Various UI components like buttons, inputs, dialogs, etc.
    - `context/`: React context providers for state management
    - `hooks/`: Custom React hooks
    - `lib/`: Utility libraries and configurations
    - `pages/`: Main application views
      - `HomePage.tsx`: Landing page
      - `ChatPage.tsx`: AI chat interface
      - `CrawlPage.tsx`: Web crawling interface
      - `SearchPage.tsx`: Search interface
      - `SitesPage.tsx`: Site management
      - `SiteDetailPage.tsx`: Detailed view of a crawled site
      - `NotificationInfo.tsx`: Notification settings and information
      - `UserProfileModal.tsx`: User profile management
      - `UserPreferencesPage.tsx`: User preferences management
    - `styles/`: CSS and styling files
    - `utils/`: Utility functions
    - `App.tsx`: Main application component
    - `main.tsx`: Entry point for the React application
  - `public/`: Static assets
  - `index.html`: HTML entry point
  - `vite.config.ts`: Vite configuration
  - `tailwind.config.js`: Tailwind CSS configuration
  - `tsconfig.json`: TypeScript configuration
  - `package.json`: NPM dependencies and scripts

---
</details>

## Database Structure

<details>
<summary>Click to expand Database Structure</summary>

![Image](https://github.com/user-attachments/assets/629345d4-3dea-489b-be0e-65cb07f53d9a)


The project uses the following tables in the Supabase database:

1. `crawl_sites`: Stores information about the sites you've crawled
   - `id`: Primary key
   - `name`: Name of the site
   - `url`: URL of the site
   - `description`: Optional description of the site
   - `created_at`: Timestamp when the site was added

2. `crawl_pages`: Stores the actual content, embeddings, titles, and summaries for each page
   - `id`: Primary key
   - `site_id`: Foreign key referencing the `crawl_sites` table
   - `url`: URL of the page (unique)
   - `title`: Title of the page
   - `content`: Content of the page
   - `summary`: Summary of the page
   - `embedding`: Vector embedding of the content
   - `metadata`: Additional metadata about the page
   - `is_chunk`: Boolean indicating if this is a chunk of a larger page
   - `chunk_index`: Index of the chunk within the parent page
   - `parent_id`: Foreign key referencing the parent page
   - `created_at`: Timestamp when the page was added
   - `updated_at`: Timestamp when the page was last updated

3. `chat_conversations`: Stores conversation history for the chat interface
   - `id`: Primary key
   - `session_id`: Unique identifier for the conversation session
   - `user_id`: Optional identifier for the user
   - `timestamp`: Timestamp when the message was sent
   - `role`: Role of the message sender (user, assistant, system)
   - `content`: Content of the message
   - `metadata`: Additional metadata about the message

When you crawl a site multiple times, the system will update existing pages rather than creating duplicates, ensuring you always have the most recent content. Similarly, the chat interface will maintain conversation history across sessions, allowing for more natural and contextual interactions.
</details>

## Supabase Explorer

![Image](https://github.com/user-attachments/assets/26e7681b-7835-4bc3-9d64-08f2d314f77f)


![Image](https://github.com/user-attachments/assets/85388083-a1d0-4054-8913-e67c6c1fb90e)

The project includes a powerful Streamlit-based Supabase Explorer app that allows you to interactively explore and analyze your database. This tool makes it easy to run SQL queries, visualize results, and gain insights from your crawled data.

### Features

- **Interactive Query Interface**: Run predefined or custom SQL queries with a single click
- **Data Visualization**: Create bar charts, line charts, and pie charts from your query results
- **Database Overview**: View statistics about your database, including site counts and page distribution
- **Export Functionality**: Download query results as CSV files for further analysis
- **Predefined Queries**: Access a comprehensive collection of useful SQL queries organized by category:
  - Site queries
  - Page queries
  - Chunk queries
  - Metadata queries
  - Conversation history queries
  - Statistics queries
  - Embedding analysis queries
  - Content quality queries
  - Advanced conversation analysis
  - Performance queries
  - Search performance analysis

### Running the Supabase Explorer

To launch the Supabase Explorer:

```bash
cd supabase_explorer
pip install -r requirements.txt
streamlit run supabase_explorer.py
```

The app will automatically connect to your Supabase database using the credentials in your root `.env` file.

#### Running Supabase Explorer in Docker

The Supabase Explorer is also available as part of the Docker setup. When you run either of the Docker Compose configurations, the Streamlit app will be accessible at:

```
http://localhost:8501
```

This allows you to explore your database directly from the Docker container without having to install Streamlit locally.

```bash
# Start the Docker containers including the Supabase Explorer
docker-compose -f docker/docker-compose.yml up -d

# Or with the integrated Crawl4AI setup
docker-compose -f docker/crawl4ai-docker-compose.yml up -d
```

### Adding Custom Queries

<details>
<summary>Click to expand Adding Custom Queries</summary>

You can add your own custom queries to the predefined list by editing the `supabase_explorer/supabase_queries.md` file. Follow the existing format:

```markdown
Your Category

Your Query Name

```sql
SELECT * FROM your_table WHERE your_condition;
```


After adding your queries, restart the Streamlit app to load the new queries.
</details>



## Docker Deployment - 3 different options! 

- Use the docker compose file to start the app
![Image](https://github.com/user-attachments/assets/a56cf708-dfe5-4aa7-a854-0685867cee18)


- If terminal is your thing then you can also just exec into the container
![Image](https://github.com/user-attachments/assets/be41b857-47ca-4804-97e2-98764a270748)



```bash
# Build and start the container
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f
```

This setup includes:
- API backend on port 8001
- Frontend UI on port 3000
- Streamlit Explorer on port 8501

---

### Integrated Crawl4AI Docker Deployment

If you want to run both the API and Crawl4AI in Docker containers, this is when you already have a supabase locally or externally, you can use the provided `crawl4ai-docker-compose.yml` file:

```bash
# Build and start both containers
docker-compose -f docker/crawl4ai-docker-compose.yml up -d

# View logs
docker-compose -f docker/crawl4ai-docker-compose.yml logs -f
```

This setup will:
1. Start a Crawl4AI container using the official image from Docker Hub
2. Start your API container with the correct configuration to connect to Crawl4AI
3. Start the frontend UI container for the web interface
4. Start the Streamlit Explorer for database exploration
5. Create a network for the containers to communicate with each other

Make sure your `.env` file in root includes the necessary Crawl4AI configuration:

```env
# Crawl4AI Configuration
CRAWL4AI_API_TOKEN=your_crawl4ai_api_token
# This will be automatically set to the Docker service name in the container
# CRAWL4AI_BASE_URL=http://crawl4ai:11235
```

Access the services:
- API: http://localhost:8001
- Frontend UI: http://localhost:3000
- Streamlit Explorer: http://localhost:8501
- Crawl4AI: http://localhost:11235

---

### Full Stack Docker Setup (Supabase + API + Crawl4AI + Frontend)

We provide a comprehensive Docker setup that includes everything you need to run the entire application stack:

- Supa Chat API Backend
- Frontend UI
- Supabase Docker images (Database, Kong, Realtime, etc.)
- Crawl4AI Docker image for web crawling

This setup comes with everything you need to run the complete application without any external dependencies.

<details>
<summary>Click to expand more images of the UI</summary>

#### Important Environment Variable Configuration

The full-stack Docker setup requires careful configuration of environment variables:

1. **SUPABASE_URL**: This should be commented out or left empty to ensure the API connects directly to the database:
   ```
   # SUPABASE_URL=http://kong:8002
   ```
   
   If this is set, the API will try to connect to Kong for database operations, which will cause SSL negotiation errors.

2. **Direct Database Connection**: Ensure these database connection parameters are set correctly:
   ```
   SUPABASE_HOST=db
   SUPABASE_PORT=5432
   SUPABASE_KEY=supabase_admin
   SUPABASE_PASSWORD=${POSTGRES_PASSWORD}
   ```

#### Setting Up the Full Stack

To use the full stack Docker setup:

1. Navigate to the docker directory:
   ```bash
   cd docker
   ```

2. Run the setup script to create necessary configuration files:
   ```bash
   chmod +x setup_update.sh
   ./setup_update.sh
   ```
   
   This script will:
   - Check for the existence of the `.env` file
   - Create SQL scripts for database initialization
   - Download Supabase initialization scripts
   - Create application tables and functions
   - Generate the Kong configuration file

3. Edit the Docker-specific `.env` file with your actual values:
   ```bash
   nano .env
   ```

4. Start the services:
   ```bash
   docker-compose -f full-stack-compose.yml up -d
   ```

5. Access the services:
   - API: http://localhost:8001
   - API Documentation: http://localhost:8001/docs
   - Frontend UI: http://localhost:3000
   - Supabase Studio: http://localhost:3001 (username: supabase, password: from your .env file)
   - Kong API Gateway: http://localhost:8002
   - Crawl4AI: http://localhost:11235

6. Monitor or manage the stack:
   ```bash
   # Check status of all services
   ./status.sh
   
   # Reset the stack (removes all data)
   ./reset.sh
   ```

#### Troubleshooting

1. **Database Connection Issues**:
   - If you see SSL negotiation errors, make sure `SUPABASE_URL` is commented out or empty in your `.env` file
   - Verify the database credentials in the `.env` file
   - Restart the API service after making changes:
     ```bash
     docker-compose -f full-stack-compose.yml restart api
     ```

2. **REST Service Issues**:
   - If the REST service is not connecting properly, run the fix script:
     ```bash
     ./fix_rest.sh
     ```

3. **Checking Logs**:
   - View logs for a specific service:
     ```bash
     docker logs supachat-api
     docker logs supachat-kong
     docker logs supachat-frontend
     ```

</details>

For more detailed instructions, see the [Docker README](docker/full-stack/README.md), [System Flows Documentation](docs/SYSTEM_FLOWS.md), and the **[HTTP API guide](docs/API.md)**.

## API

The project includes a FastAPI-based REST API that allows you to integrate the Supa-Crawl-Chat functionality with other applications or build custom frontends. The API provides endpoints for searching, crawling, managing sites, pages, and chatting.

**Full reference:** [docs/API.md](docs/API.md) (auth headers, env vars, rate limits, public routes, curl examples). **Index of all docs:** [docs/README.md](docs/README.md). API traffic is logged in the same file as the rest of the app (see [Logging](#logging) above), not under a separate `log/api/` path.

### API security (optional)

Authentication is enforced when **`SUPA_API_AUTH`** is enabled (with **`SUPA_API_KEY`**) and/or legacy **`SCC_API_KEYS`** / **`API_KEYS`** is set. Non-trusted clients must send:

- Header `x-api-key: <secret>`, or  
- Header `Authorization: Bearer <secret>`

(`x-api-key` wins if both are sent.) Localhost and optional trusted CIDRs may bypass keys; **`GET /api/health`** and **`/api/auth/webui/*`** stay public. WebUI password protection uses **`WEBUI_PASSWORD`** and JWTs from **`POST /api/auth/webui/login`**. See [docs/API.md](docs/API.md).

For the React UI, set `VITE_API_KEY` in `frontend/.env` when using legacy keys (see `frontend/.env.example`). For browser clients, set `API_CORS_ORIGINS` to your frontend origins (comma-separated); if unset, the API uses permissive CORS for local development.

Crawl targets are validated to reduce SSRF risk: only public `http`/`https` URLs are allowed unless you set `ALLOW_PRIVATE_CRAWL_URLS` or list hosts in `CRAWL_ALLOWED_HOSTS`. See `.env.example` for details.

### Running the API

To start the API server:

```bash
python run_api.py
```

or use:

```bash
cd api
uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
```

The API will be available at `http://localhost:8001`

### API Endpoints

The interactive API documentation is available at:

```
http://localhost:8001/docs
```

The API provides the following endpoints:

<details>
<summary>Click to expand API endpoints</summary>

#### Search

- `GET /api/search`: Search for content using semantic search or text search
  - Parameters:
    - `query`: The search query
    - `threshold`: Similarity threshold (0-1)
    - `limit`: Maximum number of results
    - `text_only`: Use text search instead of embeddings
    - `site_id`: Optional site ID to filter results by

#### Crawl

- `POST /api/crawl`: Crawl a website or sitemap
  - Body:
    - `url`: URL to crawl
    - `site_name`: Optional name for the site
    - `site_description`: Optional description of the site
    - `is_sitemap`: Whether the URL is a sitemap
    - `max_urls`: Maximum number of URLs to crawl from a sitemap

- `GET /api/crawl/status/{site_id}`: Get the status of a crawl by site ID

#### Sites

- `GET /api/sites`: List all crawled sites
  - Parameters:
    - `include_chunks`: Whether to include chunks in the page count

- `GET /api/sites/{site_id}`: Get a site by ID
  - Parameters:
    - `include_chunks`: Whether to include chunks in the page count

- `GET /api/sites/{site_id}/pages`: Get pages for a specific site
  - Parameters:
    - `include_chunks`: Whether to include chunks in the results
    - `limit`: Maximum number of pages to return

#### Chat

- `POST /api/chat`: Send a message to the chat bot and get a response
  - Body:
    - `message`: The user's message
    - `session_id`: Optional session ID for persistent conversations
    - `user_id`: Optional user ID
    - `profile`: Optional profile to use
  - Parameters:
    - `model`: Optional model to use
    - `result_limit`: Optional maximum number of search results
    - `similarity_threshold`: Optional similarity threshold (0-1)
    - `include_context`: Whether to include search context in the response
    - `include_history`: Whether to include conversation history in the response

- `GET /api/chat/profiles`: List all available profiles
  - Parameters:
    - `session_id`: Optional session ID to get active profile
    - `user_id`: Optional user ID

- `POST /api/chat/profiles/{profile_name}`: Set the active profile for a session
  - Parameters:
    - `session_id`: Session ID
    - `user_id`: Optional user ID

- `GET /api/chat/history`: Get conversation history for a session
  - Parameters:
    - `session_id`: Session ID
    - `user_id`: Optional user ID

- `DELETE /api/chat/history`: Clear conversation history for a session
  - Parameters:
    - `session_id`: Session ID
    - `user_id`: Optional user ID
</details>

### Example API Usage

Here's an example of how to use the API with curl:

```bash
# Search for content (add -H "x-api-key: YOUR_KEY" if SCC_API_KEYS/API_KEYS is configured)
curl -X GET "http://localhost:8001/api/search?query=pydantic&threshold=0.3&limit=5" -H "accept: application/json"

# Start a chat session
curl -X POST "http://localhost:8001/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Tell me about pydantic", "user_id": "example_user"}'

# Continue the conversation with the same session ID
curl -X POST "http://localhost:8001/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "How do I use BaseModel?", "session_id": "SESSION_ID_FROM_PREVIOUS_RESPONSE", "user_id": "example_user"}'
```
Finished crawl example 

![Image](https://github.com/user-attachments/assets/ee12f7f1-1347-4968-9e2b-6466ac835b40)




## License

This project is licensed under the MIT License - see the LICENSE file for details.