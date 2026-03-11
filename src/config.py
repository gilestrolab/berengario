"""
Configuration management for Berengario.

This module uses Pydantic Settings to load and validate configuration
from environment variables. Supports multiple instances with different configurations.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All settings can be overridden via .env file or environment variables.
    Supports instance-specific configuration for multi-tenant deployments.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Instance Configuration (customizable per deployment)
    instance_name: str = Field(
        default="Berengario", description="Name of this instance"
    )
    instance_description: str = Field(
        default="AI-powered Knowledge Base Assistant",
        description="Description of this instance",
    )
    organization: str = Field(default="", description="Organization name (optional)")
    web_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for web interface (used in email links)",
    )
    allowed_origins: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins (* for all, or specific domains)",
    )

    # OpenAI Configuration (for embeddings via Naga.ac)
    openai_api_key: str = Field(..., description="OpenAI API key (or Naga.ac)")
    openai_api_base: str = Field(
        default="https://api.openai.com/v1",
        description="API base URL (use https://api.naga.ac/v1 for Naga)",
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model"
    )

    # OpenRouter Configuration (for LLM queries)
    openrouter_api_key: str = Field(..., description="OpenRouter API key for LLM")
    openrouter_api_base: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )
    openrouter_model: str = Field(
        default="anthropic/claude-3.5-sonnet", description="OpenRouter model"
    )
    openrouter_fallback_model: Optional[str] = Field(
        default=None,
        description="Fallback LLM model if primary model fails (e.g. overloaded)",
    )

    # Email Configuration - Inbox (IMAP)
    imap_server: str = Field(
        default="imap.gmail.com", description="IMAP server address"
    )
    imap_port: int = Field(default=993, description="IMAP server port")
    imap_user: str = Field(..., description="IMAP username/email")
    imap_password: str = Field(..., description="IMAP password")
    imap_use_ssl: bool = Field(default=True, description="Use SSL for IMAP")

    # Email Configuration - Sending (SMTP)
    smtp_server: str = Field(
        default="smtp.gmail.com", description="SMTP server address"
    )
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(..., description="SMTP username/email")
    smtp_password: str = Field(..., description="SMTP password")
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP")

    # Email Processing
    email_check_interval: int = Field(
        default=300, description="Seconds between email checks"
    )
    email_target_address: str = Field(
        ..., description="Target email address for the bot"
    )
    email_display_name: str = Field(
        default="Berengario", description="Display name for sent emails"
    )
    email_temp_dir: Path = Field(
        default=Path("data/temp_attachments"),
        description="Temporary directory for email attachments",
    )
    max_attachment_size: int = Field(
        default=10485760, description="Maximum attachment size in bytes (10MB default)"
    )

    # Dedicated Teach Address
    email_teach_address: Optional[str] = Field(
        default=None,
        description="Dedicated email address for KB ingestion (e.g., teach@berengar.io). "
        "Emails addressed to this address are always treated as teaching, not queries.",
    )

    # Welcome Emails
    welcome_email_enabled: bool = Field(
        default=True,
        description="Send welcome emails when users are added to a team",
    )

    # Forwarded Email Detection
    forward_to_kb_enabled: bool = Field(
        default=True,
        description="Treat forwarded emails (To: bot) as KB content instead of queries",
    )
    forward_subject_prefixes: str = Field(
        default="fw,fwd",
        description="Comma-separated case-insensitive subject prefixes for forwarded emails",
    )

    # Database Configuration (MariaDB — used for message tracking + platform)
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=3306, description="Database port")
    db_name: str = Field(default="berengario", description="Database name")
    db_user: str = Field(default="berengario", description="Database username")
    db_password: str = Field(default="", description="Database password")
    db_pool_size: int = Field(default=5, description="Connection pool size")
    db_pool_recycle: int = Field(
        default=3600, description="Recycle connections after N seconds"
    )

    # Document Processing
    documents_path: Path = Field(
        default=Path("data/kb/documents"),
        description="Path to documents folder (watched by FileWatcher)",
    )
    chroma_db_path: Path = Field(
        default=Path("data/chroma_db"), description="Path to ChromaDB storage"
    )

    # Knowledge Base Structure
    kb_documents_path: Path = Field(
        default=Path("data/kb/documents"),
        description="Path to KB documents (attachments and uploads)",
    )
    kb_emails_path: Path = Field(
        default=Path("data/kb/emails"),
        description="Path to saved email copies (without attachments)",
    )

    # RAG Configuration
    chunk_size: int = Field(default=1024, description="Document chunk size")
    chunk_overlap: int = Field(default=200, description="Chunk overlap size")
    top_k_retrieval: int = Field(default=5, description="Number of chunks to retrieve")
    similarity_threshold: float = Field(
        default=0.7, description="Minimum similarity score for retrieval"
    )

    # Web Crawling Configuration
    crawl_timeout: int = Field(
        default=30, description="Request timeout for web crawling (seconds)"
    )
    crawl_max_size_mb: int = Field(
        default=10, description="Maximum page size for crawling (megabytes)"
    )
    crawl_delay: float = Field(
        default=1.0, description="Delay between crawl requests (seconds)"
    )
    crawl_max_pages: int = Field(
        default=50, description="Maximum pages to crawl per URL"
    )

    # RAG Customization
    rag_custom_prompt_file: Optional[Path] = Field(
        default=None,
        description="Path to custom system prompt additions (appended to base prompt)",
    )

    # Query Optimization Configuration
    query_optimization_enabled: bool = Field(
        default=True,
        description="Enable LLM-based query optimization to improve RAG retrieval accuracy",
    )
    query_optimization_model: Optional[str] = Field(
        default=None,
        description="Model to use for query optimization (default: same as openrouter_model)",
    )
    query_optimization_max_tokens: int = Field(
        default=500,
        description="Maximum tokens for query optimization response",
    )
    query_optimization_temperature: float = Field(
        default=0.3,
        description="Temperature for query optimization (lower = more deterministic)",
    )
    query_optimization_timeout: int = Field(
        default=10,
        description="API timeout for query optimization in seconds",
    )

    # Reranking Configuration (Cohere API)
    reranking_enabled: bool = Field(
        default=True, description="Enable Cohere reranking of retrieved chunks"
    )
    cohere_api_key: str = Field(default="", description="Cohere API key for reranking")
    reranking_model: str = Field(
        default="rerank-v3.5", description="Cohere reranking model"
    )
    reranking_top_n: Optional[int] = Field(
        default=None,
        description="Override top_n for reranker (defaults to top_k_retrieval)",
    )

    # Hybrid Search Configuration
    hybrid_search_enabled: bool = Field(
        default=True,
        description="Enable BM25 + vector hybrid search with Reciprocal Rank Fusion",
    )

    # Contextual Enrichment Configuration
    contextual_enrichment_enabled: bool = Field(
        default=True,
        description="Enable contextual headers on all document chunks",
    )

    # Document Enhancement Configuration
    doc_enhancement_enabled: bool = Field(
        default=True,
        description="Enable LLM-based document enhancement for structured data (CSV/Excel)",
    )
    doc_enhancement_model: Optional[str] = Field(
        default=None,
        description="Model to use for document enhancement (default: same as openrouter_model)",
    )
    doc_enhancement_max_tokens: int = Field(
        default=4000,
        description="Maximum tokens to use for document enhancement",
    )
    doc_enhancement_types: str = Field(
        default="narrative,qa",
        description="Comma-separated enhancement types: narrative, qa",
    )

    # Email Response Customization
    email_response_format: str = Field(
        default="html",
        description="Email response format: 'text', 'markdown', or 'html'",
    )
    email_custom_footer_file: Optional[Path] = Field(
        default=None,
        description="Path to custom email footer text (replaces default footer)",
    )

    # Web Search Configuration (Phase 2 - Agent Enhancement)
    web_search_max_results: int = Field(
        default=10,
        description="Maximum number of web search results to return per query",
    )

    # Web API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host address")
    api_port: int = Field(default=8000, description="API port")
    api_reload: bool = Field(default=False, description="Auto-reload on code changes")
    cors_origins: List[str] = Field(
        default=["http://localhost:8000"], description="Allowed CORS origins"
    )
    web_session_timeout: int = Field(
        default=86400, description="Web session timeout in seconds (default 24 hours)"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path = Field(
        default=Path("data/logs/berengario.log"), description="Log file path"
    )

    # Multi-Tenancy Configuration
    multi_tenant: bool = Field(
        default=False,
        description="Enable multi-tenant features (tenant creation, onboarding, platform admin). "
        "Both modes use TenantUser DB for permissions; ST auto-provisions a default tenant.",
    )
    platform_domain: str = Field(
        default="berengar.io",
        description="Platform domain for tenant email addresses ({slug}@{domain})",
    )
    platform_base_url: str = Field(
        default="https://berengar.io",
        description="Base URL for the platform (used in invite QR codes)",
    )

    # Platform Database (shared across all tenants, only used in multi-tenant mode)
    # Host/port/user/password default to their db_* counterparts when not set.
    platform_db_host: Optional[str] = Field(
        default=None, description="Platform database host (defaults to db_host)"
    )
    platform_db_port: Optional[int] = Field(
        default=None, description="Platform database port (defaults to db_port)"
    )
    platform_db_name: str = Field(
        default="berengario_platform", description="Platform database name"
    )
    platform_db_user: Optional[str] = Field(
        default=None, description="Platform database username (defaults to db_user)"
    )
    platform_db_password: Optional[str] = Field(
        default=None,
        description="Platform database password (defaults to db_password)",
    )

    # Object Storage (S3-compatible, for multi-tenant file storage)
    storage_backend: str = Field(
        default="local",
        description="Storage backend: 'local' (filesystem) or 's3' (S3/MinIO)",
    )
    s3_endpoint_url: str = Field(
        default="http://localhost:9000",
        description="S3-compatible endpoint URL (MinIO, AWS S3, etc.)",
    )
    s3_access_key: str = Field(default="", description="S3 access key ID")
    s3_secret_key: str = Field(default="", description="S3 secret access key")
    s3_region: str = Field(default="us-east-1", description="S3 region")
    s3_bucket_name: str = Field(
        default="",
        description="Single S3 bucket name (tenant data separated by key prefixes). "
        "If set, overrides s3_bucket_prefix.",
    )
    s3_bucket_prefix: str = Field(
        default="berengario-tenant-",
        description="Prefix for per-tenant S3 buckets (ignored if s3_bucket_name is set)",
    )

    # Paddle Billing
    paddle_api_key: str = Field(
        default="", description="Paddle API key for server-side API calls"
    )
    paddle_environment: str = Field(
        default="sandbox",
        description="Paddle environment: 'sandbox' or 'production'",
    )
    paddle_client_token: str = Field(
        default="", description="Paddle client-side token for Paddle.js"
    )
    paddle_webhook_secret: str = Field(
        default="", description="Paddle webhook signature verification secret"
    )
    paddle_price_id_lite: str = Field(
        default="", description="Paddle price ID for Lite plan"
    )
    paddle_price_id_team: str = Field(
        default="", description="Paddle price ID for Team plan"
    )
    paddle_price_id_department: str = Field(
        default="", description="Paddle price ID for Department plan"
    )
    trial_duration_days: int = Field(
        default=90, description="Trial duration in days for new tenants"
    )

    # Platform Admin
    platform_admin_emails: str = Field(
        default="",
        description="Comma-separated emails allowed to access platform admin panel",
    )

    # Encryption (per-tenant data encryption)
    master_encryption_key: str = Field(
        default="",
        description="Master Encryption Key (MEK) for encrypting per-tenant keys. "
        'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"',
    )

    # Tenant Database Pool Configuration
    tenant_db_pool_size: int = Field(
        default=3, description="Connection pool size per tenant database"
    )
    tenant_db_max_cached: int = Field(
        default=50,
        description="Maximum number of tenant DB connections to keep in LRU cache",
    )

    # Development
    debug: bool = Field(default=False, description="Enable debug mode")
    disable_otp_for_dev: bool = Field(
        default=False,
        description="SECURITY WARNING: Disable OTP authentication for development. "
        "DO NOT enable in production! When enabled, any login attempt will succeed "
        "without requiring email verification.",
    )

    @model_validator(mode="after")
    def _platform_db_defaults(self) -> "Settings":
        """Default platform_db_* to db_* values when not explicitly set."""
        if self.platform_db_host is None:
            self.platform_db_host = self.db_host
        if self.platform_db_port is None:
            self.platform_db_port = self.db_port
        if self.platform_db_user is None:
            self.platform_db_user = self.db_user
        if self.platform_db_password is None:
            self.platform_db_password = self.db_password
        return self

    @field_validator("documents_path", "chroma_db_path", mode="before")
    @classmethod
    def convert_to_path(cls, v: str | Path) -> Path:
        """
        Convert string paths to Path objects.

        Args:
            v: Path as string or Path object.

        Returns:
            Path object.
        """
        return Path(v) if isinstance(v, str) else v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """
        Validate log level is one of the standard levels.

        Args:
            v: Log level string.

        Returns:
            Validated log level.

        Raises:
            ValueError: If log level is invalid.
        """
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v_upper

    @field_validator("storage_backend")
    @classmethod
    def validate_storage_backend(cls, v: str) -> str:
        """
        Validate storage backend type.

        Args:
            v: Storage backend string.

        Returns:
            Validated storage backend.

        Raises:
            ValueError: If storage backend is invalid.
        """
        valid_backends = ["local", "s3"]
        v_lower = v.lower()
        if v_lower not in valid_backends:
            raise ValueError(f"Storage backend must be one of {valid_backends}")
        return v_lower

    def get_platform_admin_emails(self) -> list[str]:
        """
        Get list of platform admin emails.

        Returns:
            List of lowercase, stripped email addresses.
        """
        return [
            e.strip().lower()
            for e in self.platform_admin_emails.split(",")
            if e.strip()
        ]

    def get_platform_database_url(self) -> str:
        """
        Get SQLAlchemy URL for the platform database (multi-tenant mode).

        Returns:
            Database connection URL string for the platform DB.
        """
        if self.platform_db_password:
            return (
                f"mysql+pymysql://{self.platform_db_user}:{self.platform_db_password}"
                f"@{self.platform_db_host}:{self.platform_db_port}/{self.platform_db_name}"
            )
        else:
            return (
                f"mysql+pymysql://{self.platform_db_user}"
                f"@{self.platform_db_host}:{self.platform_db_port}/{self.platform_db_name}"
            )

    def get_tenant_database_url(self, db_name: str) -> str:
        """
        Get SQLAlchemy URL for a specific tenant database.

        Args:
            db_name: Tenant database name (e.g., "berengario_tenant_acme").

        Returns:
            Database connection URL string for the tenant DB.
        """
        # Tenant DBs use same host/credentials as platform DB
        if self.platform_db_password:
            return (
                f"mysql+pymysql://{self.platform_db_user}:{self.platform_db_password}"
                f"@{self.platform_db_host}:{self.platform_db_port}/{db_name}"
            )
        else:
            return (
                f"mysql+pymysql://{self.platform_db_user}"
                f"@{self.platform_db_host}:{self.platform_db_port}/{db_name}"
            )

    def get_database_url(self) -> str:
        """
        Get SQLAlchemy database URL for MariaDB.

        Returns:
            Database connection URL string.

        Examples:
            MariaDB: "mysql+pymysql://user:pass@host:3306/dbname"
        """
        if self.db_password:
            return (
                f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )
        else:
            return (
                f"mysql+pymysql://{self.db_user}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )

    def ensure_directories(self) -> None:
        """
        Create necessary directories if they don't exist.

        Creates:
            - Documents directory
            - ChromaDB storage directory
            - Logs directory
            - Email temp directory
        """
        self.documents_path.mkdir(parents=True, exist_ok=True)
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.email_temp_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

# Ensure directories exist on import
settings.ensure_directories()
