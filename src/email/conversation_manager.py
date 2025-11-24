"""
Conversation manager for tracking multi-turn conversations.

This module provides conversation management for both email and webchat,
supporting thread tracking, message storage, and context retrieval.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.email.db_manager import db_manager
from src.email.db_models import (
    ChannelType,
    Conversation,
    ConversationMessage,
    MessageType,
)

logger = logging.getLogger(__name__)


class ConversationManager:
    """
    Manages conversations and messages across email and webchat.

    This class handles:
    - Thread identification and tracking
    - Message storage (queries and replies)
    - Conversation history retrieval
    - Rating management for replies

    Attributes:
        db_manager: Database manager instance
    """

    def __init__(self):
        """Initialize conversation manager."""
        self.db_manager = db_manager
        logger.info("ConversationManager initialized")

    def extract_thread_id_from_email(
        self,
        message_id: str,
        in_reply_to: Optional[str] = None,
        references: Optional[str] = None,
    ) -> str:
        """
        Extract thread ID from email headers.

        Uses References header for thread tracking (like email clients do).
        Falls back to In-Reply-To, then Message-ID for new threads.

        Args:
            message_id: Current message's Message-ID header
            in_reply_to: In-Reply-To header (if replying)
            references: References header (if replying)

        Returns:
            Thread ID (normalized message ID).
        """
        # Priority 1: Use first message-id from References header (root of thread)
        if references:
            # References header contains space-separated message IDs
            # Format: "<id1> <id2> <id3>" where id1 is the root
            ref_ids = re.findall(r"<([^>]+)>", references)
            if ref_ids:
                thread_id = ref_ids[0]  # First ID is the thread root
                logger.debug(f"Thread ID from References: {thread_id}")
                return self._normalize_message_id(thread_id)

        # Priority 2: Use In-Reply-To (direct parent)
        if in_reply_to:
            # In-Reply-To typically has one message ID
            reply_match = re.search(r"<([^>]+)>", in_reply_to)
            if reply_match:
                thread_id = reply_match.group(1)
                logger.debug(f"Thread ID from In-Reply-To: {thread_id}")
                return self._normalize_message_id(thread_id)

        # Priority 3: New thread - use current Message-ID
        logger.debug(f"New thread, using Message-ID: {message_id}")
        return self._normalize_message_id(message_id)

    def _normalize_message_id(self, message_id: str) -> str:
        """
        Normalize message ID for consistent storage.

        Removes angle brackets and ensures consistent format.

        Args:
            message_id: Raw message ID

        Returns:
            Normalized message ID.
        """
        # Remove angle brackets if present
        normalized = message_id.strip("<>").strip()
        return normalized

    def get_or_create_conversation(
        self,
        thread_id: str,
        sender: str,
        channel: ChannelType = ChannelType.EMAIL,
    ) -> Conversation:
        """
        Get existing conversation or create new one.

        Args:
            thread_id: Thread identifier
            sender: User identifier (email or webchat user ID)
            channel: Channel type (email or webchat)

        Returns:
            Conversation object.
        """
        with self.db_manager.get_session() as session:
            # Try to find existing conversation
            conversation = (
                session.query(Conversation)
                .filter(Conversation.thread_id == thread_id)
                .first()
            )

            if conversation:
                logger.debug(f"Found existing conversation: {conversation.id}")
                return conversation

            # Create new conversation
            conversation = Conversation(
                thread_id=thread_id,
                sender=sender,
                channel=channel,
            )
            session.add(conversation)
            session.commit()
            session.refresh(conversation)

            logger.info(
                f"Created new conversation: id={conversation.id}, "
                f"thread_id={thread_id}, sender={sender}"
            )

            return conversation

    def add_message(
        self,
        thread_id: str,
        message_type: MessageType,
        content: str,
        sender: str,
        subject: Optional[str] = None,
        channel: ChannelType = ChannelType.EMAIL,
        timestamp: Optional[datetime] = None,
        original_query: Optional[str] = None,
        optimized_query: Optional[str] = None,
        sources_used: Optional[list] = None,
        retrieval_metadata: Optional[dict] = None,
    ) -> int:
        """
        Add a message to a conversation.

        Args:
            thread_id: Thread identifier
            message_type: Type of message (query or reply)
            content: Message content
            sender: Message sender
            subject: Email subject (optional)
            channel: Channel type (email or webchat)
            timestamp: Message timestamp (defaults to now)
            original_query: Original user query before optimization (QUERY messages only)
            optimized_query: LLM-optimized query used for RAG (QUERY messages only)
            sources_used: List of source documents with scores (REPLY messages only)
            retrieval_metadata: RAG retrieval metrics (REPLY messages only)

        Returns:
            ID of the created message.
        """
        with self.db_manager.get_session() as session:
            # Get or create conversation within this session
            conversation = (
                session.query(Conversation)
                .filter(Conversation.thread_id == thread_id)
                .first()
            )

            if not conversation:
                # Create new conversation
                conversation = Conversation(
                    thread_id=thread_id,
                    sender=sender,
                    channel=channel,
                )
                session.add(conversation)
                session.flush()  # Flush to get the ID without committing
                logger.info(
                    f"Created new conversation: id={conversation.id}, "
                    f"thread_id={thread_id}, sender={sender}"
                )

            # Get message order (count existing messages)
            message_count = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.conversation_id == conversation.id)
                .count()
            )

            # Calculate optimization_applied flag
            optimization_applied = False
            if original_query and optimized_query:
                optimization_applied = original_query != optimized_query

            # Create message
            message = ConversationMessage(
                conversation_id=conversation.id,
                message_type=message_type,
                content=content,
                sender=sender,
                subject=subject,
                timestamp=timestamp or datetime.utcnow(),
                message_order=message_count,
                original_query=original_query,
                optimized_query=optimized_query,
                optimization_applied=optimization_applied,
                sources_used=sources_used,
                retrieval_metadata=retrieval_metadata,
            )
            session.add(message)

            # Update conversation last_message_at
            conversation.last_message_at = message.timestamp
            session.add(conversation)

            session.commit()
            session.refresh(message)

            message_id = message.id  # Extract ID before session closes

            logger.info(
                f"Added message: conversation_id={conversation.id}, "
                f"type={message_type.value}, order={message_count}, message_id={message_id}"
            )

            return message_id

    def get_conversation_history(
        self,
        thread_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history for a thread.

        Args:
            thread_id: Thread identifier
            limit: Maximum number of messages to retrieve (None = all)

        Returns:
            List of message dictionaries with all data (to avoid detached instance issues).
        """
        with self.db_manager.get_session() as session:
            # Find conversation
            conversation = (
                session.query(Conversation)
                .filter(Conversation.thread_id == thread_id)
                .first()
            )

            if not conversation:
                logger.debug(f"No conversation found for thread_id: {thread_id}")
                return []

            # Get messages ordered by message_order
            query = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.conversation_id == conversation.id)
                .order_by(ConversationMessage.message_order)
            )

            if limit:
                query = query.limit(limit)

            messages = query.all()

            logger.debug(
                f"Retrieved {len(messages)} messages for conversation {conversation.id}"
            )

            # Convert to dictionaries to avoid detached instance errors
            return [
                {
                    "id": msg.id,
                    "message_type": msg.message_type,
                    "content": msg.content,
                    "sender": msg.sender,
                    "subject": msg.subject,
                    "timestamp": msg.timestamp,
                    "message_order": msg.message_order,
                    "rating": msg.rating,
                }
                for msg in messages
            ]

    def format_conversation_context(
        self,
        thread_id: str,
        max_messages: int = 10,
    ) -> str:
        """
        Format conversation history as context for LLM.

        Args:
            thread_id: Thread identifier
            max_messages: Maximum number of recent messages to include

        Returns:
            Formatted conversation context string.
        """
        messages = self.get_conversation_history(thread_id, limit=max_messages)

        if not messages:
            return ""

        context_lines = ["Previous conversation:"]
        for msg in messages:
            role = "User" if msg["message_type"] == MessageType.QUERY else "Assistant"
            # Truncate long messages for context
            content = (
                msg["content"][:500] + "..."
                if len(msg["content"]) > 500
                else msg["content"]
            )
            context_lines.append(f"{role}: {content}")

        context = "\n".join(context_lines)
        logger.debug(f"Formatted context with {len(messages)} messages")
        return context

    def set_message_rating(self, message_id: int, rating: int) -> bool:
        """
        Set rating for a message (replies only).

        Args:
            message_id: Message ID
            rating: Rating value (1-5)

        Returns:
            True if successful, False otherwise.
        """
        if not (1 <= rating <= 5):
            logger.error(f"Invalid rating: {rating} (must be 1-5)")
            return False

        with self.db_manager.get_session() as session:
            message = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.id == message_id)
                .first()
            )

            if not message:
                logger.error(f"Message not found: {message_id}")
                return False

            if message.message_type != MessageType.REPLY:
                logger.error(f"Cannot rate query messages: {message_id}")
                return False

            message.rating = rating
            session.add(message)
            session.commit()

            logger.info(f"Set rating {rating} for message {message_id}")
            return True

    def get_conversation_stats(
        self, sender: str, channel: ChannelType
    ) -> Dict[str, Any]:
        """
        Get statistics for a user's conversations.

        Args:
            sender: User identifier
            channel: Channel type

        Returns:
            Dictionary with conversation statistics.
        """
        with self.db_manager.get_session() as session:
            conversations = (
                session.query(Conversation)
                .filter(Conversation.sender == sender, Conversation.channel == channel)
                .all()
            )

            total_conversations = len(conversations)
            total_messages = sum(len(conv.messages) for conv in conversations)

            # Count rated messages
            rated_messages = (
                session.query(ConversationMessage)
                .join(Conversation)
                .filter(
                    Conversation.sender == sender,
                    Conversation.channel == channel,
                    ConversationMessage.rating.isnot(None),
                )
                .count()
            )

            stats = {
                "total_conversations": total_conversations,
                "total_messages": total_messages,
                "rated_messages": rated_messages,
            }

            logger.debug(f"Stats for {sender}: {stats}")
            return stats

    def delete_conversation(self, thread_id: str) -> bool:
        """
        Delete a conversation and all its messages.

        Args:
            thread_id: Thread identifier

        Returns:
            True if deleted, False if not found.
        """
        with self.db_manager.get_session() as session:
            conversation = (
                session.query(Conversation)
                .filter(Conversation.thread_id == thread_id)
                .first()
            )

            if not conversation:
                logger.warning(f"Conversation not found: {thread_id}")
                return False

            session.delete(conversation)
            session.commit()

            logger.info(f"Deleted conversation: {thread_id}")
            return True

    def get_usage_analytics(
        self,
        days: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get comprehensive usage analytics for queries.

        Args:
            days: Number of days to look back (from today)
            start_date: Explicit start date (overrides days)
            end_date: Explicit end date (defaults to now)

        Returns:
            Dictionary with usage analytics including:
            - overview: Total queries, unique users, avg queries/user
            - daily_stats: Daily query counts
            - user_activity: Per-user query counts and details
            - channel_breakdown: Email vs webchat distribution
        """
        from datetime import timedelta

        from sqlalchemy import func

        with self.db_manager.get_session() as session:
            # Determine date range
            if start_date is None:
                if days:
                    start_date = datetime.utcnow() - timedelta(days=days)
                else:
                    # No filter, get all data
                    start_date = datetime(1970, 1, 1)

            if end_date is None:
                end_date = datetime.utcnow()

            # Base query for queries only (not replies)
            base_query = session.query(ConversationMessage).filter(
                ConversationMessage.message_type == MessageType.QUERY,
                ConversationMessage.timestamp >= start_date,
                ConversationMessage.timestamp <= end_date,
            )

            # Overview statistics
            total_queries = base_query.count()

            unique_users = (
                session.query(func.count(func.distinct(ConversationMessage.sender)))
                .join(Conversation)
                .filter(
                    ConversationMessage.message_type == MessageType.QUERY,
                    ConversationMessage.timestamp >= start_date,
                    ConversationMessage.timestamp <= end_date,
                )
                .scalar()
                or 0
            )

            avg_queries_per_user = (
                round(total_queries / unique_users, 2) if unique_users > 0 else 0
            )

            # Daily statistics
            daily_stats = (
                session.query(
                    func.date(ConversationMessage.timestamp).label("date"),
                    func.count(ConversationMessage.id).label("count"),
                )
                .filter(
                    ConversationMessage.message_type == MessageType.QUERY,
                    ConversationMessage.timestamp >= start_date,
                    ConversationMessage.timestamp <= end_date,
                )
                .group_by(func.date(ConversationMessage.timestamp))
                .order_by(func.date(ConversationMessage.timestamp))
                .all()
            )

            daily_stats_list = [
                {"date": str(stat.date), "count": stat.count} for stat in daily_stats
            ]

            # Per-user activity
            user_stats = (
                session.query(
                    Conversation.sender,
                    Conversation.channel,
                    func.count(ConversationMessage.id).label("query_count"),
                )
                .join(ConversationMessage)
                .filter(
                    ConversationMessage.message_type == MessageType.QUERY,
                    ConversationMessage.timestamp >= start_date,
                    ConversationMessage.timestamp <= end_date,
                )
                .group_by(Conversation.sender, Conversation.channel)
                .order_by(func.count(ConversationMessage.id).desc())
                .all()
            )

            user_activity = [
                {
                    "sender": stat.sender,
                    "channel": stat.channel.value,
                    "query_count": stat.query_count,
                }
                for stat in user_stats
            ]

            # Channel breakdown
            channel_stats = (
                session.query(
                    Conversation.channel,
                    func.count(ConversationMessage.id).label("count"),
                )
                .join(ConversationMessage)
                .filter(
                    ConversationMessage.message_type == MessageType.QUERY,
                    ConversationMessage.timestamp >= start_date,
                    ConversationMessage.timestamp <= end_date,
                )
                .group_by(Conversation.channel)
                .all()
            )

            channel_breakdown = {
                stat.channel.value: stat.count for stat in channel_stats
            }

            analytics = {
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat(),
                },
                "overview": {
                    "total_queries": total_queries,
                    "unique_users": unique_users,
                    "avg_queries_per_user": avg_queries_per_user,
                },
                "daily_stats": daily_stats_list,
                "user_activity": user_activity,
                "channel_breakdown": channel_breakdown,
            }

            logger.debug(
                f"Usage analytics: {total_queries} queries from "
                f"{unique_users} users ({start_date} to {end_date})"
            )

            return analytics

    def get_user_queries(
        self,
        sender: str,
        days: Optional[int] = None,
        limit: Optional[int] = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get detailed query list for a specific user.

        Args:
            sender: User identifier
            days: Number of days to look back (None = all)
            limit: Maximum number of queries to return

        Returns:
            List of query dictionaries with content, timestamp, subject.
        """
        from datetime import timedelta

        with self.db_manager.get_session() as session:
            query = (
                session.query(ConversationMessage)
                .join(Conversation)
                .filter(
                    Conversation.sender == sender,
                    ConversationMessage.message_type == MessageType.QUERY,
                )
            )

            if days:
                start_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ConversationMessage.timestamp >= start_date)

            query = query.order_by(ConversationMessage.timestamp.desc())

            if limit:
                query = query.limit(limit)

            messages = query.all()

            return [
                {
                    "id": msg.id,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "subject": msg.subject,
                    "channel": msg.conversation.channel.value,
                }
                for msg in messages
            ]

    def get_message_optimization_details(
        self, message_id: int
    ) -> Optional[Dict[str, Any]]:
        """
        Get query optimization details for a specific message.

        Args:
            message_id: ID of the message

        Returns:
            Dictionary with optimization details or None if not found.
        """
        with self.db_manager.get_session() as session:
            message = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.id == message_id)
                .first()
            )

            if not message:
                return None

            return {
                "message_id": message.id,
                "original_query": message.original_query,
                "optimized_query": message.optimized_query,
                "optimization_applied": message.optimization_applied,
                "timestamp": (
                    message.timestamp.isoformat() if message.timestamp else None
                ),
            }

    def get_message_source_details(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get source document details for a specific reply message.

        Args:
            message_id: ID of the message

        Returns:
            Dictionary with source details or None if not found.
        """
        with self.db_manager.get_session() as session:
            message = (
                session.query(ConversationMessage)
                .filter(ConversationMessage.id == message_id)
                .first()
            )

            if not message:
                return None

            return {
                "message_id": message.id,
                "sources_used": message.sources_used,
                "retrieval_metadata": message.retrieval_metadata,
                "timestamp": (
                    message.timestamp.isoformat() if message.timestamp else None
                ),
            }

    def get_optimization_analytics(self, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Get query optimization analytics.

        Args:
            days: Number of days to analyze (None = all time)

        Returns:
            Dictionary with optimization statistics.
        """
        with self.db_manager.get_session() as session:

            # Build base query for QUERY messages
            query = session.query(ConversationMessage).filter(
                ConversationMessage.message_type == MessageType.QUERY
            )

            # Apply date filter if specified
            if days:
                from datetime import datetime, timedelta

                start_date = datetime.utcnow() - timedelta(days=days)
                query = query.filter(ConversationMessage.timestamp >= start_date)

            all_queries = query.all()
            total_queries = len(all_queries)

            if total_queries == 0:
                return {
                    "total_queries": 0,
                    "optimized_queries": 0,
                    "optimization_rate": 0.0,
                    "avg_query_length_original": 0,
                    "avg_query_length_optimized": 0,
                    "avg_expansion_ratio": 0.0,
                    "sample_optimizations": [],
                }

            # Calculate optimization metrics
            optimized_count = sum(1 for q in all_queries if q.optimization_applied)

            # Calculate average query lengths
            original_lengths = [
                len(q.original_query) for q in all_queries if q.original_query
            ]
            optimized_lengths = [
                len(q.optimized_query)
                for q in all_queries
                if q.optimized_query and q.optimization_applied
            ]

            avg_original_length = (
                sum(original_lengths) / len(original_lengths) if original_lengths else 0
            )
            avg_optimized_length = (
                sum(optimized_lengths) / len(optimized_lengths)
                if optimized_lengths
                else 0
            )

            # Calculate expansion ratio
            expansion_ratio = (
                avg_optimized_length / avg_original_length
                if avg_original_length > 0
                else 0
            )

            # Get sample optimizations (last 10)
            sample_optimizations = []
            for q in reversed(all_queries[-10:]):
                if q.optimization_applied and q.original_query and q.optimized_query:
                    sample_optimizations.append(
                        {
                            "original": q.original_query[:100],
                            "optimized": q.optimized_query[:100],
                            "timestamp": (
                                q.timestamp.isoformat() if q.timestamp else None
                            ),
                        }
                    )

            return {
                "total_queries": total_queries,
                "optimized_queries": optimized_count,
                "optimization_rate": (
                    (optimized_count / total_queries * 100) if total_queries > 0 else 0
                ),
                "avg_query_length_original": round(avg_original_length, 1),
                "avg_query_length_optimized": round(avg_optimized_length, 1),
                "avg_expansion_ratio": round(expansion_ratio, 2),
                "sample_optimizations": sample_optimizations,
            }

    def get_source_analytics(self, days: Optional[int] = None) -> Dict[str, Any]:
        """
        Get source document usage analytics.

        Args:
            days: Number of days to analyze (None = all time)

        Returns:
            Dictionary with source usage statistics.
        """
        with self.db_manager.get_session() as session:
            # Get total count of all REPLY messages
            total_replies_query = session.query(ConversationMessage).filter(
                ConversationMessage.message_type == MessageType.REPLY
            )

            # Apply date filter if specified
            if days:
                from datetime import datetime, timedelta

                start_date = datetime.utcnow() - timedelta(days=days)
                total_replies_query = total_replies_query.filter(
                    ConversationMessage.timestamp >= start_date
                )

            total_replies_count = total_replies_query.count()

            # Build query for REPLY messages with sources
            query = session.query(ConversationMessage).filter(
                ConversationMessage.message_type == MessageType.REPLY,
                ConversationMessage.sources_used.isnot(None),
            )

            # Apply date filter if specified
            if days:
                query = query.filter(ConversationMessage.timestamp >= start_date)

            all_replies = query.all()
            replies_with_sources_count = len(all_replies)

            if replies_with_sources_count == 0:
                return {
                    "total_replies": total_replies_count,
                    "total_replies_with_sources": 0,
                    "total_sources_used": 0,
                    "avg_sources_per_reply": 0.0,
                    "avg_relevance_score": 0.0,
                    "most_cited_documents": [],
                    "source_type_distribution": {},
                }

            # Count total sources and calculate metrics
            total_sources = 0
            all_scores = []
            document_counts = {}
            document_scores = {}  # Track scores per document
            source_types = {}

            for reply in all_replies:
                if reply.sources_used:
                    sources = reply.sources_used
                    total_sources += len(sources)

                    for source in sources:
                        # Track relevance scores
                        if "score" in source:
                            all_scores.append(source["score"])

                        # Track document usage and scores
                        filename = source.get("filename", "Unknown")
                        document_counts[filename] = document_counts.get(filename, 0) + 1

                        # Track scores per document
                        if "score" in source:
                            if filename not in document_scores:
                                document_scores[filename] = []
                            document_scores[filename].append(source["score"])

                        # Track source types
                        source_type = source.get("source_type", "document")
                        source_types[source_type] = source_types.get(source_type, 0) + 1

            # Calculate averages
            avg_sources = (
                total_sources / replies_with_sources_count
                if replies_with_sources_count > 0
                else 0
            )
            avg_score = sum(all_scores) / len(all_scores) if all_scores else 0

            # Get top 20 most cited documents with average scores
            most_cited = sorted(
                document_counts.items(), key=lambda x: x[1], reverse=True
            )[:20]

            most_cited_list = [
                {
                    "filename": filename,
                    "citation_count": count,
                    "avg_score": (
                        sum(document_scores.get(filename, [0]))
                        / len(document_scores.get(filename, [1]))
                        if filename in document_scores
                        else 0
                    ),
                }
                for filename, count in most_cited
            ]

            return {
                "total_replies": total_replies_count,
                "total_replies_with_sources": replies_with_sources_count,
                "total_sources_used": total_sources,
                "avg_sources_per_reply": round(avg_sources, 2),
                "avg_relevance_score": round(avg_score, 3),
                "most_cited_documents": most_cited_list,
                "source_type_distribution": source_types,
            }


# Global conversation manager instance
conversation_manager = ConversationManager()
