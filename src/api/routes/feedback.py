"""
Feedback routes for response rating and comments.

Handles both authenticated web feedback and email-based feedback via tokens.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from src.api.models import FeedbackRequest, FeedbackResponse
from src.api.routes.helpers import get_session_email, resolve_component
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
        return resolve_component(
            component_resolver, session, "conversation_manager", conversation_manager
        )

    def _upsert_feedback(db_session, message_id, is_positive, comment, user_email=None):
        """
        Validate a message and create or update its feedback record.

        Args:
            db_session: Active SQLAlchemy session.
            message_id: ID of the message to rate.
            is_positive: Whether the feedback is positive.
            comment: Optional comment text.
            user_email: Rater's email. If None, derived from the
                message's conversation sender (email-link case).

        Raises:
            HTTPException: On missing message or wrong message type.
        """
        from src.email.db_models import ConversationMessage, ResponseFeedback

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

        if user_email is None:
            user_email = message.conversation.sender

        existing = (
            db_session.query(ResponseFeedback)
            .filter(
                ResponseFeedback.message_id == message_id,
                ResponseFeedback.user_email == user_email,
            )
            .first()
        )

        if existing:
            existing.is_positive = is_positive
            existing.comment = comment
            existing.submitted_at = datetime.utcnow()
            db_session.commit()
            logger.info(f"Updated feedback for message {message_id} from {user_email}")
        else:
            new_feedback = ResponseFeedback(
                message_id=message_id,
                is_positive=is_positive,
                comment=comment,
                user_email=user_email,
                channel=message.conversation.channel,
            )
            db_session.add(new_feedback)
            db_session.commit()
            logger.info(f"Stored feedback for message {message_id} from {user_email}")

    @router.get("/feedback")
    def feedback_page():
        """Serve feedback page for email link clicks."""
        feedback_file = static_dir / "feedback.html"
        if feedback_file.exists():
            return FileResponse(feedback_file)
        raise HTTPException(status_code=404, detail="Feedback page not found")

    @router.post("/api/feedback/email", response_model=FeedbackResponse)
    def submit_email_feedback(
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
            from src.email.email_sender import decode_feedback_token

            token = feedback.get("token")
            message_id = feedback.get("message_id")
            is_positive = feedback.get("is_positive")
            comment = feedback.get("comment")

            if not token or message_id is None:
                raise HTTPException(status_code=400, detail="Missing required fields")

            decoded_message_id, tenant_slug = decode_feedback_token(token)
            if decoded_message_id != message_id:
                raise HTTPException(status_code=400, detail="Invalid feedback token")

            # Resolve the correct conversation manager for the tenant
            cm = conversation_manager
            if tenant_slug and component_resolver:
                try:
                    components = component_resolver._factory.get_components_for_slug(
                        tenant_slug
                    )
                    cm = components.conversation_manager
                except Exception as e:
                    logger.warning(
                        f"Could not resolve tenant '{tenant_slug}' for feedback: {e}"
                    )

            with cm.db_manager.get_session() as db_session:
                _upsert_feedback(db_session, message_id, is_positive, comment)

            return FeedbackResponse(
                success=True, message="Feedback submitted successfully"
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error submitting email feedback: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to submit feedback")

    @router.post("/api/feedback", response_model=FeedbackResponse)
    def submit_feedback(
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
            user_email = get_session_email(session)

            cm = _get_cm(session)
            with cm.db_manager.get_session() as db_session:
                _upsert_feedback(
                    db_session,
                    feedback.message_id,
                    feedback.is_positive,
                    feedback.comment,
                    user_email=user_email,
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
