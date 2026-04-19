import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiService, Site, Page } from '@/api/apiService';
import { api } from '@/api/apiWrapper';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import PageListItem from '@/components/PageListItem';
import { createNotification } from '@/utils/notifications';
import { sanitizeHtml } from '@/lib/sanitize';
import { PageHeader } from '@/components/PageHeader';

// Add this type definition at the top of the file, after imports
type FilteredPage = {
  id: number;
  site_id: number;
  url: string;
  title?: string;
  content?: string;
  summary?: string;
  metadata?: any;
  is_chunk?: boolean;
  chunk_index?: number | null;
  parent_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
  is_parent?: boolean;
  parent_title?: string;
};

const SiteDetailPage = () => {
  const { siteId } = useParams<{ siteId: string }>();

  const [site, setSite] = useState<Site | null>(null);
  const [pages, setPages] = useState<Page[]>([]);
  const [filteredPages, setFilteredPages] = useState<any[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<any | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [pageSize, setPageSize] = useState(10); // Number of items per page
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedPage, setSelectedPage] = useState<Page | null>(null);
  const [contentViewMode, setContentViewMode] = useState<'raw' | 'rendered'>('raw');
  const [contentSource, setContentSource] = useState<'database' | 'live' | 'unknown'>('unknown');
  const [isLoadingContent, setIsLoadingContent] = useState(false);
  const [databaseContent, setDatabaseContent] = useState<string | null>(null);
  const [liveContent, setLiveContent] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'database' | 'live'>('database');
  const [relatedChunks, setRelatedChunks] = useState<Page[]>([]);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [sortOption, setSortOption] = useState<'title' | 'created' | 'updated'>('title');
  const [expandedPageIds, setExpandedPageIds] = useState<number[]>([]);
  const [isSorting, setIsSorting] = useState(false);
  const [showDebug, setShowDebug] = useState(false);

  useEffect(() => {
    if (!siteId) return;
    const id = parseInt(siteId, 10);
    if (Number.isNaN(id)) return;
    // Silent by default: visiting /sites/:id should not spam success toasts (incl. Strict Mode double-invoke)
    void loadSiteDetails(id, { notifySuccess: false });
  }, [siteId]);

  useEffect(() => {
    console.log("Sort option changed to:", sortOption);
    if (pages.length > 0) {
      // Call applyFilters directly when sortOption changes
      applyFilters();
    }
  }, [sortOption]);

  useEffect(() => {
    if (pages.length > 0) {
      applyFilters();
    }
  }, [pages, searchTerm, currentPage, pageSize, sortOption]);

  // When a page is selected, find related chunks and fetch content
  useEffect(() => {
    if (selectedPage) {
      // Find related chunks (other chunks of the same parent page)
      if (selectedPage.is_chunk && selectedPage.parent_id) {
        // If this is a chunk, find other chunks with the same parent_id
        const chunks = pages.filter(p =>
          p.parent_id === selectedPage.parent_id && p.id !== selectedPage.id
        );
        setRelatedChunks(chunks);
      } else if (!selectedPage.is_chunk) {
        // If this is a parent page, find all its chunks
        const chunks = pages.filter(p =>
          p.parent_id === selectedPage.id
        );
        setRelatedChunks(chunks);
      } else {
        setRelatedChunks([]);
      }

      // Fetch content if needed and not already loading
      if (selectedPage.id && !isLoadingContent && !selectedPage.content) {
        console.log("Fetching content for selected page:", selectedPage.id);
        fetchDatabaseContent(selectedPage.id);
      }
    } else {
      setRelatedChunks([]);
    }
  }, [selectedPage, pages, isLoadingContent]);

  type LoadSiteOptions = { notifySuccess?: boolean };

  const applyPagesPayload = (siteData: Site, pagesData: unknown) => {
    let raw = pagesData as any;
    if (raw && typeof raw === 'object' && 'pages' in raw) {
      raw = (raw as { pages: unknown }).pages;
    }
    const pagesArray: any[] = Array.isArray(raw) ? raw : (raw as any)?.pages ?? [];
    const processedPages = pagesArray.map((page: any) => ({
      ...page,
      is_parent: !page.is_chunk,
      created_at: page.created_at || null,
      updated_at: page.updated_at || null,
    }));
    setDebugInfo({ site: siteData, pages: pagesData });
    setPages(processedPages);
    const parentPages = processedPages.filter((p: any) => !p.is_chunk);
    const totalPagesCount = Math.ceil(parentPages.length / pageSize);
    setTotalPages(totalPagesCount > 0 ? totalPagesCount : 1);
    setCurrentPage(1);
    return processedPages;
  };

  const loadSiteDetails = async (siteId: number, options: LoadSiteOptions = {}) => {
    const notifySuccess = options.notifySuccess === true;
    setIsLoading(true);
    setError(null);

    try {
      const siteData = await apiService.getSite(siteId);
      setSite(siteData);

      try {
        let pagesPayload: unknown;

        try {
          const response = await axios.get(`/api/sites/${siteId}/pages/`, {
            params: {
              include_chunks: true,
              include_dates: true,
              include_content: false,
              limit: 1000,
            },
          });
          pagesPayload = response.data;
        } catch (directError) {
          console.error('Error with direct API call:', directError);
          pagesPayload = await apiService.getSitePages(siteId, true);
        }

        applyPagesPayload(siteData, pagesPayload);

        if (notifySuccess) {
          toast.success('Site data updated', {
            id: 'site-detail-refresh-success',
            duration: 2200,
          });
        }
      } catch (pagesError) {
        console.error('Error fetching site pages:', pagesError);
        createNotification('Error', 'Failed to load site pages', 'error', true);
        setPages([]);
      }
    } catch (siteError) {
      console.error('Error fetching site details:', siteError);
      createNotification('Error', 'Failed to load site details', 'error', true);
      setError('Failed to load site details. Please try again later.');
    } finally {
      setIsLoading(false);
    }
  };

  const checkApiDirectly = async () => {
    if (!siteId) return;

    try {
      // First check the site details
      const siteResponse = await axios.get(`/api/sites/${siteId}`);
      console.log('Direct site API response:', siteResponse.data);

      // Then check the pages
      const pagesResponse = await axios.get(`/api/sites/${siteId}/pages/`, {
        params: {
          include_chunks: true,
          include_content: false,
          limit: 1000
        }
      });
      console.log('Direct pages API response:', pagesResponse.data);

      // Check the first few pages for date fields
      const pagesData = pagesResponse.data.pages || pagesResponse.data;
      if (Array.isArray(pagesData) && pagesData.length > 0) {
        console.log('First page date fields:', {
          page_id: pagesData[0].id,
          created_at: pagesData[0].created_at,
          updated_at: pagesData[0].updated_at,
          created_at_type: typeof pagesData[0].created_at,
          updated_at_type: typeof pagesData[0].updated_at
        });

        // Try to parse the dates
        if (pagesData[0].created_at) {
          try {
            const date = new Date(pagesData[0].created_at);
            console.log('Parsed created_at:', date.toISOString());
          } catch (error) {
            console.error('Error parsing created_at:', error);
          }
        }

        if (pagesData[0].updated_at) {
          try {
            const date = new Date(pagesData[0].updated_at);
            console.log('Parsed updated_at:', date.toISOString());
          } catch (error) {
            console.error('Error parsing updated_at:', error);
          }
        }
      }

      createNotification('Success', 'Check console for API response', 'success', true);
    } catch (error) {
      console.error('Error checking API directly:', error);
      createNotification('Error', 'Failed to check API directly', 'error', true);
    }
  };

  const applyFilters = () => {
    console.log("Running applyFilters with sort option:", sortOption);

    // Create a copy of the pages array to work with
    let filtered = [...pages].map((page: any) => ({
      ...page,
      // Ensure these properties exist for sorting
      created_at: page.created_at || null,
      updated_at: page.updated_at || null,
      title: page.title || '',
      is_parent: !page.is_chunk && !page.parent_id
    }));

    // Filter out chunk pages - only show parent pages in the main list
    filtered = filtered.filter(page => !page.is_chunk);

    // Apply search filter
    if (searchTerm.trim()) {
      const searchLower = searchTerm.toLowerCase();
      filtered = filtered.filter(page =>
        (page.title && page.title.toLowerCase().includes(searchLower)) ||
        (page.url && page.url.toLowerCase().includes(searchLower)) ||
        (page.summary && page.summary.toLowerCase().includes(searchLower)) ||
        (page.content && page.content.toLowerCase().includes(searchLower))
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      switch (sortOption) {
        case 'title':
          // Case-insensitive alphabetical sort
          return (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase());

        case 'created':
          // Handle null or undefined dates
          if (!a.created_at && !b.created_at) return 0;
          if (!a.created_at) return 1; // b comes first
          if (!b.created_at) return -1; // a comes first

          // Convert to timestamps and compare (newest first)
          const aCreated = new Date(a.created_at).getTime();
          const bCreated = new Date(b.created_at).getTime();
          return bCreated - aCreated;

        case 'updated':
          // Handle null or undefined dates
          if (!a.updated_at && !b.updated_at) return 0;
          if (!a.updated_at) return 1; // b comes first
          if (!b.updated_at) return -1; // a comes first

          // Convert to timestamps and compare (newest first)
          const aUpdated = new Date(a.updated_at).getTime();
          const bUpdated = new Date(b.updated_at).getTime();
          return bUpdated - aUpdated;

        default:
          return 0;
      }
    });

    // Update filtered pages
    setFilteredPages(filtered);

    // Recalculate total pages based on filtered results
    const newTotalPages = Math.ceil(filtered.length / pageSize);
    setTotalPages(newTotalPages > 0 ? newTotalPages : 1);

    // Adjust current page if needed
    if (currentPage > newTotalPages) {
      setCurrentPage(1);
    }
  };

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return 'Unknown';

    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch (error) {
      return 'Invalid date';
    }
  };

  // Function to fetch database content from the API
  const fetchDatabaseContent = async (pageId: number) => {
    if (!pageId) return null;

    setIsLoadingContent(true);
    try {
      // First try to get content directly from the pages API
      try {
        const pageData = await api.getPageById(pageId);

        if (pageData && pageData.content) {
          setDatabaseContent(pageData.content);
          setContentSource('database');

          // Update the selected page with additional data only if needed
          if (selectedPage && (!selectedPage.content || selectedPage.content.trim() === '')) {
            setSelectedPage({
              ...selectedPage,
              created_at: pageData.created_at || selectedPage.created_at,
              updated_at: pageData.updated_at || selectedPage.updated_at,
              content: pageData.content
            });
          }

          // If this is a parent page, fetch its chunks
          if (!pageData.is_chunk) {
            try {
              const chunks = await api.getPageChunks(pageId);
              if (chunks && chunks.length > 0) {
                setRelatedChunks(chunks);
              }
            } catch (chunkError) {
              console.error('Error fetching chunks:', chunkError);
            }
          }

          return pageData.content;
        }
      } catch (pageError) {
        console.error('Error fetching from pages API:', pageError);
      }

      // If the direct API call didn't work, fall back to the sites API
      if (siteId) {
        try {
          const response = await axios.get(`/api/sites/${siteId}/pages/`, {
            params: { include_chunks: true }
          });

          console.log('Sites API response:', response.data);

          let pagesData = response.data;
          if (pagesData && typeof pagesData === 'object' && 'pages' in pagesData) {
            pagesData = pagesData.pages;
          }

          if (Array.isArray(pagesData)) {
            const pageData = pagesData.find((p: any) => p.id === pageId);
            if (pageData && pageData.content) {
              setDatabaseContent(pageData.content);
              setContentSource('database');

              // Update the selected page with additional data if available and needed
              if (selectedPage && (!selectedPage.content || selectedPage.content.trim() === '')) {
                setSelectedPage({
                  ...selectedPage,
                  created_at: pageData.created_at || selectedPage.created_at,
                  updated_at: pageData.updated_at || selectedPage.updated_at,
                  content: pageData.content
                });
              }

              return pageData.content;
            }
          }
        } catch (sitesError) {
          console.error('Error fetching from sites API:', sitesError);
        }
      }

      // If we still don't have content, try the search API as a last resort
      try {
        const searchResponse = await axios.get('/api/search/', {
          params: {
            query: selectedPage?.url || '',
            text_only: true,
            limit: 1
          }
        });

        console.log('Search API response:', searchResponse.data);

        let searchResults = searchResponse.data;
        if (searchResponse.data && typeof searchResponse.data === 'object' && 'results' in searchResponse.data) {
          searchResults = searchResponse.data.results;
        }

        if (Array.isArray(searchResults) && searchResults.length > 0) {
          const searchResult = searchResults[0];
          if (searchResult.content) {
            setDatabaseContent(searchResult.content);
            setContentSource('database');

            // Update the selected page with additional data if available
            if (selectedPage) {
              setSelectedPage({
                ...selectedPage,
                content: searchResult.content
              });
            }

            return searchResult.content;
          }
        }
      } catch (searchError) {
        console.error('Error fetching from search API:', searchError);
      }

      // If all methods failed, show a message
      setDatabaseContent(null);
      setContentSource('unknown');
      createNotification('Error', 'No content found in database', 'error', true);
      return null;
    } catch (error) {
      console.error('Error fetching database content:', error);
      setDatabaseContent(null);
      setContentSource('unknown');
      return null;
    } finally {
      setIsLoadingContent(false);
    }
  };

  // Function to fetch content directly from the live URL
  const fetchLiveContent = async (url: string) => {
    if (!url) return null;

    setIsLoadingContent(true);
    try {
      const corsProxyUrl = `https://api.allorigins.win/raw?url=${encodeURIComponent(url)}`;
      const response = await axios.get(corsProxyUrl);

      if (response.data) {
        const htmlContent = typeof response.data === 'string'
          ? response.data
          : JSON.stringify(response.data);

        setLiveContent(htmlContent);
        setContentSource('live');
        return htmlContent;
      }

      return null;
    } catch (error) {
      console.error('Error fetching live content:', error);
      return null;
    } finally {
      setIsLoadingContent(false);
    }
  };

  // Function to determine if content is likely HTML
  const isHtmlContent = (content: string): boolean => {
    return /<\/?[a-z][\s\S]*>/i.test(content);
  };

  // Function to determine if content is likely Markdown
  const isMarkdownContent = (content: string): boolean => {
    // Check for common markdown patterns
    const markdownPatterns = [
      /^#+ .*$/m, // Headers
      /\[.*\]\(.*\)/, // Links
      /\*\*.*\*\*/, // Bold
      /\*.*\*/, // Italic
      /```[\s\S]*```/, // Code blocks
      /^\s*[-*+] .*$/m, // Lists
      /^\s*\d+\. .*$/m, // Numbered lists
      /^\s*>\s.*$/m, // Blockquotes
    ];

    return markdownPatterns.some(pattern => pattern.test(content));
  };

  // Function to detect content type
  const detectContentType = (content: string | undefined): 'html' | 'markdown' | 'text' => {
    if (!content) return 'text';
    if (isHtmlContent(content)) return 'html';
    if (isMarkdownContent(content)) return 'markdown';
    return 'text';
  };

  const handlePageChange = (pageNumber: number) => {
    setCurrentPage(pageNumber);
  };

  const handlePageClick = (page: Page) => {
    // Check if we're already viewing this page
    if (selectedPage?.id === page.id) {
      console.log("Already viewing this page, skipping");
      return;
    }

    setSelectedPage(page);
  };

  const handleBackToList = () => {
    setSelectedPage(null);
    setDatabaseContent(null);
    setLiveContent(null);
    setContentSource('unknown');
  };

  const handleViewChunk = (chunk: Page) => {
    setSelectedPage(chunk);
  };

  // Update the handleSortChange function
  const handleSortChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newSortOption = e.target.value as 'title' | 'created' | 'updated';
    console.log("Changing sort option to:", newSortOption);

    // Show loading indicator
    setIsSorting(true);

    // Update sort option
    setSortOption(newSortOption);

    // Force immediate re-sorting with a longer timeout to ensure state updates
    setTimeout(() => {
      console.log("Applying filters after sort change with option:", newSortOption);

      // Create a copy of the pages array to work with
      let filtered = [...pages].map((page: any) => ({
        ...page,
        // Ensure these properties exist for sorting
        created_at: page.created_at || null,
        updated_at: page.updated_at || null,
        title: page.title || '',
        is_parent: !page.is_chunk && !page.parent_id
      }));

      // Filter out chunk pages - only show parent pages in the main list
      filtered = filtered.filter(page => !page.is_chunk);

      // Apply search filter
      if (searchTerm.trim()) {
        const searchLower = searchTerm.toLowerCase();
        filtered = filtered.filter(page =>
          (page.title && page.title.toLowerCase().includes(searchLower)) ||
          (page.url && page.url.toLowerCase().includes(searchLower)) ||
          (page.summary && page.summary.toLowerCase().includes(searchLower)) ||
          (page.content && page.content.toLowerCase().includes(searchLower))
        );
      }

      // Apply sorting
      filtered.sort((a, b) => {
        switch (newSortOption) {
          case 'title':
            // Case-insensitive alphabetical sort
            return (a.title || '').toLowerCase().localeCompare((b.title || '').toLowerCase());

          case 'created':
            // Handle null or undefined dates
            if (!a.created_at && !b.created_at) return 0;
            if (!a.created_at) return 1; // b comes first
            if (!b.created_at) return -1; // a comes first

            // Convert to timestamps and compare (newest first)
            const aCreated = new Date(a.created_at).getTime();
            const bCreated = new Date(b.created_at).getTime();
            return bCreated - aCreated;

          case 'updated':
            // Handle null or undefined dates
            if (!a.updated_at && !b.updated_at) return 0;
            if (!a.updated_at) return 1; // b comes first
            if (!b.updated_at) return -1; // a comes first

            // Convert to timestamps and compare (newest first)
            const aUpdated = new Date(a.updated_at).getTime();
            const bUpdated = new Date(b.updated_at).getTime();
            return bUpdated - aUpdated;

          default:
            return 0;
        }
      });

      // Update filtered pages
      setFilteredPages(filtered);
      setIsSorting(false);
    }, 200);
  };

  // Add a function to toggle expanded state
  const togglePageExpanded = (pageId: number) => {
    setExpandedPageIds(prev =>
      prev.includes(pageId)
        ? prev.filter(id => id !== pageId)
        : [...prev, pageId]
    );
  };

  // Check if a page is expanded
  const isPageExpanded = (pageId: number) => expandedPageIds.includes(pageId);

  return (
    <div className="max-w-4xl mx-auto px-4">
      <PageHeader
        title={site ? site.name : 'Site details'}
        subtitle={site?.url ? site.url : undefined}
        backTo="/sites"
      />

      {isLoading ? (
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
        </div>
      ) : selectedPage ? (
        <div>
          <button
            onClick={handleBackToList}
            className="btn-secondary mb-4 px-4 py-2"
          >
            ← Back to Pages
          </button>

          <div className="card p-6">
            <h2 className="text-xl font-semibold mb-2">{selectedPage.title || 'Untitled'}</h2>

            <div className="flex flex-wrap gap-2 mb-4">
              <a
                href={selectedPage.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline break-all"
              >
                {selectedPage.url}
              </a>

              {selectedPage.is_chunk && (
                <span className="text-sm bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-1 rounded">
                  Chunk {selectedPage.chunk_index}
                </span>
              )}
            </div>

            <div className="grid grid-cols-2 gap-4 mb-4 text-sm text-gray-600 dark:text-gray-400">
              <div>
                <span className="font-medium">Created: </span>
                {formatDate(selectedPage.created_at)}
              </div>
              <div>
                <span className="font-medium">Updated: </span>
                {formatDate(selectedPage.updated_at)}
              </div>
              <div>
                <span className="font-medium">Page ID: </span>
                {selectedPage.id}
              </div>
              {selectedPage.parent_id && (
                <div>
                  <span className="font-medium">Parent ID: </span>
                  {selectedPage.parent_id}
                </div>
              )}
            </div>

            {selectedPage.summary && (
              <div className="mb-4">
                <h3 className="text-lg font-medium mb-2">Summary</h3>
                <p className="bg-gray-50 dark:bg-gray-800 p-3 rounded">{selectedPage.summary}</p>
              </div>
            )}

            {/* Related chunks section */}
            {relatedChunks.length > 0 && (
              <div className="mb-4">
                <h3 className="text-lg font-medium mb-2">
                  {selectedPage.is_chunk ? 'Other Chunks' : 'Chunks'}
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {relatedChunks.map(chunk => (
                    <button
                      key={chunk.id}
                      onClick={() => handleViewChunk(chunk)}
                      className="text-left p-2 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <div className="text-sm font-medium">
                        Chunk {chunk.chunk_index}
                      </div>
                      {chunk.title && (
                        <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {chunk.title}
                        </div>
                      )}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div>
              <div className="flex flex-col space-y-2 mb-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-medium">Content</h3>
                  <div className="flex items-center space-x-4">
                    {contentSource !== 'unknown' && (
                      <div className="text-xs px-2 py-1 rounded bg-gray-100 dark:bg-gray-800">
                        Source: {contentSource === 'database' ? 'Database' : 'Live URL'}
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  <div className="flex rounded-md shadow-sm" role="group">
                    <button
                      type="button"
                      onClick={() => {
                        setViewMode('database');
                        if (selectedPage.id) {
                          fetchDatabaseContent(selectedPage.id);
                        }
                      }}
                      className={`px-3 py-1 text-xs font-medium rounded-l-lg ${
                        viewMode === 'database'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      Database Content
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setViewMode('live');
                        if (selectedPage.url) {
                          fetchLiveContent(selectedPage.url);
                        }
                      }}
                      className={`px-3 py-1 text-xs font-medium rounded-r-lg ${
                        viewMode === 'live'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      Live URL Content
                    </button>
                  </div>

                  <div className="flex rounded-md shadow-sm" role="group">
                    <button
                      type="button"
                      onClick={() => setContentViewMode('raw')}
                      className={`px-3 py-1 text-xs font-medium rounded-l-lg ${
                        contentViewMode === 'raw'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      Raw
                    </button>
                    <button
                      type="button"
                      onClick={() => setContentViewMode('rendered')}
                      className={`px-3 py-1 text-xs font-medium rounded-r-lg ${
                        contentViewMode === 'rendered'
                          ? 'bg-blue-600 text-white'
                          : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
                      }`}
                    >
                      Rendered
                    </button>
                  </div>
                </div>
              </div>

              {isLoadingContent ? (
                <div className="flex justify-center items-center h-32">
                  <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
                </div>
              ) : (
                <>
                  {viewMode === 'database' ? (
                    <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded overflow-auto max-h-[500px]">
                      {databaseContent ? (
                        contentViewMode === 'raw' ? (
                          <pre className="whitespace-pre-wrap text-sm font-mono">{databaseContent}</pre>
                        ) : (
                          <div className="prose dark:prose-invert max-w-none">
                            {detectContentType(databaseContent) === 'html' ? (
                              <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(databaseContent) }} />
                            ) : (
                              <ReactMarkdown>
                                {databaseContent}
                              </ReactMarkdown>
                            )}
                          </div>
                        )
                      ) : (
                        <div className="flex flex-col items-center justify-center py-4">
                          <p className="text-gray-500 dark:text-gray-400 mb-2">No database content available</p>
                          <button
                            onClick={() => selectedPage.id && fetchDatabaseContent(selectedPage.id)}
                            className="btn-secondary text-xs py-1 px-3"
                          >
                            Try to Fetch Database Content
                          </button>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded overflow-auto max-h-[500px]">
                      {liveContent ? (
                        contentViewMode === 'raw' ? (
                          <pre className="whitespace-pre-wrap text-sm font-mono">{liveContent}</pre>
                        ) : (
                          <div className="prose dark:prose-invert max-w-none">
                            {detectContentType(liveContent) === 'html' ? (
                              <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(liveContent) }} />
                            ) : (
                              <ReactMarkdown>
                                {liveContent}
                              </ReactMarkdown>
                            )}
                          </div>
                        )
                      ) : (
                        <div className="flex flex-col items-center justify-center py-4">
                          <p className="text-gray-500 dark:text-gray-400 mb-2">No live content available</p>
                          <button
                            onClick={() => selectedPage.url && fetchLiveContent(selectedPage.url)}
                            className="btn-secondary text-xs py-1 px-3"
                          >
                            Try to Fetch Live Content
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Debug information section */}
            <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
              <details className="text-sm">
                <summary className="cursor-pointer font-medium mb-2">Debug Information</summary>
                <div className="bg-gray-50 dark:bg-gray-800 p-3 rounded overflow-auto max-h-[300px]">
                  <pre className="text-xs whitespace-pre-wrap">
                    {JSON.stringify(selectedPage, null, 2)}
                  </pre>
                </div>
              </details>
            </div>
          </div>
        </div>
      ) : error ? (
        <div className="bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-200 p-4 rounded mb-6">
          {error}
        </div>
      ) : site ? (
        <div>
          <div className="card p-6 mb-6">
            <h2 className="text-xl font-semibold mb-2">{site.name}</h2>
            <p className="text-gray-600 dark:text-gray-400 mb-4">
              <a
                href={site.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline"
              >
                {site.url}
              </a>
            </p>

            {site.description && (
              <div className="mb-4">
                <h3 className="text-lg font-medium mb-2">Description</h3>
                <p className="bg-gray-50 dark:bg-gray-800 p-3 rounded">{site.description}</p>
                {site.description === "AI is generating a description... (refresh in a moment)" && (
                  <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
                    The AI is currently generating a description. Click the "Refresh Data" button below to check if it's ready.
                  </p>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 text-sm text-gray-600 dark:text-gray-400">
              <div>
                <span className="font-medium">Created: </span>
                {formatDate(site.created_at)}
              </div>
            </div>

            <div className="mt-4 flex gap-2">
              <button
                onClick={checkApiDirectly}
                className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 px-3 py-1 rounded-md flex items-center"
                title="Fetch raw data from the API for debugging purposes"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
                Debug API Data
              </button>

              <button
                onClick={() => siteId && loadSiteDetails(parseInt(siteId), { notifySuccess: true })}
                className="text-xs bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-700 px-3 py-1 rounded-md flex items-center"
                title="Refresh site and pages data"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                Refresh Data
              </button>

              <button
                onClick={() => setShowDebug(!showDebug)}
                className="text-xs bg-purple-100 dark:bg-purple-800 text-purple-700 dark:text-purple-300 hover:bg-purple-200 dark:hover:bg-purple-700 px-3 py-1 rounded-md flex items-center"
                title="Toggle debug information"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4 mr-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {showDebug ? 'Hide Debug Info' : 'Show Debug Info'}
              </button>
            </div>
          </div>

          <div className="flex justify-between items-center mb-4">
            <div className="flex items-center">
              <h2 className="text-xl font-semibold">
                Pages ({filteredPages.length} of {pages.filter(p => !p.is_chunk).length})
              </h2>
              <button
                onClick={() => siteId && loadSiteDetails(parseInt(siteId), { notifySuccess: true })}
                className="ml-2 text-xs bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 p-1 rounded-full flex items-center"
                title="Refresh pages data"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2 mb-4">
            <div className="flex items-center">
              <span className="text-sm text-gray-600 dark:text-gray-400 mr-2">Sort by:</span>
              <div className="relative">
                <select
                  value={sortOption}
                  onChange={handleSortChange}
                  className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 appearance-none pr-8"
                >
                  <option value="title">Title (A-Z)</option>
                  <option value="created">Created Date (newest)</option>
                  <option value="updated">Updated Date (newest)</option>
                </select>
                <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-700 dark:text-gray-300">
                  <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">
                    <path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z" />
                  </svg>
                </div>
              </div>
              {isSorting && (
                <div className="ml-2">
                  <div className="animate-spin rounded-full h-4 w-4 border-t-2 border-b-2 border-blue-500"></div>
                </div>
              )}
            </div>
            <div className="flex-1">
              <input
                type="text"
                placeholder="Search pages..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="px-3 py-2 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 w-full"
              />
            </div>
          </div>

          {filteredPages.length === 0 ? (
            <div className="text-center py-8 text-gray-500 dark:text-gray-400">
              <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mx-auto mb-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p className="text-lg font-medium">No pages found</p>
              <p className="mt-1">Try adjusting your search or filters</p>
              {searchTerm && (
                <button
                  onClick={() => setSearchTerm('')}
                  className="mt-4 px-4 py-2 bg-blue-100 dark:bg-blue-800 text-blue-700 dark:text-blue-300 rounded-md hover:bg-blue-200 dark:hover:bg-blue-700"
                >
                  Clear search
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              {filteredPages
                .slice((currentPage - 1) * pageSize, currentPage * pageSize)
                .map((page: any, index: number) => {
                  if (!page || !page.id) return null;

                  // Get chunks for this page
                  const pageChunks = pages.filter(p => p.parent_id === page.id);
                  const isExpanded = isPageExpanded(page.id);

                  return (
                    <PageListItem
                      key={page.id}
                      page={page}
                      selectedPageId={null}
                      pageChunks={pageChunks}
                      onPageClick={handlePageClick}
                      isExpanded={isExpanded}
                      onToggleExpand={togglePageExpanded}
                      showDebug={showDebug && index < 3}
                    />
                  );
                })}
            </div>
          )}

          {filteredPages.length > 0 && (
            <div className="mt-4 text-sm text-gray-600 dark:text-gray-400 text-center">
              Showing {Math.min(filteredPages.length, (currentPage - 1) * pageSize + 1)} - {Math.min(filteredPages.length, currentPage * pageSize)} of {filteredPages.length} pages
            </div>
          )}

          {totalPages > 1 && (
            <div className="flex flex-col sm:flex-row justify-between items-center mt-6 gap-4">
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-600 dark:text-gray-400">Show:</span>
                <select
                  value={pageSize}
                  onChange={(e) => {
                    const newSize = parseInt(e.target.value);
                    setPageSize(newSize);
                    // Recalculate total pages
                    const newTotalPages = Math.ceil(filteredPages.length / newSize);
                    setTotalPages(newTotalPages);
                    // Adjust current page if needed
                    if (currentPage > newTotalPages) {
                      setCurrentPage(1);
                    }
                  }}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-700 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-sm"
                >
                  <option value="5">5 per page</option>
                  <option value="10">10 per page</option>
                  <option value="20">20 per page</option>
                  <option value="50">50 per page</option>
                </select>
              </div>

              <nav className="flex items-center space-x-2">
                <button
                  onClick={() => handlePageChange(1)}
                  disabled={currentPage === 1}
                  className="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 disabled:opacity-50 text-sm"
                  title="First page"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
                  </svg>
                </button>
                <button
                  onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                  className="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 disabled:opacity-50 text-sm"
                  title="Previous page"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
                  </svg>
                </button>

                <span className="text-sm text-gray-600 dark:text-gray-400">
                  Page {currentPage} of {totalPages}
                </span>

                <button
                  onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                  className="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 disabled:opacity-50 text-sm"
                  title="Next page"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </button>
                <button
                  onClick={() => handlePageChange(totalPages)}
                  disabled={currentPage === totalPages}
                  className="px-2 py-1 rounded border border-gray-300 dark:border-gray-700 disabled:opacity-50 text-sm"
                  title="Last page"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 5l7 7-7 7M5 5l7 7-7 7" />
                  </svg>
                </button>
              </nav>
            </div>
          )}
        </div>
      ) : (
        <div className="text-center py-8 text-gray-500 dark:text-gray-400">
          No site found
        </div>
      )}
    </div>
  );
};

export default SiteDetailPage;
