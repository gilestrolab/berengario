"""
Query handler for processing user queries.

Provides a high-level interface for query processing with logging and error handling.
"""

import logging
from datetime import datetime
from typing import Dict, Optional

from src.rag.query_optimizer import QueryOptimizer
from src.rag.rag_engine import RAGEngine
from src.rag.tools import clear_tool_context, set_tool_context

logger = logging.getLogger(__name__)


class QueryHandler:
    """
    Handles user queries with logging and error handling.

    Provides a wrapper around RAGEngine with additional functionality.
    """

    def __init__(
        self,
        rag_engine: Optional[RAGEngine] = None,
        tenant_context: Optional["TenantContext"] = None,  # noqa: F821
        conversation_manager: Optional[object] = None,
    ):
        """
        Initialize the query handler.

        Args:
            rag_engine: RAG engine instance (creates new if None).
            tenant_context: Optional tenant context for multi-tenant config.
                When provided, passes optimization settings to QueryOptimizer.
            conversation_manager: Optional ConversationManager for MT per-tenant DB.
                Injected into tool context so database_tools use the correct tenant's data.
        """
        self.rag_engine = rag_engine or RAGEngine()
        self.tenant_context = tenant_context
        self.conversation_manager = conversation_manager

        # Configure query optimizer with tenant-specific settings when available
        ctx = self.tenant_context
        if ctx:
            self.query_optimizer = QueryOptimizer(
                enabled=ctx.query_optimization_enabled,
                model=ctx.query_optimization_model,
            )
        else:
            self.query_optimizer = QueryOptimizer()

        logger.info("QueryHandler initialized")

    def process_query(
        self,
        query_text: str,
        user_email: Optional[str] = None,
        is_admin: bool = False,
        is_email_request: bool = False,
        context: Optional[Dict] = None,
    ) -> Dict[str, any]:
        """
        Process a user query.

        Args:
            query_text: The query string.
            user_email: Email address of the user (for logging).
            is_admin: Whether the user has admin privileges (for whitelist management tools).
            is_email_request: Whether this is an email request (requires confirmation for whitelist changes).
            context: Additional context information.

        Returns:
            Dictionary containing:
                - success: Boolean indicating if query succeeded
                - response: Response text (if successful)
                - sources: List of sources (if successful)
                - attachments: List of attachments (if any)
                - error: Error message (if failed)
                - timestamp: Processing timestamp
                - user_email: User email (if provided)

        """
        timestamp = datetime.now().isoformat()

        # Log query
        log_msg = f"Processing query from {user_email or 'unknown'}: {query_text[:100]}"
        logger.info(log_msg)

        try:
            # Validate query
            if not query_text or not query_text.strip():
                raise ValueError("Query text cannot be empty")

            # Set tool context for admin-only tools and MT KB/DB routing
            tenant_id = (
                getattr(self.tenant_context, "tenant_id", None)
                if self.tenant_context
                else None
            )
            set_tool_context(
                user_email=user_email or "unknown",
                is_admin=is_admin,
                is_email_request=is_email_request,
                kb_manager=self.rag_engine.kb_manager,
                conversation_manager=self.conversation_manager,
                tenant_id=tenant_id,
            )

            try:
                # Extract conversation history from context if available
                conversation_history = None
                if context and "conversation_history" in context:
                    conversation_history = context["conversation_history"]

                # Optimize query for better RAG retrieval
                optimized_query = self.query_optimizer.optimize_query(
                    query_text, conversation_history
                )

                # Log optimization for analysis
                if optimized_query != query_text:
                    logger.info(
                        f"Query optimized: '{query_text[:80]}...' → '{optimized_query[:80]}...'"
                    )

                # Process query through RAG engine with conversation history
                result = self.rag_engine.query(
                    optimized_query,
                    conversation_history=conversation_history,
                )

                # Build response
                response = {
                    "success": True,
                    "response": result["response"],
                    "sources": result["sources"],
                    "attachments": result.get("attachments", []),
                    "metadata": result["metadata"],
                    "timestamp": timestamp,
                    # Query optimization tracking
                    "original_query": query_text,
                    "optimized_query": optimized_query,
                    "optimization_applied": optimized_query != query_text,
                }

                if user_email:
                    response["user_email"] = user_email

                num_attachments = len(response["attachments"])
                logger.info(
                    f"Query processed successfully for {user_email or 'unknown'} "
                    f"with {len(result['sources'])} sources and {num_attachments} attachments"
                )

                return response

            finally:
                # Always clear tool context after processing
                clear_tool_context()

        except Exception as e:
            logger.error(f"Error processing query: {e}")

            return {
                "success": False,
                "error": str(e),
                "timestamp": timestamp,
                "user_email": user_email,
            }

    def format_for_email(self, result: Dict[str, any]) -> str:
        """
        Format query result for email response.

        Args:
            result: Result dictionary from process_query().

        Returns:
            Formatted email body text.
        """
        if not result["success"]:
            from src.config import settings

            return (
                "I apologize, but I encountered an error processing your query.\n\n"
                f"Error: {result.get('error', 'Unknown error')}\n\n"
                "Please try rephrasing your question or contact support if the issue persists.\n\n"
                f"Best regards,\n{settings.instance_name}"
            )

        return self.rag_engine.format_response_for_email(result)

    def format_for_web(self, result: Dict[str, any]) -> Dict[str, any]:
        """
        Format query result for web API response.

        Args:
            result: Result dictionary from process_query().

        Returns:
            Dictionary formatted for JSON API response.
        """
        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "timestamp": result["timestamp"],
            }

        web_result = self.rag_engine.format_response_for_web(result)
        web_result["success"] = True
        web_result["timestamp"] = result["timestamp"]

        return web_result

    def get_stats(self) -> Dict[str, any]:
        """
        Get knowledge base statistics.

        Returns:
            Dictionary containing KB stats.
        """
        return self.rag_engine.get_kb_stats()
