#!/usr/bin/env python
"""
Script to run the Supa-Crawl-Chat API server.
"""

import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from app_logging import configure_logging

configure_logging()

if __name__ == "__main__":
    # Get port from environment variable or use default
    port = int(os.getenv("API_PORT", "8001"))
    
    # Run the API server
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
    
    print(f"API server running at http://localhost:{port}")
    print(f"API documentation available at http://localhost:{port}/docs") 