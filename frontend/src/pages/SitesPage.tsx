import { useState, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiService, Site } from '@/api/apiService';
import { api } from '@/api/apiWrapper';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RefreshCw, Trash2 } from 'lucide-react';
import { createNotification } from '@/utils/notifications';
import { PageHeader } from '@/components/PageHeader';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type SitesSortOption =
  | 'created_desc'
  | 'created_asc'
  | 'name_asc'
  | 'name_desc'
  | 'url_asc'
  | 'url_desc'
  | 'pages_desc'
  | 'pages_asc'
  | 'last_crawled_desc'
  | 'last_crawled_asc'
  | 'updated_desc'
  | 'updated_asc';

function siteCreatedTime(site: Site): number {
  if (!site.created_at) return 0;
  const t = new Date(site.created_at).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function siteOptionalTime(value: string | null | undefined): number {
  if (!value) return 0;
  const t = new Date(value).getTime();
  return Number.isNaN(t) ? 0 : t;
}

function compareSites(a: Site, b: Site, sort: SitesSortOption): number {
  switch (sort) {
    case 'created_desc':
      return siteCreatedTime(b) - siteCreatedTime(a);
    case 'created_asc':
      return siteCreatedTime(a) - siteCreatedTime(b);
    case 'name_asc':
      return (a.name || '').localeCompare(b.name || '', undefined, { sensitivity: 'base' });
    case 'name_desc':
      return (b.name || '').localeCompare(a.name || '', undefined, { sensitivity: 'base' });
    case 'url_asc':
      return (a.url || '').localeCompare(b.url || '', undefined, { sensitivity: 'base' });
    case 'url_desc':
      return (b.url || '').localeCompare(a.url || '', undefined, { sensitivity: 'base' });
    case 'pages_desc':
      return (b.page_count ?? 0) - (a.page_count ?? 0);
    case 'pages_asc':
      return (a.page_count ?? 0) - (b.page_count ?? 0);
    case 'last_crawled_desc':
      return siteOptionalTime(b.last_crawled_at) - siteOptionalTime(a.last_crawled_at);
    case 'last_crawled_asc':
      return siteOptionalTime(a.last_crawled_at) - siteOptionalTime(b.last_crawled_at);
    case 'updated_desc':
      return siteOptionalTime(b.updated_at) - siteOptionalTime(a.updated_at);
    case 'updated_asc':
      return siteOptionalTime(a.updated_at) - siteOptionalTime(b.updated_at);
    default:
      return 0;
  }
}

const SitesPage = () => {
  const [sites, setSites] = useState<Site[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [debugInfo, setDebugInfo] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [siteToDelete, setSiteToDelete] = useState<Site | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState<SitesSortOption>('created_desc');

  // Load sites on mount; poll in the background without swapping the whole page for a spinner.
  useEffect(() => {
    void loadSites(false, false);
    const interval = setInterval(() => {
      void loadSites(false, true);
    }, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadSites = async (bypassCache = false, silent = false) => {
    if (!silent) {
      setIsLoading(true);
    }
    try {
      let sitesData;
      
      if (bypassCache) {
        // Bypass cache by making a direct API call
        const response = await axios.get('/api/sites');
        console.log('Direct API response for sites (bypass cache):', response.data);
        
        // Handle the response format with a sites array
        if (response.data && response.data.sites && Array.isArray(response.data.sites)) {
          sitesData = response.data.sites;
        } else {
          sitesData = response.data;
        }
      } else {
        // Use the API wrapper which might use cached data
        sitesData = await api.getSites();
        console.log('API wrapper response for sites:', sitesData);
      }
      
      // Debug each site's created_at field
      if (Array.isArray(sitesData)) {
        sitesData.forEach((site, index) => {
          console.log(`Site ${index} (${site.name || 'unnamed'}) created_at:`, site.created_at);
          console.log(`Formatted date:`, formatDate(site.created_at));
        });

        setSites(sitesData as Site[]);
      } else {
        console.error('Unexpected sites data format:', sitesData);
        setSites([]);
      }
    } catch (error) {
      console.error('Error loading sites:', error);
      if (!silent) {
        toast.error('Failed to load sites');
        setSites([]);
      }
    } finally {
      if (!silent) {
        setIsLoading(false);
      }
    }
  };

  const displaySites = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    let list = sites;
    if (q) {
      list = sites.filter((site) => {
        const name = (site.name || '').toLowerCase();
        const url = (site.url || '').toLowerCase();
        const desc = (site.description || '').toLowerCase();
        return name.includes(q) || url.includes(q) || desc.includes(q);
      });
    }
    return [...list].sort((a, b) => compareSites(a, b, sortBy));
  }, [sites, searchQuery, sortBy]);

  const checkApiDirectly = async () => {
    setIsLoading(true);
    setDebugInfo(null);
    
    try {
      // Try to fetch sites directly from the API
      const response = await axios.get('/api/sites');
      console.log('Direct API response:', response.data);
      
      // If the API call is successful, try to update the sites with the direct data
      if (Array.isArray(response.data)) {
        setSites(response.data);
        createNotification('Success', `Found ${response.data.length} sites directly from API`, 'success', true);
      }
      
      setDebugInfo(JSON.stringify(response.data, null, 2));
    } catch (err) {
      console.error('Error checking API directly:', err);
      setDebugInfo(JSON.stringify(err, null, 2));
      toast.error('API check failed');
    } finally {
      setIsLoading(false);
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

  const confirmDeleteSite = async () => {
    if (!siteToDelete) return;
    setDeleting(true);
    try {
      await apiService.deleteSite(siteToDelete.id);
      toast.success(`Deleted “${siteToDelete.name || 'site'}”`);
      setSiteToDelete(null);
      await loadSites(true, true);
    } catch (err) {
      console.error(err);
      toast.error('Failed to delete site');
    } finally {
      setDeleting(false);
    }
  };

  const manualRefresh = async () => {
    setRefreshing(true);
    try {
      await loadSites(true, true); // bypass + silent: button spinner only, no full-page flash
      toast.success('Sites updated', { id: 'sites-list-refresh', duration: 2200 });
    } catch (error) {
      console.error('Error refreshing sites:', error);
      toast.error('Failed to refresh sites');
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="container mx-auto px-4 py-8">
      {debugInfo && (
        <div className="mb-6 p-4 bg-gray-100 dark:bg-gray-800 rounded-lg overflow-auto max-h-96">
          <h3 className="text-lg font-medium mb-2">Debug Info</h3>
          <pre className="text-xs">{debugInfo}</pre>
        </div>
      )}
      
      <div className="flex flex-col gap-4 mb-6">
        <PageHeader title="Sites" subtitle="Crawled sites and page counts" backTo="/" />
        <div className="flex justify-end gap-2 flex-wrap">
          <Button 
            variant="outline" 
            size="sm"
            onClick={checkApiDirectly}
            className="text-gray-700 dark:text-gray-300"
          >
            Debug API
          </Button>
          <Button 
            variant="outline" 
            size="sm"
            onClick={manualRefresh}
            disabled={refreshing}
            className="flex items-center gap-2"
          >
            {refreshing ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-gray-500 border-t-transparent"></div>
                <span>Refreshing...</span>
              </>
            ) : (
              <>
                <RefreshCw className="h-4 w-4" />
                <span>Refresh Sites</span>
              </>
            )}
          </Button>
          <Link 
            to="/crawl" 
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Crawl New Site
          </Link>
        </div>
        {sites.length > 0 ? (
          <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
            <div className="flex-1 min-w-[min(100%,220px)] max-w-md space-y-1.5">
              <Label htmlFor="sites-search" className="text-gray-700 dark:text-gray-300">
                Search sites
              </Label>
              <Input
                id="sites-search"
                type="search"
                placeholder="Filter by name, URL, or description…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoComplete="off"
                className="border-gray-300 bg-white text-gray-900 placeholder:text-gray-500 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 dark:placeholder:text-gray-500"
              />
            </div>
            <div className="w-full min-w-[200px] max-w-xs space-y-1.5 sm:w-56">
              <Label htmlFor="sites-sort" className="text-gray-700 dark:text-gray-300">
                Sort by
              </Label>
              <Select value={sortBy} onValueChange={(v) => setSortBy(v as SitesSortOption)}>
                <SelectTrigger
                  id="sites-sort"
                  className="border-gray-300 bg-white text-gray-900 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100"
                >
                  <SelectValue placeholder="Sort" />
                </SelectTrigger>
                <SelectContent className="border-gray-200 bg-white dark:border-gray-700 dark:bg-gray-800">
                  <SelectItem value="created_desc">Date added (newest first)</SelectItem>
                  <SelectItem value="created_asc">Date added (oldest first)</SelectItem>
                  <SelectItem value="name_asc">Name (A–Z)</SelectItem>
                  <SelectItem value="name_desc">Name (Z–A)</SelectItem>
                  <SelectItem value="url_asc">URL (A–Z)</SelectItem>
                  <SelectItem value="url_desc">URL (Z–A)</SelectItem>
                  <SelectItem value="pages_desc">Page count (high → low)</SelectItem>
                  <SelectItem value="pages_asc">Page count (low → high)</SelectItem>
                  <SelectItem value="last_crawled_desc">Last crawled (newest)</SelectItem>
                  <SelectItem value="last_crawled_asc">Last crawled (oldest)</SelectItem>
                  <SelectItem value="updated_desc">Updated (newest)</SelectItem>
                  <SelectItem value="updated_asc">Updated (oldest)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        ) : null}
      </div>

      {isLoading ? (
        <div className="text-center py-12">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-current border-r-transparent align-[-0.125em] motion-reduce:animate-[spin_1.5s_linear_infinite]"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading sites...</p>
        </div>
      ) : error ? (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 text-center">
          <p className="text-red-500 mb-4">{error}</p>
          <Button onClick={manualRefresh} variant="outline">
            Try Again
          </Button>
        </div>
      ) : sites.length > 0 && displaySites.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 text-center">
          <h2 className="text-xl font-semibold mb-2">No matching sites</h2>
          <p className="mb-4 text-gray-600 dark:text-gray-400">
            Nothing matches “{searchQuery.trim()}”. Try a different search or clear the filter.
          </p>
          <Button type="button" variant="outline" onClick={() => setSearchQuery('')}>
            Clear search
          </Button>
        </div>
      ) : sites.length > 0 ? (
        <>
          {searchQuery.trim() ? (
            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              Showing {displaySites.length} of {sites.length} sites
            </p>
          ) : null}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {displaySites.map((site) => (
            <div
              key={site.id}
              className="relative bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 hover:shadow-md transition-shadow duration-200 flex flex-col h-full"
            >
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute right-2 top-2 z-10 h-9 w-9 text-muted-foreground hover:text-destructive"
                aria-label={`Delete site ${site.name || site.id}`}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setSiteToDelete(site);
                }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
              <Link
                to={`/sites/${site.id}`}
                className="p-6 flex flex-col h-full flex-1 min-w-0"
              >
                <h2 className="text-xl font-semibold mb-2 truncate pr-8">{site.name || 'Unnamed Site'}</h2>

                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 truncate">
                  {site.url || 'No URL'}
                </p>

                {site.description && (
                  <p className="text-sm mb-4 line-clamp-2">{site.description}</p>
                )}

                <div className="flex justify-between items-center mt-auto pt-4 border-t border-gray-200 dark:border-gray-700">
                  <div className="flex items-center">
                    <span className="text-sm font-medium">{site.page_count || 0}</span>
                    <span className="text-xs text-gray-600 dark:text-gray-400 ml-1">
                      {site.page_count === 1 ? 'page' : 'pages'}
                    </span>
                  </div>

                  <div className="text-xs text-gray-600 dark:text-gray-400">
                    {site.created_at ? formatDate(site.created_at) : 'No date'}
                  </div>
                </div>
              </Link>
            </div>
          ))}
        </div>
        </>
      ) : (
        <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 text-center">
          <h2 className="text-xl font-semibold mb-4">No Sites Found</h2>
          <p className="mb-6 text-gray-600 dark:text-gray-400">
            You haven't crawled any websites yet. Start by crawling your first site.
          </p>
          <Link 
            to="/crawl" 
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-medium text-white bg-blue-600 border border-transparent rounded-md shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
          >
            Crawl New Site
          </Link>
        </div>
      )}

      <Dialog open={!!siteToDelete} onOpenChange={(open) => !open && setSiteToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete site?</DialogTitle>
            <DialogDescription>
              This removes the site, all crawled pages and chunks, and crawl job history for this site. This cannot be undone.
              {siteToDelete ? (
                <>
                  <br />
                  <span className="font-medium text-foreground mt-2 block truncate">{siteToDelete.name}</span>
                  <span className="text-xs break-all">{siteToDelete.url}</span>
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setSiteToDelete(null)} disabled={deleting}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={confirmDeleteSite} disabled={deleting}>
              {deleting ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default SitesPage; 