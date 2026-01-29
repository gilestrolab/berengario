"""
Web search tools for RAG agent.

Provides web search capability using DuckDuckGo for retrieving current information
not available in the knowledge base.
"""

import logging
from typing import Any, Dict

from src.config import settings

from .base import ParameterType, Tool, ToolParameter, register_tool

logger = logging.getLogger(__name__)


def web_search(query: str, num_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for current information using DuckDuckGo.

    Args:
        query: The search query string
        num_results: Maximum number of results to return (default: 5)

    Returns:
        Dictionary containing:
            - success: Boolean indicating success
            - results: List of search results with title, url, snippet
            - query: The original query
            - num_results: Number of results returned
            - error: Error message (if failed)
    """
    try:
        from duckduckgo_search import DDGS

        # Validate parameters
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        if num_results < 1 or num_results > settings.web_search_max_results:
            num_results = min(max(1, num_results), settings.web_search_max_results)
            logger.warning(
                f"Adjusted num_results to {num_results} (valid range: 1-{settings.web_search_max_results})"
            )

        logger.info(f"Performing web search: '{query}' (max results: {num_results})")

        # Perform search
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(query, max_results=num_results))

        # Format results
        results = []
        for r in raw_results:
            results.append(
                {
                    "title": r.get("title", "No title"),
                    "url": r.get("link", r.get("href", "")),
                    "snippet": r.get("body", r.get("description", "")),
                }
            )

        logger.info(f"Web search returned {len(results)} results")

        return {
            "success": True,
            "results": results,
            "query": query,
            "num_results": len(results),
        }

    except ImportError:
        error_msg = "duckduckgo-search library not installed. Install with: pip install duckduckgo-search"
        logger.error(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "results": [],
            "query": query,
            "num_results": 0,
        }
    except Exception as e:
        error_msg = f"Web search failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "results": [],
            "query": query,
            "num_results": 0,
        }


# Tool definition
web_search_tool = Tool(
    name="web_search",
    description="Search the internet for current information not available in the knowledge base. Use this when the knowledge base doesn't contain relevant information or when current/recent information is needed (e.g., news, current events, recent updates).",
    parameters=[
        ToolParameter(
            name="query",
            type=ParameterType.STRING,
            description="The search query. Be specific and include relevant keywords.",
            required=True,
        ),
        ToolParameter(
            name="num_results",
            type=ParameterType.INTEGER,
            description=f"Maximum number of results to return (default: 5, max: {settings.web_search_max_results if hasattr(settings, 'web_search_max_results') else 10})",
            required=False,
        ),
    ],
    function=web_search,
    returns_attachment=False,
)

# Register tool
register_tool(web_search_tool)
