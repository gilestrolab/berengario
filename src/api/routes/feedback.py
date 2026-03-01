"""
Feedback routes for response rating and comments.

Handles both authenticated web feedback and email-based feedback via tokens.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.api.models import FeedbackRequest, FeedbackResponse
from src.email.conversation_manager import MessageType

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["feedback"])


def create_feedback_router(
    conversation_manager,
    static_dir,
    require_auth,
    component_resolver=None,
):
    """
    Create feedback router with dependency injection.

    Args:
        conversation_manager: Conversation manager instance
        static_dir: Path to static files directory
        require_auth: Authentication dependency function
        component_resolver: ComponentResolver for MT mode (optional)

    Returns:
        Configured APIRouter instance
    """

    def _get_cm(session):
        """Get the conversation manager for this session (MT-aware)."""
        if component_resolver:
            return component_resolver.resolve(session).conversation_manager
        return conversation_manager

    @router.get("/feedback")
    async def feedback_page():
        """Serve feedback page for email link clicks."""
        feedback_file = static_dir / "feedback.html"
        if feedback_file.exists():
            return FileResponse(feedback_file)
        raise HTTPException(status_code=404, detail="Feedback page not found")

    @router.post("/api/feedback/email", response_model=FeedbackResponse)
    async def submit_email_feedback(
        feedback: dict,
    ):
        """
        Submit feedback from email link (no authentication required).

        This endpoint is for users clicking feedback links in emails.
        It validates the token before accepting feedback.

        Args:
            feedback: Dict with token, message_id, is_positive, optional comment

        Returns:
            FeedbackResponse with success status
        """
        try:
            from src.email.db_models import ConversationMessage, ResponseFeedback
            from src.email.email_sender import decode_feedback_token

            # Extract fields
            token = feedback.get("token")
            message_id = feedback.get("message_id")
            is_positive = feedback.get("is_positive")
            comment = feedback.get("comment")

            if not token or message_id is None:
                raise HTTPException(status_code=400, detail="Missing required fields")

            # Decode and validate token
            decoded_message_id = decode_feedback_token(token)
            if decoded_message_id != message_id:
                raise HTTPException(status_code=400, detail="Invalid feedback token")

            # Verify message exists and is a reply
            with conversation_manager.db_manager.get_session() as db_session:
                message = (
                    db_session.query(ConversationMessage)
                    .filter(ConversationMessage.id == message_id)
                    .first()
                )

                if not message:
                    raise HTTPException(status_code=404, detail="Message not found")

                if message.message_type != MessageType.REPLY:
                    raise HTTPException(
                        status_code=400,
                        detail="Can only provide feedback on assistant replies",
                    )

                # Get user email from the conversation
                user_email = message.conversation.sender

                # Check if feedback already exists for this message from this user
                existing_feedback = (
                    db_session.query(ResponseFeedback)
                    .filter(
                        ResponseFeedback.message_id == message_id,
                        ResponseFeedback.user_email == user_email,
                    )
                    .first()
                )

                if existing_feedback:
                    # Update existing feedback
                    existing_feedback.is_positive = is_positive
                    existing_feedback.comment = comment
                    existing_feedback.submitted_at = datetime.utcnow()
                    db_session.commit()
                    logger.info(
                        f"Updated email feedback for message {message_id} from {user_email}"
                    )
                else:
                    # Create new feedback
                    new_feedback = ResponseFeedback(
                        message_id=message_id,
                        is_positive=is_positive,
                        comment=comment,
                        user_email=user_email,
                        channel=message.conversation.channel,
                    )
                    db_session.add(new_feedback)
                    db_session.commit()
                    logger.info(
                        f"Stored email feedback for message {message_id} from {user_email}"
                    )

            return FeedbackResponse(
                success=True, message="Feedback submitted successfully"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting email feedback: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to submit feedback")

    @router.post("/api/feedback", response_model=FeedbackResponse)
    async def submit_feedback(
        feedback: FeedbackRequest,
        session=Depends(require_auth),
    ):
        """
        Submit feedback on an assistant response.

        Requires authentication.

        Args:
            feedback: Feedback data (message_id, is_positive, optional comment)
            session: Authenticated session (injected by dependency)

        Returns:
            FeedbackResponse with success status
        """
        try:
            from src.email.db_models import ConversationMessage, ResponseFeedback

            # Get user email from session
            user_email = (
                session.email
                if hasattr(session, "email") and session.email
                else f"web_user_{session.session_id[:8]}"
            )

            # Verify message exists and is a reply
            cm = _get_cm(session)
            with cm.db_manager.get_session() as db_session:
                message = (
                    db_session.query(ConversationMessage)
                    .filter(ConversationMessage.id == feedback.message_id)
                    .first()
                )

                if not message:
                    raise HTTPException(status_code=404, detail="Message not found")

                if message.message_type != MessageType.REPLY:
                    raise HTTPException(
                        status_code=400,
                        detail="Can only provide feedback on assistant replies",
                    )

                # Check if feedback already exists for this message from this user
                existing_feedback = (
                    db_session.query(ResponseFeedback)
                    .filter(
                        ResponseFeedback.message_id == feedback.message_id,
                        ResponseFeedback.user_email == user_email,
                    )
                    .first()
                )

                if existing_feedback:
                    # Update existing feedback
                    existing_feedback.is_positive = feedback.is_positive
                    existing_feedback.comment = feedback.comment
                    existing_feedback.submitted_at = datetime.utcnow()
                    db_session.commit()
                    logger.info(
                        f"Updated feedback for message {feedback.message_id} from {user_email}"
                    )
                else:
                    # Create new feedback
                    new_feedback = ResponseFeedback(
                        message_id=feedback.message_id,
                        is_positive=feedback.is_positive,
                        comment=feedback.comment,
                        user_email=user_email,
                        channel=message.conversation.channel,
                    )
                    db_session.add(new_feedback)
                    db_session.commit()
                    logger.info(
                        f"Stored feedback for message {feedback.message_id} from {user_email}"
                    )

            return FeedbackResponse(
                success=True, message="Feedback submitted successfully"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting feedback: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to submit feedback")

    return router
