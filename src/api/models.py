"""
Pydantic models for API request/response schemas.

This module contains all data models used by the FastAPI endpoints,
organized by functional area.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr

# ============================================================================
# Query Models
# ============================================================================


class QueryRequest(BaseModel):
    """Request model for query endpoint."""

    query: str
    conversation_id: Optional[int] = None  # To continue existing conversation
    context: Optional[Dict] = None


class QueryResponse(BaseModel):
    """Response model for query endpoint."""

    success: bool
    response: Optional[str] = None
    sources: Optional[List[Dict]] = None
    attachments: Optional[List[Dict]] = None
    error: Optional[str] = None
    timestamp: str
    session_id: str
    message_id: Optional[int] = None  # Database ID of reply message for feedback


# ============================================================================
# Feedback Models
# ============================================================================


class FeedbackRequest(BaseModel):
    """Request model for feedback submission."""

    message_id: int
    is_positive: bool
    comment: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Response model for feedback submission."""

    success: bool
    message: str


# ============================================================================
# History Models
# ============================================================================


class HistoryResponse(BaseModel):
    """Response model for history endpoint."""

    session_id: str
    messages: List[Dict]
    created_at: str
    last_activity: str


class StatsResponse(BaseModel):
    """Response model for KB stats endpoint."""

    total_chunks: int
    unique_documents: int
    documents: List[str]


# ============================================================================
# Conversation Models
# ============================================================================


class ConversationListItem(BaseModel):
    """Single conversation item in list."""

    id: int
    thread_id: str
    channel: str
    sender: str
    created_at: str
    last_message_at: str
    message_count: int
    preview: Optional[str] = None
    subject: Optional[str] = None


class ConversationsResponse(BaseModel):
    """Response model for conversations list."""

    conversations: List[ConversationListItem]
    total_count: int


class ConversationMessagesResponse(BaseModel):
    """Response model for conversation messages."""

    conversation_id: int
    thread_id: str
    channel: str
    messages: List[Dict]


class ConversationSearchResponse(BaseModel):
    """Response model for conversation search."""

    results: List[ConversationListItem]
    query: str
    total_results: int


# ============================================================================
# Authentication Models
# ============================================================================


class OTPRequest(BaseModel):
    """Request model for OTP generation."""

    email: EmailStr


class OTPVerifyRequest(BaseModel):
    """Request model for OTP verification."""

    email: EmailStr
    otp_code: str


class AuthResponse(BaseModel):
    """Response model for authentication operations."""

    success: bool
    message: str
    email: Optional[str] = None


class AuthStatusResponse(BaseModel):
    """Response model for authentication status."""

    authenticated: bool
    email: Optional[str] = None
    session_id: Optional[str] = None
    is_admin: bool = False


@dataclass
class OTPEntry:
    """
    OTP entry with expiration and attempt tracking.

    Attributes:
        code: 6-digit OTP code
        email: Email address
        created_at: Creation timestamp
        expires_at: Expiration timestamp
        attempts: Number of verification attempts
        max_attempts: Maximum allowed attempts
    """

    code: str
    email: str
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: datetime = field(
        default_factory=lambda: datetime.now() + timedelta(minutes=5)
    )
    attempts: int = 0
    max_attempts: int = 5

    def is_expired(self) -> bool:
        """Check if OTP has expired."""
        return datetime.now() > self.expires_at

    def is_locked(self) -> bool:
        """Check if maximum attempts reached."""
        return self.attempts >= self.max_attempts

    def increment_attempts(self) -> None:
        """Increment verification attempts."""
        self.attempts += 1


# ============================================================================
# Admin Models
# ============================================================================


class WhitelistEntryRequest(BaseModel):
    """Request model for whitelist entry operations."""

    entry: str


class WhitelistResponse(BaseModel):
    """Response model for whitelist data."""

    entries: List[str]
    whitelist_type: str


class AdminActionResponse(BaseModel):
    """Response model for admin actions."""

    success: bool
    message: str
    details: Optional[Dict] = None


class DocumentListResponse(BaseModel):
    """Response model for document list."""

    documents: List[Dict]
    total_count: int


class DocumentDeleteRequest(BaseModel):
    """Request model for document deletion."""

    file_hash: str
    archive: bool = True


# ============================================================================
# Analytics Models
# ============================================================================


class UsageAnalyticsResponse(BaseModel):
    """Response model for usage analytics."""

    date_range: Dict[str, str]
    overview: Dict
    daily_stats: List[Dict]
    user_activity: List[Dict]
    channel_breakdown: Dict[str, int]


class UserQueriesResponse(BaseModel):
    """Response model for user query details."""

    sender: str
    queries: List[Dict]
    total_count: int


class FeedbackAnalyticsResponse(BaseModel):
    """Response model for feedback analytics."""

    date_range: Dict[str, str]
    overview: Dict  # total_feedback, positive_count, negative_count, positive_rate
    negative_responses: List[Dict]  # Low-rated responses with details


class TopicClusteringResponse(BaseModel):
    """Response model for topic clustering."""

    topics: List[Dict]
    total_queries: int
    clustered_queries: int


# ============================================================================
# Crawling Models
# ============================================================================


class CrawlRequest(BaseModel):
    """Request model for URL crawling."""

    url: str
    crawl_depth: int = 1


class CrawledUrlResponse(BaseModel):
    """Response model for crawled URL list."""

    urls: List[Dict]
    total_count: int
