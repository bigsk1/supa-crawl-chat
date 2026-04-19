import React, { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { CrawlStatus } from '@/api/apiService';
import { api } from '@/api/apiWrapper';
import { createNotification } from '@/utils/notifications';
import { Button } from '@/components/ui/button';
import { toast } from 'react-hot-toast';
import axios from 'axios';
import { Eye, Search, RefreshCw } from 'lucide-react';
import AdvancedCrawlOptions from '@/components/AdvancedCrawlOptions';
import { PageHeader } from '@/components/PageHeader';

const DebugPanel = ({ isOpen, onClose, data }: { isOpen: boolean; onClose: () => void; data: any }) => {
  if (!isOpen) return null;
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <div className="debug-panel w-full max-w-4xl bg-[#171923] border border-white/[0.05] rounded-lg shadow-lg overflow-hidden">
        <div className="debug-panel-header flex justify-between items-center p-4 border-b border-white/[0.05]">
          <h3 className="text-lg font-medium text-gray-200">API Debug Info</h3>
          <Button 
            variant="ghost" 
            size="sm" 
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground"
          >
            Close
          </Button>
        </div>
        <div className="p-4 max-h-[70vh] overflow-auto">
          <pre className="bg-[#0f1117] text-foreground p-4 rounded-md overflow-auto text-sm">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      </div>
    </div>
  );
};

const CrawlPage = () => {
  const navigate = useNavigate();
  const [url, setUrl] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [depth, setDepth] = useState(2);
  const [maxPages, setMaxPages] = useState(25);
  const [followExternalLinks, setFollowExternalLinks] = useState(false);
  const [includePatterns, setIncludePatterns] = useState('');
  const [excludePatterns, setExcludePatterns] = useState('');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [activeCrawls, setActiveCrawls] = useState<CrawlStatus[]>([]);
  const [debugData, setDebugData] = useState<any>(null);
  const [showDebugPanel, setShowDebugPanel] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [pollingInterval, setPollingInterval] = useState<NodeJS.Timeout | null>(null);
  
  // Advanced options
  const [headless, setHeadless] = useState(true);
  const [browserType, setBrowserType] = useState('chromium');
  const [javascriptEnabled, setJavascriptEnabled] = useState(true);
  const [userAgent, setUserAgent] = useState('');
  const [timeout, setTimeout] = useState(30000);
  const [waitForSelector, setWaitForSelector] = useState('');
  const [downloadImages, setDownloadImages] = useState(false);
  const [downloadVideos, setDownloadVideos] = useState(false);
  const [downloadFiles, setDownloadFiles] = useState(false);
  const [followRedirects, setFollowRedirects] = useState(true);
  const [maxDepth, setMaxDepth] = useState(3);
  const [extractionType, setExtractionType] = useState('basic');
  const [cssSelector, setCssSelector] = useState('');

  useEffect(() => {
    // Initial load
    loadActiveCrawls();
    
    // Set up polling every 10 seconds to check for new crawls
    const interval = setInterval(loadActiveCrawls, 10000);
    setPollingInterval(interval);
    
    // Clean up interval when component unmounts
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, []);

  const loadActiveCrawls = async (bypassCache = false) => {
    try {
      let sitesData;
      
      if (bypassCache) {
        // Bypass cache by making a direct API call
        const response = await axios.get('/api/sites');
        console.log('Direct API response for crawls (bypass cache):', response.data);
        
        // Handle the response format with a sites array
        if (response.data && response.data.sites && Array.isArray(response.data.sites)) {
          sitesData = response.data.sites;
        } else {
          sitesData = response.data;
        }
      } else {
        // First try to get all sites, as they contain the crawl information
        sitesData = await api.getSites();
        console.log('Sites data for crawls:', sitesData);
      }
      
      // Handle different response formats
      if (Array.isArray(sitesData) && sitesData.length > 0) {
        // Convert sites to crawl status format
        const crawlsFromSites = sitesData.map(site => ({
          site_id: site.id,
          site_name: site.name,
          name: site.name,
          url: site.url,
          page_count: site.page_count || 0,
          chunk_count: 0,
          total_count: site.page_count || 0,
          created_at: site.created_at,
          updated_at: site.created_at,
          status: 'completed',
          next_steps: {
            view_pages: `/sites/${site.id}`,
            search_content: `/search?site_id=${site.id}`
          }
        }));
        
        // Sort crawls by created_at date (newest first)
        const sortedCrawls = [...crawlsFromSites].sort((a, b) => {
          // Convert dates to timestamps for comparison
          const dateA = a.created_at ? new Date(a.created_at).getTime() : 0;
          const dateB = b.created_at ? new Date(b.created_at).getTime() : 0;
          // Sort in descending order (newest first)
          return dateB - dateA;
        });
        
        setActiveCrawls(sortedCrawls);
        return;
      } else if (sitesData && typeof sitesData === 'object' && !Array.isArray(sitesData)) {
        // If it's a single site object, convert to array
        console.log('Single site object received, converting to crawl status');
        const site = sitesData;
        const crawlStatus = {
          site_id: site.id,
          site_name: site.name,
          name: site.name,
          url: site.url,
          page_count: site.page_count || 0,
          chunk_count: 0,
          total_count: site.page_count || 0,
          created_at: site.created_at,
          updated_at: site.created_at,
          status: 'completed',
          next_steps: {
            view_pages: `/sites/${site.id}`,
            search_content: `/search?site_id=${site.id}`
          }
        };
        setActiveCrawls([crawlStatus]);
        return;
      }
      
      // If no sites are found or the format is unexpected, set empty array
      console.log('No valid sites data found, setting empty array');
      setActiveCrawls([]);
    } catch (error) {
      console.error('Error loading active crawls:', error);
      // Don't show toast for background polling
      setActiveCrawls([]); // Set empty array on error
    }
  };

  const manualRefresh = async () => {
    setRefreshing(true);
    try {
      await loadActiveCrawls(true); // Pass true to bypass cache
      toast.success('Crawl list updated', { id: 'crawl-list-refresh', duration: 2200 });
    } catch (error) {
      console.error('Error refreshing crawls:', error);
      toast.error('Failed to refresh crawls');
    } finally {
      setRefreshing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!url) {
      createNotification('Error', 'Please enter a URL', 'error', true);
      return;
    }
    
    setIsSubmitting(true);
    
    try {
      // Prepare the frontend crawl parameters
      const frontendParams = {
        url,
        name: name || url,
        description,
        depth,
        max_pages: maxPages,
        follow_external_links: followExternalLinks,
        include_patterns: includePatterns ? includePatterns.split(',').map(p => p.trim()) : [],
        exclude_patterns: excludePatterns ? excludePatterns.split(',').map(p => p.trim()) : []
      };
      
      // Log the frontend parameters for debugging
      console.log('Frontend crawl params:', frontendParams);
      setDebugData(frontendParams);
      
      // Transform frontend parameters to API parameters
      const apiParams: any = {
        url,
        site_name: name || url,
        site_description: description || null,
        is_sitemap: depth === 3, // Map depth=3 (Deep Crawl) to is_sitemap=true
        max_urls: maxPages,
        follow_external_links: followExternalLinks,
        include_patterns: includePatterns ? includePatterns.split(',').map(p => p.trim()) : [],
        exclude_patterns: excludePatterns ? excludePatterns.split(',').map(p => p.trim()) : []
      };
      
      // Add advanced options if they are set
      if (showAdvanced) {
        // Browser options
        if (headless !== true) apiParams.headless = headless;
        if (browserType !== 'chromium') apiParams.browser_type = browserType;
        if (javascriptEnabled !== true) apiParams.javascript_enabled = javascriptEnabled;
        if (userAgent) apiParams.user_agent = userAgent;
        
        // Navigation options
        if (timeout !== 30000) apiParams.timeout = timeout;
        if (waitForSelector) apiParams.wait_for_selector = waitForSelector;
        
        // Media options
        if (downloadImages) apiParams.download_images = downloadImages;
        if (downloadVideos) apiParams.download_videos = downloadVideos;
        if (downloadFiles) apiParams.download_files = downloadFiles;
        
        // Link options
        if (followRedirects !== true) apiParams.follow_redirects = followRedirects;
        if (maxDepth !== 3) apiParams.max_depth = maxDepth;
        
        // Extraction options
        if (extractionType !== 'basic') apiParams.extraction_type = extractionType;
        if (extractionType === 'custom' && cssSelector) apiParams.css_selector = cssSelector;
      }
      
      console.log('Transformed API params:', apiParams);
      
      // Start the crawl with the transformed parameters
      const result = await api.startCrawl(apiParams);
      console.log('Crawl started:', result);
      
      // Reset the form
      resetForm();
      
      // Refresh the crawl list
      await loadActiveCrawls(true);
      
    } catch (error) {
      console.error('Error starting crawl:', error);
      createNotification('Error', 'Failed to start crawl. Please try again.', 'error', true);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setUrl('');
    setName('');
    setDescription('');
    setDepth(2);
    setMaxPages(25);
    setFollowExternalLinks(false);
    setIncludePatterns('');
    setExcludePatterns('');
    
    // Reset advanced options
    setHeadless(true);
    setBrowserType('chromium');
    setJavascriptEnabled(true);
    setUserAgent('');
    setTimeout(30000);
    setWaitForSelector('');
    setDownloadImages(false);
    setDownloadVideos(false);
    setDownloadFiles(false);
    setFollowRedirects(true);
    setMaxDepth(3);
    setExtractionType('basic');
    setCssSelector('');
  };

  const handleViewSite = (siteId: number | string) => {
    navigate(`/sites/${siteId}`);
  };

  const getStatusColor = (status: string | undefined) => {
    if (!status) return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
    
    switch (status.toLowerCase()) {
      case 'completed':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-200';
      case 'in_progress':
      case 'processing':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-200';
      case 'failed':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-200';
      case 'queued':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
    }
  };

  const formatDate = (dateString: string) => {
    try {
      // Check if dateString is null, undefined, or empty
      if (!dateString) {
        return 'No date';
      }
      
      // Check for epoch dates (1970-01-01 or close to it)
      const date = new Date(dateString);
      if (date.getFullYear() < 1980) {
        console.log('Epoch date detected:', dateString);
        return 'Recent';
      }
      
      // Check if the date is valid (not Invalid Date)
      if (isNaN(date.getTime())) {
        console.error('Invalid date string:', dateString);
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
      console.error('Error formatting date:', error, 'Date string:', dateString);
      return 'No date';
    }
  };

  // Add debug API handler
  const handleDebugApi = async () => {
    try {
      const sitesData = await api.getSites();
      setDebugData(sitesData);
      setShowDebugPanel(true);
      
      // Add to notification center
      createNotification('API Debug', 'API debug information loaded', 'info', true);
    } catch (error) {
      createNotification('API Debug Error', 'Failed to load API debug information', 'error', true);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      <PageHeader title="Crawl a Website" subtitle="Start a crawl and monitor progress" backTo="/" />
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <div className="card p-6 mb-6">
            <h2 className="text-xl font-semibold mb-4">Start a New Crawl</h2>
            
            <form onSubmit={handleSubmit}>
              <div className="mb-4">
                <label htmlFor="url" className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  URL to Crawl
                </label>
                <input
                  type="url"
                  id="url"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com"
                  required
                  className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
              </div>
              
              <div>
                <label htmlFor="name" className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  Site Name
                </label>
                <input
                  type="text"
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="My Website"
                  className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
              </div>
              
              <div>
                <label htmlFor="description" className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                  Site Description (Optional)
                </label>
                <textarea
                  id="description"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Enter a description for this site"
                  rows={2}
                  className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  If left empty, a description will be automatically generated using AI.
                </p>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label htmlFor="depth" className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    Crawl Type
                  </label>
                  <select
                    id="depth"
                    value={depth}
                    onChange={(e) => setDepth(parseInt(e.target.value))}
                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    <option value="1">URL Only</option>
                    <option value="2">URL + Linked Pages</option>
                    <option value="3">Deep Crawl (Sitemap Mode)</option>
                  </select>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    URL Only: Crawls just the specified URL<br/>
                    URL + Linked Pages: Crawls the URL and pages it links to<br/>
                    Deep Crawl: Uses sitemap.xml to find and crawl all pages
                  </p>
                </div>
                
                <div>
                  <label htmlFor="maxPages" className="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">
                    Max Pages
                  </label>
                  <select
                    id="maxPages"
                    value={maxPages}
                    onChange={(e) => setMaxPages(parseInt(e.target.value))}
                    className="w-full p-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                  >
                    <option value="1">1 page</option>
                    <option value="5">5 pages</option>
                    <option value="10">10 pages</option>
                    <option value="25">25 pages</option>
                    <option value="50">50 pages</option>
                    <option value="100">100 pages</option>
                    <option value="250">250 pages</option>
                  </select>
                </div>
              </div>
              
              <div className="mt-4">
                <button
                  type="button"
                  onClick={() => setShowAdvanced(!showAdvanced)}
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline flex items-center"
                >
                  {showAdvanced ? 'Hide Advanced Options' : 'Show Advanced Options'}
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    className={`h-4 w-4 ml-1 transition-transform ${showAdvanced ? 'rotate-180' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              </div>
              
              {showAdvanced && (
                <div className="mt-4 p-4 border border-gray-200 dark:border-gray-700 rounded-md">
                  <h3 className="text-md font-medium mb-3 text-gray-700 dark:text-gray-300">Advanced Crawl Options</h3>
                  
                  <AdvancedCrawlOptions
                    followExternalLinks={followExternalLinks}
                    setFollowExternalLinks={setFollowExternalLinks}
                    includePatterns={includePatterns}
                    setIncludePatterns={setIncludePatterns}
                    excludePatterns={excludePatterns}
                    setExcludePatterns={setExcludePatterns}
                    headless={headless}
                    setHeadless={setHeadless}
                    browserType={browserType}
                    setBrowserType={setBrowserType}
                    javascriptEnabled={javascriptEnabled}
                    setJavascriptEnabled={setJavascriptEnabled}
                    userAgent={userAgent}
                    setUserAgent={setUserAgent}
                    timeout={timeout}
                    setTimeout={setTimeout}
                    waitForSelector={waitForSelector}
                    setWaitForSelector={setWaitForSelector}
                    downloadImages={downloadImages}
                    setDownloadImages={setDownloadImages}
                    downloadVideos={downloadVideos}
                    setDownloadVideos={setDownloadVideos}
                    downloadFiles={downloadFiles}
                    setDownloadFiles={setDownloadFiles}
                    followRedirects={followRedirects}
                    setFollowRedirects={setFollowRedirects}
                    maxDepth={maxDepth}
                    setMaxDepth={setMaxDepth}
                    extractionType={extractionType}
                    setExtractionType={setExtractionType}
                    cssSelector={cssSelector}
                    setCssSelector={setCssSelector}
                  />
                </div>
              )}
              
              <div className="mt-6 flex justify-end">
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md flex items-center"
                >
                  {isSubmitting ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Starting Crawl...
                    </>
                  ) : (
                    <>
                      <Search className="mr-2 h-4 w-4" />
                      Start Crawl
                    </>
                  )}
                </Button>
              </div>
            </form>
          </div>
          
          {debugData && (
            <div className="card p-4 mb-6">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-md font-medium text-gray-700 dark:text-gray-300">Debug Information</h3>
                <button
                  onClick={() => setShowDebugPanel(true)}
                  className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 px-2 py-1 rounded-md"
                >
                  View Details
                </button>
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                <p>URL: {debugData.url}</p>
                <p>Crawl Type: {depth === 1 ? 'URL Only' : depth === 2 ? 'URL + Linked Pages' : 'Deep Crawl (Sitemap)'}</p>
                <p>Max Pages: {debugData.max_pages}</p>
              </div>
            </div>
          )}
        </div>
        
        <div>
          <div className="card p-6">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-semibold">Active Crawls</h2>
              <button
                onClick={() => loadActiveCrawls(true)}
                className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 p-2 rounded-full flex items-center"
                disabled={refreshing}
                title="Refresh crawl list"
              >
                <RefreshCw className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
            </div>
            
            {isLoading ? (
              <div className="flex justify-center items-center h-32">
                <div className="animate-spin rounded-full h-8 w-8 border-t-2 border-b-2 border-blue-500"></div>
              </div>
            ) : activeCrawls.length === 0 ? (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                <svg xmlns="http://www.w3.org/2000/svg" className="h-12 w-12 mx-auto mb-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
                <p className="text-lg font-medium">No active crawls</p>
                <p className="mt-1">Start a new crawl to see it here</p>
              </div>
            ) : (
              <div className="space-y-4">
                {activeCrawls.map((crawl) => (
                  <div key={crawl.site_id} className="border border-gray-200 dark:border-gray-700 rounded-md p-4">
                    <div className="flex justify-between items-start">
                      <div>
                        <h3 className="font-medium text-gray-900 dark:text-gray-100">{crawl.site_name}</h3>
                        <p className="text-sm text-gray-600 dark:text-gray-400 break-all">{crawl.url}</p>
                      </div>
                      <div className="flex items-center">
                        <span className={`text-xs px-2 py-1 rounded-full ${getStatusColor(crawl.status)}`}>
                          {crawl.status || 'Unknown'}
                        </span>
                      </div>
                    </div>
                    
                    <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                      <p>Created: {formatDate(crawl.created_at)}</p>
                      <p>Pages: {crawl.page_count || 0}</p>
                      {crawl.depth && <p>Crawled with depth={crawl.depth}, follow_external={crawl.follow_external_links?.toString() || 'false'}</p>}
                    </div>
                    
                    <div className="mt-3 flex justify-end">
                      <button
                        onClick={() => handleViewSite(crawl.site_id)}
                        className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-800/50 px-3 py-1 rounded-md flex items-center"
                      >
                        <Eye className="mr-1 h-3 w-3" />
                        View Site
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
      
      <DebugPanel
        isOpen={showDebugPanel}
        onClose={() => setShowDebugPanel(false)}
        data={debugData}
      />
    </div>
  );
};

export default CrawlPage; 