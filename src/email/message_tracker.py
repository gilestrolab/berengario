"""
Message tracking interface for email processing.

This module provides a high-level interface for tracking processed emails
and maintaining processing statistics. Prevents duplicate processing and
provides monitoring capabilities.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Dict, Optional

from sqlalchemy import func

from src.email.db_manager import db_manager
from src.email.db_models import ProcessedMessage, ProcessingStats

logger = logging.getLogger(__name__)


class MessageTracker:
    """
    Track processed email messages and provide statistics.

    This class provides methods for:
    - Checking if messages have been processed (deduplication)
    - Marking messages as processed
    - Retrieving processing statistics
    - Cleaning up old records
    """

    def __init__(self, auto_init_db: bool = True):
        """
        Initialize message tracker.

        Args:
            auto_init_db: If True, automatically initialize database tables.
                         Set to False for testing with custom database setup.
        """
        if auto_init_db:
            # Ensure database tables exist
            db_manager.init_db()
        logger.info("MessageTracker initialized")

    def is_processed(self, message_id: str) -> bool:
        """
        Check if a message has already been processed.

        Args:
            message_id: Email message ID to check.

        Returns:
            True if message has been processed, False otherwise.
        """
        with db_manager.get_session() as session:
            exists = (
                session.query(ProcessedMessage)
                .filter(ProcessedMessage.message_id == message_id)
                .first()
                is not None
            )
            logger.debug(f"Message {message_id} processed: {exists}")
            return exists

    def mark_processed(
        self,
        message_id: str,
        sender: str,
        subject: Optional[str] = None,
        attachment_count: int = 0,
        chunks_created: int = 0,
        status: str = "success",
        error_message: Optional[str] = None,
    ) -> None:
        """
        Mark a message as processed.

        Args:
            message_id: Email message ID.
            sender: Email address of sender.
            subject: Email subject line.
            attachment_count: Number of attachments in email.
            chunks_created: Number of KB chunks created.
            status: Processing status ('success', 'error', 'skipped').
            error_message: Error details if status is 'error'.

        Raises:
            Exception: If database operation fails.
        """
        with db_manager.get_session() as session:
            # Create processed message record
            message = ProcessedMessage(
                message_id=message_id,
                sender=sender,
                subject=subject,
                attachment_count=attachment_count,
                chunks_created=chunks_created,
                status=status,
                error_message=error_message,
                processed_at=datetime.utcnow(),
            )
            session.add(message)

            # Update daily statistics
            self._update_daily_stats(
                session,
                success=(status == "success"),
                attachment_count=attachment_count,
                chunks_created=chunks_created,
            )

        logger.info(
            f"Marked message {message_id} as processed: "
            f"status={status}, attachments={attachment_count}, chunks={chunks_created}"
        )

    def _update_daily_stats(
        self,
        session,
        success: bool,
        attachment_count: int = 0,
        chunks_created: int = 0,
    ) -> None:
        """
        Update daily processing statistics.

        Args:
            session: Database session (must be active).
            success: Whether processing was successful.
            attachment_count: Number of attachments processed.
            chunks_created: Number of chunks created.
        """
        today = date.today()

        # Get or create today's stats record
        stats = (
            session.query(ProcessingStats).filter(ProcessingStats.date == today).first()
        )

        if stats is None:
            # Create new stats record for today
            stats = ProcessingStats(
                date=today,
                emails_processed=1,
                attachments_processed=attachment_count,
                chunks_created=chunks_created,
                errors_count=0 if success else 1,
            )
            session.add(stats)
        else:
            # Update existing stats
            stats.emails_processed += 1
            stats.attachments_processed += attachment_count
            stats.chunks_created += chunks_created
            if not success:
                stats.errors_count += 1
            stats.last_updated = datetime.utcnow()

    def get_stats(self, days: int = 30) -> Dict:
        """
        Get processing statistics for the last N days.

        Args:
            days: Number of days to include in statistics.

        Returns:
            Dictionary with aggregated statistics.
        """
        cutoff_date = date.today() - timedelta(days=days)

        with db_manager.get_session() as session:
            # Get daily stats
            daily_stats = (
                session.query(ProcessingStats)
                .filter(ProcessingStats.date >= cutoff_date)
                .order_by(ProcessingStats.date.desc())
                .all()
            )

            # Aggregate totals
            total_emails = sum(s.emails_processed for s in daily_stats)
            total_attachments = sum(s.attachments_processed for s in daily_stats)
            total_chunks = sum(s.chunks_created for s in daily_stats)
            total_errors = sum(s.errors_count for s in daily_stats)

            # Get status breakdown from messages
            status_counts = dict(
                session.query(
                    ProcessedMessage.status,
                    func.count(ProcessedMessage.message_id),
                )
                .filter(ProcessedMessage.processed_at >= cutoff_date)
                .group_by(ProcessedMessage.status)
                .all()
            )

            # Get top senders
            top_senders = (
                session.query(
                    ProcessedMessage.sender,
                    func.count(ProcessedMessage.message_id).label("count"),
                )
                .filter(ProcessedMessage.processed_at >= cutoff_date)
                .group_by(ProcessedMessage.sender)
                .order_by(func.count(ProcessedMessage.message_id).desc())
                .limit(5)
                .all()
            )

            return {
                "period_days": days,
                "total_emails": total_emails,
                "total_attachments": total_attachments,
                "total_chunks": total_chunks,
                "total_errors": total_errors,
                "success_rate": (
                    (total_emails - total_errors) / total_emails * 100
                    if total_emails > 0
                    else 0
                ),
                "status_counts": status_counts,
                "top_senders": [
                    {"sender": sender, "count": count} for sender, count in top_senders
                ],
                "daily_stats": [s.to_dict() for s in daily_stats],
            }

    def cleanup_old_records(self, days: int = 90) -> int:
        """
        Delete message records older than specified days.

        Keeps daily statistics but removes detailed message records to
        prevent unbounded database growth.

        Args:
            days: Delete messages older than this many days.

        Returns:
            Number of records deleted.
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with db_manager.get_session() as session:
            deleted = (
                session.query(ProcessedMessage)
                .filter(ProcessedMessage.processed_at < cutoff_date)
                .delete(synchronize_session=False)
            )

        logger.info(f"Cleaned up {deleted} message records older than {days} days")
        return deleted
