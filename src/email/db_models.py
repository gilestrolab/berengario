"""
SQLAlchemy database models for email message tracking.

This module defines the ORM models for tracking processed emails and
processing statistics. Supports both SQLite and MariaDB/MySQL backends.
"""

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Text,
    Date,
    Index,
    ForeignKey,
    Enum,
)
from sqlalchemy.orm import declarative_base, relationship
import enum

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
            "processed_at": (
                self.processed_at.isoformat() if self.processed_at else None
            ),
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
            "last_updated": (
                self.last_updated.isoformat() if self.last_updated else None
            ),
        }


class ChannelType(enum.Enum):
    """Enum for conversation channel types."""

    EMAIL = "email"
    WEBCHAT = "webchat"


class MessageType(enum.Enum):
    """Enum for message types in conversations."""

    QUERY = "query"  # User message
    REPLY = "reply"  # Assistant response


class Conversation(Base):
    """
    Track conversation threads across email and webchat.

    Each conversation represents a thread (email thread or webchat session)
    with multiple messages exchanged between user and assistant.

    Attributes:
        id: Auto-increment primary key
        thread_id: Unique thread identifier (email: Message-ID/References, webchat: session ID)
        sender: User identifier (email address or webchat user ID)
        channel: Source channel (email or webchat)
        created_at: Timestamp when conversation started
        last_message_at: Timestamp of most recent message
        messages: Relationship to ConversationMessage records
    """

    __tablename__ = "conversations"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Thread identification
    thread_id = Column(String(500), nullable=False, unique=True, index=True)

    # User identification
    sender = Column(String(255), nullable=False, index=True)

    # Channel (email or webchat)
    channel = Column(Enum(ChannelType), nullable=False, default=ChannelType.EMAIL)

    # Timestamps
    created_at = Column(DateTime, nullable=False, index=True)
    last_message_at = Column(DateTime, nullable=False)

    # Relationship to messages
    messages = relationship(
        "ConversationMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
    )

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_sender_channel", "sender", "channel"),
        Index("idx_last_message", "last_message_at"),
    )

    def __init__(
        self,
        thread_id: str,
        sender: str,
        channel: ChannelType = ChannelType.EMAIL,
        created_at: Optional[datetime] = None,
        last_message_at: Optional[datetime] = None,
    ):
        """Initialize Conversation with defaults."""
        self.thread_id = thread_id
        self.sender = sender
        self.channel = channel
        now = datetime.utcnow()
        self.created_at = created_at or now
        self.last_message_at = last_message_at or now

    def __repr__(self) -> str:
        """String representation of Conversation."""
        return (
            f"<Conversation(id={self.id}, thread_id='{self.thread_id}', "
            f"sender='{self.sender}', channel='{self.channel.value}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "id": self.id,
            "thread_id": self.thread_id,
            "sender": self.sender,
            "channel": (
                self.channel.value
                if isinstance(self.channel, ChannelType)
                else self.channel
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_message_at": (
                self.last_message_at.isoformat() if self.last_message_at else None
            ),
            "message_count": len(self.messages) if self.messages else 0,
        }


class ConversationMessage(Base):
    """
    Individual messages within a conversation thread.

    Stores each query and reply in a conversation with metadata and
    optional rating for future rating feature.

    Attributes:
        id: Auto-increment primary key
        conversation_id: Foreign key to Conversation
        message_type: Type of message (query or reply)
        content: Message text content
        sender: Who sent this message (email or user ID)
        subject: Email subject (nullable, for email messages)
        timestamp: When message was sent/received
        message_order: Sequential order within conversation
        rating: Optional 1-5 rating for replies (for future rating feature)
        conversation: Relationship to Conversation record
    """

    __tablename__ = "conversation_messages"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign key to conversation
    conversation_id = Column(
        Integer,
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Message metadata
    message_type = Column(Enum(MessageType), nullable=False)
    content = Column(Text, nullable=False)
    sender = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=True)  # For email messages
    timestamp = Column(DateTime, nullable=False, index=True)
    message_order = Column(Integer, nullable=False)  # Sequential order in conversation

    # Rating (1-5, nullable, for future rating feature)
    rating = Column(Integer, nullable=True)

    # Relationship to conversation
    conversation = relationship("Conversation", back_populates="messages")

    # Composite indexes for common queries
    __table_args__ = (
        Index("idx_conversation_order", "conversation_id", "message_order"),
        Index("idx_conversation_timestamp", "conversation_id", "timestamp"),
        Index("idx_message_type", "message_type"),
    )

    def __init__(
        self,
        conversation_id: int,
        message_type: MessageType,
        content: str,
        sender: str,
        subject: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        message_order: int = 0,
        rating: Optional[int] = None,
    ):
        """Initialize ConversationMessage with defaults."""
        self.conversation_id = conversation_id
        self.message_type = message_type
        self.content = content
        self.sender = sender
        self.subject = subject
        self.timestamp = timestamp or datetime.utcnow()
        self.message_order = message_order
        self.rating = rating

    def __repr__(self) -> str:
        """String representation of ConversationMessage."""
        return (
            f"<ConversationMessage(id={self.id}, conversation_id={self.conversation_id}, "
            f"type='{self.message_type.value}', order={self.message_order})>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "message_type": (
                self.message_type.value
                if isinstance(self.message_type, MessageType)
                else self.message_type
            ),
            "content": self.content,
            "sender": self.sender,
            "subject": self.subject,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "message_order": self.message_order,
            "rating": self.rating,
        }


class DocumentDescription(Base):
    """
    Store AI-generated descriptions for ingested documents.

    This model stores 2-sentence summaries of documents for display
    in the admin panel and other UI elements.

    Attributes:
        id: Auto-increment primary key
        file_path: Relative path to the document file
        filename: Name of the file
        description: 2-sentence AI-generated description
        file_size: Size of file in bytes
        file_type: File extension/type (pdf, docx, txt, csv)
        chunk_count: Number of chunks created from this document
        created_at: When the description was generated
        updated_at: When the description was last updated
    """

    __tablename__ = "document_descriptions"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # File identification
    file_path = Column(String(500), nullable=False, unique=True, index=True)
    filename = Column(String(255), nullable=False)

    # Description and metadata
    description = Column(Text, nullable=False)
    file_size = Column(Integer, nullable=True)
    file_type = Column(String(10), nullable=True)
    chunk_count = Column(Integer, nullable=False, default=0)

    # Timestamps
    created_at = Column(DateTime, nullable=False, index=True)
    updated_at = Column(DateTime, nullable=False)

    # Indexes
    __table_args__ = (
        Index("idx_filename", "filename"),
        Index("idx_file_type", "file_type"),
    )

    def __init__(
        self,
        file_path: str,
        filename: str,
        description: str,
        file_size: Optional[int] = None,
        file_type: Optional[str] = None,
        chunk_count: int = 0,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ):
        """Initialize DocumentDescription with defaults."""
        self.file_path = file_path
        self.filename = filename
        self.description = description
        self.file_size = file_size
        self.file_type = file_type
        self.chunk_count = chunk_count
        now = datetime.utcnow()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def __repr__(self) -> str:
        """String representation of DocumentDescription."""
        return (
            f"<DocumentDescription(id={self.id}, filename='{self.filename}', "
            f"chunks={self.chunk_count})>"
        )

    def to_dict(self) -> dict:
        """
        Convert model to dictionary.

        Returns:
            Dictionary representation of the model.
        """
        return {
            "id": self.id,
            "file_path": self.file_path,
            "filename": self.filename,
            "description": self.description,
            "file_size": self.file_size,
            "file_type": self.file_type,
            "chunk_count": self.chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
