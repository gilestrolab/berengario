"""
Conversation management routes.

Handles conversation history, listing, retrieval, deletion, and search.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import desc, func, or_

from src.api.models import (
    ConversationListItem,
    ConversationMessagesResponse,
    ConversationSearchResponse,
    ConversationsResponse,
    HistoryResponse,
)
from src.email.db_models import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["conversations"])


def create_conversations_router(
    conversation_manager,
    session_manager,
    require_auth,
):
    """
    Create conversations router with dependency injection.

    Args:
        conversation_manager: Conversation manager instance
        session_manager: Session manager instance
        require_auth: Authentication dependency function

    Returns:
        Configured APIRouter instance
    """

    @router.get("/history", response_model=HistoryResponse)
    async def get_history(
        session=Depends(require_auth),
    ):
        """
        Get conversation history for authenticated session.

        Requires authentication.

        Args:
            session: Authenticated session (injected by dependency)

        Returns:
            HistoryResponse with conversation messages
        """
        return HistoryResponse(
            session_id=session.session_id,
            messages=session.messages,
            created_at=session.created_at.isoformat(),
            last_activity=session.last_activity.isoformat(),
        )

    @router.delete("/session")
    async def clear_session(
        response: Response,
        session=Depends(require_auth),
    ):
        """
        Clear session history and delete attachments.

        Requires authentication.

        Args:
            response: FastAPI response object
            session: Authenticated session (injected by dependency)

        Returns:
            Success message
        """
        if session_manager.delete_session(session.session_id):
            # Clear cookie
            response.delete_cookie("session_id")
            return {"success": True, "message": "Session cleared"}

        return {"success": False, "message": "Failed to clear session"}

    @router.get("/conversations", response_model=ConversationsResponse)
    async def list_conversations(
        session=Depends(require_auth),
    ):
        """
        Get list of all conversations for authenticated user.

        Returns conversations from database (both email and webchat) sorted by
        most recent activity.

        Requires authentication.

        Args:
            session: Authenticated session (injected by dependency)

        Returns:
            ConversationsResponse with list of conversations
        """
        user_email = (
            session.email if hasattr(session, "email") and session.email else None
        )
        if not user_email:
            return ConversationsResponse(conversations=[], total_count=0)

        with conversation_manager.db_manager.get_session() as db_session:
            # Query conversations for this user, ordered by most recent
            conversations_query = (
                db_session.query(Conversation)
                .filter(Conversation.sender == user_email)
                .order_by(desc(Conversation.last_message_at))
            )

            conversations = conversations_query.all()
            conversation_items = []

            for conv in conversations:
                # Get message count
                message_count = (
                    db_session.query(func.count(ConversationMessage.id))
                    .filter(ConversationMessage.conversation_id == conv.id)
                    .scalar()
                ) or 0

                # Get first message for preview
                first_message = (
                    db_session.query(ConversationMessage)
                    .filter(ConversationMessage.conversation_id == conv.id)
                    .order_by(ConversationMessage.message_order)
                    .first()
                )

                preview = None
                subject = None
                if first_message:
                    # Truncate preview to 100 chars
                    preview = (
                        (first_message.content[:100] + "...")
                        if len(first_message.content) > 100
                        else first_message.content
                    )
                    subject = first_message.subject

                conversation_items.append(
                    ConversationListItem(
                        id=conv.id,
                        thread_id=conv.thread_id,
                        channel=(
                            conv.channel.value
                            if hasattr(conv.channel, "value")
                            else str(conv.channel)
                        ),
                        sender=conv.sender,
                        created_at=conv.created_at.isoformat(),
                        last_message_at=conv.last_message_at.isoformat(),
                        message_count=message_count,
                        preview=preview,
                        subject=subject,
                    )
                )

            return ConversationsResponse(
                conversations=conversation_items,
                total_count=len(conversation_items),
            )

    @router.get(
        "/conversations/{conversation_id}", response_model=ConversationMessagesResponse
    )
    async def get_conversation_messages(
        conversation_id: int,
        session=Depends(require_auth),
    ):
        """
        Get all messages for a specific conversation.

        Requires authentication. Users can only access their own conversations.

        Args:
            conversation_id: Conversation ID
            session: Authenticated session (injected by dependency)

        Returns:
            ConversationMessagesResponse with all messages

        Raises:
            HTTPException: If conversation not found or unauthorized
        """
        user_email = (
            session.email if hasattr(session, "email") and session.email else None
        )
        if not user_email:
            raise HTTPException(status_code=401, detail="Not authenticated")

        with conversation_manager.db_manager.get_session() as db_session:
            # Get conversation and verify ownership
            conversation = (
                db_session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )

            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Normalize comparison to match SQL case-insensitive behavior
            if (conversation.sender or "").lower() != (user_email or "").lower():
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. You can only view your own conversations.",
                )

            # Get all messages ordered by message_order
            messages = (
                db_session.query(ConversationMessage)
                .filter(ConversationMessage.conversation_id == conversation_id)
                .order_by(ConversationMessage.message_order)
                .all()
            )

            # Convert to dictionaries
            message_list = [
                {
                    "id": msg.id,
                    "role": (
                        "user" if msg.message_type.value == "query" else "assistant"
                    ),
                    "content": msg.content,
                    "sender": msg.sender,
                    "subject": msg.subject,
                    "timestamp": msg.timestamp.isoformat(),
                    "message_order": msg.message_order,
                    "rating": msg.rating,
                    "sources": msg.sources_used,  # Include sources for historical chat display
                    "retrieval_metadata": msg.retrieval_metadata,  # Include RAG metadata
                }
                for msg in messages
            ]

            return ConversationMessagesResponse(
                conversation_id=conversation.id,
                thread_id=conversation.thread_id,
                channel=(
                    conversation.channel.value
                    if hasattr(conversation.channel, "value")
                    else str(conversation.channel)
                ),
                messages=message_list,
            )

    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation(
        conversation_id: int,
        session=Depends(require_auth),
    ):
        """
        Delete a conversation and all its messages.

        Requires authentication. Users can only delete their own conversations.

        Args:
            conversation_id: Conversation ID to delete
            session: Authenticated session (injected by dependency)

        Returns:
            Success message

        Raises:
            HTTPException: If conversation not found or unauthorized
        """
        user_email = (
            session.email if hasattr(session, "email") and session.email else None
        )
        if not user_email:
            raise HTTPException(status_code=401, detail="Not authenticated")

        with conversation_manager.db_manager.get_session() as db_session:
            # Get conversation and verify ownership
            conversation = (
                db_session.query(Conversation)
                .filter(Conversation.id == conversation_id)
                .first()
            )

            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")

            # Normalize comparison to match SQL case-insensitive behavior
            if (conversation.sender or "").lower() != (user_email or "").lower():
                raise HTTPException(
                    status_code=403,
                    detail="Access denied. You can only delete your own conversations.",
                )

            # Delete conversation (messages cascade delete automatically)
            thread_id = conversation.thread_id
            db_session.delete(conversation)
            db_session.commit()

            logger.info(
                f"User {user_email} deleted conversation {conversation_id} (thread: {thread_id})"
            )

            return {"success": True, "message": "Conversation deleted"}

    @router.get("/conversations/search", response_model=ConversationSearchResponse)
    async def search_conversations(
        q: str,
        session=Depends(require_auth),
    ):
        """
        Search conversations by content, subject, or sender.

        Requires authentication. Only searches user's own conversations.

        Args:
            q: Search query string
            session: Authenticated session (injected by dependency)

        Returns:
            ConversationSearchResponse with matching conversations
        """
        user_email = (
            session.email if hasattr(session, "email") and session.email else None
        )
        if not user_email:
            return ConversationSearchResponse(results=[], query=q, total_results=0)

        if not q or len(q.strip()) < 2:
            return ConversationSearchResponse(results=[], query=q, total_results=0)

        search_term = f"%{q}%"

        with conversation_manager.db_manager.get_session() as db_session:
            # Find conversations where message content or subject matches search
            matching_conv_ids = (
                db_session.query(ConversationMessage.conversation_id)
                .distinct()
                .filter(
                    or_(
                        ConversationMessage.content.ilike(search_term),
                        ConversationMessage.subject.ilike(search_term),
                    )
                )
                .subquery()
            )

            # Get conversations that match
            conversations_query = (
                db_session.query(Conversation)
                .filter(
                    Conversation.sender == user_email,
                    Conversation.id.in_(matching_conv_ids),
                )
                .order_by(desc(Conversation.last_message_at))
            )

            conversations = conversations_query.all()
            results = []

            for conv in conversations:
                # Get message count
                message_count = (
                    db_session.query(func.count(ConversationMessage.id))
                    .filter(ConversationMessage.conversation_id == conv.id)
                    .scalar()
                ) or 0

                # Get first matching message for context
                matching_message = (
                    db_session.query(ConversationMessage)
                    .filter(
                        ConversationMessage.conversation_id == conv.id,
                        or_(
                            ConversationMessage.content.ilike(search_term),
                            ConversationMessage.subject.ilike(search_term),
                        ),
                    )
                    .first()
                )

                preview = None
                subject = None
                if matching_message:
                    # Show snippet around match
                    content = matching_message.content
                    preview = (content[:100] + "...") if len(content) > 100 else content
                    subject = matching_message.subject

                results.append(
                    ConversationListItem(
                        id=conv.id,
                        thread_id=conv.thread_id,
                        channel=(
                            conv.channel.value
                            if hasattr(conv.channel, "value")
                            else str(conv.channel)
                        ),
                        sender=conv.sender,
                        created_at=conv.created_at.isoformat(),
                        last_message_at=conv.last_message_at.isoformat(),
                        message_count=message_count,
                        preview=preview,
                        subject=subject,
                    )
                )

            return ConversationSearchResponse(
                results=results,
                query=q,
                total_results=len(results),
            )

    return router
