import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { apiService, SearchResult } from '@/api/apiService';
import ReactMarkdown from 'react-markdown';
import { sanitizeHtml } from '@/lib/sanitize';
import { PageHeader } from '@/components/PageHeader';

const SearchPage = () => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [threshold, setThreshold] = useState(0.3);
  const [limit, setLimit] = useState(10);
  const [showDuplicates, setShowDuplicates] = useState(false);
  const [selectedResult, setSelectedResult] = useState<SearchResult | null>(null);
  const [contentViewMode, setContentViewMode] = useState<'raw' | 'rendered'>('rendered');

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!query.trim()) {
      toast.error('Please enter a search query');
      return;
    }

    setIsLoading(true);
    setResults([]);
    setSelectedResult(null);

    try {
      const searchResults = await apiService.search(query, undefined, threshold, limit);
      console.log('Search results:', searchResults); // Debug log

      // Process results to handle duplicates
      const processedResults = processSearchResults(searchResults);
      setResults(processedResults);
      setHasSearched(true);

      if (processedResults.length === 0) {
        toast('No results found for your query', {
          icon: 'ℹ️',
        });
      }
    } catch (error) {
      console.error('Error searching:', error);
      toast.error('Failed to perform search');
    } finally {
      setIsLoading(false);
    }
  };

  // Process search results to handle duplicates
  const processSearchResults = (results: SearchResult[]): SearchResult[] => {
    if (showDuplicates) {
      return results;
    }

    // Group results by URL without the #chunk part
    const urlGroups = new Map<string, SearchResult[]>();

    results.forEach(result => {
      // Remove #chunk-X from URL for grouping
      const baseUrl = result.url.split('#')[0];

      if (!urlGroups.has(baseUrl)) {
        urlGroups.set(baseUrl, []);
      }

      urlGroups.get(baseUrl)!.push(result);
    });

    // For each group, keep only the result with the highest similarity
    const deduplicated: SearchResult[] = [];

    urlGroups.forEach(group => {
      // Sort by similarity (highest first)
      group.sort((a, b) => b.similarity - a.similarity);

      // Keep the highest similarity result
      deduplicated.push(group[0]);
    });

    // Sort by similarity again
    deduplicated.sort((a, b) => b.similarity - a.similarity);

    return deduplicated;
  };

  const escapeHtml = (text: string) =>
    text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

  const highlightQuery = (text: string) => {
    const escapedText = escapeHtml(text || '');
    if (!query.trim() || !escapedText) return escapedText;

    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
    return escapedText.replace(regex, '<mark class="bg-yellow-200 dark:bg-yellow-800">$1</mark>');
  };

  const handleViewResult = async (result: SearchResult) => {
    setSelectedResult(result);
    if (!result.content || result.content_truncated) {
      try {
        const page = await apiService.getPageById(result.id);
        setSelectedResult({
          ...result,
          content: page.content,
          content_length: page.content_length,
          content_truncated: page.content_truncated,
          summary: page.summary || result.summary,
          metadata: page.metadata || result.metadata,
        });
      } catch (error) {
        console.error('Error loading full result content:', error);
      }
    }
  };

  const handleBackToResults = () => {
    setSelectedResult(null);
  };

  // Clean URL by removing #chunk-X
  const getCleanUrl = (url: string) => {
    return url.split('#')[0];
  };

  // Add a function to find related chunks for a result
  const findRelatedChunks = (result: SearchResult): SearchResult[] => {
    if (!result.url || !results.length) return [];

    // Get base URL without chunk identifier
    const baseUrl = result.url.split('#')[0];

    // Find all results with the same base URL that are chunks
    return results.filter(r =>
      r.id !== result.id && // Not the current result
      r.url.startsWith(baseUrl) && // Same base URL
      r.is_chunk // Is a chunk
    ).sort((a, b) => {
      // Sort by chunk index if available
      if (a.chunk_index !== null && b.chunk_index !== null) {
        return a.chunk_index - b.chunk_index;
      }
      // Otherwise sort by similarity
      return b.similarity - a.similarity;
    });
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

  return (
    <div className="max-w-4xl mx-auto px-4">
      <PageHeader title="Semantic Search" subtitle="Vector and text search over crawled pages" backTo="/" />

      {selectedResult ? (
        <div>
          <div className="mb-4">
            <button onClick={handleBackToResults} className="btn-secondary px-4 py-2">
              ← Back to Results
            </button>
          </div>

          <div className="card p-6">
            <h2 className="text-2xl font-bold mb-2">{selectedResult.title || 'Untitled'}</h2>

            <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
              <a
                href={selectedResult.url}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:underline"
              >
                {selectedResult.url}
              </a>
            </p>

            <div className="flex flex-wrap gap-2 mb-4">
              <span className="text-sm bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded">
                {Math.round(selectedResult.similarity * 100)}% match
              </span>

              {selectedResult.is_chunk && (
                <span className="text-sm bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-1 rounded">
                  Chunk {selectedResult.chunk_index}
                  {selectedResult.parent_title && ` of ${selectedResult.parent_title}`}
                </span>
              )}

              {selectedResult.site_name && (
                <Link
                  to={`/sites/${selectedResult.site_id}`}
                  className="text-sm bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-1 rounded hover:bg-green-200 dark:hover:bg-green-900/50"
                >
                  {selectedResult.site_name}
                </Link>
              )}
            </div>

            {selectedResult.context && (
              <div className="bg-gray-100 dark:bg-gray-800 p-3 rounded mb-4">
                <p className="text-sm font-medium">Context:</p>
                <p className="text-sm">{selectedResult.context}</p>
              </div>
            )}

            <div className="border-t border-gray-200 dark:border-gray-700 pt-4 mt-4">
              <div className="flex justify-between items-center mb-2">
                <h3 className="text-lg font-medium">Content</h3>
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

              {(selectedResult.content || selectedResult.snippet) ? (
                <div className="max-h-[60vh] overflow-y-auto p-2 bg-gray-50 dark:bg-gray-800 rounded">
                  {contentViewMode === 'raw' ? (
                    <pre className="whitespace-pre-wrap text-sm font-mono">
                      {selectedResult.content || selectedResult.snippet || ''}
                    </pre>
                  ) : (
                    <div className="prose dark:prose-invert max-w-none">
                      {detectContentType(selectedResult.content || selectedResult.snippet) === 'html' ? (
                        <div dangerouslySetInnerHTML={{ __html: sanitizeHtml(selectedResult.content || selectedResult.snippet || '') }} />
                      ) : (
                        <ReactMarkdown>
                          {selectedResult.content || selectedResult.snippet || ''}
                        </ReactMarkdown>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-500 dark:text-gray-400">No content available</p>
              )}
            </div>

            {/* Related chunks section */}
            {selectedResult.is_chunk && (
              <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
                <h3 className="text-lg font-medium mb-3">Other Chunks from This Document</h3>
                <div className="space-y-2">
                  {findRelatedChunks(selectedResult).map(chunk => (
                    <div
                      key={chunk.id}
                      className="p-3 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                      onClick={() => handleViewResult(chunk)}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-medium">
                            Chunk {chunk.chunk_index}
                            {chunk.similarity && <span className="text-xs ml-2 text-gray-500">({Math.round(chunk.similarity * 100)}% match)</span>}
                          </p>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                            {chunk.snippet || chunk.content?.substring(0, 150) || 'No preview available'}...
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}

                  {findRelatedChunks(selectedResult).length === 0 && (
                    <p className="text-sm text-gray-500 dark:text-gray-400">No other chunks found for this document</p>
                  )}
                </div>
              </div>
            )}

            {!selectedResult.is_chunk && findRelatedChunks(selectedResult).length > 0 && (
              <div className="mt-6 border-t border-gray-200 dark:border-gray-700 pt-4">
                <h3 className="text-lg font-medium mb-3">Chunks from This Document</h3>
                <div className="space-y-2">
                  {findRelatedChunks(selectedResult).map(chunk => (
                    <div
                      key={chunk.id}
                      className="p-3 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                      onClick={() => handleViewResult(chunk)}
                    >
                      <div className="flex justify-between items-start">
                        <div>
                          <p className="font-medium">
                            Chunk {chunk.chunk_index}
                            {chunk.similarity && <span className="text-xs ml-2 text-gray-500">({Math.round(chunk.similarity * 100)}% match)</span>}
                          </p>
                          <p className="text-sm text-gray-600 dark:text-gray-400 mt-1 line-clamp-2">
                            {chunk.snippet || chunk.content?.substring(0, 150) || 'No preview available'}...
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      ) : (
        <>
          <form onSubmit={handleSearch} className="mb-8">
            <div className="flex flex-col gap-4">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search your crawled content..."
                  className="input flex-1"
                  disabled={isLoading}
                />
                <button
                  type="submit"
                  className="btn-primary px-6"
                  disabled={isLoading || !query.trim()}
                >
                  {isLoading ? 'Searching...' : 'Search'}
                </button>
              </div>

              <div className="flex flex-wrap gap-4">
                <div className="flex items-center">
                  <label htmlFor="threshold" className="mr-2 text-sm">Threshold:</label>
                  <select
                    id="threshold"
                    value={threshold}
                    onChange={(e) => setThreshold(parseFloat(e.target.value))}
                    className="input py-1 px-2 text-sm"
                    disabled={isLoading}
                  >
                    <option value="0.1">0.1 (More results)</option>
                    <option value="0.2">0.2</option>
                    <option value="0.3">0.3 (Default)</option>
                    <option value="0.4">0.4</option>
                    <option value="0.5">0.5 (Better quality)</option>
                    <option value="0.6">0.6</option>
                    <option value="0.7">0.7 (High precision)</option>
                  </select>
                </div>

                <div className="flex items-center">
                  <label htmlFor="limit" className="mr-2 text-sm">Results:</label>
                  <select
                    id="limit"
                    value={limit}
                    onChange={(e) => setLimit(parseInt(e.target.value))}
                    className="input py-1 px-2 text-sm"
                    disabled={isLoading}
                  >
                    <option value="5">5</option>
                    <option value="10">10 (Default)</option>
                    <option value="20">20</option>
                    <option value="50">50</option>
                    <option value="100">100</option>
                  </select>
                </div>

                <div className="flex items-center">
                  <label className="flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showDuplicates}
                      onChange={() => setShowDuplicates(!showDuplicates)}
                      className="sr-only"
                      disabled={isLoading}
                    />
                    <div className={`relative inline-block w-10 h-5 transition-colors duration-200 ease-in-out rounded-full ${showDuplicates ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}`}>
                      <span className={`absolute left-0.5 top-0.5 bg-white w-4 h-4 rounded-full transition-transform duration-200 ease-in-out ${showDuplicates ? 'transform translate-x-5' : ''}`}></span>
                    </div>
                    <span className="ml-2 text-sm">Show duplicates</span>
                  </label>
                </div>
              </div>
            </div>
          </form>

          {isLoading ? (
            <div className="text-center py-12">
              <div className="inline-block animate-spin text-4xl">↻</div>
              <p className="mt-4 text-gray-600 dark:text-gray-400">Searching...</p>
            </div>
          ) : hasSearched ? (
            results.length > 0 ? (
              <div className="space-y-6">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Found {results.length} results
                </p>
                {results.map((result) => (
                  <div key={result.id} className="card p-6 hover:shadow-md transition-shadow duration-200">
                    <div className="flex justify-between items-start mb-2">
                      <h2 className="text-lg font-semibold">
                        <span
                          dangerouslySetInnerHTML={{
                            __html: sanitizeHtml(highlightQuery(result.title || 'Untitled')),
                          }}
                        />
                      </h2>
                      <span className="text-sm bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 px-2 py-1 rounded">
                        {Math.round(result.similarity * 100)}% match
                      </span>
                    </div>

                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                      {result.site_name && (
                        <Link
                          to={`/sites/${result.site_id}`}
                          className="hover:underline text-blue-600 dark:text-blue-400"
                        >
                          {result.site_name}
                        </Link>
                      )}
                      {' • '}
                      <a
                        href={getCleanUrl(result.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:underline"
                      >
                        {new URL(result.url).hostname}
                      </a>
                    </p>

                    <div className="text-sm mb-4">
                      <span
                        dangerouslySetInnerHTML={{
                          __html: sanitizeHtml(highlightQuery((result.snippet || result.content || '').substring(0, 300) + '...')),
                        }}
                      />
                    </div>

                    {result.context && (
                      <div className="text-xs bg-gray-100 dark:bg-gray-800 p-2 rounded mb-2">
                        {result.context}
                      </div>
                    )}

                    <div className="flex justify-between items-center">
                      <button
                        onClick={() => handleViewResult(result)}
                        className="text-blue-600 dark:text-blue-400 hover:underline"
                      >
                        View Full Content
                      </button>

                      {result.is_chunk && (
                        <span className="text-xs bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 px-2 py-1 rounded">
                          Chunk {result.chunk_index}
                          {result.parent_title && ` of ${result.parent_title}`}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <p className="text-xl font-medium mb-2">No results found</p>
                <p className="text-gray-600 dark:text-gray-400">
                  Try a different search term, lower the threshold, or crawl more content
                </p>
              </div>
            )
          ) : (
            <div className="card p-6">
              <h2 className="text-xl font-semibold mb-4">Search Instructions</h2>
              <p className="mb-4">
                Use semantic search to find content in your crawled websites. Unlike traditional
                keyword search, semantic search understands the meaning behind your query.
              </p>
              <ul className="list-disc list-inside space-y-2 text-sm">
                <li>Enter natural language queries like "What is machine learning?"</li>
                <li>Results are ranked by semantic similarity to your query</li>
                <li>Adjust the threshold to control result quality (lower = more results)</li>
                <li>Toggle "Show duplicates" to see all matching chunks</li>
                <li>Click on site names to view all pages from that site</li>
                <li>Click "View Full Content" to see the complete result</li>
              </ul>

              <div className="bg-blue-50 dark:bg-blue-900/20 p-4 rounded-lg mt-6">
                <h3 className="text-sm font-medium text-blue-800 dark:text-blue-300">Tips for Better Results</h3>
                <ul className="list-disc list-inside space-y-1 text-xs text-blue-700 dark:text-blue-400 mt-2">
                  <li>Be specific in your queries</li>
                  <li>Use complete sentences for better semantic matching</li>
                  <li>Try different phrasings if you don't get the results you expect</li>
                  <li>Lower the threshold to find more results</li>
                  <li>Crawl more content to improve search coverage</li>
                </ul>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default SearchPage;
