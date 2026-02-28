"""
Analytics routes for query optimization, source usage, and topic clustering.

Requires admin privileges for all endpoints.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from src.api.models import (
    FeedbackAnalyticsResponse,
    TopicClusteringResponse,
    UsageAnalyticsResponse,
    UserQueriesResponse,
)
from src.email.db_models import ConversationMessage, MessageType, ResponseFeedback

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/admin", tags=["analytics"])


def create_analytics_router(
    conversation_manager,
    query_handler,
    require_admin,
    component_resolver=None,
):
    """
    Create analytics router with dependency injection.

    Args:
        conversation_manager: ConversationManager instance
        query_handler: QueryHandler instance (for topic clustering)
        require_admin: Admin authentication dependency
        component_resolver: ComponentResolver for MT mode (optional)

    Returns:
        Configured APIRouter
    """

    def _get_cm(session):
        """Get the conversation manager for this session (MT-aware)."""
        if component_resolver:
            return component_resolver.resolve(session).conversation_manager
        return conversation_manager

    def _get_qh(session):
        """Get the query handler for this session (MT-aware)."""
        if component_resolver:
            return component_resolver.resolve(session).query_handler
        return query_handler

    # ============================================================================
    # Usage Analytics
    # ============================================================================

    @router.get("/usage/analytics", response_model=UsageAnalyticsResponse)
    async def get_usage_analytics(
        days: Optional[int] = None,
        session=Depends(require_admin),
    ):
        """
        Get comprehensive usage analytics.

        Requires admin privileges.

        Args:
            days: Number of days to look back (7, 30, 90, or None for all)
            session: Admin session (injected by dependency)

        Returns:
            UsageAnalyticsResponse with comprehensive analytics

        Raises:
            HTTPException: If query fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested usage analytics (days={days})"
            )

            analytics = _get_cm(session).get_usage_analytics(days=days)

            return UsageAnalyticsResponse(**analytics)

        except Exception as e:
            logger.error(f"Error getting usage analytics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error getting usage analytics: {str(e)}"
            )

    @router.get("/usage/user/{sender}", response_model=UserQueriesResponse)
    async def get_user_queries(
        sender: str,
        days: Optional[int] = None,
        limit: Optional[int] = 100,
        session=Depends(require_admin),
    ):
        """
        Get detailed query list for a specific user.

        Requires admin privileges.

        Args:
            sender: User identifier (email)
            days: Number of days to look back (None = all)
            limit: Maximum number of queries to return
            session: Admin session (injected by dependency)

        Returns:
            UserQueriesResponse with query details

        Raises:
            HTTPException: If query fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested queries for user {sender} (days={days}, limit={limit})"
            )

            queries = _get_cm(session).get_user_queries(
                sender=sender, days=days, limit=limit
            )

            return UserQueriesResponse(
                sender=sender, queries=queries, total_count=len(queries)
            )

        except Exception as e:
            logger.error(f"Error getting user queries: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error getting user queries: {str(e)}"
            )

    # ============================================================================
    # Query Optimization Analytics
    # ============================================================================

    @router.get("/analytics/optimization")
    async def get_optimization_analytics(
        days: Optional[int] = None,
        session=Depends(require_admin),
    ):
        """
        Get query optimization analytics.

        Requires admin privileges.

        Args:
            days: Number of days to look back (None for all time)
            session: Admin session (injected by dependency)

        Returns:
            Dictionary with optimization statistics

        Raises:
            HTTPException: If query fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested optimization analytics (days={days})"
            )

            analytics = _get_cm(session).get_optimization_analytics(days=days)

            # Transform data to match frontend expectations
            return {
                "total_queries": analytics["total_queries"],
                "optimized_count": analytics["optimized_queries"],
                "optimization_rate": analytics["optimization_rate"],
                "avg_query_expansion": (analytics["avg_expansion_ratio"] - 1.0)
                * 100,  # Convert ratio to percentage
                "sample_optimizations": [
                    {
                        "original_query": s["original"],
                        "optimized_query": s["optimized"],
                        "timestamp": s.get("timestamp"),
                    }
                    for s in analytics["sample_optimizations"]
                ],
            }

        except Exception as e:
            logger.error(f"Error getting optimization analytics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error getting optimization analytics: {str(e)}",
            )

    # ============================================================================
    # Source Document Analytics
    # ============================================================================

    @router.get("/analytics/sources")
    async def get_source_analytics(
        days: Optional[int] = None,
        session=Depends(require_admin),
    ):
        """
        Get source document usage analytics.

        Requires admin privileges.

        Args:
            days: Number of days to look back (None for all time)
            session: Admin session (injected by dependency)

        Returns:
            Dictionary with source usage statistics

        Raises:
            HTTPException: If query fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested source analytics (days={days})"
            )

            analytics = _get_cm(session).get_source_analytics(days=days)

            # Transform data to match frontend expectations
            return {
                "total_replies": analytics["total_replies"],
                "replies_with_sources": analytics["total_replies_with_sources"],
                "avg_sources_per_reply": analytics["avg_sources_per_reply"],
                "avg_relevance_score": analytics["avg_relevance_score"],
                "top_sources": analytics["most_cited_documents"],
            }

        except Exception as e:
            logger.error(f"Error getting source analytics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error getting source analytics: {str(e)}"
            )

    # ============================================================================
    # Feedback Analytics
    # ============================================================================

    @router.get("/feedback/analytics", response_model=FeedbackAnalyticsResponse)
    async def get_feedback_analytics(
        days: Optional[int] = None,
        session=Depends(require_admin),
    ):
        """
        Get comprehensive feedback analytics.

        Requires admin privileges.

        Args:
            days: Number of days to look back (7, 30, 90, or None for all)
            session: Admin session (injected by dependency)

        Returns:
            FeedbackAnalyticsResponse with overview stats and negative responses

        Raises:
            HTTPException: If query fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested feedback analytics (days={days})"
            )

            # Determine date range
            start_date = None
            if days:
                start_date = datetime.utcnow() - timedelta(days=days)

            with _get_cm(session).db_manager.get_session() as db_session:
                # Base query
                query = db_session.query(ResponseFeedback)

                if start_date:
                    query = query.filter(ResponseFeedback.submitted_at >= start_date)

                # Get all feedback
                all_feedback = query.all()

                # Calculate overview stats
                total_feedback = len(all_feedback)
                positive_count = sum(1 for f in all_feedback if f.is_positive)
                negative_count = total_feedback - positive_count
                positive_rate = (
                    (positive_count / total_feedback * 100) if total_feedback > 0 else 0
                )

                overview = {
                    "total_feedback": total_feedback,
                    "positive_count": positive_count,
                    "negative_count": negative_count,
                    "positive_rate": round(positive_rate, 1),
                }

                # Get negative responses with details
                negative_query = (
                    db_session.query(ResponseFeedback, ConversationMessage)
                    .join(
                        ConversationMessage,
                        ResponseFeedback.message_id == ConversationMessage.id,
                    )
                    .filter(ResponseFeedback.is_positive.is_(False))
                )

                if start_date:
                    negative_query = negative_query.filter(
                        ResponseFeedback.submitted_at >= start_date
                    )

                negative_query = negative_query.order_by(
                    ResponseFeedback.submitted_at.desc()
                )

                negative_responses = []
                for feedback, message in negative_query.all():
                    negative_responses.append(
                        {
                            "id": feedback.id,
                            "message_id": feedback.message_id,
                            "response_content": (
                                message.content[:200] + "..."
                                if len(message.content) > 200
                                else message.content
                            ),
                            "comment": feedback.comment,
                            "user_email": feedback.user_email,
                            "channel": (
                                feedback.channel.value
                                if hasattr(feedback.channel, "value")
                                else feedback.channel
                            ),
                            "submitted_at": feedback.submitted_at.isoformat(),
                        }
                    )

                # Date range
                if start_date:
                    date_range = {
                        "start": start_date.date().isoformat(),
                        "end": datetime.utcnow().date().isoformat(),
                    }
                else:
                    if all_feedback:
                        earliest = min(f.submitted_at for f in all_feedback)
                        date_range = {
                            "start": earliest.date().isoformat(),
                            "end": datetime.utcnow().date().isoformat(),
                        }
                    else:
                        date_range = {
                            "start": "N/A",
                            "end": "N/A",
                        }

            return FeedbackAnalyticsResponse(
                date_range=date_range,
                overview=overview,
                negative_responses=negative_responses,
            )

        except Exception as e:
            logger.error(f"Error getting feedback analytics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error getting feedback analytics: {str(e)}"
            )

    # ============================================================================
    # Topic Clustering
    # ============================================================================

    @router.post("/usage/topics", response_model=TopicClusteringResponse)
    async def cluster_query_topics(
        days: Optional[int] = 30,
        session=Depends(require_admin),
    ):
        """
        Analyze and cluster query topics using LLM.

        Requires admin privileges.

        Args:
            days: Number of days to analyze (default: 30)
            session: Admin session (injected by dependency)

        Returns:
            TopicClusteringResponse with topic analysis

        Raises:
            HTTPException: If analysis fails
        """
        try:
            logger.info(
                f"Admin {session.email} requested topic clustering (days={days})"
            )

            # Get all queries for the period
            analytics = _get_cm(session).get_usage_analytics(days=days)
            total_queries = analytics["overview"]["total_queries"]

            if total_queries == 0:
                return TopicClusteringResponse(
                    topics=[],
                    total_queries=0,
                    clustered_queries=0,
                )

            # Get all query content
            cm = _get_cm(session)

            with cm.db_manager.get_session() as db_session:
                # Calculate start date
                start_date = (
                    datetime.utcnow() - timedelta(days=days)
                    if days
                    else datetime(1970, 1, 1)
                )

                queries = (
                    db_session.query(ConversationMessage)
                    .filter(
                        ConversationMessage.message_type == MessageType.QUERY,
                        ConversationMessage.timestamp >= start_date,
                    )
                    .all()
                )

                query_texts = [q.content for q in queries]

            # Use LLM to cluster topics
            from src.rag.topic_clustering import cluster_topics

            topics = cluster_topics(query_texts, _get_qh(session).rag_engine)

            return TopicClusteringResponse(
                topics=topics,
                total_queries=total_queries,
                clustered_queries=len(query_texts),
            )

        except Exception as e:
            logger.error(f"Error clustering topics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500, detail=f"Error clustering topics: {str(e)}"
            )

    return router
