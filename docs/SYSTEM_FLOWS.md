# Supa Crawl Chat Docs

This document provides a detailed explanation of all the components, flows, and interactions in the Supa Crawl Chat system. It covers how different parts of the system work together, what happens in different scenarios, and how various settings affect the behavior of the system.


## Core Components

### 1. Database (Supabase)
- Stores crawled content, embeddings, site information
- Maintains conversation history
- Stores user preferences and metadata

### 2. LLM Integration (OpenAI)
- Used for multiple purposes throughout the system:
  - Generating embeddings for vector search
  - Creating titles and summaries for crawled content
  - Analyzing conversation history
  - Understanding query intent
  - Generating responses to user queries
  - Extracting user preferences

### 3. Crawler
- Fetches content from websites
- Processes and chunks content
- Stores content in the database

### 4. Chat Interface
- Provides interactive command-line interface
- Manages conversation flow
- Handles user commands
- Displays formatted responses

### 5. Frontend UI
- Provides a modern web-based user interface
- Visualizes crawled data and search results
- Offers an interactive chat experience
- Manages site and page administration

### 6. Security boundaries (API and crawl targets)

- **Optional API authentication (`api/supa_auth.py`, `api/auth.py`):**  
  - **`SUPA_API_AUTH`** + **`SUPA_API_KEY`**: when enabled, non-trusted IPs must send the key as **`x-api-key`** or **`Authorization: Bearer`** (localhost and optional **`SUPA_API_TRUST_CIDRS`** / **`SUPA_API_TRUST_FORWARDED`** may bypass).  
  - **Legacy keys:** **`SCC_API_KEYS`** or **`API_KEYS`** — same headers; the React app can use **`VITE_API_KEY`** for `x-api-key`.  
  - **WebUI JWT:** If **`WEBUI_PASSWORD`** is set, the browser logs in via **`POST /api/auth/webui/login`** and sends a **`Authorization: Bearer`** token (JWT) on subsequent API calls.  
  - **`/api/health`** and **`/api/auth/webui/*`** stay public (no key). Full detail: [API.md](./API.md).  
- **Crawl URL validation:** User-supplied crawl and fetch URLs are checked in `security_utils.validate_fetch_url` to limit SSRF-style abuse (private IPs, non-http(s) schemes, credentials in URLs, etc.). Sitemap fetches validate every redirect hop, and every URL extracted from a sitemap/llms.txt-style file is revalidated before Crawl4AI receives it. Sitemap expansion is same-host by default; external sitemap URLs, external-link following, redirects, custom proxies, and file downloads are opt-in with the `CRAWL_*` safety flags documented in `.env.example`. Trusted internal crawls can use `ALLOW_PRIVATE_CRAWL_URLS` or host allowlists via `CRAWL_ALLOWED_HOSTS`. CORS: set **`API_CORS_ORIGINS`** for production browser origins.
- **Crawled content hygiene:** Before title/summary generation, chunking, embeddings, and storage, crawled text passes through `content_hygiene.clean_crawled_content`. This removes high-risk retrieval noise such as huge base64 data URIs, encoded fenced blocks, long encoded tokens, control characters, and over-large page bodies (`CRAWL_MAX_CONTENT_CHARS`). Metadata records cleanup flags under `content_hygiene` so noisy pages can be audited later.

### Search, embeddings, and keyword retrieval (not BM25)

The stack does **not** use **BM25** or a dedicated Elasticsearch-style ranker.

1. **Semantic / similarity search (default)**  
   - Query text is embedded with the same OpenAI embedding model used at crawl time.  
   - **PostgreSQL `pgvector`**: stored page/chunk embeddings use the `vector` type; retrieval uses cosine distance (`<=>`). Similarity is reported as `1 - distance` in `[0, 1]`.  
   - **`hybrid_search` in `db_client.py`**: prefers vector hits above a (slightly relaxed) threshold; if needed, it supplements with text search (below).

2. **Keyword / text-only search** (`text_only=true` on `/api/search`, or CLI/text path)  
   - **`search_by_text`**: title `ILIKE` first, then **PostgreSQL full-text search** — `to_tsvector('english', …)`, `plainto_tsquery`, and **`ts_rank_cd`** for ordering. That is the built-in FTS ranking (cover density), **not** BM25.  
   - Fallback: broader `ILIKE` on content if FTS returns nothing.

3. **Embeddings in chat (RAG)**  
   - Context for answers comes from the same embedding + vector similarity path (unless the message is treated as a greeting and retrieval is skipped).

Optional future improvements: true hybrid fusion scores, `pg_trgm` for fuzzy match, or an external BM25/lexical service — none of those are required for the current design to work.

## Frontend Architecture and Components

The frontend is built using React with TypeScript, providing a modern, responsive user interface for interacting with the Crawl4AI system. This section details the architecture, components, and data flows within the frontend.

### Technology Stack

- **React**: Core UI library
- **TypeScript**: Type-safe JavaScript
- **Vite**: Build tool and development server
- **Tailwind CSS**: Utility-first CSS framework
- **Shadcn UI**: Component library based on Radix UI
- **React Router**: Client-side routing
- **React Query**: Data fetching and state management
- **Lucide React**: Icon library

### Application Structure

The frontend follows a modular architecture with clear separation of concerns:

1. **Pages**: Container components representing different views
2. **Components**: Reusable UI elements
3. **API Layer**: Services for backend communication
4. **Context Providers**: Global state management
5. **Hooks**: Custom React hooks for shared logic
6. **Utilities**: Helper functions and constants

### Key Components

#### Layout Components
- **Layout**: Main application shell with consistent navigation
- **Navbar**: Top navigation bar with user controls and notifications
- **Sidebar**: Side navigation menu for accessing different sections
- **NotificationCenter**: System for displaying and managing notifications

#### Page Components
- **HomePage**: Landing page with system overview and quick actions
- **SitesPage**: List of crawled sites with management options
- **SiteDetailPage**: Detailed view of a site with its pages and content
- **ChatPage**: Interactive AI chat interface
- **CrawlPage**: Interface for initiating and monitoring crawls
- **SearchPage**: Advanced search interface with filters and visualization
- **NotificationInfo**: Settings and information about the notification system

#### UI Components
- **Shadcn UI Library**: Collection of accessible, customizable components
  - Buttons, inputs, dialogs, dropdowns, etc.
  - Consistent styling and behavior across the application
- **Custom Components**:
  - **PageListItem**: Component for displaying page items in lists
  - **UserProfileModal**: Modal for user profile management
  - **DateDebugger**: Developer tool for debugging date-related issues

### State Management

The frontend uses a combination of state management approaches:

1. **Local Component State**: For UI-specific state
2. **React Context**: For shared state across components
   - **ThemeContext**: Manages light/dark mode
   - **NotificationContext**: Manages notification state
   - **UserContext**: Manages user preferences and session information
3. **URL State**: For shareable and bookmarkable state
4. **React Query**: For server state management
   - Caching
   - Background refetching
   - Optimistic updates

### API Integration

The frontend communicates with the backend through a structured API layer:

1. **apiService.ts**: Core service for making HTTP requests
   - Attaches the optional `x-api-key` header when `VITE_API_KEY` is set
   - Manages request/response formatting
   - Implements error handling
   - Provides logging and debugging

2. **apiWrapper.ts**: Type-safe wrapper around API endpoints
   - Provides strongly-typed function calls for each endpoint
   - Handles request validation
   - Transforms responses into application-specific formats

### Data Flow Patterns

#### Fetching Data
1. Component mounts or user triggers an action
2. API request is initiated through the API layer
3. Loading state is displayed to the user
4. Data is received and transformed if necessary
5. Component renders with the received data
6. Error handling if the request fails

#### Submitting Data
1. User completes a form or triggers an action
2. Client-side validation is performed
3. API request is initiated with the form data
4. Optimistic UI update is applied if appropriate
5. Success/error notification is displayed
6. UI is updated based on the response

### Frontend-Specific Flows

#### Site Management Flow
1. User navigates to the Sites page
2. Frontend fetches the list of sites from `/api/sites`
3. Sites are displayed in a sortable, filterable table
4. User can:
   - Click on a site to view details
   - Refresh the site list
   - Delete a site (with confirmation)
5. When viewing a site, the frontend fetches:
   - Site details from `/api/sites/{site_id}`
   - Pages for the site from `/api/sites/{site_id}/pages`
6. Pages are displayed with pagination, search, and filtering options

#### Chat Interface Flow
1. User navigates to the Chat page
2. Frontend initializes a chat session:
   - Generates a new session ID or uses an existing one from local storage
   - Fetches available profiles from `/api/chat/profiles`
   - Loads conversation history for the session from `/api/chat/history`
3. User sends a message:
   - Message is displayed in the chat interface
   - Request is sent to `/api/chat` with the message, session information, profile, and selected context source mode
   - Context source mode controls retrieval routing:
     - `auto`: crawled-site context with the server's configured Brave fallback policy
     - `indexed`: crawled-site context only
     - `web`: crawled-site context plus forced Brave web context
     - `none`: no indexed or web context
   - "Thinking" indicator is displayed
   - Response is received and displayed in the chat
   - Chat history is updated
4. User can:
   - Change the active profile
   - Change the context source mode
   - Clear the conversation history
   - Copy the session ID for reference
   - View and manage preferences extracted from the conversation

#### Crawl Initiation Flow
1. User navigates to the Crawl page
2. Frontend displays the crawl form
3. User enters:
   - URL to crawl
   - Site name (optional)
   - Site description (optional)
   - Crawl type (URL or sitemap)
   - Maximum URLs (for sitemaps)
4. User can expand the Advanced Options section to configure:
   - **General Options**:
     - Follow external links
     - Include/exclude URL patterns
     - Follow redirects
     - Maximum crawl depth
   - **Browser Options**:
     - Headless mode
     - Browser type (Chromium, Firefox, WebKit)
     - JavaScript enabled/disabled
     - Custom user agent
   - **Navigation Options**:
     - Page load timeout
     - Wait for selector
   - **Media Options**:
     - Download images
     - Download videos
     - Download files
   - **Extraction Options**:
     - Extraction type (basic, article, custom)
     - CSS selector for custom extraction
5. User submits the form
6. Frontend sends a request to `/api/crawl` with all standard and advanced options
7. Progress indicator is displayed
8. Frontend polls `/api/crawl/status/{site_id}` for updates
9. Upon completion, success notification is displayed
10. User is redirected to the site detail page

### Media Handling in Crawling

The system provides options for handling various media types during the crawling process. This section explains how these options work and their impact on the crawled content.

#### Media Options Overview

1. **Download Images**: When enabled, the crawler processes images found on the pages.
   - Images are not downloaded to the local file system
   - Image URLs and metadata are stored in the page content
   - This enhances the context available for vector embeddings and search

2. **Download Videos**: When enabled, the crawler processes video content.
   - Video URLs and metadata are captured
   - This allows the chat interface to reference videos in responses
   - Video content itself is not stored in the database

3. **Download Files**: When enabled, the crawler processes downloadable files (PDFs, DOCs, etc.).
   - File URLs and metadata are stored
   - This allows the system to reference these resources in search results
   - File contents may be extracted for certain file types

#### Media Processing Flow

1. User enables media options in the Advanced Options section
2. Frontend sends these preferences to the API
3. API passes the options to the Crawl4AI service
4. Crawl4AI processes the media according to the specified options
5. Media information is returned as part of the crawl results
6. The system stores media references in the page content and metadata
7. When searching, media references are included in the vector embeddings
8. Chat responses can include references to relevant media

#### Impact on Performance and Storage

- Enabling media options may increase crawl time
- Media references increase the context available for search
- Vector embeddings include media information for more comprehensive results
- Database storage requirements increase with media metadata
- The system maintains references to media rather than storing the actual media files

### Advanced Crawling Options

The system provides a comprehensive set of advanced options for fine-tuning the crawling process. These options are organized into categories for easier navigation and configuration.

#### General Options

1. **Follow External Links**: Controls whether the crawler follows links to external domains.
   - When enabled: Crawler will follow links to other websites
   - When disabled (default): Crawler stays within the initial domain
   - Impact: Significantly affects crawl scope and duration

2. **Include/Exclude URL Patterns**: Allows filtering which URLs are crawled.
   - Include patterns: Only URLs matching these patterns will be crawled
   - Exclude patterns: URLs matching these patterns will be skipped
   - Pattern format: Supports wildcards (e.g., `/blog/*`, `/docs/*`)
   - Multiple patterns: Comma-separated list

3. **Follow Redirects**: Controls whether HTTP redirects are followed.
   - When enabled (default): Crawler follows HTTP 301/302 redirects
   - When disabled: Crawler stops at redirect responses

4. **Maximum Crawl Depth**: Limits how deep the crawler will go from the starting URL.
   - Default: 3 levels deep
   - Range: 1-10
   - Impact: Higher values increase crawl time and result count

#### Browser Options

1. **Headless Mode**: Controls browser visibility during crawling.
   - When enabled (default): Browser runs invisibly
   - When disabled: Browser UI is visible (rarely needed)

2. **Browser Type**: Selects which browser engine to use.
   - Options: Chromium (default), Firefox, WebKit
   - Each engine may render certain sites differently

3. **JavaScript Enabled**: Controls JavaScript execution.
   - When enabled (default): JavaScript on pages will execute
   - When disabled: Only static HTML is processed
   - Impact: Disabling may miss dynamically loaded content

4. **Custom User Agent**: Sets the browser's user agent string.
   - Default: Standard Chromium user agent
   - Custom: Any valid user agent string
   - Use case: Bypassing bot detection or testing mobile views

#### Navigation Options

1. **Page Load Timeout**: Maximum time to wait for a page to load.
   - Default: 30000 ms (30 seconds)
   - Range: 1000-60000 ms
   - Impact: Lower values speed up crawling but may miss slow-loading content

2. **Wait For Selector**: CSS selector to wait for before considering a page loaded.
   - Example: `#content`, `.main-article`
   - Use case: Ensuring dynamic content is loaded before processing

#### Extraction Options

1. **Extraction Type**: Controls how content is extracted from pages.
   - Basic (default): Extracts all visible text
   - Article: Focuses on main article content, ignoring navigation and sidebars
   - Custom: Uses a custom CSS selector to extract specific content

2. **CSS Selector**: Specifies which elements to extract when using custom extraction.
   - Example: `article`, `.content`, `#main-text`
   - Only used when extraction type is set to "custom"

#### Implementation Details

These advanced options are passed through multiple layers:

1. **Frontend**: Options are collected via the AdvancedCrawlOptions component
2. **API**: Options are validated using Pydantic field validators
3. **WebCrawler**: Options are processed and prepared for the Crawl4AI client
4. **Crawl4AI Client**: Options are formatted according to the Crawl4AI API requirements
5. **Crawl4AI Service**: Options are applied during the actual crawling process

The system uses sensible defaults for all options, so users only need to modify settings relevant to their specific crawling needs.

#### Search Flow
1. User navigates to the Search page
2. User enters a search query and optional parameters:
   - Similarity threshold
   - Result limit
   - Site filter
   - Search type (semantic or text-only)
3. Frontend sends a request to `/api/search`
4. Results are displayed grouped by site
5. User can:
   - Click on a result to view the full content
   - Adjust search parameters and search again
   - Sort and filter results

### Notification System

The frontend implements a comprehensive notification system:

1. **Types of Notifications**:
   - Success: Positive action confirmations
   - Error: Failed operations or system errors
   - Info: Neutral information
   - Warning: Potential issues requiring attention

2. **Notification Components**:
   - Toast notifications: Temporary pop-up messages
   - Notification center: Persistent list of all notifications
   - Notification settings: User preferences for notification behavior

3. **Notification Flow**:
   - Notification is created via `createNotification` function
   - Notification is added to the notification store
   - Toast is displayed (if not muted)
   - Notification is added to the notification center
   - Notification can be dismissed or marked as read

4. **Mute Functionality**:
   - Users can mute non-critical notifications
   - Mute preference is stored in local storage
   - Error notifications are always shown regardless of mute setting
   - Muted notifications still appear in the notification center

### Responsive Design

The frontend is fully responsive, adapting to different screen sizes:

1. **Mobile View** (< 640px):
   - Collapsed sidebar with hamburger menu
   - Simplified layouts with stacked elements
   - Touch-optimized controls

2. **Tablet View** (640px - 1024px):
   - Compact sidebar
   - Adjusted grid layouts
   - Optimized table views

3. **Desktop View** (> 1024px):
   - Full sidebar with labels
   - Multi-column layouts
   - Expanded data tables

### Accessibility Features

The frontend implements several accessibility features:

1. **Keyboard Navigation**:
   - All interactive elements are focusable
   - Logical tab order
   - Keyboard shortcuts for common actions

2. **Screen Reader Support**:
   - ARIA attributes for dynamic content
   - Semantic HTML structure
   - Descriptive alt text for images

3. **Visual Accessibility**:
   - High contrast mode
   - Resizable text
   - Color schemes that meet WCAG guidelines

## User Identification and Session Management

### User ID
- Set via `--user` parameter or `CHAT_USER_ID` environment variable
- Stored with each message in the conversation history
- Used to personalize responses (e.g., "Your name is Joe")
- Included in system prompts to the LLM
- Persists across multiple chat sessions

### Session ID
- Generated automatically or set via `--session` parameter or `CHAT_SESSION_ID` environment variable
- Used to group related messages in the conversation history
- Allows continuing conversations across multiple chat sessions
- Critical for maintaining context and memory
- auto generated if empty, can set the uuid in the .env or copy generate session id from UI after first run to maintain context and memory

### Combinations and Effects

| User ID | Session ID | Effect |
|---------|------------|--------|
| ✓ | ✓ | Full personalization and conversation continuity. The system remembers both the user's name and all previous conversations in that session. |
| ✓ | ✗ (new) | The system knows the user's name but starts a fresh conversation. |
| ✗ | ✓ | The system remembers previous conversations but doesn't know the user's name. |
| ✗ | ✗ (new) | Completely fresh start with no personalization or history. |

## Chat Profiles

### Profile Components
- **Name**: Identifier used to select the profile
- **Description**: Brief explanation of the profile's purpose
- **System Prompt**: Instructions that guide the LLM's behavior and personality
- **Search Settings**:
  - **Sites**: List of site name patterns to filter search results
  - **Threshold**: Similarity threshold for vector search (0-1)
  - **Limit**: Maximum number of results to return

### Profile Selection
- Set via `--profile` parameter or `CHAT_PROFILE` environment variable
- Can be changed during a chat session with `profile <name>` command
- Profiles are loaded from YAML files in the profiles directory
- Default profile is used if specified profile is not found

### Site Filtering
- If `sites` array is empty, searches ALL sites in the database
- If `sites` array contains patterns, only searches sites with matching names
- Pattern matching is case-insensitive and partial (e.g., "pydantic" matches "Pydantic Docs")
- Multiple patterns can be specified to search across several related sites

## Memory and Conversation History

### Storage
- All messages (user, assistant, system) are stored in the database
- Messages are grouped by session ID
- Messages include metadata (user ID, profile, preferences)
- Messages include timestamps

### Retrieval
- When starting a chat session with an existing session ID, previous messages are loaded
- A sliding window approach is used to manage very long conversations:
  - Always includes the first few messages for context
  - Includes the most recent messages (up to a limit - 20 )
  - This prevents token limit issues with the LLM

### Conversation Analysis
- When a user asks a question, the system may analyze the conversation history
- An LLM is used to extract relevant information from previous messages
- This analysis focuses on:
  - User preferences (likes, dislikes, favorites)
  - Personal information shared by the user
  - Previous topics related to the current query
  - Commitments or promises made by the assistant
- The analysis is included in the context sent to the LLM for generating responses

### Follow-up Detection
- The system detects when a user asks a follow-up question about something just mentioned
- An LLM is used to determine if the current query is a follow-up to the previous response
- If it is a follow-up, the system:
  - Extracts key entities from the previous response
  - Enhances the search query with these entities
  - Adds a special reminder to the LLM about the previous response
- This ensures continuity in the conversation and prevents the LLM from "forgetting" what it just said

## User Preferences

### Extraction
- When a user expresses a preference (e.g., "I like Corvettes"), the system detects it
- An LLM is used to extract the preference in a clean format
- The preference is stored as metadata with the message

### Storage and Retrieval
- Preferences are stored in the database as part of message metadata
- When loading conversation history, preferences are extracted from metadata
- Unique preferences are added to the system prompt for the LLM
- This ensures the LLM remembers user preferences across multiple chat sessions

### Enhanced Preference System
- Preferences are now stored in a dedicated `user_preferences` table for identified users
- Each preference includes:
  - Type (like, dislike, expertise, experience, goal, etc.)
  - Value (the specific preference)
  - Confidence score (0.0-1.0)
  - Context (why this preference was extracted)
  - Timestamps (created, updated, last used)
  - Source session
  - Active/inactive status
  - Metadata (additional information)

### Preference Management
- CLI commands for managing preferences:
  - `preferences`: List all preferences for the current user
  - `add preference <type> <value> [confidence]`: Manually add a preference
  - `delete preference <id>`: Delete a specific preference
  - `clear preferences`: Delete all preferences for the current user
- API endpoints for preference management:
  - `GET /api/chat/preferences`: List user preferences
  - `POST /api/chat/preferences`: Create a preference
  - `DELETE /api/chat/preferences/{id}`: Delete a preference
  - `PUT /api/chat/preferences/{id}/deactivate`: Deactivate a preference
  - `DELETE /api/chat/preferences`: Clear all preferences

### Confidence Scoring
- Preferences are assigned confidence scores based on certainty:
  - 0.95-1.0: Very high confidence (explicit statements)
  - 0.85-0.94: High confidence (strong implications)
  - 0.75-0.84: Moderate confidence (reasonable inferences)
  - 0.65-0.74: Low confidence (possible but uncertain)
  - <0.65: Very low confidence (typically not extracted)
- Only preferences with confidence ≥ 0.7 are used in responses by default
- Higher confidence preferences are given more weight in responses

### Smart Preference Merging
- Similar preferences are merged rather than duplicated
- Confidence scores are updated to the maximum of the two scores
- Context information is combined
- Last used timestamp is updated
- This prevents duplicate preferences while enriching existing ones

## Search Process

### Query Intent Analysis
- For complex queries, an LLM is used to determine the search strategy:
  - REGULAR_SEARCH: Standard semantic search for information
  - URL_SEARCH: The user is specifically asking for URLs or links
  - BEST_CONTENT: The user is asking for the best/top/recommended content

### Direct Site Matching
- For simple queries that might be website names or domains:
  - Domain detection for queries containing .com, .org, .net, etc.
  - Site name matching for short queries without question words
  - Direct retrieval of pages from matching sites
  - Higher similarity scores assigned to direct matches
  - This ensures reliable results for website-specific queries

### Search Strategies

#### URL Search
- Retrieves URLs from sites matching the profile's site patterns
- Sorts by recency (most recent first)
- Formats results as a list of URLs with titles and site names

#### Best Content Search
- Retrieves pages with titles and summaries from matching sites
- Sorts by a quality heuristic (currently content length)
- Formats results as a list of the best articles with summaries

#### Regular Search
- If the profile specifies site patterns, searches each matching site separately
- Otherwise, searches all sites
- Uses hybrid search (vector + text) for best results
- Formats results grouped by site

### Hybrid Search Process
The system uses a sophisticated hybrid search approach that combines vector similarity with text matching:

1. **Vector Search Component**:
   - Generate an embedding for the query using OpenAI's embedding model
   - Search the database for documents with similar embeddings
   - Filter results based on similarity threshold and site ID (if specified)
   - Sort results by similarity score

2. **Text Search Component**:
   - Parse the query for keywords
   - Search the database for documents containing those keywords
   - Filter results based on site ID (if specified)
   - Sort results by relevance

3. **Combined Results**:
   - Merge results from both search methods
   - Remove duplicates
   - Prioritize results that appear in both search methods
   - Return the top results based on the limit

This hybrid approach ensures that even when vector similarity might not find exact matches, the text search component can still retrieve relevant information. The system automatically adjusts the search strategy based on the query type and available content.

## Response Generation

### Context Assembly
1. System prompt from the profile
2. User information (name, preferences)
3. Current date and time
4. Conversation history (sliding window)
5. Current query
6. Follow-up context (if applicable)
7. Conversation analysis (if applicable)
8. Search results

### Preference Integration
- User preferences are retrieved from the database with a minimum confidence of 0.7
- Preferences are grouped by type (like, dislike, expertise, experience, goal, etc.)
- Each preference type is added to the system prompt as a separate section
- Each preference includes its confidence score and context
- This organization makes it easier for the LLM to understand and use preferences naturally
- The `last_used` timestamp is updated for each preference used in a response

### LLM Processing
- All context is sent to the LLM (OpenAI API)
- The LLM generates a response based on the context
- The response is formatted and displayed to the user
- The response is saved to the conversation history

## Command Flow

### Starting a Chat Session
1. Parse command-line arguments
2. Load profiles from the specified directory
3. Set up the session ID (from parameter, environment variable, or generate new)
4. Initialize the ChatBot with the specified parameters
5. Load conversation history for the session
6. Display welcome message and session information
7. Start the chat loop

### Chat Loop
1. Get user input
2. Check for special commands (exit, clear, history, profiles, profile)
3. If not a command, process as a query:
   - Show "Thinking..." indicator
   - Get response from the LLM
   - Display the response
4. Repeat until user exits

### Processing a Query
1. Add user message to conversation history
2. Check for special query types (user info, time)
3. Check if it's a follow-up question
4. Search for relevant context
5. Analyze conversation history
6. Assemble context for the LLM
7. Generate response using the LLM
8. Add assistant message to conversation history
9. Return the response

## Configuration Options

### Environment Variables
- `OPENAI_API_KEY`: API key for OpenAI
- `CHAT_MODEL`: OpenAI model to use for chat (default: gpt-4o)
- `CHAT_RESULT_LIMIT`: Maximum number of search results (default: 5)
- `CHAT_SIMILARITY_THRESHOLD`: Similarity threshold for vector search (default: 0.5)
- `CHAT_SESSION_ID`: Default session ID
- `CHAT_USER_ID`: Default user ID
- `CHAT_PROFILE`: Default chat profile (default: default)
- `CHAT_PROFILES_DIR`: Directory containing profile YAML files (default: profiles)
- `CHAT_VERBOSE`: Enable verbose debug output (default: false)
- `OPENAI_EMBEDDING_MODEL`: Model to use for embeddings (default: text-embedding-3-small)
- `OPENAI_CONTENT_MODEL`: Model to use for title and summary generation (default: gpt-4o-mini)

### Command-Line Parameters
- `--model`: OpenAI model to use
- `--limit`: Maximum number of search results
- `--threshold`: Similarity threshold for vector search
- `--session`: Session ID for the conversation
- `--user`: User ID for the conversation
- `--profile`: Chat profile to use
- `--profiles-dir`: Directory containing profile YAML files
- `--new-session`: Start a new session (ignore saved session ID)
- `--verbose`: Enable verbose debug output

### Profile Settings (YAML)
```yaml
name: profile_name
description: Profile description
system_prompt: |
  Instructions for the LLM
search_settings:
  sites: ["site1", "site2"]  # Site patterns to search
  threshold: 0.6  # Similarity threshold
  limit: 8  # Result limit
```

## LLM Usage Throughout the System

| Component | Purpose | Model Used |
|-----------|---------|------------|
| Embeddings | Generate vector embeddings for search | text-embedding-3-small |
| Title/Summary Generation | Create titles and summaries for crawled content | gpt-4o-mini |
| Chat Responses | Generate responses to user queries | gpt-4o (configurable) |
| Conversation Analysis | Extract relevant information from conversation history | Same as chat model |
| Follow-up Detection | Determine if a query is a follow-up question | Same as chat model |
| Entity Extraction | Extract key entities from previous responses | Same as chat model |
| Preference Extraction | Extract user preferences from messages with confidence scoring | gpt-4o-mini |
| Query Intent Analysis | Determine the best search strategy | Same as chat model |
| Domain Matching | Enhance search for website-specific queries | N/A (rule-based) |

## Complete Flow Example

### Scenario: Returning User Asks About a Topic

1. **Startup**:
   - User starts chat with `python chat.py --user Joe --session abc123 --verbose`
   - System loads profiles from the profiles directory
   - ChatBot is initialized with the specified user and session
   - System enables verbose debug output
   - System loads conversation history for session abc123
   - System retrieves user preferences from the database
   - Welcome message and session information are displayed

2. **User Query**:
   - User asks "Tell me more about Corvettes"
   - System adds user message to conversation history
   - System analyzes the message for preferences (none found in this query)

3. **Query Processing**:
   - System checks if this is a follow-up question (in this case, it's not)
   - System uses an LLM to analyze the query intent (REGULAR_SEARCH)
   - System searches for relevant context using the regular search strategy
   - System filters search results based on the profile's site patterns
   - System formats the search results

4. **Preference Retrieval**:
   - System retrieves active preferences for user "Joe" with confidence ≥ 0.7
   - System groups preferences by type (likes, dislikes, expertise, etc.)
   - System updates the `last_used` timestamp for each preference
   - System adds preferences to the system prompt, organized by type

5. **Conversation Analysis**:
   - System analyzes the conversation history using an LLM
   - System extracts that the user likes Corvettes (from previous messages)
   - System includes this information in the context

6. **Response Generation**:
   - System assembles the context:
     - System prompt from the profile
     - User information ("The user's name is Joe")
     - Current date and time
     - User preferences (grouped by type)
     - Conversation history
     - Current query
     - Conversation analysis
     - Search results
   - System sends the context to the LLM
   - LLM generates a response
   - System adds the response to the conversation history
   - System displays the response to the user

7. **Follow-up Query**:
   - User asks "What's the best model?"
   - System adds user message to conversation history
   - System analyzes the message for preferences (none found in this query)
   - System detects this is a follow-up question about Corvettes
   - System extracts key entities from the previous response (Corvettes, models, etc.)
   - System enhances the search query with these entities
   - System searches for relevant context
   - System includes the previous response in the context
   - System generates and displays a response

8. **Preference Management**:
   - User types `preferences` to view their stored preferences
   - System displays a table of all preferences for user "Joe"
   - User adds a new preference with `add preference expertise Corvettes 0.95`
   - System saves the preference to the database with context "Manually added via CLI"
   - User can delete a preference with `delete preference <id>` if needed
   - User can clear all preferences with `clear preferences` if needed

This flow demonstrates how the system maintains context, remembers user preferences, and provides continuity in the conversation, even across multiple chat sessions. The enhanced preference system allows for more nuanced understanding of user characteristics and more natural integration into responses.

## Clearing Conversation History

### Clear Current Session
- Command: `clear`
- Deletes all messages for the current session from the database
- Resets the in-memory conversation history
- Adds a new system message with the profile's system prompt

### Clear All Sessions
- Command: `clear all`
- Requires confirmation
- Deletes all messages for all sessions from the database
- Resets the in-memory conversation history
- Adds a new system message with the profile's system prompt

## Error Handling

- Database connection errors: Fallback to chat-only mode
- LLM API errors: Display error message and continue
- User interruptions (Ctrl+C): Graceful handling with option to continue
- Empty queries: Prompt for valid input
- Invalid commands: Display help message 

## Docker Deployment Options

The system can be deployed using Docker in three different configurations, each offering different levels of integration and complexity. This section provides detailed information about each option, including setup instructions, configuration details, and troubleshooting tips.

### 1. API-Only Docker Deployment

This is the simplest deployment option, containerizing only the API service while relying on external Supabase and Crawl4AI instances.

#### Components
- **Containerized**: API service, Frontend UI
- **External**: Supabase database, Crawl4AI service

#### Configuration
The API-only deployment uses the root `.env` file for configuration. Key environment variables:

```env
# External Supabase configuration
SUPABASE_URL=your_supabase_host:port
SUPABASE_DB=postgres
SUPABASE_KEY=postgres
SUPABASE_PASSWORD=postgres

# External Crawl4AI configuration
CRAWL4AI_API_TOKEN=your_crawl4ai_api_token
CRAWL4AI_BASE_URL=your_crawl4ai_base_url
```

#### Setup and Deployment

1. Build and start the container:
   ```bash
   docker-compose -f docker/docker-compose.yml up -d
   ```

2. Access the services:
   - API: http://localhost:8001
   - API Documentation: http://localhost:8001/docs
   - Frontend UI: http://localhost:3000
   - Supabase Explorer: http://localhost:8501

3. Interact with the container:
   ```bash
   # Execute commands inside the API container
   docker exec -it supachat-api bash
   
   # Run a crawl from inside the container
   python run_crawl.py
   
   # Start a chat session from inside the container
   python chat.py
   ```

#### Network Architecture
- The API container exposes ports 8001 (API) and 8501 (Supabase Explorer)
- The Frontend container exposes port 3000
- The containers connect to external Supabase and Crawl4AI services over the internet
- The Frontend container communicates with the API container via http://api:8001
- Both containers are connected via an internal Docker network

### 2. API + Crawl4AI Docker Deployment

This option containerizes the API service, Frontend UI, and the Crawl4AI service, creating a more integrated deployment while still relying on an external Supabase instance.

#### Components
- **Containerized**: API service, Frontend UI, Crawl4AI service
- **External**: Supabase database

#### Configuration
This deployment uses the root `.env` file with specific settings for the Crawl4AI service:

```env
# External Supabase configuration
SUPABASE_URL=your_supabase_host:port
SUPABASE_DB=postgres
SUPABASE_KEY=postgres
SUPABASE_PASSWORD=postgres

# Crawl4AI configuration (automatically set in the container)
CRAWL4AI_API_TOKEN=your_crawl4ai_api_token
# CRAWL4AI_BASE_URL=http://crawl4ai:11235  # Uncomment in container, comment out for local use
```

#### Setup and Deployment

1. Build and start the containers:
   ```bash
   docker-compose -f docker/crawl4ai-docker-compose.yml up -d
   ```

2. Access the services:
   - API: http://localhost:8001
   - API Documentation: http://localhost:8001/docs
   - Frontend UI: http://localhost:3000
   - Supabase Explorer: http://localhost:8501
   - Crawl4AI: http://localhost:11235

3. Interact with the containers:
   ```bash
   # Execute commands inside the API container
   docker exec -it supachat-api bash
   
   # Run a crawl from inside the container
   python run_crawl.py
   
   # Check Crawl4AI logs
   docker logs supachat-crawl4ai
   ```

#### Network Architecture
- All containers are connected via an internal Docker network named `supachat-network`
- The API container communicates with the Crawl4AI container using the service name `crawl4ai`
- The Frontend container communicates with the API container using the service name `api`
- The API container connects to the external Supabase instance over the internet
- Ports 8001 (API), 3000 (Frontend), 8501 (Supabase Explorer), and 11235 (Crawl4AI) are exposed to the host

### 3. Full-Stack Docker Deployment

The most comprehensive deployment option, containerizing the entire stack: API service, Frontend UI, Crawl4AI service, and Supabase (including database, Kong API gateway, and other Supabase services).

#### Components
- **Containerized**: 
  - API service
  - Frontend UI
  - Crawl4AI service
  - Supabase services:
    - PostgreSQL database
    - Kong API gateway
    - Supabase Studio
    - Meta service
    - REST API

#### Configuration
The full-stack deployment uses a separate `.env` file located in the `docker/` directory:

```env
# API Configuration
OPENAI_API_KEY=your_openai_api_key
CRAWL4AI_API_TOKEN=your_crawl4ai_api_token
CRAWL4AI_BASE_URL=http://crawl4ai:11235

# OpenAI Models
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CONTENT_MODEL=gpt-4o-mini
CHAT_MODEL=gpt-4o

# Supabase Configuration
POSTGRES_PASSWORD=your-super-secret-and-long-postgres-password
JWT_SECRET=your-super-secret-jwt-token-with-at-least-32-characters
ANON_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
DASHBOARD_PASSWORD=your-dashboard-password

# Connection Information for Application
SUPABASE_HOST=db
SUPABASE_PORT=5432
SUPABASE_DB=postgres
SUPABASE_KEY=supabase_admin
SUPABASE_PASSWORD=${POSTGRES_PASSWORD}

# IMPORTANT: Comment out or leave empty to ensure direct database connection
# SUPABASE_URL=http://kong:8002
```

#### Critical Environment Variable Configuration

The `SUPABASE_URL` environment variable requires special attention:

1. **Direct Database Connection**: The API service should connect directly to the database using the PostgreSQL protocol, not through Kong. To ensure this:
   - Comment out or leave empty the `SUPABASE_URL` variable in your `.env` file
   - Ensure the direct connection parameters are set correctly:
     ```
     SUPABASE_HOST=db
     SUPABASE_PORT=5432
     SUPABASE_KEY=supabase_admin
     SUPABASE_PASSWORD=${POSTGRES_PASSWORD}
     ```

2. **Kong's Role**: Kong is an API gateway that routes HTTP/HTTPS requests, not database connections. It's used by:
   - The frontend to access REST API endpoints
   - Supabase Studio for database management
   - External clients accessing the API

3. **SSL Negotiation Errors**: If `SUPABASE_URL` is set to `http://kong:8002`, the API will try to connect to Kong for database operations, resulting in SSL negotiation errors.

#### Setup and Deployment

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

3. Edit the Docker-specific `.env` file if needed:
   ```bash
   nano .env
   ```

4. Start all services:
   ```bash
   docker-compose -f full-stack-compose.yml up -d
   ```

5. Access the services:
   - API: http://localhost:8001
   - API Documentation: http://localhost:8001/docs
   - Frontend UI: http://localhost:3000
   - Supabase Studio: http://localhost:3001
   - Kong API Gateway: http://localhost:8002
   - Crawl4AI: http://localhost:11235

6. Check service status:
   ```bash
   ./status.sh
   ```

7. Reset everything (if needed):
   ```bash
   ./reset.sh
   ```

#### Network Architecture
- All containers are connected via an internal Docker network named `supachat-network`
- The API container communicates with the database using direct connection parameters:
  - Host: `db`
  - Port: `5432`
- The API container communicates with Crawl4AI using the service name `crawl4ai`
- The Frontend container communicates with the API container using the service name `api`
- Persistent data is stored in Docker volumes:
  - `pgdata`: PostgreSQL database files
  - `volumes/db/init`: Database initialization scripts
  - `volumes/api`: API configuration files
  - `volumes/shm`: Shared memory for Crawl4AI

#### Kong Configuration

The Kong configuration file is located at `volumes/api/kong.yml`. This file is mounted to the Kong container and defines the API routes and services:

```yaml
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
```

If you need to modify the Kong configuration:
1. Edit `volumes/api/kong.yml`
2. Restart Kong:
   ```bash
   docker-compose -f full-stack-compose.yml restart kong
   ```

#### Troubleshooting

1. **Database Connection Issues**:
   - Check if the database container is healthy: `docker ps | grep supachat-db`
   - Verify the database credentials in the `.env` file
   - Ensure the API container has the correct environment variables:
     ```bash
     docker exec -it supachat-api env | grep SUPA
     ```
   - If you see SSL negotiation errors, make sure `SUPABASE_URL` is commented out or empty in your `.env` file
   - Restart the API service after making changes:
     ```bash
     docker-compose -f full-stack-compose.yml restart api
     ```

2. **REST Service Issues**:
   - If the REST service is not connecting properly, run the fix script:
     ```bash
     ./fix_rest.sh
     ```
   - This script will:
     - Extract the correct database password from your `.env` file
     - Restart the REST service with the correct configuration
     - Restart Kong to ensure it connects to the REST service

3. **Missing Database Tables**:
   - The setup script should create all necessary tables
   - If tables are missing, you can manually set up the database:
     ```bash
     docker exec -it supachat-api python main.py setup
     ```

4. **Restarting Services**:
   - Restart a specific service:
     ```bash
     docker-compose -f full-stack-compose.yml restart api
     ```
   - Restart all services:
     ```bash
     docker-compose -f full-stack-compose.yml down
     docker-compose -f full-stack-compose.yml up -d
     ```

5. **Checking Logs**:
   - View logs for a specific service:
     ```bash
     docker logs supachat-api
     docker logs supachat-kong
     docker logs supachat-frontend
     ```
   - Follow logs in real-time:
     ```bash
     docker logs -f supachat-api
     ```

### Docker Volumes and Data Persistence

The full-stack Docker setup uses several volumes to persist data:

1. **pgdata**: Stores PostgreSQL database files
   - Location: Docker managed volume
   - Content: All database data, including tables, indexes, and stored procedures
   - Persistence: Survives container restarts and rebuilds

2. **volumes/db/init**: Contains database initialization scripts
   - Location: `docker/volumes/db/init/`
   - Content:
     - `00-initial-schema.sql`: Initial Supabase schema
     - `03-post-setup.sql`: Post-setup configuration
     - `04-app-tables.sql`: Application-specific tables
   - Execution: Scripts run in alphabetical order when the database container is first initialized

3. **volumes/api**: Contains API configuration files
   - Location: `docker/volumes/api/`
   - Content: `kong.yml` - Kong API gateway configuration

4. **volumes/shm**: Shared memory for Crawl4AI
   - Location: `docker/volumes/shm/`
   - Content: Temporary files used by Crawl4AI for browser automation
   - Note: This directory should be excluded from version control

### Docker Networking

The full-stack setup creates a custom bridge network named `supachat-network` that allows containers to communicate with each other using service names as hostnames:

- `api` → `db`: Direct PostgreSQL connection (port 5432)
- `api` → `crawl4ai`: HTTP connection (port 11235)
- `studio` → `meta`: HTTP connection (port 8080)
- `studio` → `kong`: HTTP connection (port 8000)
- `kong` → `rest`: HTTP connection (port 3000)
- `kong` → `meta`: HTTP connection (port 8080)

This network isolation provides security benefits and simplifies container communication without exposing unnecessary ports to the host system.

### Environment Variable Precedence

When using Docker, environment variables are resolved in the following order (highest precedence first):

1. Variables defined in the `environment` section of the Docker Compose file
2. Variables defined in the `.env` file in the same directory as the Docker Compose file
3. Variables defined in the container's environment

This precedence order is important to understand when troubleshooting configuration issues. For example, even if `SUPABASE_URL` is commented out in your `.env` file, it might still be set in the Docker Compose file's `environment` section.
