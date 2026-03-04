"""
Platform database models for multi-tenancy.

These models live in the shared platform database and manage tenant
registration, user-to-tenant mappings, and encryption keys.
Separate from per-tenant models in src/email/db_models.py.
"""

import enum
import random
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

# Separate Base for platform models (different database than tenant models)
PlatformBase = declarative_base()


class TenantStatus(enum.Enum):
    """Tenant lifecycle states."""

    PROVISIONING = "provisioning"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class TenantUserRole(enum.Enum):
    """User roles within a tenant."""

    ADMIN = "admin"
    TEACHER = "teacher"
    QUERIER = "querier"


def generate_uuid() -> str:
    """Generate a new UUID string."""
    return str(uuid.uuid4())


class Tenant(PlatformBase):
    """
    Organization/tenant registry.

    Each tenant represents one organization using the platform.
    Stores configuration that was previously in .env files and
    whitelist text files.

    Attributes:
        id: UUID primary key
        slug: URL-safe identifier (e.g., "acme", "my-team")
        name: Human-readable organization name
        description: Used in RAG system prompt
        organization: Organization name for display
        status: Lifecycle state (provisioning, active, suspended)
        email_address: Tenant's email (e.g., "acme@berengar.io")
        email_display_name: Display name for sent emails
        custom_prompt: Custom RAG system prompt additions
        email_footer: Custom email footer text
        chunk_size: Document chunking size
        chunk_overlap: Document chunk overlap
        top_k_retrieval: Number of chunks to retrieve
        similarity_threshold: Minimum similarity score
        llm_model: Per-tenant LLM model override
        db_name: Tenant's database name
        storage_path: Tenant's storage path/bucket
        created_at: When tenant was created
        updated_at: When tenant was last updated
    """

    __tablename__ = "tenants"

    # Primary key
    id = Column(String(36), primary_key=True, default=generate_uuid)

    # Identification
    slug = Column(String(63), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    organization = Column(String(255), nullable=True)
    status = Column(
        Enum(TenantStatus),
        nullable=False,
        default=TenantStatus.PROVISIONING,
        index=True,
    )

    # Email config
    email_address = Column(String(255), unique=True, nullable=False)
    email_display_name = Column(String(255), nullable=True)

    # RAG config (per-tenant overrides, all nullable to fall back to defaults)
    custom_prompt = Column(Text, nullable=True)
    email_footer = Column(Text, nullable=True)
    chunk_size = Column(Integer, default=1024)
    chunk_overlap = Column(Integer, default=200)
    top_k_retrieval = Column(Integer, default=5)
    similarity_threshold = Column(Float, default=0.7)

    # LLM config
    llm_model = Column(String(255), nullable=True)

    # Invite / join settings
    invite_code = Column(String(12), unique=True, nullable=True, index=True)
    join_approval_required = Column(Boolean, default=False, nullable=False)

    # Infrastructure references
    db_name = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    users = relationship(
        "TenantUser",
        back_populates="tenant",
        cascade="all, delete-orphan",
    )
    encryption_key = relationship(
        "TenantEncryptionKey",
        back_populates="tenant",
        uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_tenant_status", "status"),
        Index("idx_tenant_email", "email_address"),
        Index("idx_tenant_invite_code", "invite_code"),
    )

    # Characters excluding ambiguous ones: O/0, I/1/L
    _INVITE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"

    @staticmethod
    def generate_invite_code(length: int = 8) -> str:
        """
        Generate a random invite code using unambiguous characters.

        Args:
            length: Code length (default 8).

        Returns:
            Random invite code string.
        """
        return "".join(random.choices(Tenant._INVITE_ALPHABET, k=length))

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<Tenant(id='{self.id}', slug='{self.slug}', "
            f"name='{self.name}', status='{self.status.value}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert to dictionary for API responses.

        Returns:
            Dictionary representation (excludes sensitive fields).
        """
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "description": self.description,
            "organization": self.organization,
            "status": (
                self.status.value
                if isinstance(self.status, TenantStatus)
                else self.status
            ),
            "email_address": self.email_address,
            "email_display_name": self.email_display_name,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "top_k_retrieval": self.top_k_retrieval,
            "similarity_threshold": self.similarity_threshold,
            "llm_model": self.llm_model,
            "invite_code": self.invite_code,
            "join_approval_required": self.join_approval_required,
            "db_name": self.db_name,
            "storage_path": self.storage_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "user_count": len(self.users) if self.users else 0,
        }


class TenantUser(PlatformBase):
    """
    Maps users to tenants with roles.

    Replaces file-based whitelists (allowed_teachers.txt, allowed_queriers.txt).
    One user can have one role per tenant, but can belong to multiple tenants.

    Role hierarchy: admin > teacher > querier
    - admin: Full access (teach + query + admin panel)
    - teacher: Can add content to KB and query
    - querier: Can only query the KB

    Attributes:
        id: Auto-increment primary key
        email: User's email address
        tenant_id: Foreign key to tenant
        role: User's role in this tenant
        created_at: When user was added
    """

    __tablename__ = "tenant_users"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # User identification
    email = Column(String(255), nullable=False, index=True)

    # Tenant association
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Role
    role = Column(Enum(TenantUserRole), nullable=False, default=TenantUserRole.QUERIER)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")

    __table_args__ = (
        UniqueConstraint("email", "tenant_id", name="uq_user_tenant"),
        Index("idx_user_email", "email"),
        Index("idx_user_tenant", "tenant_id"),
        Index("idx_user_role", "tenant_id", "role"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<TenantUser(id={self.id}, email='{self.email}', "
            f"tenant_id='{self.tenant_id}', role='{self.role.value}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert to dictionary for API responses.

        Returns:
            Dictionary representation.
        """
        return {
            "id": self.id,
            "email": self.email,
            "tenant_id": self.tenant_id,
            "role": (
                self.role.value if isinstance(self.role, TenantUserRole) else self.role
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JoinRequestStatus(enum.Enum):
    """Status of a tenant join request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JoinRequest(PlatformBase):
    """
    Tracks requests to join a tenant (when approval is required).

    Created when a user tries to join a tenant that has
    join_approval_required=True. Admins can approve or reject.

    Attributes:
        id: Auto-increment primary key
        email: Requesting user's email
        tenant_id: Target tenant
        status: Request status (pending, approved, rejected)
        created_at: When request was created
        resolved_at: When request was approved/rejected
        resolved_by: Admin email who resolved the request
    """

    __tablename__ = "join_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), nullable=False, index=True)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(
        Enum(JoinRequestStatus),
        nullable=False,
        default=JoinRequestStatus.PENDING,
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(255), nullable=True)

    # Relationships
    tenant = relationship("Tenant")

    __table_args__ = (
        Index("idx_join_request_email", "email"),
        Index("idx_join_request_tenant", "tenant_id"),
        Index("idx_join_request_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<JoinRequest(id={self.id}, email='{self.email}', "
            f"tenant_id='{self.tenant_id}', status='{self.status.value}')>"
        )

    def to_dict(self) -> dict:
        """
        Convert to dictionary for API responses.

        Returns:
            Dictionary representation.
        """
        return {
            "id": self.id,
            "email": self.email,
            "tenant_id": self.tenant_id,
            "status": (
                self.status.value
                if isinstance(self.status, JoinRequestStatus)
                else self.status
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "resolved_at": (self.resolved_at.isoformat() if self.resolved_at else None),
            "resolved_by": self.resolved_by,
        }


class TenantEncryptionKey(PlatformBase):
    """
    Stores per-tenant encryption keys (encrypted with master key).

    Uses envelope encryption: each tenant has a unique Tenant Encryption Key (TEK)
    which is itself encrypted by the Master Encryption Key (MEK) from environment.

    Attributes:
        id: Auto-increment primary key
        tenant_id: Foreign key to tenant (one-to-one)
        encrypted_key: TEK encrypted with MEK (Fernet)
        key_version: Key version for rotation support
        created_at: When key was created
        rotated_at: When key was last rotated
    """

    __tablename__ = "tenant_encryption_keys"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Tenant association (one-to-one)
    tenant_id = Column(
        String(36),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Encrypted key material
    encrypted_key = Column(LargeBinary, nullable=False)

    # Key metadata
    key_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    rotated_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="encryption_key")

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"<TenantEncryptionKey(tenant_id='{self.tenant_id}', "
            f"version={self.key_version})>"
        )
