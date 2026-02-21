"""
Web Search Utilities
Handles web search functionality using various APIs.
"""

import logging

import requests
from config.settings import Settings

logger = logging.getLogger(__name__)


class BraveSearch:
    """Web search using Brave Search API."""

    def __init__(self, api_key=None):
        """Initialize Brave Search with API key."""
        self.api_key = api_key or Settings.BRAVE_API_KEY
        if not self.api_key:
            raise ValueError("Brave API key not configured")

    def search(self, query, num_results=5, freshness="pd"):
        """
        Search the web using Brave Search API.

        Args:
            query: Search query string
            num_results: Number of results to return (default: 5)
            freshness: Time filter - "pd" (past day), "pw" (past week), etc.

        Returns:
            List of search results with title, snippet, url, and age
        """
        logger.info("Searching: %s", query)

        try:
            url = "https://api.search.brave.com/res/v1/web/search"
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }
            params = {
                "q": query,
                "count": num_results,
                "freshness": freshness
            }

            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()

            # Format results
            results = []
            for item in data.get("web", {}).get("results", [])[:num_results]:
                results.append({
                    "title": item.get("title"),
                    "snippet": item.get("description"),
                    "url": item.get("url"),
                    "age": item.get("age", "")
                })

            logger.info("Found %d results", len(results))
            return results

        except Exception as e:
            logger.error("Search error: %s", e)
            return []
