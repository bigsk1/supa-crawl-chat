# Supa Crawl Chat Frontend

A modern React frontend for the Supa Crawl Chat application. This UI provides a user-friendly interface to interact with the Supa Crawl Chat API, allowing you to crawl websites, search content, and chat with your data using AI.

## Features

- **Modern React with TypeScript**: Built with React 18 and TypeScript for type safety
- **Vite**: Fast development server and optimized builds
- **Tailwind CSS**: Utility-first CSS framework for rapid UI development
- **shadcn/ui**: High-quality UI components built with Radix UI and Tailwind CSS
- **Dark Mode**: Full dark mode support with system preference detection
- **Responsive Design**: Works on desktop, tablet, and mobile devices
- **API Integration**: Seamless integration with the Supa Crawl Chat API
- **Notification System**: Toast notifications and notification center for system events

## Pages

- **Home**: Overview of the application features
- **Chat**: Interactive chat interface to query your crawled data
- **Crawl**: Form to start new crawls of websites or sitemaps
- **Search**: Search interface to find content in your crawled data
- **Sites**: List of crawled sites with details and statistics
- **Site Detail**: Detailed view of a specific site with its pages

## Getting Started

### Prerequisites

- Node.js 16+ and npm/yarn

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   # or
   yarn
   ```

3. (Optional) If the backend uses `SCC_API_KEYS` / `API_KEYS`, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_KEY` to a matching key so the UI can call `/api`.

4. Start the development server:
   ```bash
   npm run dev
   # or
   yarn dev
   ```

5. Open your browser and navigate to http://localhost:3001

### Building for Production

```bash
npm run build
# or
yarn build
```

The build output will be in the `dist` directory.

## Project Structure

```
frontend/
├── public/            # Static assets
├── src/
│   ├── api/           # API service and types
│   │   ├── apiService.ts    # Core API service with type definitions
│   │   └── apiWrapper.ts    # Wrapper with notification integration
│   ├── components/    # Reusable UI components
│   │   ├── ui/        # shadcn/ui components
│   │   ├── Navbar.tsx # Main navigation bar
│   │   ├── Sidebar.tsx # Side navigation (mobile)
│   │   └── NotificationCenter.tsx # Notification system
│   ├── context/       # React context providers
│   ├── hooks/         # Custom React hooks
│   ├── pages/         # Page components
│   │   ├── ChatPage.tsx     # Chat interface
│   │   ├── CrawlPage.tsx    # Crawl form and recent crawls
│   │   ├── HomePage.tsx     # Landing page
│   │   ├── SearchPage.tsx   # Search interface
│   │   ├── SitesPage.tsx    # List of crawled sites
│   │   └── SiteDetailPage.tsx # Site details and pages
│   ├── styles/        # Global styles and Tailwind config
│   ├── utils/         # Utility functions
│   │   └── notifications.ts # Notification utilities
│   ├── App.tsx        # Main App component with routing
│   └── main.tsx       # Entry point
├── index.html         # HTML template
├── package.json       # Dependencies and scripts
├── tsconfig.json      # TypeScript configuration
└── vite.config.ts     # Vite configuration
```

## Key Components

### Navigation

- **Navbar.tsx**: Main navigation bar at the top of the application
  - Responsive design that adapts to different screen sizes
  - Contains links to all main pages: Home, Chat, Crawl, Search, Sites
  - Includes theme toggle and notification center

- **Sidebar.tsx**: Side navigation for mobile devices
  - Appears when the hamburger menu is clicked
  - Contains the same navigation items as the Navbar

### UI Components

- **shadcn/ui**: Collection of reusable UI components
  - Button, Input, Select, Dialog, etc.
  - Customized with Tailwind CSS
  - Located in `src/components/ui/`

- **NotificationCenter.tsx**: System for displaying notifications
  - Toast notifications for immediate feedback
  - Notification center for persistent messages
  - Filters out duplicate and unnecessary notifications

### Page Components

- **CrawlPage.tsx**: Interface for crawling websites
  - Form for entering website URL and crawl parameters
  - Display of recent crawls with status and links
  - Refresh functionality to update the list of crawls

- **SitesPage.tsx**: List of crawled sites
  - Grid of site cards with name, URL, and page count
  - Created date displayed for each site
  - Refresh button to update the list

- **SiteDetailPage.tsx**: Detailed view of a specific site
  - Site information and statistics
  - List of pages with titles and URLs
  - Options to search within the site

- **ChatPage.tsx**: Chat interface for interacting with the data
  - Message input for asking questions
  - Display of conversation history
  - Support for markdown, code blocks, and lists in messages

- **SearchPage.tsx**: Interface for searching crawled content
  - Search input with options for filtering
  - Results display with snippets and highlighting
  - Links to view full pages

## API Models

The frontend interacts with several key data models:

### Site

```typescript
interface Site {
  id: number;
  name: string;
  url: string;
  description: string;
  page_count: number;
  created_at: string;  // ISO date string
  updated_at?: string; // ISO date string
}
```

### Page

```typescript
interface Page {
  id: number;
  url: string;
  title: string;
  content?: string;
  summary: string;
  is_chunk: boolean;
  chunk_index: number | null;
  parent_id: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}
```

### CrawlStatus

```typescript
interface CrawlStatus {
  site_id: number;
  site_name: string;
  name?: string;
  url: string;
  page_count: number;
  chunk_count: number;
  total_count: number;
  created_at: string;
  updated_at: string;
  status?: string;
  progress?: number;
  pages_crawled?: number;
  pages_found?: number;
  max_pages?: number;
  depth?: number;
  error?: string;
  next_steps: {
    view_pages: string;
    search_content: string;
  };
}
```

### ChatMessage

```typescript
interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at?: string;
  timestamp?: string;
}
```

### SearchResult

```typescript
interface SearchResult {
  id: number;
  url: string;
  title: string;
  content?: string;
  snippet?: string;
  summary?: string;
  similarity: number;
  context?: string | null;
  is_chunk: boolean;
  chunk_index: number | null;
  parent_id: number | null;
  parent_title?: string | null;
  site_id: number;
  site_name?: string;
}
```

## API Integration

The frontend uses two main services for API integration:

1. **apiService.ts**: Core service that handles direct API calls
   - Defines TypeScript interfaces for API requests and responses
   - Implements caching for GET requests
   - Handles error responses

2. **apiWrapper.ts**: Wrapper around apiService that adds notification integration
   - Tracks API calls and displays appropriate notifications
   - Provides consistent user feedback for loading, success, and error states
   - Can suppress notifications for background operations

Example usage:

```typescript
// Using the API wrapper with notifications
const sites = await api.getSites();

// Starting a crawl with notifications
const result = await api.startCrawl({
  url: 'https://example.com',
  name: 'Example Site',
  depth: 2,
  max_pages: 50
});
```

## Recent Changes and Fixes

### Date Handling

- Added proper date formatting for `created_at` and `updated_at` fields
- Implemented robust date display with fallbacks for invalid dates
- Added special handling for epoch dates (1970-01-01)
- Sort sites and crawls by date (newest first)

### API Response Handling

- Updated to handle the response format with a `sites` array
- Added proper error handling for unexpected response formats
- Improved logging for debugging API responses

### UI Improvements

- Enhanced the CrawlPage with better status indicators
- Improved the Sites page with better card layout
- Fixed navigation links to ensure proper routing
- Added loading states for refresh buttons

### Notification System

- Implemented filtering to prevent duplicate notifications
- Added throttling for similar notifications
- Improved notification display with better styling
- Added option to suppress notifications for background operations

## Development Guidelines

### API Calls

When making API calls, follow these patterns:

1. For background operations that shouldn't show notifications:
```typescript
// Set showNotification to false
const result = await api.getSites({
  showNotification: false
});
```

2. For direct API calls that bypass the cache:
```typescript
// Make a direct axios call
const response = await axios.get('/api/sites/');
```

### Date Formatting

Use the `formatDate` function to display dates consistently:

```typescript
const formatDate = (dateString: string) => {
  try {
    // Check if dateString is null, undefined, or empty
    if (!dateString) {
      return 'No date';
    }
    
    // Check for epoch dates (1970-01-01 or close to it)
    const date = new Date(dateString);
    if (date.getFullYear() < 1980) {
      return 'Recent';
    }
    
    // Check if the date is valid
    if (isNaN(date.getTime())) {
      return 'No date';
    }
    
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  } catch (error) {
    return 'No date';
  }
};
```

### Component Structure

Follow these patterns for new components:

1. Use TypeScript interfaces for props
2. Implement responsive design with Tailwind CSS
3. Use shadcn/ui components where appropriate
4. Add proper loading states and error handling

## Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Commit your changes: `git commit -m 'Add my feature'`
3. Push to the branch: `git push origin feature/my-feature`
4. Submit a pull request 