"""
Configuration management for RAGInbox.

This module uses Pydantic Settings to load and validate configuration
from environment variables. Supports multiple instances with different configurations.
"""

from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
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
        default="RAGInbox", description="Name of this instance"
    )
    instance_description: str = Field(
        default="AI-powered Knowledge Base Assistant",
        description="Description of this instance",
    )
    organization: str = Field(
        default="", description="Organization name (optional)"
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

    # Email Configuration - Inbox (IMAP)
    imap_server: str = Field(default="imap.gmail.com", description="IMAP server address")
    imap_port: int = Field(default=993, description="IMAP server port")
    imap_user: str = Field(..., description="IMAP username/email")
    imap_password: str = Field(..., description="IMAP password")
    imap_use_ssl: bool = Field(default=True, description="Use SSL for IMAP")

    # Email Configuration - Sending (SMTP)
    smtp_server: str = Field(default="smtp.gmail.com", description="SMTP server address")
    smtp_port: int = Field(default=587, description="SMTP server port")
    smtp_user: str = Field(..., description="SMTP username/email")
    smtp_password: str = Field(..., description="SMTP password")
    smtp_use_tls: bool = Field(default=True, description="Use TLS for SMTP")

    # Email Processing
    email_check_interval: int = Field(
        default=300, description="Seconds between email checks"
    )
    email_target_address: str = Field(
        ..., description="Target email address (dols.gpt@...)"
    )
    email_display_name: str = Field(
        default="DoLS GPT assistant", description="Display name for sent emails"
    )
    email_temp_dir: Path = Field(
        default=Path("data/temp_attachments"),
        description="Temporary directory for email attachments",
    )
    max_attachment_size: int = Field(
        default=10485760, description="Maximum attachment size in bytes (10MB default)"
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

    # Email Whitelist (Security) - Dual whitelists for teach vs query permissions
    # Teaching whitelist (for KB ingestion via CC/BCC/forwarding)
    email_teach_whitelist: str = Field(
        default="",
        description="Comma-separated list of email addresses/domains allowed to add content to KB",
    )
    email_teach_whitelist_file: Optional[Path] = Field(
        default=Path("data/config/allowed_teachers.txt"),
        description="Path to file with email addresses/domains allowed to teach (one per line)",
    )
    email_teach_whitelist_enabled: bool = Field(
        default=True,
        description="Enable teaching whitelist validation",
    )

    # Query whitelist (for asking questions and receiving RAG replies)
    email_query_whitelist: str = Field(
        default="",
        description="Comma-separated list of email addresses/domains allowed to query the KB",
    )
    email_query_whitelist_file: Optional[Path] = Field(
        default=Path("data/config/allowed_queriers.txt"),
        description="Path to file with email addresses/domains allowed to query (one per line)",
    )
    email_query_whitelist_enabled: bool = Field(
        default=True,
        description="Enable query whitelist validation",
    )

    # Legacy whitelist support (deprecated - maps to teach whitelist)
    email_whitelist: str = Field(
        default="",
        description="DEPRECATED: Use email_teach_whitelist or email_query_whitelist instead",
    )
    email_whitelist_file: Optional[Path] = Field(
        default=None,
        description="DEPRECATED: Use email_teach_whitelist_file or email_query_whitelist_file instead",
    )
    email_whitelist_enabled: bool = Field(
        default=True,
        description="DEPRECATED: Use email_teach_whitelist_enabled or email_query_whitelist_enabled instead",
    )

    # Database Configuration (Message Tracking)
    db_type: str = Field(
        default="sqlite",
        description="Database type: 'sqlite' or 'mariadb'",
    )
    # SQLite settings
    sqlite_db_path: Path = Field(
        default=Path("data/message_tracker.db"),
        description="SQLite database file path",
    )
    # MariaDB/MySQL settings
    db_host: str = Field(default="localhost", description="Database host")
    db_port: int = Field(default=3306, description="Database port")
    db_name: str = Field(default="raginbox", description="Database name")
    db_user: str = Field(default="raginbox", description="Database username")
    db_password: str = Field(default="", description="Database password")
    db_pool_size: int = Field(default=5, description="Connection pool size")
    db_pool_recycle: int = Field(
        default=3600, description="Recycle connections after N seconds"
    )

    # Document Processing
    documents_path: Path = Field(
        default=Path("data/documents"), description="Path to documents folder"
    )
    chroma_db_path: Path = Field(
        default=Path("data/chroma_db"), description="Path to ChromaDB storage"
    )

    # RAG Configuration
    chunk_size: int = Field(default=1024, description="Document chunk size")
    chunk_overlap: int = Field(default=200, description="Chunk overlap size")
    top_k_retrieval: int = Field(
        default=5, description="Number of chunks to retrieve"
    )
    similarity_threshold: float = Field(
        default=0.7, description="Minimum similarity score for retrieval"
    )

    # RAG Customization
    rag_custom_prompt_file: Optional[Path] = Field(
        default=None,
        description="Path to custom system prompt additions (appended to base prompt)",
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

    # Web API Configuration
    api_host: str = Field(default="0.0.0.0", description="API host address")
    api_port: int = Field(default=8000, description="API port")
    api_reload: bool = Field(default=False, description="Auto-reload on code changes")
    cors_origins: List[str] = Field(
        default=["http://localhost:8000"], description="Allowed CORS origins"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path = Field(
        default=Path("data/logs/dols_gpt.log"), description="Log file path"
    )

    # Development
    debug: bool = Field(default=False, description="Enable debug mode")

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

    @field_validator("db_type")
    @classmethod
    def validate_db_type(cls, v: str) -> str:
        """
        Validate database type is supported.

        Args:
            v: Database type string.

        Returns:
            Validated database type.

        Raises:
            ValueError: If database type is invalid.
        """
        valid_types = ["sqlite", "mariadb", "mysql"]
        v_lower = v.lower()
        if v_lower not in valid_types:
            raise ValueError(f"Database type must be one of {valid_types}")
        return v_lower

    def get_database_url(self) -> str:
        """
        Get SQLAlchemy database URL based on configuration.

        Returns:
            Database connection URL string.

        Examples:
            SQLite: "sqlite:///data/message_tracker.db"
            MariaDB: "mysql+pymysql://user:pass@host:3306/dbname"
        """
        if self.db_type == "sqlite":
            return f"sqlite:///{self.sqlite_db_path}"
        elif self.db_type in ("mariadb", "mysql"):
            # Use pymysql driver (pure Python, works in containers)
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
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def ensure_directories(self) -> None:
        """
        Create necessary directories if they don't exist.

        Creates:
            - Documents directory
            - ChromaDB storage directory
            - Logs directory
            - Email temp directory
            - SQLite database directory (if using SQLite)
        """
        self.documents_path.mkdir(parents=True, exist_ok=True)
        self.chroma_db_path.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.email_temp_dir.mkdir(parents=True, exist_ok=True)
        if self.db_type == "sqlite":
            self.sqlite_db_path.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()

# Ensure directories exist on import
settings.ensure_directories()
