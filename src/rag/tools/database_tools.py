"""
Database query tools for RAG agent.

Provides access to conversation history and analytics for the agent to answer
meta-questions about system usage, conversation patterns, etc.
"""

import logging
from typing import Any, Dict, Optional

from .base import ParameterType, Tool, ToolParameter, register_tool
from .context import get_conversation_manager

logger = logging.getLogger(__name__)


def _get_conv_manager():
    """Get conversation manager from tool context, falling back to global default."""
    mgr = get_conversation_manager()
    if mgr is not None:
        return mgr
    from src.email.conversation_manager import ConversationManager

    return ConversationManager()


def query_conversation_history(
    sender: Optional[str] = None, days: int = 30, limit: int = 10
) -> Dict[str, Any]:
    """
    Query conversation history for a specific user or overall.

    Args:
        sender: Email address of sender (optional, None for overall stats)
        days: Number of days to look back (default: 30)
        limit: Maximum number of conversations to return (default: 10)

    Returns:
        Dictionary containing:
            - success: Boolean indicating success
            - conversations: List of conversation data
            - sender: The queried sender (if specified)
            - days: Time range queried
            - total_count: Total number of conversations
            - error: Error message (if failed)
    """
    try:
        conv_mgr = _get_conv_manager()

        # Validate parameters
        if days < 1:
            days = 30
            logger.warning("Adjusted days to 30 (minimum: 1)")

        if limit < 1:
            limit = 10
            logger.warning("Adjusted limit to 10 (minimum: 1)")

        logger.info(
            f"Querying conversation history: sender={sender}, days={days}, limit={limit}"
        )

        # Query based on sender
        if sender:
            # Get recent queries from specific user
            conversations = conv_mgr.get_user_queries(sender, days=days, limit=limit)
            summary = {
                "sender": sender,
                "num_conversations": len(conversations),
                "time_range_days": days,
            }
        else:
            # Get overall usage analytics
            analytics = conv_mgr.get_usage_analytics(days=days)
            conversations = []
            summary = {
                "total_queries": analytics.get("total_queries", 0),
                "unique_senders": analytics.get("unique_senders", 0),
                "time_range_days": days,
            }

        return {
            "success": True,
            "conversations": conversations[:limit],
            "summary": summary,
            "total_count": len(conversations),
        }

    except Exception as e:
        error_msg = f"Failed to query conversation history: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "conversations": [],
            "total_count": 0,
        }


def query_analytics(metric: str = "usage", days: int = 7) -> Dict[str, Any]:
    """
    Query system analytics (usage, optimization, sources).

    Args:
        metric: Type of analytics ('usage', 'optimization', or 'sources')
        days: Number of days to look back (default: 7)

    Returns:
        Dictionary containing:
            - success: Boolean indicating success
            - metric: The metric type queried
            - data: Analytics data
            - days: Time range queried
            - error: Error message (if failed)
    """
    try:
        conv_mgr = _get_conv_manager()

        # Validate parameters
        if days < 1:
            days = 7
            logger.warning("Adjusted days to 7 (minimum: 1)")

        valid_metrics = ["usage", "optimization", "sources"]
        if metric not in valid_metrics:
            raise ValueError(
                f"Invalid metric '{metric}'. Must be one of: {', '.join(valid_metrics)}"
            )

        logger.info(f"Querying {metric} analytics for last {days} days")

        # Get analytics based on metric type
        if metric == "usage":
            data = conv_mgr.get_usage_analytics(days=days)
        elif metric == "optimization":
            data = conv_mgr.get_optimization_analytics(days=days)
        elif metric == "sources":
            data = conv_mgr.get_source_analytics(days=days)
        else:
            raise ValueError(f"Unknown metric: {metric}")

        return {
            "success": True,
            "metric": metric,
            "data": data,
            "days": days,
        }

    except Exception as e:
        error_msg = f"Failed to query analytics: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "metric": metric,
            "data": {},
            "days": days,
        }


# Tool definitions
query_conversation_history_tool = Tool(
    name="db_query_conversations",
    description="Query conversation history for a specific user or get overall usage statistics. Use this to answer questions about past conversations, user activity, or interaction patterns.",
    parameters=[
        ToolParameter(
            name="sender",
            type=ParameterType.STRING,
            description="Email address of sender to query (optional, omit for overall stats)",
            required=False,
        ),
        ToolParameter(
            name="days",
            type=ParameterType.INTEGER,
            description="Number of days to look back (default: 30)",
            required=False,
        ),
        ToolParameter(
            name="limit",
            type=ParameterType.INTEGER,
            description="Maximum number of conversations to return (default: 10)",
            required=False,
        ),
    ],
    function=query_conversation_history,
    returns_attachment=False,
)

query_analytics_tool = Tool(
    name="query_analytics",
    description="Query system analytics including usage statistics, query optimization metrics, or source document usage. Use this to answer questions about system performance, optimization effectiveness, or which documents are most frequently cited.",
    parameters=[
        ToolParameter(
            name="metric",
            type=ParameterType.STRING,
            description="Type of analytics: 'usage' (user activity), 'optimization' (query optimization stats), or 'sources' (document citation stats). Default: 'usage'",
            required=False,
        ),
        ToolParameter(
            name="days",
            type=ParameterType.INTEGER,
            description="Number of days to look back (default: 7)",
            required=False,
        ),
    ],
    function=query_analytics,
    returns_attachment=False,
)

# Register tools
register_tool(query_conversation_history_tool)
register_tool(query_analytics_tool)
