from fastapi import APIRouter, Query, HTTPException, status, Path, Depends
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Import from main project
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_client import SupabaseClient

# Create a function to get the db client
def get_db_client():
    return SupabaseClient()

# Create router
router = APIRouter(
    tags=["pages"],
)

# Define models
class Page(BaseModel):
    id: int
    site_id: int
    url: str
    title: Optional[str] = None
    content: Optional[str] = None
    content_length: Optional[int] = None
    content_truncated: Optional[bool] = None
    summary: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    is_chunk: bool = False
    chunk_index: Optional[int] = None
    parent_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    
    class Config:
        arbitrary_types_allowed = True
        
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

class PageDetail(Page):
    site_name: Optional[str] = None

class ChunkList(BaseModel):
    chunks: List[Page]
    count: int
    parent_id: int

@router.post("/maintenance/deduplicate", response_model=Dict[str, int])
async def deduplicate_chunks(db_client: SupabaseClient = Depends(get_db_client)):
    """
    Remove exact duplicate chunks and disable parent-page embeddings where chunks exist.
    """
    try:
        return db_client.cleanup_duplicate_chunks()
    except Exception as e:
        print(f"Error in deduplicate_chunks: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/{page_id}", response_model=Optional[Page])
async def get_page_by_id(
    page_id: int,
    content_chars: int = Query(20000, ge=0, le=200000, description="Maximum content characters to return"),
    full: bool = Query(False, description="Return full page content"),
    db_client: SupabaseClient = Depends(get_db_client),
):
    """
    Get a page by ID.
    """
    print(f"Fetching page with ID: {page_id}")
    try:
        page = db_client.get_page_by_id(page_id)
        print(f"Page result: {page}")
        if not page:
            raise HTTPException(status_code=404, detail=f"Page with ID {page_id} not found")
        content = page.get("content")
        if content is not None:
            page["content_length"] = len(content)
            if not full and len(content) > content_chars:
                page["content"] = content[:content_chars]
                page["content_truncated"] = True
            else:
                page["content_truncated"] = False
        return page
    except Exception as e:
        print(f"Error in get_page_by_id: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@router.get("/{page_id}/chunks", response_model=List[Page])
async def get_chunks_by_parent_id(page_id: int, db_client: SupabaseClient = Depends(get_db_client)):
    """
    Get all chunks for a specific parent page.
    """
    print(f"Fetching chunks for parent ID: {page_id}")
    try:
        chunks = db_client.get_chunks_by_parent_id(page_id)
        print(f"Chunks result: {chunks}")
        return chunks
    except Exception as e:
        print(f"Error in get_chunks_by_parent_id: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
