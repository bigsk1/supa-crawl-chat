import axios from 'axios';
import { clearWebUiToken, getWebUiToken } from '@/lib/authStorage';

// Base URL for API requests - ensure trailing slash
const API_BASE_URL = '/api';
const API_KEY = import.meta.env.VITE_API_KEY as string | undefined;

if (API_KEY) {
  axios.defaults.headers.common['x-api-key'] = API_KEY;
}

// Simple cache for GET requests
interface CacheEntry {
  data: any;
  timestamp: number;
  expiry: number; // Time in milliseconds when this entry expires
}

const apiCache: Record<string, CacheEntry> = {};

/** Drop cached GET responses whose URL path matches (fixes stale list after site delete / crawl). */
export function invalidateApiCacheUrlPrefix(prefix: string): void {
  for (const key of Object.keys(apiCache)) {
    if (key.includes(prefix)) {
      delete apiCache[key];
    }
  }
}

function invalidateSitesRelatedCache(): void {
  invalidateApiCacheUrlPrefix('/sites');
}

/** After page delete/recrawl, drop cached site detail and page GETs. */
function invalidateSiteAndPagesCache(siteId?: number): void {
  invalidateSitesRelatedCache();
  invalidateApiCacheUrlPrefix('/pages');
  if (siteId != null && !Number.isNaN(siteId)) {
    invalidateApiCacheUrlPrefix(`/sites/${siteId}`);
  }
}

// Cache expiry times (in milliseconds)
const CACHE_EXPIRY = {
  default: 60 * 1000, // 1 minute
  sites: 5 * 60 * 1000, // 5 minutes
  profiles: 10 * 60 * 1000, // 10 minutes
};

// Create an axios instance with the base URL
const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    ...(API_KEY ? { 'x-api-key': API_KEY } : {}),
  },
});

// Minimal logging — avoid spam on frequently polled paths (e.g. crawl job status).
function shouldLogApiRequest(url: string | undefined, method: string | undefined): boolean {
  if (!url) return false;
  if (method && method.toLowerCase() !== 'get') return true;
  if (url.includes('/crawl/status') || url.includes('/crawl/activity')) return false;
  if (url.includes('/chat/')) return true;
  if (url.includes('/crawl')) return true;
  return false;
}

// Add request interceptor with caching for GET requests
apiClient.interceptors.request.use(async (request) => {
  const web = getWebUiToken();
  if (web) {
    request.headers.set('Authorization', `Bearer ${web}`);
  }

  if (shouldLogApiRequest(request.url, request.method)) {
    console.log(`API Request: ${request.method?.toUpperCase()} ${request.url}`);
  }

  // Never cache live crawl dashboards — polling must see fresh job state
  const skipCache =
    request.method === 'get' &&
    request.url &&
    (request.url.includes('/crawl/status') || request.url.includes('/crawl/activity'));

  // Check cache for GET requests
  if (request.method === 'get' && request.url && !skipCache) {
    const cacheKey = `${request.url}${JSON.stringify(request.params || {})}`;
    const cachedResponse = apiCache[cacheKey];

    if (cachedResponse && Date.now() < cachedResponse.expiry) {
      // Return cached response
      console.log(`Using cached response for ${request.url}`);

      // Create a new Promise that resolves with the cached data
      return Promise.resolve({
        ...request,
        adapter: () => {
          return Promise.resolve({
            data: cachedResponse.data,
            status: 200,
            statusText: 'OK',
            headers: {},
            config: request,
            request: request
          });
        }
      });
    }
  }

  return request;
});

// Add response interceptor with caching
apiClient.interceptors.response.use(
  response => {
    if (shouldLogApiRequest(response.config.url, response.config.method)) {
      console.log(`API Response: ${response.status} ${response.config.url}`);
    }

    // Cache successful GET responses (skip volatile crawl status)
    if (
      response.config.method === 'get' &&
      response.config.url &&
      !response.config.url.includes('/crawl/status') &&
      !response.config.url.includes('/crawl/activity')
    ) {
      const url = response.config.url;
      const cacheKey = `${url}${JSON.stringify(response.config.params || {})}`;

      // Determine cache expiry based on endpoint
      let expiryTime = CACHE_EXPIRY.default;
      if (url.includes('/sites/')) {
        expiryTime = CACHE_EXPIRY.sites;
      } else if (url.includes('/profiles/')) {
        expiryTime = CACHE_EXPIRY.profiles;
      }

      // Store in cache
      apiCache[cacheKey] = {
        data: response.data,
        timestamp: Date.now(),
        expiry: Date.now() + expiryTime
      };
    }

    // Mutations: list views must not stay stale (GET /sites was cached up to 5 min).
    const method = response.config.method?.toLowerCase();
    const url = response.config.url || '';
    if (method === 'delete' && url.includes('/sites')) {
      invalidateSitesRelatedCache();
    }
    if (method === 'delete' && url.includes('/pages/')) {
      invalidateSiteAndPagesCache();
    }
    if (method === 'post' && (url.startsWith('/crawl') || url.includes('/crawl'))) {
      invalidateSitesRelatedCache();
    }

    return response;
  },
  error => {
    const status = error.response?.status;
    if (status === 401 && getWebUiToken()) {
      clearWebUiToken();
      if (typeof window !== 'undefined' && window.location.pathname !== '/login') {
        window.location.assign('/login');
      }
    }
    console.error('API Error:',
      error.response?.status || 'Network Error',
      error.config?.url || 'Unknown URL',
      error.response?.data || error.message
    );
    return Promise.reject(error);
  }
);

// Site interfaces
export interface Site {
  id: number;
  name: string;
  url: string;
  description: string;
  page_count: number;
  created_at: string;
  updated_at?: string | null;
  /** Latest finished crawl job time, or started_at while queued/running */
  last_crawled_at?: string | null;
  /** Latest crawl_jobs.status for this site, if any */
  crawl_job_status?: string | null;
}

// Page interfaces
export interface Page {
  id: number;
  site_id: number;
  url: string;
  title?: string;
  content?: string;
  content_length?: number;
  content_truncated?: boolean;
  summary?: string;
  metadata?: any;
  is_chunk?: boolean;
  chunk_index?: number | null;
  parent_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_parent?: boolean;
  parent_title?: string;
}

// Search interfaces
export interface SearchResult {
  id: number;
  url: string;
  title: string;
  content?: string;
  content_length?: number;
  content_truncated?: boolean;
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
  metadata?: any;
}

export interface SearchResponse {
  results: SearchResult[];
  count: number;
  query: string;
  threshold: number;
  use_embedding: boolean;
}

// Crawl interfaces
export interface CrawlRequest {
  url: string;
  site_name?: string;
  site_description?: string;
  is_sitemap?: boolean;
  max_urls?: number;
}

export interface CrawlResponse {
  site_id: number;
  site_name: string;
  url: string;
  message: string;
  status: string;
  job_id?: number;
  next_steps: {
    check_status: string;
    view_pages: string;
    search_content: string;
  };
}

export interface CrawlStatus {
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
  follow_external_links?: boolean;
  error?: string;
  next_steps: {
    view_pages: string;
    search_content: string;
  };
}

// Chat interfaces
export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  created_at?: string;
  context?: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string;
  user_id?: string;
  profile?: string;
}

export interface ChatResponse {
  response: string;
  session_id: string;
  user_id: string | null;
  context?: SearchResult[];
  conversation_history?: ChatMessage[];
}

export interface Profile {
  name: string;
  description: string;
}

export interface ProfilesResponse {
  profiles: Profile[];
  active_profile: string;
}

export interface UserPreference {
  id?: number;
  user_id: string;
  preference_type: string;
  preference_value: string;
  context?: string;
  confidence: number;
  created_at?: string;
  updated_at?: string;
  last_used?: string;
  source_session?: string;
  is_active: boolean;
  metadata?: any;
}

export interface UserPreferenceResponse {
  preferences: UserPreference[];
  count: number;
  user_id: string;
}

// API service
export const apiService = {
  // Site methods
  getSites: async (): Promise<Site[]> => {
    try {
      const response = await apiClient.get('/sites');
      console.log('Raw sites response:', response.data);

      // Handle different response formats
      if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && response.data.sites && Array.isArray(response.data.sites)) {
        // This is the expected format from the API: { sites: [...], count: number }
        console.log('Found sites array in response:', response.data.sites);
        return response.data.sites;
      } else if (response.data && typeof response.data === 'object') {
        // Try to extract sites from the response object
        const possibleSites = Object.values(response.data).find(val => Array.isArray(val));
        if (possibleSites && Array.isArray(possibleSites)) {
          console.log('Found possible sites array in response:', possibleSites);
          return possibleSites as Site[];
        }
      }

      // If we can't determine the format, return an empty array
      console.error('Unexpected sites response format:', response.data);
      return [];
    } catch (error) {
      console.error('Error fetching sites:', error);
      throw error;
    }
  },

  getSite: async (siteId: number): Promise<Site> => {
    try {
      const response = await apiClient.get(`/sites/${siteId}`);
      return response.data;
    } catch (error) {
      console.error(`Error getting site ${siteId}:`, error);
      throw error;
    }
  },

  deleteSite: async (siteId: number): Promise<void> => {
    await apiClient.delete(`/sites/${siteId}`);
    invalidateSitesRelatedCache();
  },

  deletePage: async (pageId: number, siteId?: number): Promise<void> => {
    await apiClient.delete(`/pages/${pageId}`);
    invalidateSiteAndPagesCache(siteId);
  },

  getSitePages: async (siteId: number, includeChunks: boolean = false): Promise<Page[] | { pages: Page[] }> => {
    try {
      const response = await apiClient.get(`/sites/${siteId}/pages`, {
        params: { include_chunks: includeChunks }
      });

      console.log('Raw site pages response:', response.data);

      // Return the data as is, let the component handle the format
      return response.data;
    } catch (error) {
      console.error(`Error getting pages for site ${siteId}:`, error);
      throw error;
    }
  },

  getPageById: async (pageId: number): Promise<Page> => {
    try {
      const response = await apiClient.get(`/pages/${pageId}`, {
        params: { full: true }
      });
      console.log('Page by ID response:', response.data);
      return response.data;
    } catch (error) {
      console.error(`Error getting page ${pageId}:`, error);
      throw error;
    }
  },

  getPageChunks: async (pageId: number): Promise<Page[]> => {
    try {
      const response = await apiClient.get(`/pages/${pageId}/chunks`);
      console.log('Page chunks response:', response.data);

      // Handle different response formats
      if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && response.data.chunks && Array.isArray(response.data.chunks)) {
        return response.data.chunks;
      } else {
        console.error('Unexpected page chunks response format:', response.data);
        return [];
      }
    } catch (error) {
      console.error(`Error getting chunks for page ${pageId}:`, error);
      throw error;
    }
  },

  // Crawl methods
  startCrawl: async (crawlRequest: any): Promise<CrawlStatus> => {
    try {
      const response = await apiClient.post('/crawl/', crawlRequest);

      // Check if the response contains a site_id
      if (response.data && response.data.site_id) {
        // Return the crawl status
        return response.data;
      } else {
        throw new Error('Invalid response from crawl API');
      }
    } catch (error) {
      console.error('Error starting crawl:', error);
      throw error;
    }
  },

  /** Queue a refresh crawl for an existing site (POST /api/crawl/refresh/{site_id}). */
  refreshSiteCrawl: async (siteId: number): Promise<CrawlResponse> => {
    const response = await apiClient.post<CrawlResponse>(`/crawl/refresh/${siteId}`, {});
    return response.data;
  },

  /** Re-fetch one page URL only (POST /api/crawl/refresh/{site_id}/pages/{page_id}). */
  refreshPageCrawl: async (siteId: number, pageId: number): Promise<CrawlResponse> => {
    const response = await apiClient.post<CrawlResponse>(
      `/crawl/refresh/${siteId}/pages/${pageId}`,
      {}
    );
    invalidateSiteAndPagesCache(siteId);
    return response.data;
  },

  getCrawlStatus: async (siteId?: string | number): Promise<CrawlStatus | CrawlStatus[]> => {
    try {
      // If no siteId is provided, try to get all sites instead
      if (!siteId) {
        console.log('No siteId provided, fetching all sites instead');
        return apiService.getSites() as unknown as CrawlStatus[];
      }

      // Use the correct endpoint format with siteId
      const endpoint = `/crawl/status/${siteId}/`;

      console.log('Fetching crawl status from:', endpoint);
      const response = await apiClient.get(endpoint);
      console.log('Crawl status response:', response.data);

      return response.data;
    } catch (error) {
      console.error('Error fetching crawl status:', error);
      throw error;
    }
  },

  // Search methods
  search: async (
    query: string,
    siteId?: number,
    threshold: number = 0.3,
    limit: number = 10,
    textOnly: boolean = false
  ): Promise<SearchResult[]> => {
    try {
      const response = await apiClient.get('/search/', {
        params: {
          query,
          site_id: siteId,
          threshold,
          limit,
          text_only: textOnly
        }
      });

      // Handle both array response and SearchResponse object
      if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && Array.isArray(response.data.results)) {
        return response.data.results;
      } else {
        console.error('Unexpected search response format:', response.data);
        return [];
      }
    } catch (error) {
      console.error('Error searching:', error);
      throw error;
    }
  },

  // Chat methods
  sendMessage: async (message: string, profile: string, sessionId?: string, userName?: string): Promise<ChatMessage> => {
    try {
      const payload: any = {
        message,
        profile
      };

      // Use the user's name as the user_id if provided, otherwise use the profile name
      if (userName) {
        payload.user_id = userName;
      }

      // Add session_id if provided
      if (sessionId) {
        payload.session_id = sessionId;
      }

      // Add query parameters to always include context and search settings
      const params = {
        include_context: true,  // Always include search context
        result_limit: 10,       // Reasonable default
        similarity_threshold: 0.5 // Reasonable default
      };

      const response = await apiClient.post('/chat/', payload, { params });

      console.log('Chat response:', response.data);

      // Handle different response formats
      if (response.data && typeof response.data === 'object') {
        if (response.data.response) {
          // Standard format: { response: string, session_id: string, ... }
          const assistantMessage: ChatMessage = {
            id: Date.now().toString(),
            role: 'assistant',
            content: response.data.response,
            created_at: new Date().toISOString()
          };

          // If context was included, add it to the message
          if (response.data.context) {
            assistantMessage.context = response.data.context;
          }

          return assistantMessage;
        } else if (response.data.content) {
          // Message format: { role: string, content: string, ... }
          const message: ChatMessage = {
            id: Date.now().toString(),
            role: response.data.role || 'assistant',
            content: response.data.content,
            created_at: new Date().toISOString()
          };

          // If context was included, add it to the message
          if (response.data.context) {
            message.context = response.data.context;
          }

          return message;
        }
      }

      // Fallback for unexpected formats
      console.error('Unexpected chat response format:', response.data);
      return {
        id: Date.now().toString(),
        role: 'assistant',
        content: typeof response.data === 'string'
          ? response.data
          : 'Received an unexpected response format. Please try again.',
        created_at: new Date().toISOString()
      };
    } catch (error) {
      console.error('Error sending message:', error);
      throw error;
    }
  },

  getProfiles: async (sessionId?: string): Promise<Profile[]> => {
    try {
      const params: any = {};

      // Add session_id if provided
      if (sessionId) {
        params.session_id = sessionId;
      }

      // Use URL without trailing slash
      const response = await apiClient.get('/chat/profiles', { params });

      // Handle both array response and ProfilesResponse object
      if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && Array.isArray(response.data.profiles)) {
        return response.data.profiles;
      } else {
        console.error('Unexpected profiles response format:', response.data);
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
      const params: any = {};

      // Use the user's name as the user_id if provided
      if (userName) {
        params.user_id = userName;
      }

      // Add session_id if provided
      if (sessionId) {
        params.session_id = sessionId;
      }

      // Use URL without trailing slash
      await apiClient.post(`/chat/profiles/${profileId}`, null, { params });

      // Clear any cached chat history to ensure fresh data with the new profile
      if (sessionId) {
        const cacheKey = `/chat/history/${JSON.stringify({ session_id: sessionId })}`;
        if (apiCache[cacheKey]) {
          delete apiCache[cacheKey];
          console.log('Cleared chat history cache after profile change');
        }
      }
    } catch (error) {
      console.error('Error setting profile:', error);
      // Don't throw to prevent UI errors
    }
  },

  getChatHistory: async (sessionId: string): Promise<ChatMessage[]> => {
    try {
      // Use the correct endpoint format with query parameters
      const response = await apiClient.get('/chat/history', {
        params: { session_id: sessionId }
      });

      let messages: ChatMessage[] = [];

      // Handle different response formats
      if (Array.isArray(response.data)) {
        // Format: ChatMessage[]
        messages = response.data;
      } else if (response.data && response.data.messages && Array.isArray(response.data.messages)) {
        // Format: { messages: ChatMessage[], count: number, ... }
        messages = response.data.messages;
      } else if (response.data && typeof response.data === 'object') {
        // Try to extract messages from the response object
        const possibleMessages = Object.values(response.data).find(val => Array.isArray(val));
        if (possibleMessages && Array.isArray(possibleMessages)) {
          messages = possibleMessages as ChatMessage[];
        }
      }

      // Don't filter out system messages that contain search context
      return messages;
    } catch (error) {
      console.error('Error getting chat history:', error);
      // Return empty array instead of throwing to prevent UI errors
      return [];
    }
  },

  clearChatHistory: async (sessionId: string): Promise<void> => {
    try {
      await apiClient.delete('/chat/history', {
        params: { session_id: sessionId }
      });

      // Clear the cache for this session's chat history
      // This prevents old messages from reappearing after clearing
      const cacheKey = `/chat/history/${JSON.stringify({ session_id: sessionId })}`;
      if (apiCache[cacheKey]) {
        delete apiCache[cacheKey];
        console.log('Cleared chat history cache for session:', sessionId);
      }
    } catch (error) {
      console.error('Error clearing chat history:', error);
      throw error;
    }
  },

  // User Preferences methods
  getUserPreferences: async (userId: string, minConfidence: number = 0.7, activeOnly: boolean = true): Promise<UserPreference[]> => {
    try {
      const response = await apiClient.get('/chat/preferences', {
        params: {
          user_id: userId,
          min_confidence: minConfidence,
          active_only: activeOnly
        }
      });

      // Handle different response formats
      if (Array.isArray(response.data)) {
        return response.data;
      } else if (response.data && Array.isArray(response.data.preferences)) {
        return response.data.preferences;
      } else {
        console.error('Unexpected preferences response format:', response.data);
        return [];
      }
    } catch (error) {
      console.error('Error getting user preferences:', error);
      return [];
    }
  },

  addUserPreference: async (
    userId: string,
    preferenceType: string,
    preferenceValue: string,
    context?: string,
    confidence: number = 0.9,
    sessionId?: string
  ): Promise<UserPreference | null> => {
    try {
      const response = await apiClient.post('/chat/preferences', {
        preference_type: preferenceType,
        preference_value: preferenceValue,
        context: context || 'Manually added via UI',
        confidence: confidence,
        source_session: sessionId
      }, {
        params: { user_id: userId }
      });

      return response.data;
    } catch (error) {
      console.error('Error adding user preference:', error);
      return null;
    }
  },

  deleteUserPreference: async (userId: string, preferenceId: number): Promise<boolean> => {
    try {
      await apiClient.delete(`/chat/preferences/${preferenceId}`, {
        params: { user_id: userId }
      });
      return true;
    } catch (error) {
      console.error(`Error deleting preference ${preferenceId}:`, error);
      return false;
    }
  },

  deactivateUserPreference: async (userId: string, preferenceId: number): Promise<boolean> => {
    try {
      await apiClient.put(`/chat/preferences/${preferenceId}/deactivate`, null, {
        params: { user_id: userId }
      });
      return true;
    } catch (error) {
      console.error(`Error deactivating preference ${preferenceId}:`, error);
      return false;
    }
  },

  activateUserPreference: async (userId: string, preferenceId: number): Promise<boolean> => {
    try {
      await apiClient.put(`/chat/preferences/${preferenceId}/activate`, null, {
        params: { user_id: userId }
      });
      return true;
    } catch (error) {
      console.error(`Error activating preference ${preferenceId}:`, error);
      return false;
    }
  },

  clearUserPreferences: async (userId: string): Promise<boolean> => {
    try {
      await apiClient.delete('/chat/preferences', {
        params: { user_id: userId }
      });
      return true;
    } catch (error) {
      console.error(`Error clearing preferences for user ${userId}:`, error);
      return false;
    }
  }
};
