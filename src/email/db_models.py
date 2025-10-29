"""
SQLAlchemy database models for email message tracking.

This module defines the ORM models for tracking processed emails and
processing statistics. Supports both SQLite and MariaDB/MySQL backends.
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import Column, String, Integer, DateTime, Text, Date, Index
from sqlalchemy.orm import declarative_base

# Base class for all models
Base = declarative_base()


class ProcessedMessage(Base):
    """
    Track processed email messages to prevent duplicate processing.

    This model stores metadata about each processed email including
    sender, subject, processing status, and statistics about attachments
    and knowledge base chunks created.

    Attributes:
        message_id: Unique email message ID (RFC822 Message-ID header)
        sender: Email address of sender
        subject: Email subject line
        processed_at: Timestamp when message was processed
        status: Processing status ('success', 'error', 'skipped')
        error_message: Error details if processing failed
        attachment_count: Number of attachments in email
        chunks_created: Number of KB chunks created from this email
    """

    __tablename__ = "processed_messages"

    # Primary key: Email Message-ID
    message_id = Column(String(255), primary_key=True, nullable=False)

    # Email metadata
    sender = Column(String(255), nullable=False, index=True)
    subject = Column(String(500), nullable=True)

    # Processing metadata
    processed_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(50), nullable=False)
    error_message = Column(Text, nullable=True)

    # Statistics
    attachment_count = Column(Integer, nullable=False)
    chunks_created = Column(Integer, nullable=False)

    def __init__(
        self,
        message_id: str,
        sender: str,
        subject: Optional[str] = None,
        processed_at: Optional[datetime] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        attachment_count: int = 0,
        chunks_created: int = 0,
    ):
        """Initialize ProcessedMessage with defaults."""
        self.message_id = message_id
        self.sender = sender
        self.subject = subject
        self.processed_at = processed_at or datetime.utcnow()
        self.status = status
        self.error_message = error_message
        self.attachment_count = attachment_count
        self.chunks_created = chunks_created

    # Composite indexes for common queries
    __table_args__ = (
        # Query by sender and date
        Index("idx_sender_date", "sender", "processed_at"),
        # Query by status
        Index("idx_status", "status"),
    )

    def __repr__(self) -> str:
        """String representation of ProcessedMessage."""
        return (
            f"<ProcessedMessage(message_id='{self.message_id}', "
            f"sender='{self.sender}', status='{self.status}', "
            f"processed_at='{self.processed_at}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "subject": self.subject,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "attachment_count": self.attachment_count,
            "chunks_created": self.chunks_created,
        }


class ProcessingStats(Base):
    """
    Aggregated daily statistics for email processing.

    This model tracks daily aggregated statistics for monitoring and
    reporting purposes. One record per day.

    Attributes:
        id: Auto-increment primary key
        date: Date for these statistics (unique)
        emails_processed: Total emails processed on this date
        attachments_processed: Total attachments processed
        chunks_created: Total KB chunks created
        errors_count: Number of processing errors
        last_updated: Timestamp of last update to this record
    """

    __tablename__ = "processing_stats"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Date for statistics (one record per day)
    date = Column(Date, nullable=False, unique=True, index=True)

    # Daily statistics
    emails_processed = Column(Integer, nullable=False)
    attachments_processed = Column(Integer, nullable=False)
    chunks_created = Column(Integer, nullable=False)
    errors_count = Column(Integer, nullable=False)

    # Metadata
    last_updated = Column(DateTime, nullable=False)

    def __init__(
        self,
        date: date,
        emails_processed: int = 0,
        attachments_processed: int = 0,
        chunks_created: int = 0,
        errors_count: int = 0,
        last_updated: Optional[datetime] = None,
    ):
        """Initialize ProcessingStats with defaults."""
        self.date = date
        self.emails_processed = emails_processed
        self.attachments_processed = attachments_processed
        self.chunks_created = chunks_created
        self.errors_count = errors_count
        self.last_updated = last_updated or datetime.utcnow()

    def __repr__(self) -> str:
        """String representation of ProcessingStats."""
        return (
            f"<ProcessingStats(date='{self.date}', "
            f"emails={self.emails_processed}, "
            f"chunks={self.chunks_created}, "
            f"errors={self.errors_count})>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "id": self.id,
            "date": self.date.isoformat() if self.date else None,
            "emails_processed": self.emails_processed,
            "attachments_processed": self.attachments_processed,
            "chunks_created": self.chunks_created,
            "errors_count": self.errors_count,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }
