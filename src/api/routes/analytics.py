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
from src.api.routes.helpers import resolve_component
from src.email.db_models import ConversationMessage, MessageType, ResponseFeedback

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/admin", tags=["analytics"])


def _compute_health_score(structural: dict, retrieval: dict) -> dict:
    """
    Compute a composite KB health score (0-100) from structural and retrieval data.

    Four equally-weighted factors (25 points each):
    - has_documents: 25 if KB has any documents, else 0
    - freshness: scaled by ratio of non-stale docs
    - citation_coverage: scaled by coverage percentage
    - relevance_quality: scaled inversely by low-relevance rate

    Args:
        structural: Output of KBManager.get_kb_health_metrics()
        retrieval: Output of ConversationManager.get_retrieval_health_metrics()

    Returns:
        Dictionary with total score and per-factor breakdown.
    """
    total_docs = structural.get("total_documents", 0)

    # Factor 1: Has documents (binary)
    has_docs_score = 25.0 if total_docs > 0 else 0.0

    # Factor 2: Freshness (ratio of non-stale docs)
    stale_count = structural.get("stale_count", 0)
    if total_docs > 0:
        non_stale_ratio = (total_docs - stale_count) / total_docs
        freshness_score = round(25.0 * non_stale_ratio, 1)
    else:
        freshness_score = 0.0

    # Factor 3: Citation coverage
    coverage_pct = retrieval.get("citation_coverage_pct", 0)
    citation_score = round(25.0 * coverage_pct / 100, 1)

    # Factor 4: Relevance quality (inverse of low-relevance rate)
    low_rel_rate = retrieval.get("low_relevance_rate", 0)
    relevance_score = round(25.0 * (1 - low_rel_rate / 100), 1)

    total = round(has_docs_score + freshness_score + citation_score + relevance_score)

    return {
        "total": total,
        "factors": {
            "has_documents": {"score": has_docs_score, "max": 25},
            "freshness": {"score": freshness_score, "max": 25},
            "citation_coverage": {"score": citation_score, "max": 25},
            "relevance_quality": {"score": relevance_score, "max": 25},
        },
    }


def create_analytics_router(
    conversation_manager,
    query_handler,
    require_admin,
    component_resolver=None,
    kb_manager=None,
    app_settings=None,
):
    """
    Create analytics router with dependency injection.

    Args:
        conversation_manager: ConversationManager instance
        query_handler: QueryHandler instance (for topic clustering)
        require_admin: Admin authentication dependency
        component_resolver: ComponentResolver for MT mode (optional)
        kb_manager: KnowledgeBaseManager instance (for KB health metrics)
        app_settings: Application settings (for similarity threshold)

    Returns:
        Configured APIRouter
    """

    def _get_cm(session):
        return resolve_component(
            component_resolver, session, "conversation_manager", conversation_manager
        )

    def _get_qh(session):
        return resolve_component(
            component_resolver, session, "query_handler", query_handler
        )

    def _get_km(session):
        return resolve_component(component_resolver, session, "kb_manager", kb_manager)

    # ============================================================================
    # Usage Analytics
    # ============================================================================

    @router.get("/usage/analytics", response_model=UsageAnalyticsResponse)
    def get_usage_analytics(
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
    def get_user_queries(
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
    def get_optimization_analytics(
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
    def get_source_analytics(
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
    def get_feedback_analytics(
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
    def cluster_query_topics(
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

    # ============================================================================
    # KB Health Metrics
    # ============================================================================

    @router.get("/kb/health")
    def get_kb_health(
        days: Optional[int] = None,
        session=Depends(require_admin),
    ):
        """
        Get knowledge base health metrics combining structural and retrieval data.

        Requires admin privileges.

        Args:
            days: Number of days for retrieval metrics (None for all time)
            session: Admin session (injected by dependency)

        Returns:
            Dictionary with structural metrics, retrieval metrics, and health score.

        Raises:
            HTTPException: If computation fails.
        """
        try:
            logger.info(
                f"Admin {session.email} requested KB health metrics (days={days})"
            )

            km = _get_km(session)

            if km is None:
                raise HTTPException(
                    status_code=501,
                    detail="KB health metrics not available (kb_manager not configured)",
                )

            # Structural metrics from ChromaDB
            structural = km.get_kb_health_metrics()

            # Extract filenames for cross-referencing
            kb_filenames = [
                doc.get("filename", "")
                for doc in structural.get("documents", [])
                if doc.get("filename")
            ]

            # Retrieval metrics from conversation data
            sim_threshold = app_settings.similarity_threshold if app_settings else 0.3
            retrieval = _get_cm(session).get_retrieval_health_metrics(
                kb_document_filenames=kb_filenames,
                days=days,
                similarity_threshold=sim_threshold,
            )

            # Compute composite health score
            health_score = _compute_health_score(structural, retrieval)

            # Remove full document list from response (too large)
            structural_response = {
                k: v for k, v in structural.items() if k != "documents"
            }

            return {
                "health_score": health_score,
                "structural": structural_response,
                "retrieval": retrieval,
            }

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error getting KB health metrics: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error getting KB health metrics: {str(e)}",
            )

    return router
