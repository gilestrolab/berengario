"""
Query processing routes.

Handles RAG query processing and attachment downloads.
"""

import logging
import uuid
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import FileResponse

from src.api.models import QueryRequest, QueryResponse
from src.email.conversation_manager import MessageType
from src.email.db_models import ChannelType

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["query"])


def create_query_router(
    query_handler,
    conversation_manager,
    session_manager,
    settings,
    require_auth,
    set_session_cookie,
    cleanup_old_attachments,
):
    """
    Create query router with dependency injection.

    Args:
        query_handler: Query handler instance
        conversation_manager: Conversation manager instance
        session_manager: Session manager instance
        settings: Application settings
        require_auth: Authentication dependency function
        set_session_cookie: Function to set session cookie
        cleanup_old_attachments: Function to cleanup old attachments

    Returns:
        Configured APIRouter instance
    """

    @router.post("/query", response_model=QueryResponse)
    async def query(
        query_request: QueryRequest,
        request: Request,
        response: Response,
        background_tasks: BackgroundTasks,
        session=Depends(require_auth),
    ):
        """
        Process a RAG query and return response.

        Requires authentication.

        Args:
            query_request: Query request with text and optional context
            request: FastAPI request object
            response: FastAPI response object
            background_tasks: Background task manager
            session: Authenticated session (injected by dependency)

        Returns:
            QueryResponse with answer, sources, and attachments
        """
        # Session is already authenticated via dependency
        set_session_cookie(response, session.session_id)

        user_identifier = (
            session.email
            if hasattr(session, "email") and session.email
            else f"web_user_{session.session_id[:8]}"
        )

        # Determine thread_id: use existing conversation or create new
        thread_id = None
        channel = ChannelType.WEBCHAT

        if query_request.conversation_id:
            # Continue existing conversation
            from src.email.db_models import Conversation

            with conversation_manager.db_manager.get_session() as db_session:
                existing_conv = (
                    db_session.query(Conversation)
                    .filter(Conversation.id == query_request.conversation_id)
                    .first()
                )

                if not existing_conv:
                    raise HTTPException(
                        status_code=404, detail="Conversation not found"
                    )

                # Verify user owns this conversation
                if existing_conv.sender != user_identifier:
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied. You can only continue your own conversations.",
                    )

                thread_id = existing_conv.thread_id
                channel = existing_conv.channel

                logger.info(
                    f"Continuing conversation {query_request.conversation_id} (thread: {thread_id})"
                )
        else:
            # Create new conversation with unique thread_id
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = str(uuid.uuid4())[:8]
            thread_id = f"webchat_{session.session_id[:8]}_{timestamp}_{unique_id}"

            logger.info(f"Created new conversation thread: {thread_id}")

        # Add user message to in-memory session history (before processing)
        session.add_message("user", query_request.query)

        # Build conversation history from session messages for context
        conversation_history = conversation_manager.format_conversation_context(
            thread_id=thread_id,
            max_messages=10,  # Last 10 messages for context
        )

        try:
            # Process query through RAG engine with conversation history
            # Pass admin status from session for tool access control
            context = query_request.context or {}
            context["conversation_history"] = conversation_history

            result = query_handler.process_query(
                query_text=query_request.query,
                user_email=user_identifier,
                is_admin=session.is_admin if hasattr(session, "is_admin") else False,
                context=context,
            )

            # Store user query in conversation database (after processing to capture optimization data)
            conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.QUERY,
                content=query_request.query,
                sender=user_identifier,
                channel=channel,
                original_query=result.get("original_query"),
                optimized_query=result.get("optimized_query"),
            )

            if not result["success"]:
                error_response = f"Error: {result.get('error', 'Unknown error')}"
                session.add_message("assistant", error_response)

                # Store error response in conversation database
                conversation_manager.add_message(
                    thread_id=thread_id,
                    message_type=MessageType.REPLY,
                    content=error_response,
                    sender=settings.instance_name,
                    channel=channel,
                )

                return QueryResponse(
                    success=False,
                    error=result.get("error", "Unknown error"),
                    timestamp=result["timestamp"],
                    session_id=session.session_id,
                )

            # Process attachments - save to session directory and generate URLs
            attachment_urls = []
            if result.get("attachments"):
                session_dir = settings.email_temp_dir / f"web_{session.session_id}"
                session_dir.mkdir(parents=True, exist_ok=True)

                for attachment in result["attachments"]:
                    filename = attachment.get("filename", "attachment")
                    content = attachment.get("content")

                    if isinstance(content, str):
                        content = content.encode("utf-8")

                    filepath = session_dir / filename
                    with open(filepath, "wb") as f:
                        f.write(content)

                    attachment_url = {
                        "filename": filename,
                        "url": f"/api/attachments/{session.session_id}/{filename}",
                        "content_type": attachment.get(
                            "content_type", "application/octet-stream"
                        ),
                    }
                    attachment_urls.append(attachment_url)

            # Add assistant response to in-memory session history
            session.add_message(
                "assistant",
                result["response"],
                sources=result["sources"],
                attachments=attachment_urls,
            )

            # Store assistant response in conversation database with sources and metadata
            reply_message_id = conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.REPLY,
                content=result["response"],
                sender=settings.instance_name,
                channel=channel,
                sources_used=result.get("sources"),
                retrieval_metadata=result.get("metadata"),
            )

            # Schedule cleanup
            background_tasks.add_task(session_manager.cleanup_inactive_sessions)
            background_tasks.add_task(cleanup_old_attachments)

            return QueryResponse(
                success=True,
                response=result["response"],
                sources=result["sources"],
                attachments=attachment_urls,
                timestamp=result["timestamp"],
                session_id=session.session_id,
                message_id=reply_message_id,
            )

        except Exception as e:
            logger.error(f"Error processing query: {e}", exc_info=True)
            error_msg = str(e)
            error_response = f"Error: {error_msg}"
            session.add_message("assistant", error_response)

            # Store exception error in conversation database
            conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.REPLY,
                content=error_response,
                sender=settings.instance_name,
                channel=channel,
            )

            return QueryResponse(
                success=False,
                error=error_msg,
                timestamp=datetime.now().isoformat(),
                session_id=session.session_id,
            )

    @router.get("/attachments/{session_id}/{filename}")
    async def download_attachment(
        session_id: str,
        filename: str,
        session=Depends(require_auth),
    ):
        """
        Download attachment file.

        Requires authentication. Users can only download attachments from their own session.

        Args:
            session_id: Session ID
            filename: Attachment filename
            session: Authenticated session (injected by dependency)

        Returns:
            File download response

        Raises:
            HTTPException: If file not found or unauthorized
        """
        # Verify user is requesting their own session's attachments
        if session.session_id != session_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied. You can only download your own attachments.",
            )

        filepath = settings.email_temp_dir / f"web_{session_id}" / filename

        if not filepath.exists():
            raise HTTPException(status_code=404, detail="Attachment not found")

        # Determine content type
        content_type = "application/octet-stream"
        if filename.endswith(".ics"):
            content_type = "text/calendar"
        elif filename.endswith(".csv"):
            content_type = "text/csv"
        elif filename.endswith(".json"):
            content_type = "application/json"

        return FileResponse(
            filepath,
            media_type=content_type,
            filename=filename,
        )

    return router
