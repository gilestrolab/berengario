"""
Conversation manager for tracking multi-turn conversations.

This module provides conversation management for both email and webchat,
supporting thread tracking, message storage, and context retrieval.
"""

import hashlib
import logging
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session

from src.email.db_manager import db_manager
from src.email.db_models import Conversation, ConversationMessage, ChannelType, MessageType

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
    ) -> ConversationMessage:
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

        Returns:
            Created ConversationMessage object.
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

            # Create message
            message = ConversationMessage(
                conversation_id=conversation.id,
                message_type=message_type,
                content=content,
                sender=sender,
                subject=subject,
                timestamp=timestamp or datetime.utcnow(),
                message_order=message_count,
            )
            session.add(message)

            # Update conversation last_message_at
            conversation.last_message_at = message.timestamp
            session.add(conversation)

            session.commit()
            session.refresh(message)

            logger.info(
                f"Added message: conversation_id={conversation.id}, "
                f"type={message_type.value}, order={message_count}"
            )

            return message

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
            content = msg["content"][:500] + "..." if len(msg["content"]) > 500 else msg["content"]
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

    def get_conversation_stats(self, sender: str, channel: ChannelType) -> Dict[str, Any]:
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


# Global conversation manager instance
conversation_manager = ConversationManager()
