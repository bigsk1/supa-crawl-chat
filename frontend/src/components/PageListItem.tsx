import React, { useState } from 'react';
import { Page } from '@/api/apiService';
import DateDebugger from './DateDebugger';

interface PageListItemProps {
  page: Page;
  selectedPageId: number | null;
  pageChunks: Page[];
  onPageClick: (page: Page) => void;
  isExpanded: boolean;
  onToggleExpand: (pageId: number) => void;
  showDebug?: boolean;
  /** Re-fetch this page URL only (omit while a crawl is already in progress). */
  onRecrawlPage?: (page: Page) => void;
  /** Remove this page (and its chunks) from the index. */
  onDeletePage?: (page: Page) => void;
}

const PageListItem: React.FC<PageListItemProps> = ({
  page,
  selectedPageId,
  pageChunks,
  onPageClick,
  isExpanded,
  onToggleExpand,
  showDebug = false,
  onRecrawlPage,
  onDeletePage,
}) => {
  const hasChunks = pageChunks.length > 0;
  
  // Format dates properly with fallback display
  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return null;
    
    try {
      const date = new Date(dateString);
      // Check if date is valid
      if (isNaN(date.getTime())) return null;
      return date.toLocaleDateString();
    } catch (error) {
      console.error('Error formatting date:', error);
      return null;
    }
  };
  
  const createdDate = formatDate(page.created_at);
  const updatedDate = formatDate(page.updated_at);
  
  // Debug date information
  console.log(`Page ${page.id} dates:`, { 
    raw_created: page.created_at,
    raw_updated: page.updated_at,
    formatted_created: createdDate,
    formatted_updated: updatedDate
  });

  return (
    <div className="mb-3">
      {showDebug && (
        <div className="mb-2 p-2 bg-gray-100 dark:bg-gray-800 rounded">
          <h3 className="font-bold text-sm mb-2">Debug Info for Page {page.id}</h3>
          <DateDebugger dateString={page.created_at} label="Created Date" />
          <DateDebugger dateString={page.updated_at} label="Updated Date" />
          <div className="mt-2">
            <pre className="text-xs overflow-auto max-h-40">
              {JSON.stringify(page, null, 2)}
            </pre>
          </div>
        </div>
      )}
      
      <div
        className={`p-4 rounded-md transition-colors duration-150 ${
          selectedPageId === page.id
            ? 'bg-blue-100 dark:bg-blue-900'
            : 'bg-white dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700'
        }`}
      >
        <div className="flex justify-between items-start gap-3">
          <div
            className="flex-1 cursor-pointer min-w-0"
            onClick={() => onPageClick(page)}
          >
            <div className="font-medium text-lg mb-1">{page.title || 'Untitled Page'}</div>
            <div className="text-sm text-gray-500 dark:text-gray-400 break-all mb-2">
              {page.url}
            </div>
            {page.summary && (
              <div className="text-sm text-gray-600 dark:text-gray-400 mb-2 break-words">
                {page.summary}
              </div>
            )}
            <div className="flex flex-wrap items-center text-xs text-gray-500 dark:text-gray-400">
              {createdDate && (
                <span className="mr-3 mb-1">
                  Created: {createdDate}
                </span>
              )}
              {updatedDate && (
                <span className="mb-1 mr-3">
                  Updated: {updatedDate}
                </span>
              )}
              {!createdDate && !updatedDate && (
                <span className="mb-1 mr-3">No date information available</span>
              )}
              {hasChunks && (
                <span 
                  className="mb-1 flex items-center text-blue-600 dark:text-blue-400 cursor-pointer"
                  onClick={(e) => {
                    e.stopPropagation();
                    onToggleExpand(page.id);
                  }}
                >
                  <svg 
                    xmlns="http://www.w3.org/2000/svg" 
                    className={`h-4 w-4 mr-1 transition-transform ${isExpanded ? 'transform rotate-180' : ''}`} 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                  {pageChunks.length} chunk{pageChunks.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
          {(onRecrawlPage || onDeletePage) && (
            <div
              className="flex flex-shrink-0 flex-col sm:flex-row gap-1"
              onClick={e => e.stopPropagation()}
            >
              {onRecrawlPage && (
                <button
                  type="button"
                  title="Re-fetch this URL only (POST /api/crawl/refresh/…/pages/…)"
                  onClick={() => onRecrawlPage(page)}
                  className="text-xs px-2 py-1 rounded-md bg-emerald-100 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200 hover:bg-emerald-200 dark:hover:bg-emerald-800/50 whitespace-nowrap"
                >
                  Recrawl page
                </button>
              )}
              {onDeletePage && (
                <button
                  type="button"
                  title="Remove this page from the index"
                  onClick={() => onDeletePage(page)}
                  className="text-xs px-2 py-1 rounded-md bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 hover:bg-red-100 dark:hover:bg-red-900/50 whitespace-nowrap"
                >
                  Delete
                </button>
              )}
            </div>
          )}
        </div>
      </div>
      
      {/* Expandable chunks section */}
      {isExpanded && hasChunks && (
        <div className="ml-6 mt-2 space-y-2 border-l-2 border-blue-200 dark:border-blue-800 pl-3">
          {pageChunks
            .sort((a, b) => {
              const aIndex = a.chunk_index ?? 0;
              const bIndex = b.chunk_index ?? 0;
              return aIndex - bIndex;
            })
            .map(chunk => (
              <div
                key={chunk.id}
                className="p-3 rounded-md bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 cursor-pointer"
                onClick={() => onPageClick(chunk)}
              >
                <div className="flex items-center mb-1">
                  <span className="text-xs px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded-full mr-2">
                    Chunk {chunk.chunk_index !== null && chunk.chunk_index !== undefined ? chunk.chunk_index : ''}
                  </span>
                  <div className="text-sm font-medium">{chunk.title || 'Untitled Chunk'}</div>
                </div>
                {chunk.summary && (
                  <div className="text-xs text-gray-600 dark:text-gray-400 mt-1 ml-8 break-words">
                    {chunk.summary}
                  </div>
                )}
              </div>
            ))
          }
        </div>
      )}
    </div>
  );
};

export default PageListItem; 