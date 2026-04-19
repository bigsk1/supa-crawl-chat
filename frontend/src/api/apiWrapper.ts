import { apiService, ChatMessage, Profile, UserPreference } from './apiService';
import { trackApiCall } from '@/utils/notifications';

// API base URL
const API_BASE_URL = '/api';
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

const jsonHeaders = () => ({
  'Content-Type': 'application/json',
  ...(API_KEY ? { 'x-api-key': API_KEY } : {}),
});

// Create a wrapper around the API service that integrates our notification system
export const api = {
  // Site methods
  getSites: () => trackApiCall(
    apiService.getSites(),
    {
      pendingTitle: 'Loading Sites',
      pendingMessage: 'Fetching available sites...',
      successTitle: 'Sites Loaded',
      successMessage: 'Successfully loaded sites',
      errorTitle: 'Failed to Load Sites',
      showToast: false, // Don't show toast for background operations
      showNotification: false // Don't show notification for this operation at all
    }
  ),

  getSite: (siteId: number) => trackApiCall(
    apiService.getSite(siteId),
    {
      pendingTitle: 'Loading Site',
      pendingMessage: `Fetching site details for ID ${siteId}...`,
      successTitle: 'Site Loaded',
      successMessage: 'Successfully loaded site details',
      errorTitle: 'Failed to Load Site',
      showToast: false
    }
  ),

  getSitePages: (siteId: number, includeChunks: boolean = false) => trackApiCall(
    apiService.getSitePages(siteId, includeChunks),
    {
      pendingTitle: 'Loading Pages',
      pendingMessage: `Fetching pages for site ID ${siteId}...`,
      successTitle: 'Pages Loaded',
      successMessage: 'Successfully loaded site pages',
      errorTitle: 'Failed to Load Pages',
      showToast: false
    }
  ),

  getPageById: (pageId: number) => trackApiCall(
    apiService.getPageById(pageId),
    {
      pendingTitle: 'Loading Page',
      pendingMessage: `Fetching page details for ID ${pageId}...`,
      successTitle: 'Page Loaded',
      successMessage: 'Successfully loaded page details',
      errorTitle: 'Failed to Load Page',
      showToast: false
    }
  ),

  getPageChunks: (pageId: number) => trackApiCall(
    apiService.getPageChunks(pageId),
    {
      pendingTitle: 'Loading Chunks',
      pendingMessage: `Fetching chunks for page ID ${pageId}...`,
      successTitle: 'Chunks Loaded',
      successMessage: 'Successfully loaded page chunks',
      errorTitle: 'Failed to Load Chunks',
      showToast: false
    }
  ),

  // Crawl methods
  startCrawl: (crawlRequest: any) => trackApiCall(
    apiService.startCrawl(crawlRequest),
    {
      pendingTitle: 'Starting Crawl',
      pendingMessage: `Starting crawl for ${crawlRequest.url}...`,
      successTitle: 'Crawl Started',
      successMessage: `Successfully started crawling ${crawlRequest.url}`,
      errorTitle: 'Failed to Start Crawl',
      showToast: false
    }
  ),

  getCrawlStatus: (siteId?: string | number) => trackApiCall(
    apiService.getCrawlStatus(siteId),
    {
      pendingTitle: 'Checking Crawl Status',
      pendingMessage: siteId ? `Checking status for site ID ${siteId}...` : 'Checking status of all crawls...',
      successTitle: 'Crawl Status',
      successMessage: 'Successfully retrieved crawl status',
      errorTitle: 'Failed to Get Crawl Status',
      showToast: false
    }
  ),

  // Search methods
  search: (query: string, siteId?: number, threshold: number = 0.3, limit: number = 10, textOnly: boolean = false) => trackApiCall(
    apiService.search(query, siteId, threshold, limit, textOnly),
    {
      pendingTitle: 'Searching',
      pendingMessage: `Searching for "${query}"...`,
      successTitle: 'Search Complete',
      successMessage: 'Search completed successfully',
      errorTitle: 'Search Failed',
      showToast: true
    }
  ),

  // Chat methods
  sendMessage: async (
    message: string,
    profile?: string,
    user_id?: string,
    session_id?: string
  ): Promise<any> => {
    // Check if this is a simple greeting
    const greeting_patterns = [
      "hi", "hello", "hey", "greetings", "howdy", "hola",
      "how are you", "how's it going", "what's up", "sup",
      "good morning", "good afternoon", "good evening"
    ];

    const clean_message = message.trim().toLowerCase();
    const is_greeting = greeting_patterns.some(greeting => clean_message.includes(greeting));

    // Try both versions of the URL (with and without trailing slash)
    const urls = [
      `${API_BASE_URL}/chat`,
      `${API_BASE_URL}/chat/`
    ];

    // Prepare the payload
    const payload = {
      message,
      profile,
      user_id,
      session_id
    };

    // Set query parameters - for greetings, we don't need context
    const queryParams = new URLSearchParams({
      include_context: is_greeting ? 'false' : 'true',
      result_limit: '10',  // Increase result limit for better coverage
      similarity_threshold: '0.6'  // Lower threshold to catch more potential matches
    });

    // Try each URL until we get a successful response
    let lastError = null;
    for (const url of urls) {
      try {
        const response = await fetch(`${url}?${queryParams}`, {
          method: 'POST',
          headers: jsonHeaders(),
          body: JSON.stringify(payload),
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Format the context for better display - only if not a greeting
        if (!is_greeting && data.context && Array.isArray(data.context) && data.context.length > 0) {
          // Create a formatted context string
          let contextString = "===== INFORMATION FROM YOUR CRAWLED SITES =====\n\n";

          // Sort results by similarity if available
          if (data.context[0].similarity) {
            data.context.sort((a: any, b: any) =>
              (b.similarity || 0) - (a.similarity || 0)
            );
          }

          // Deduplicate results by URL
          const seenUrls = new Set<string>();
          const uniqueResults = data.context.filter((result: any) => {
            const url = result.url || "";
            // Remove chunk identifiers for deduplication
            const baseUrl = url.split('#')[0];
            if (seenUrls.has(baseUrl)) return false;
            seenUrls.add(baseUrl);
            return true;
          });

          uniqueResults.forEach((result: any) => {
            const title = result.title || "Untitled";
            const url = result.url || "";
            const siteName = result.site_name || "Unknown site";
            const content = result.content || "";
            const summary = result.summary || "";

            contextString += `SOURCE: ${siteName}\n`;
            contextString += `TITLE: ${title}\n`;
            contextString += `URL: ${url}\n`;

            if (summary) {
              contextString += `SUMMARY: ${summary}\n\n`;
            } else if (content) {
              // Create a brief summary from the content
              const briefContent = content.length > 500 ? content.substring(0, 500) + "..." : content;
              contextString += `CONTENT: ${briefContent}\n\n`;
            } else {
              contextString += "\n";
            }
          });

          // Add the formatted context as a system message
          if (data.conversation_history) {
            data.conversation_history.push({
              role: "system",
              content: contextString,
              created_at: new Date().toISOString()
            });
          }
        }

        return data;
      } catch (error) {
        lastError = error;
        console.error(`Error with URL ${url}:`, error);
      }
    }

    // If we've tried all URLs and none worked, throw the last error
    throw lastError;
  },

  getProfiles: async (sessionId?: string): Promise<Profile[]> => {
    try {
      // Try both versions of the URL (with and without trailing slash)
      // This ensures it works in both Docker and CLI environments
      const urls = [
        `/api/chat/profiles${sessionId ? `?session_id=${sessionId}` : ''}`,
        `/api/chat/profiles/${sessionId ? `?session_id=${sessionId}` : ''}`
      ];

      let data = null;
      let error = null;

      // Try each URL until one works
      for (const url of urls) {
        try {
          console.log('Attempting to fetch profiles from:', url);
          const response = await fetch(url, {
            method: 'GET',
            headers: jsonHeaders()
          });

          if (response.ok) {
            data = await response.json();
            console.log('Profiles response from', url, ':', data);
            break; // Exit the loop if successful
          } else {
            console.log(`URL ${url} returned status ${response.status}`);
          }
        } catch (e) {
          error = e;
          console.log(`Error fetching from ${url}:`, e);
        }
      }

      // If we didn't get data from any URL, return empty array
      if (!data) {
        console.error('Failed to fetch profiles from any URL', error);
        return [];
      }

      // Handle both array response and ProfilesResponse object
      if (Array.isArray(data)) {
        return data;
      } else if (data && Array.isArray(data.profiles)) {
        return data.profiles;
      } else {
        console.error('Unexpected profiles response format:', data);
        return [];
      }
    } catch (error) {
      console.error('Error getting profiles:', error);
      // Return empty array instead of throwing to prevent UI errors
      return [];
    }
  },

  setProfile: async (profileId: string, sessionId?: string, userName?: string): Promise<void> => {
    try {
      // Build query parameters
      const params = new URLSearchParams();
      if (sessionId) params.append('session_id', sessionId);
      if (userName) params.append('user_id', userName);

      // Try both versions of the URL (with and without trailing slash)
      // This ensures it works in both Docker and CLI environments
      const urls = [
        `/api/chat/profiles/${profileId}${params.toString() ? `?${params.toString()}` : ''}`,
        `/api/chat/profiles/${profileId}/${params.toString() ? `?${params.toString()}` : ''}`
      ];

      let success = false;

      // Try each URL until one works
      for (const url of urls) {
        try {
          console.log('Attempting to set profile with:', url);
          const response = await fetch(url, {
            method: 'POST',
            headers: jsonHeaders()
          });

          if (response.ok) {
            console.log(`Successfully set profile using ${url}`);
            success = true;
            break; // Exit the loop if successful
          } else {
            console.log(`URL ${url} returned status ${response.status}`);
          }
        } catch (e) {
          console.log(`Error setting profile with ${url}:`, e);
        }
      }

      if (!success) {
        console.error('Failed to set profile with any URL');
      }
    } catch (error) {
      console.error('Error setting profile:', error);
      // Don't throw to prevent UI errors
    }
  },

  getChatHistory: async (sessionId: string): Promise<ChatMessage[]> => {
    try {
      // Try both versions of the URL (with and without trailing slash)
      // This ensures it works in both Docker and CLI environments
      const urls = [
        `/api/chat/history?session_id=${sessionId}`,
        `/api/chat/history/?session_id=${sessionId}`
      ];

      let data = null;
      let error = null;

      // Try each URL until one works
      for (const url of urls) {
        try {
          console.log('Attempting to fetch chat history from:', url);
          const response = await fetch(url, {
            method: 'GET',
            headers: jsonHeaders()
          });

          if (response.ok) {
            data = await response.json();
            console.log('Chat history response from', url, ':', data);
            break; // Exit the loop if successful
          } else {
            console.log(`URL ${url} returned status ${response.status}`);
          }
        } catch (e) {
          error = e;
          console.log(`Error fetching from ${url}:`, e);
        }
      }

      // If we didn't get data from any URL, return empty array
      if (!data) {
        console.error('Failed to fetch chat history from any URL', error);
        return [];
      }

      // Process the data
      let messages: ChatMessage[] = [];

      if (Array.isArray(data)) {
        messages = data;
      } else if (data && data.messages && Array.isArray(data.messages)) {
        messages = data.messages;
      } else if (data && typeof data === 'object') {
        const possibleMessages = Object.values(data).find(val => Array.isArray(val));
        if (possibleMessages && Array.isArray(possibleMessages)) {
          messages = possibleMessages as ChatMessage[];
        }
      }

      // Don't filter out system messages - we need them for context
      return messages;
    } catch (error) {
      console.error('Error getting chat history:', error);
      // Return empty array instead of throwing to prevent UI errors
      return [];
    }
  },

  clearChatHistory: async (sessionId: string): Promise<void> => {
    try {
      // Try both versions of the URL (with and without trailing slash)
      // This ensures it works in both Docker and CLI environments
      const urls = [
        `/api/chat/history?session_id=${sessionId}`,
        `/api/chat/history/?session_id=${sessionId}`
      ];

      let success = false;

      // Try each URL until one works
      for (const url of urls) {
        try {
          console.log('Attempting to clear chat history with:', url);
          const response = await fetch(url, {
            method: 'DELETE',
            headers: jsonHeaders()
          });

          if (response.ok) {
            console.log(`Successfully cleared chat history using ${url}`);
            success = true;
            break; // Exit the loop if successful
          } else {
            console.log(`URL ${url} returned status ${response.status}`);
          }
        } catch (e) {
          console.log(`Error clearing chat history with ${url}:`, e);
        }
      }

      if (!success) {
        console.error('Failed to clear chat history with any URL');
      }
    } catch (error) {
      console.error('Error clearing chat history:', error);
      // Don't throw to prevent UI errors
    }
  }
};
