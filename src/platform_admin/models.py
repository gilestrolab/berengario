"""
Pydantic models for the platform admin API.

Request/response models for tenant management, auth, and health endpoints.
"""

from datetime import UTC, datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field

# ============================================================================
# Authentication Models
# ============================================================================


class AdminOTPRequest(BaseModel):
    """Request model for admin OTP generation."""

    email: EmailStr


class AdminOTPVerifyRequest(BaseModel):
    """Request model for admin OTP verification."""

    email: EmailStr
    otp_code: str


class AdminAuthResponse(BaseModel):
    """Response model for admin auth operations."""

    success: bool
    message: str
    email: Optional[str] = None


class AdminAuthStatus(BaseModel):
    """Response model for admin auth status check."""

    authenticated: bool
    email: Optional[str] = None


# ============================================================================
# Tenant Models
# ============================================================================


class TenantCreateRequest(BaseModel):
    """Request model for creating a new tenant."""

    slug: str = Field(
        ..., min_length=2, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*[a-z0-9]$"
    )
    name: str = Field(..., min_length=1, max_length=200)
    admin_email: EmailStr
    description: Optional[str] = None
    organization: Optional[str] = None
    custom_prompt: Optional[str] = None
    llm_model: Optional[str] = None


class TenantUserRequest(BaseModel):
    """Request model for adding a user to a tenant."""

    email: EmailStr
    role: str = Field(default="querier", pattern=r"^(admin|teacher|querier)$")


class TenantUserResponse(BaseModel):
    """Response model for a tenant user."""

    id: int
    email: str
    role: str
    tenant_id: str
    created_at: str


class TenantSummary(BaseModel):
    """Summary model for tenant listing."""

    id: str
    slug: str
    name: str
    status: str
    organization: Optional[str] = None
    email_address: str
    user_count: int
    created_at: str


class TenantDetail(BaseModel):
    """Detailed model for a single tenant."""

    id: str
    slug: str
    name: str
    description: Optional[str] = None
    organization: Optional[str] = None
    status: str
    email_address: str
    email_display_name: Optional[str] = None
    db_name: str
    storage_path: str
    db_healthy: bool
    user_count: int
    users: List[TenantUserResponse]
    chunk_size: int
    chunk_overlap: int
    top_k_retrieval: int
    similarity_threshold: float
    llm_model: Optional[str] = None
    invite_code: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


# ============================================================================
# Usage / Stats Models
# ============================================================================


class TenantStats(BaseModel):
    """Usage statistics for a single tenant."""

    slug: str
    # Query stats
    total_queries: int = 0
    total_replies: int = 0
    total_conversations: int = 0
    unique_users: int = 0
    # Document stats
    total_documents: int = 0
    total_chunks: int = 0
    documents_by_type: dict = Field(default_factory=dict)
    total_document_bytes: int = 0
    # Storage
    disk_usage_bytes: int = 0
    disk_usage_human: str = ""
    # Feedback
    total_feedback: int = 0
    positive_feedback: int = 0
    # Email processing
    emails_processed: int = 0
    emails_errors: int = 0
    # Time range
    first_activity: Optional[str] = None
    last_activity: Optional[str] = None


# ============================================================================
# Health Models
# ============================================================================


class PlatformHealth(BaseModel):
    """Response model for platform health check."""

    status: str
    platform_db: bool
    cache_stats: dict
    tenant_counts: dict
    encryption_enabled: bool
    storage_backend: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
