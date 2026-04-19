# Supa Crawl Chat Frontend TODOs

## Recent Improvements (2025-03-14)

### Site Details Page Enhancements
- ✅ **Fixed Pagination Issues**: Updated pagination to only count parent pages, not chunks
  - Added page size selector (5, 10, 20, 50 items per page)
  - Improved pagination controls with first/last page buttons
  - Added visual indicators for empty pages and better page count display
  - Fixed issue with empty pages appearing in pagination

- ✅ **Improved Page List Display**:
  - Added expandable chunks feature with dropdown arrows
  - Enhanced date display with proper formatting
  - Added debug mode for troubleshooting date issues
  - Improved sorting functionality with loading indicators

- ✅ **Enhanced Content Display**:
  - Added better content source indicators (database vs. live)
  - Improved content rendering with HTML/Markdown detection
  - Added debug information panel for developers

- ✅ **UI Improvements**:
  - Added refresh buttons for site and pages data
  - Enhanced search functionality with clear button
  - Improved empty state displays with helpful messages
  - Added visual feedback for loading states

## Content Display Issues

### Current Problems

1. ~~**Missing API Endpoint**: The `/api/pages/{pageId}/` endpoint returns 404, making it impossible to directly fetch a single page's content.~~
   -~~This forces us to use workarounds like fetching from `/api/sites/{siteId}/pages/` with `include_chunks=true` or using the search API.~~

2. **Inconsistent Content Storage**: Some pages have content in the database, while others only have metadata (URL, title, summary).
   - This is likely by design for chunking purposes (vector search for AI), but makes UI display challenging.

3. **Content Rendering**: Need better detection and rendering of HTML/Markdown content from the database.
   - ✅ Basic implementation added, but could be improved with syntax highlighting and better MIME type detection

### Desired Behavior

- ✅ The UI should show exactly what's in the database for each page/chunk to understand what was crawled and chunked.
- ✅ Users should be able to see individual chunks (chunk 0, chunk 1, etc.) for a page.
- ✅ The UI should replace the need to use Supabase Studio to view page content.
- ✅ Live URL viewing is secondary - users can click the URL to visit the actual page if needed.

## Docker and API Issues

### Current Problems

1. ~~**Profiles Endpoint Redirect Issue**: The `/api/chat/profiles/` endpoint returns a 307 Temporary Redirect in Docker.~~
   ~~- When accessed through nginx in the Docker setup, requests with trailing slashes cause redirect loops.~~
   ~~- This affects the profiles dropdown in the chat interface, preventing users from selecting different AI personalities.~~
   ~~- The issue only occurs in the Docker environment, not when running the app natively.~~
   ~~- Multiple attempted fixes (rewriting URLs, modifying FastAPI settings, updating frontend code) have not resolved the issue.~~
   
   **FIXED (2025-03-12)**: The trailing slash issue has been resolved by:
   - Modifying the API router in `api/routers/sites.py` to use an empty string instead of a trailing slash in the route definition: `@router.get("", response_model=SiteList)` instead of `@router.get("/", response_model=SiteList)`.
   - **UPDATED (2025-03-12)**: Made the Vite proxy configuration environment-aware by:
     - Using an environment variable `DOCKER_ENV` to determine the API target URL
     - In Docker: uses `host.docker.internal:8001`
     - In native development: uses `localhost:8001`
     - Added the `DOCKER_ENV=true` environment variable to the Docker Compose configuration
   - The root cause was that the API routes were registered with trailing slashes, but the frontend was making requests without them, causing 307 redirects.
   - This fix ensures that the API correctly handles requests without trailing slashes, which is the convention used by the frontend.

2. ~~**Sites Endpoint Redirect Issue**: The `/api/sites/` endpoint returns a 307 Temporary Redirect in Docker.~~
   ~~- Similar to the profiles issue, this affects the sites listing and site details pages.~~
   ~~- The issue only occurs in the Docker environment, not when running the app natively.~~
   
   **FIXED (2025-03-12)**: Fixed with the same solution as the profiles endpoint issue above.

### Trailing Slash Handling

**IMPORTANT (2025-03-12)**: The API now handles trailing slashes correctly through a dual approach:

1. **Router Level**: All router endpoints are defined without trailing slashes using `@router.get("")` instead of `@router.get("/")`.
2. **Middleware Level**: The `TrailingSlashMiddleware` in `api/main.py` removes trailing slashes from incoming requests.

When a request with a trailing slash is received, you'll see a log message like:
```
Removing trailing slash: /api/search/ -> /api/search
```

This is expected behavior and indicates that the middleware is working correctly.

#### Adding New Endpoints

When adding new endpoints to the API, follow these guidelines:

1. **Root Endpoints**: Use empty strings instead of trailing slashes:
   ```python
   # CORRECT
   @router.get("", response_model=MyResponseModel)
   async def my_endpoint():
       # ...

   # INCORRECT - DO NOT USE
   @router.get("/", response_model=MyResponseModel)
   async def my_endpoint():
       # ...
   ```

2. **Subpath Endpoints**: Use the subpath without a trailing slash:
   ```python
   # CORRECT
   @router.get("/subpath", response_model=MyResponseModel)
   async def my_subpath_endpoint():
       # ...

   # INCORRECT - DO NOT USE
   @router.get("/subpath/", response_model=MyResponseModel)
   async def my_subpath_endpoint():
       # ...
   ```

3. **Path Parameters**: Use the path parameter without a trailing slash:
   ```python
   # CORRECT
   @router.get("/{item_id}", response_model=MyResponseModel)
   async def get_item(item_id: int):
       # ...

   # INCORRECT - DO NOT USE
   @router.get("/{item_id}/", response_model=MyResponseModel)
   async def get_item(item_id: int):
       # ...
   ```

#### Frontend API Requests

When making API requests from the frontend, you can use either format (with or without trailing slashes) since the middleware will handle it, but it's recommended to be consistent and use the format without trailing slashes:

```typescript
// RECOMMENDED
const response = await apiClient.get('/sites');
const response = await apiClient.get(`/sites/${siteId}`);
const response = await apiClient.get(`/sites/${siteId}/pages`);

// WORKS BUT NOT RECOMMENDED
const response = await apiClient.get('/sites/');
const response = await apiClient.get(`/sites/${siteId}/`);
const response = await apiClient.get(`/sites/${siteId}/pages/`);
```

### Workarounds

~~- For now, users should be aware that the profiles dropdown may not work in the Docker environment.~~
~~- When developing locally (non-Docker), the profiles feature works as expected.~~
~~- Future investigation is needed to determine if this is related to how FastAPI handles trailing slashes or how nginx proxies requests.~~

**RESOLVED (2025-03-12)**: No workarounds needed anymore as the issue has been fixed. The API now correctly handles requests without trailing slashes.

## Future Improvements

### Backend Enhancements

1. ~~**`/api/pages/{pageId}` and chunks**~~ — **Done** (`api/routers/pages.py`): `GET /api/pages/{page_id}`, `GET /api/pages/{page_id}/chunks`, `POST /api/pages/maintenance/deduplicate`. Frontend uses `apiService.getPageById` / `getPageChunks`.

2. **API discoverability (non-OpenAPI)** — **Done** (`GET /api`): returns `openapi_url`, `docs_url`, and a `capabilities` map listing crawl, sites, pages, search, and chat routes so scripts and integrations can mirror the UI without hunting through `/docs`.

3. **Ensure consistent metadata (created_at, updated_at) is returned for all pages.**
   - ✅ Partially implemented in the database query, but needs to be consistent across all endpoints
   - All page-related endpoints should return consistent metadata.
   - Use the `from_dict` method to ensure consistent conversion of datetime objects to strings.
   - Example implementation:
   ```python
   @classmethod
   def from_dict(cls, page_dict):
       """Create a Page from a dictionary, converting datetime to string if needed."""
       if 'created_at' in page_dict and page_dict['created_at'] is not None:
           if not isinstance(page_dict['created_at'], str):
               page_dict['created_at'] = str(page_dict['created_at'])
       if 'updated_at' in page_dict and page_dict['updated_at'] is not None:
           if not isinstance(page_dict['updated_at'], str):
               page_dict['updated_at'] = str(page_dict['updated_at'])
       return cls(**page_dict)
   ```

4. ~~**Fix Docker API Redirect Issues**: Resolve the 307 redirect issue with trailing slashes in the Docker environment.~~
   ~~- Investigate FastAPI's `redirect_slashes` setting and its interaction with nginx.~~
   ~~- Consider modifying the API to explicitly handle both versions of endpoints (with and without trailing slashes).~~
   ~~- Ensure consistent behavior between Docker and native environments.~~
   
   **COMPLETED (2025-03-12)**: The Docker API redirect issues have been resolved by modifying the route definitions in the API to match the frontend's convention (no trailing slashes).

### Frontend Enhancements

1. **Content View Improvements**:
   - ✅ Added toggle between raw and rendered content
   - Better MIME type detection for rendered content
   - Add syntax highlighting for code blocks
   - Add options to download content as file

2. **Chunk Navigation**:
   - ✅ Added expandable chunks feature to easily navigate between chunks of the same page
   - ✅ Show chunk relationships and context
   - Add ability to compare chunks side by side

3. **Database Explorer**:
   - Create a more comprehensive database explorer view
   - Show vector embeddings and similarity scores
   - Allow editing of page metadata

4. **User Experience**:
   - ✅ Added loading states for async operations
   - ✅ Improved error handling and user feedback
   - ✅ Added pagination for large result sets
   - ✅ Added search functionality with clear button
   - ✅ Added refresh buttons for site and pages data

5. **User Profile**:
   - Complete user profile functionality
   - Add preferences for default view modes
   - ✅ Added mute notifications preference that persists in local storage
   - ✅ Added Switch component to UI library (@radix-ui/react-switch)

6. **Performance Optimizations**:
   - Implement virtualized lists for better performance with large datasets
   - Add caching for frequently accessed data
   - Optimize API calls to reduce data transfer

## Implementation Priority (updated 2026-04)

1. ✅ Fix content display issues by improving the existing workarounds
2. ✅ Core pages API + `GET /api` capabilities map for full API-driven workflows
3. ✅ Add chunk navigation (site detail)
4. ✅ Improve content rendering (raw vs rendered; further polish below)
5. **Next (highest value)**:
   - **Content UX**: Syntax highlighting for code blocks in rendered page/chat content; stronger MIME / HTML vs markdown detection
   - **Performance**: Virtualized lists on site detail + search when hundreds of rows; optional smaller page list payloads
   - **Preferences UI**: Tighter integration with chat (indicators when prefs apply); optional “Memory” summary — backend already exposes `/api/chat/preferences`
   - **Explorer**: Lightweight “embeddings / stats” view is still optional; Supabase Explorer remains the heavy option
6. User profile: optional defaults (threshold, site filter) stored in UI only or future API
7. ~~Docker API / trailing slash~~ **Done**
8. Performance optimizations for large datasets (see above)

## Notes for Development

- The current implementation uses multiple approaches to fetch content:
  1. Try to get content from the sites API with `include_chunks=true`
  2. Try the search API as a fallback
  3. Fetch from the live URL as a last resort

- Remember that the primary goal is to show what's in the database, not to recreate the original page.
- Keep the UI simple and focused on the data exploration use case.
- **Docker Environment**: Be cautious when making changes that might affect the Docker environment differently than the native environment. Test both scenarios when possible.

## Completed Features (2025-03-14)

### Site Details Page
- ✅ Implemented expandable chunks feature
- ✅ Fixed pagination to only count parent pages
- ✅ Added page size selector
- ✅ Improved pagination controls
- ✅ Enhanced date display
- ✅ Added debug mode for troubleshooting
- ✅ Improved sorting functionality
- ✅ Added refresh buttons
- ✅ Enhanced search functionality
- ✅ Improved empty state displays
- ✅ Added visual feedback for loading states

### API and Backend
- ✅ Fixed Docker API redirect issues
- ✅ Implemented trailing slash handling
- ✅ Updated database query to include date fields
- ✅ Added debug information for developers

### Content Display
- ✅ Added content source indicators
- ✅ Improved content rendering
- ✅ Added debug information panel
- ✅ Enhanced content view toggle

### User Preferences
- ✅ Added mute notifications toggle in notification center
- ✅ Implemented persistent notification preferences using local storage
- ✅ Updated notification info page with mute option and documentation
- ✅ Added Switch component to UI library (@radix-ui/react-switch)

## Known Issues

1. **TypeScript Linter Error**: There's a persistent TypeScript linter error about "Property 'id' does not exist on type 'never'" in the `SiteDetailPage.tsx` file. This is a type inference issue that doesn't affect functionality.

2. **Date Display Inconsistency**: Some pages may still show "No date information available" if the database doesn't have date information for those pages. This is a data issue, not a UI issue.

3. **Content Rendering**: The content rendering could be improved with better MIME type detection and syntax highlighting for code blocks.

4. **Performance with Large Datasets**: The current implementation may have performance issues with very large datasets (hundreds of pages). Future optimizations should include virtualized lists and pagination improvements.

## Next Steps

1. ~~Implement `/api/pages/{id}` and chunks~~ — shipped; use `GET /api` for the full route map
2. Enhance content rendering (syntax highlighting, safer HTML, markdown tables)
3. Virtualize long lists; reduce duplicate fetches (site detail already prefers one pages request)
4. Optional: embedded “stats” panel (counts, last crawl) using existing `/api/sites` + search
5. User profile: saved UI defaults (not blocking API parity)

## Implementation Notes (2025-03-14)

### Notification System Enhancements
- Added mute notifications feature that allows users to disable popup notifications while still keeping them in the notification center
- The mute preference is stored in local storage and persists between sessions
- Added a Switch component to the UI library for toggling preferences
- Updated the NotificationCenter component to include a mute toggle
- Enhanced the NotificationInfo page with documentation about the mute feature
- Even when muted, error notifications will still show popups to ensure critical issues are not missed
- Fixed direct toast calls throughout the application to use the notification system that respects the mute setting

### Chat Session Enhancements
- Added session ID display and copy functionality to help with database debugging
- Session IDs are now visible on hover and can be copied to clipboard with a single click
- Maintained user-friendly session names in the UI while providing access to the underlying database IDs
- Added tooltips to explain the purpose of session IDs

## Enhanced Memory and Preference System (Planned)

### Overview
The current preference system relies too heavily on explicit keyword triggers and doesn't provide meaningful context to conversations. The plan is to implement a more natural and intelligent memory system similar to ChatGPT's personalization features.

### Core Components

1. **Smart Preference Extraction**
   - Replace keyword-based preference detection with intelligent LLM analysis
   - Implement continuous context understanding during conversations
   - Use smaller LLM model for efficient real-time analysis
   - Extract meaningful preferences and context that actually enhance future conversations

2. **Dual Memory Architecture**
   - **Session Memory** (session_id based):
     - Maintains conversation flow and immediate context
     - Tracks discussion topics and temporary preferences
     - Handles follow-up questions and conversation continuity
   
   - **User Memory** (user_id based):
     - Stores long-term user preferences and characteristics
     - Maintains consistent user understanding across sessions
     - Handles persistent user traits and preferences

3. **Database Schema Updates**
   - Add new `user_preferences` table:
     ```sql
     CREATE TABLE user_preferences (
       id SERIAL PRIMARY KEY,
       user_id TEXT NOT NULL,
       preference_type TEXT NOT NULL,
       preference_value TEXT NOT NULL,
       context TEXT,
       confidence FLOAT,
       created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
       last_used TIMESTAMP WITH TIME ZONE,
       source_session TEXT
     );
     ```
   - Add preference metadata improvements:
     - Track preference strength/confidence
     - Store contextual information
     - Track when/where preference was learned
     - Enable preference versioning and updates

4. **Frontend Enhancements**
   - Create new "Memory & Preferences" page:
     - Display active user preferences with context
     - Show preference history and changes
     - Allow manual preference management
     - Visualize preference confidence levels
   - Add preference indicators in chat:
     - Show when AI is using remembered preferences
     - Indicate new preference learning
     - Allow immediate preference correction
   - Implement preference sync:
     - Real-time updates between UI and database
     - Conflict resolution for preference changes
     - Batch preference updates

### Implementation Status (2025-03-20)

#### ✅ Completed Backend Implementation

1. **Database Schema**
   - ✅ Created new `user_preferences` table with fields for:
     - User ID, preference type, preference value
     - Confidence score (0-1)
     - Context information
     - Timestamps (created, updated, last used)
     - Source session tracking
     - Active/inactive flag
   - ✅ Added database functions:
     - `merge_preference_contexts`: Combines old and new context information
     - `update_user_preference`: Smart upsert function for preferences
     - `get_user_preferences`: Retrieves preferences with filtering options
   - ✅ Created indexes for efficient querying

2. **Database Client**
   - ✅ Added methods to `SupabaseClient`:
     - `save_user_preference`: Creates or updates preferences
     - `get_user_preferences`: Retrieves preferences with filtering
     - `deactivate_user_preference`: Soft-deletes preferences
     - `delete_user_preference`: Hard-deletes preferences
     - `get_preference_by_id`: Gets a single preference
     - `update_preference_last_used`: Updates usage timestamp
     - `get_preferences_by_type`: Filters by preference type
     - `clear_user_preferences`: Removes all preferences for a user

3. **ChatBot Class**
   - ✅ Updated `add_user_message` to use LLM for preference extraction
   - ✅ Added `analyze_for_preferences` method with intelligent detection
   - ✅ Modified `get_response` to retrieve preferences from database
   - ✅ Enhanced system prompt with preference context and confidence

4. **API Endpoints**
   - ✅ Added new endpoints for preference management:
     - `GET /api/chat/preferences`: List user preferences
     - `POST /api/chat/preferences`: Create a preference
     - `DELETE /api/chat/preferences/{id}`: Delete a preference
     - `PUT /api/chat/preferences/{id}/deactivate`: Deactivate a preference
     - `DELETE /api/chat/preferences`: Clear all preferences

#### Testing Instructions

To test the new preference system, follow these steps:

1. **Setup the Database**
   ```bash
   conda activate supa-crawl-chat
   python main.py setup
   ```

2. **Test CLI Preference Extraction**
   ```bash
   conda activate supa-crawl-chat
   python chat.py --user TestUser
   ```
   
   Try these conversation patterns:
   - Direct preferences: "I really enjoy programming in Python"
   - Indirect preferences: "Whenever I need to build something quickly, I reach for JavaScript"
   - Characteristics: "I've been a software engineer for 10 years"
   - Opinions: "I think Docker is the best way to deploy applications"

3. **Test API Endpoints**
   ```bash
   conda activate supa-crawl-chat
   # Start the API server
   cd api
   uvicorn main:app --reload --port 8001
   ```

   Then use curl or a tool like Postman to test the endpoints:
   
   **List preferences:**
   ```bash
   curl -X GET "http://localhost:8001/api/chat/preferences?user_id=TestUser"
   ```
   
   **Create a preference:**
   ```bash
   curl -X POST "http://localhost:8001/api/chat/preferences?user_id=TestUser" \
     -H "Content-Type: application/json" \
     -d '{"preference_type":"like","preference_value":"REST APIs","context":"Manually added","confidence":0.9}'
   ```
   
   **Delete a preference:**
   ```bash
   curl -X DELETE "http://localhost:8001/api/chat/preferences/1?user_id=TestUser"
   ```

4. **Verify Memory Persistence**
   - Start a chat session with a specific user ID
   - Express some preferences
   - End the session and start a new one with the same user ID
   - Ask "What do you know about me?" or "What do I like?"
   - The AI should recall your preferences from the previous session

5. **Test Cross-Session Memory**
   - Start a chat with user_id=UserA and session_id=Session1
   - Express preferences
   - Start a new chat with user_id=UserA but a different session_id
   - The AI should remember preferences but not conversation details
   - Start a chat with the same session_id but different user_id
   - The AI should remember conversation details but not user preferences

#### Next Steps

1. **Frontend Implementation**
   - Create "Memory & Preferences" page
   - Add preference indicators in chat
   - Implement preference management UI

2. **Refinement**
   - Fine-tune LLM prompt for better preference extraction
   - Optimize confidence thresholds
   - Add preference categorization
   - Implement preference expiration for time-sensitive information

3. **Advanced Features**
   - Add preference strength tracking
   - Implement preference conflict resolution
   - Add preference versioning
   - Create preference analytics

### Notes for Development

- The preference extraction is conservative by design - it's better to miss a preference than to store an incorrect one
- The system uses a smaller LLM model for efficiency in preference extraction
- Preferences are tied to user_id, not session_id, for long-term memory
- The confidence score (0-1) determines how strongly the system believes in a preference
- The context field stores why a preference was extracted, helping with debugging and explanation
- The is_active flag allows for soft deletion of preferences
- The last_used timestamp helps track which preferences are actively being used


