"""
Script to test the crawl4ai API.
"""

import os
import sys
import json
import requests
from dotenv import load_dotenv

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawl_client import _crawl4ai_request_headers

# Load environment variables
load_dotenv()

def test_crawl_api():
    """Test the connection to the crawl4ai API."""
    base_url = os.getenv("CRAWL4AI_URL") or os.getenv("CRAWL4AI_BASE_URL")
    timeout = float(os.getenv("CRAWL4AI_HTTP_TIMEOUT", "60"))
    if not base_url:
        print("Error: CRAWL4AI_URL/CRAWL4AI_BASE_URL not found in environment variables.")
        return
    try:
        headers = _crawl4ai_request_headers()
    except ValueError as e:
        print(f"Error: {e}")
        return

    # Test the health endpoint
    try:
        print(f"Testing health endpoint: {base_url}/health")
        health_response = requests.get(f"{base_url}/health", headers=headers, timeout=timeout)

        if health_response.status_code == 200:
            print("Health check successful!")
            print(f"Response: {health_response.json()}")
        else:
            print(f"Health check failed with status code: {health_response.status_code}")
            print(f"Response: {health_response.text}")
    except Exception as e:
        print(f"Error checking health endpoint: {e}")

    # Test a simple crawl
    try:
        print(f"\nTesting crawl endpoint: {base_url}/crawl")

        payload = {
            "urls": "https://example.com",
            "priority": 10
        }

        crawl_response = requests.post(
            f"{base_url}/crawl",
            headers=headers,
            json=payload,
            timeout=timeout,
        )

        if crawl_response.status_code == 200:
            print("Crawl request successful!")
            response_data = crawl_response.json()
            print(f"Task ID: {response_data.get('task_id')}")

            # Check task status
            task_id = response_data.get('task_id')
            if task_id:
                print(f"\nChecking task status: {base_url}/task/{task_id}")

                status_response = requests.get(
                    f"{base_url}/task/{task_id}",
                    headers=headers,
                    timeout=timeout,
                )

                if status_response.status_code == 200:
                    print("Task status check successful!")
                    print(f"Status: {status_response.json().get('status')}")
                else:
                    print(f"Task status check failed with status code: {status_response.status_code}")
                    print(f"Response: {status_response.text}")
        else:
            print(f"Crawl request failed with status code: {crawl_response.status_code}")
            print(f"Response: {crawl_response.text}")
    except Exception as e:
        print(f"Error testing crawl endpoint: {e}")

if __name__ == "__main__":
    test_crawl_api()
