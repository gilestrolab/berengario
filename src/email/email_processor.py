"""
Email processor that integrates all email handling components.

This module orchestrates:
- Email fetching (IMAP client)
- Email parsing (with whitelist validation)
- Attachment extraction
- Document processing into knowledge base
- Message tracking
- Query handling
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from imap_tools import MailMessage

from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.email.attachment_handler import AttachmentHandler, AttachmentInfo
from src.email.conversation_manager import (
    ChannelType,
    MessageType,
    conversation_manager,
)
from src.email.email_client import EmailClient
from src.email.email_parser import EmailMessage, EmailParser
from src.email.email_sender import EmailSender, format_response_email
from src.email.message_tracker import MessageTracker
from src.email.whitelist_validator import WhitelistValidator
from src.rag.tools.pending_actions import get_pending_action_manager

# Lazy imports to avoid circular dependency
if TYPE_CHECKING:
    from src.email.tenant_email_router import TenantEmailRouter
    from src.rag.query_handler import QueryHandler

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """
    Result of processing an email message.

    Attributes:
        message_id: Email message ID
        success: Whether processing succeeded
        error: Error message if failed
        action: What action was taken (kb_ingestion, query, rejected, duplicate)
        attachments_processed: Number of attachments processed
        chunks_created: Number of text chunks created
    """

    message_id: str
    success: bool
    error: Optional[str] = None
    action: str = ""
    attachments_processed: int = 0
    chunks_created: int = 0


class EmailProcessor:
    """
    Orchestrates email processing pipeline.

    Integrates all components to:
    1. Fetch unread emails
    2. Parse and validate senders
    3. Extract attachments
    4. Process into knowledge base
    5. Track processed messages
    6. Handle queries (future)

    Attributes:
        email_client: IMAP client for fetching emails
        parser: Email parser with whitelist
        attachment_handler: Attachment extractor
        doc_processor: Document processor
        kb_manager: Knowledge base manager
        message_tracker: Message tracking database
    """

    def __init__(
        self,
        email_client: Optional[EmailClient] = None,
        parser: Optional[EmailParser] = None,
        attachment_handler: Optional[AttachmentHandler] = None,
        doc_processor: Optional[DocumentProcessor] = None,
        kb_manager: Optional[KnowledgeBaseManager] = None,
        message_tracker: Optional[MessageTracker] = None,
        email_sender: Optional[EmailSender] = None,
        query_handler: Optional["QueryHandler"] = None,
        teach_validator: Optional[WhitelistValidator] = None,
        query_validator: Optional[WhitelistValidator] = None,
        admin_validator: Optional[WhitelistValidator] = None,
        tenant_email_router: Optional["TenantEmailRouter"] = None,
        storage_backend=None,
    ):
        """
        Initialize email processor with components.

        Args:
            email_client: Email client (creates new if None)
            parser: Email parser (creates new if None)
            attachment_handler: Attachment handler (creates new if None)
            doc_processor: Document processor (creates new if None)
            kb_manager: Knowledge base manager (creates new if None)
            message_tracker: Message tracker (creates new if None)
            email_sender: Email sender (creates new if None)
            query_handler: Query handler (creates new if None)
            teach_validator: Whitelist validator for teaching (KB ingestion)
            query_validator: Whitelist validator for querying
            admin_validator: Whitelist validator for admin access
            tenant_email_router: Router for multi-tenant email dispatch (None=ST mode)
            storage_backend: StorageBackend for MT file archival (None=local filesystem)
        """
        self.email_client = email_client or EmailClient()
        self.attachment_handler = attachment_handler or AttachmentHandler()
        self.doc_processor = doc_processor or DocumentProcessor()
        self.kb_manager = kb_manager or KnowledgeBaseManager()
        self.message_tracker = message_tracker or MessageTracker()
        self.email_sender = email_sender or EmailSender()

        # Lazy import to avoid circular dependency
        if query_handler is None:
            from src.rag.query_handler import QueryHandler

            query_handler = QueryHandler()
        self.query_handler = query_handler

        # Initialize hierarchical whitelists with parent relationships
        # Hierarchy: Admin > Teacher > Querier
        # - Admins can do everything (teach + query)
        # - Teachers can teach and query
        # - Queriers can only query

        # First create admin validator (top of hierarchy, no parents)
        self.admin_validator = admin_validator or WhitelistValidator(
            whitelist=settings.email_admin_whitelist,
            whitelist_file=settings.email_admin_whitelist_file,
            enabled=settings.email_admin_whitelist_enabled,
        )

        # Create teach validator (admins can also teach)
        self.teach_validator = teach_validator or WhitelistValidator(
            whitelist=settings.email_teach_whitelist,
            whitelist_file=settings.email_teach_whitelist_file,
            enabled=settings.email_teach_whitelist_enabled,
            parent_validators=[self.admin_validator],  # Admins can teach
        )

        # Create query validator (admins and teachers can also query)
        self.query_validator = query_validator or WhitelistValidator(
            whitelist=settings.email_query_whitelist,
            whitelist_file=settings.email_query_whitelist_file,
            enabled=settings.email_query_whitelist_enabled,
            parent_validators=[
                self.admin_validator,
                self.teach_validator,
            ],  # Admins and teachers can query
        )

        # Initialize parser with teach validator for whitelist checking
        # The parser uses the teach validator to set is_whitelisted field,
        # which is used by should_process_for_kb() to determine KB ingestion eligibility
        self.parser = parser or EmailParser(validator=self.teach_validator)

        # Multi-tenant router and storage (None in single-tenant mode)
        self.tenant_email_router = tenant_email_router
        self.storage_backend = storage_backend

        mode = "multi-tenant" if tenant_email_router else "single-tenant"
        logger.info(
            f"EmailProcessor initialized in {mode} mode "
            f"with hierarchical whitelists (admin > teacher > querier)"
        )

    def reload_whitelists(self) -> None:
        """
        Reload all whitelist validators from their source files.

        This allows the email service to pick up changes made to whitelist files
        (e.g., through the admin interface) without requiring a restart.
        """
        logger.info("Reloading all whitelist validators...")
        self.admin_validator.reload()
        self.teach_validator.reload()
        self.query_validator.reload()
        logger.info("All whitelist validators reloaded successfully")

    def process_message(
        self, mail_message: MailMessage, mark_seen: bool = True
    ) -> ProcessingResult:
        """
        Process a single email message.

        Dispatches to single-tenant or multi-tenant processing based on
        whether a tenant_email_router was provided.

        Args:
            mail_message: MailMessage from imap-tools
            mark_seen: Whether to mark message as seen after processing

        Returns:
            ProcessingResult with processing outcome.
        """
        message_id = mail_message.uid or "unknown"

        try:
            # Parse email
            email = self.parser.parse(mail_message)
            if not email:
                logger.error(f"Failed to parse message {message_id}")
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Failed to parse email",
                    action="parse_error",
                )

            message_id = email.message_id
            logger.info(
                f"Processing email {message_id} from {email.sender.email} "
                f"(whitelisted={email.is_whitelisted}, cc'd={email.is_cced})"
            )

            # Check if already processed (global dedup)
            if self.message_tracker.is_processed(message_id):
                logger.info(f"Message {message_id} already processed, skipping")
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="duplicate",
                )

            # Dispatch to ST or MT processing
            if self.tenant_email_router:
                result = self._process_mt(email, mail_message)
            else:
                result = self._process_st(email, mail_message, mark_seen)

            # Mark as seen if requested (for MT, always mark after fan-out)
            if mark_seen and result.success:
                self.email_client.mark_seen(mail_message.uid)

            return result

        except Exception as e:
            logger.error(f"Error processing message {message_id}: {e}", exc_info=True)

            # Try to track the error
            try:
                email_addr = "unknown"
                subject = ""
                if "email" in locals():
                    email_addr = email.sender.email
                    subject = email.subject

                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email_addr,
                    subject=subject,
                    status="error",
                    error_message=str(e),
                )
            except Exception as track_error:
                logger.error(f"Failed to track error: {track_error}")

            return ProcessingResult(
                message_id=message_id,
                success=False,
                error=str(e),
                action="error",
            )

    def _process_st(
        self,
        email: EmailMessage,
        mail_message: MailMessage,
        mark_seen: bool = True,
    ) -> ProcessingResult:
        """
        Single-tenant email processing (original behavior).

        Uses file-based whitelists and global singletons.

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage from imap-tools
            mark_seen: Whether to mark as seen on rejection

        Returns:
            ProcessingResult with processing outcome.
        """
        message_id = email.message_id

        # Determine action based on recipient type and check appropriate whitelist
        if self.parser.should_process_as_query(email):
            # Direct message (To: bot) = query - check query whitelist
            if not self.query_validator.is_allowed(email.sender.email):
                logger.warning(
                    f"Message {message_id} from {email.sender.email} rejected "
                    f"(not in query whitelist)"
                )
                self._send_rejection_email(email, "query")
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="rejected",
                    error_message="Sender not authorized to query",
                )
                if mark_seen:
                    self.email_client.mark_seen(mail_message.uid)
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Sender not authorized to query",
                    action="rejected",
                )
            return self._process_query(email)
        elif self.parser.should_process_for_kb(email):
            # CC'd/BCC'd/forwarded = KB ingestion - check teach whitelist
            if not self.teach_validator.is_allowed(email.sender.email):
                logger.warning(
                    f"Message {message_id} from {email.sender.email} rejected "
                    f"(not in teach whitelist)"
                )
                self._send_rejection_email(email, "teach")
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="rejected",
                    error_message="Sender not authorized to teach",
                )
                if mark_seen:
                    self.email_client.mark_seen(mail_message.uid)
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Sender not authorized to teach",
                    action="rejected",
                )
            return self._process_for_kb(email, mail_message)
        else:
            logger.warning(
                f"Message {message_id} doesn't match any processing criteria"
            )
            return ProcessingResult(
                message_id=message_id,
                success=True,
                action="skipped",
            )

    def _process_mt(
        self,
        email: EmailMessage,
        mail_message: MailMessage,
    ) -> ProcessingResult:
        """
        Multi-tenant email processing.

        Resolves sender to tenant(s) via TenantUser table, checks permissions
        per role, and processes with tenant-specific components.

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage from imap-tools

        Returns:
            ProcessingResult (success if at least one tenant processed OK).
        """
        message_id = email.message_id
        router = self.tenant_email_router

        # Determine action type from email structure (tenant-independent)
        is_query = self.parser.should_process_as_query(email)
        is_kb = self.parser.should_process_for_kb(email)
        action = "query" if is_query else "teach" if is_kb else None

        if not action:
            logger.warning(
                f"MT: Message {message_id} doesn't match any processing criteria"
            )
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="success",
            )
            return ProcessingResult(
                message_id=message_id, success=True, action="skipped"
            )

        # Resolve sender to tenant(s)
        tenant_mappings = router.resolve_sender(email.sender.email)
        if not tenant_mappings:
            logger.warning(f"MT: Sender {email.sender.email} not found in any tenant")
            self._send_rejection_email(email, action)
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="rejected",
                error_message=f"Sender not found in any tenant for {action}",
            )
            return ProcessingResult(
                message_id=message_id,
                success=False,
                error="Sender not found in any tenant",
                action="rejected",
            )

        # Process for each tenant where sender has permission
        successes = 0
        failures = 0

        for mapping in tenant_mappings:
            tenant_slug = mapping["tenant_slug"]
            role = mapping["role"]

            if not router.check_permission(role, action):
                logger.info(
                    f"MT: Sender {email.sender.email} has role '{role}' in "
                    f"tenant '{tenant_slug}' — insufficient for '{action}', skipping"
                )
                continue

            try:
                components = router.get_components(tenant_slug)
                ctx = components.context

                if is_query:
                    # Check for "add user" admin command (MT)
                    if role == "admin":
                        from src.email.admin_commands import detect_add_user_command

                        body_text = email.get_body(prefer_text=True) or ""
                        if detect_add_user_command(email.subject or "", body_text):
                            logger.info(
                                f"MT: Detected add-user command from admin "
                                f"{email.sender.email} for tenant '{tenant_slug}'"
                            )
                            result = self._handle_add_user_command_mt(
                                email,
                                message_id,
                                body_text,
                                tenant_id=mapping["tenant_id"],
                                tenant_slug=tenant_slug,
                                email_sender=self.email_sender,
                                instance_name=ctx.instance_name,
                                organization=ctx.organization,
                                from_address=ctx.instance_name,
                                from_name=ctx.instance_name,
                            )
                            if result.success:
                                successes += 1
                            else:
                                failures += 1
                            continue

                    result = self._process_query_with(
                        email=email,
                        query_handler=components.query_handler,
                        conv_manager=components.conversation_manager,
                        email_sender=self.email_sender,
                        instance_name=ctx.instance_name,
                        organization=ctx.organization,
                        from_address=ctx.instance_name,  # Use tenant email if available
                        from_name=ctx.instance_name,
                    )
                else:
                    result = self._process_for_kb_with(
                        email=email,
                        mail_message=mail_message,
                        kb_manager=components.kb_manager,
                        doc_processor=components.doc_processor,
                        kb_emails_path=ctx.kb_emails_path,
                        kb_documents_path=ctx.kb_documents_path,
                        temp_dir=ctx.temp_dir,
                        instance_name=ctx.instance_name,
                        organization=ctx.organization,
                        storage_backend=self.storage_backend,
                        tenant_slug=ctx.tenant_slug,
                    )

                if result.success:
                    successes += 1
                else:
                    failures += 1
                    logger.warning(
                        f"MT: Failed processing for tenant '{tenant_slug}': "
                        f"{result.error}"
                    )

            except Exception as e:
                failures += 1
                logger.error(
                    f"MT: Error processing for tenant '{tenant_slug}': {e}",
                    exc_info=True,
                )

        # Mark processed globally (once, after fan-out)
        status = "success" if successes > 0 else "error"
        self.message_tracker.mark_processed(
            message_id=message_id,
            sender=email.sender.email,
            subject=email.subject,
            status=status,
            error_message=(f"{failures} tenant(s) failed" if failures > 0 else None),
        )

        logger.info(
            f"MT: Message {message_id} processed for "
            f"{successes + failures} tenant(s): "
            f"{successes} success, {failures} failed"
        )

        return ProcessingResult(
            message_id=message_id,
            success=successes > 0,
            action=action,
            error=(
                f"{failures} tenant(s) failed"
                if failures > 0 and successes == 0
                else None
            ),
        )

    def _archive_file(
        self,
        source_path: Path,
        dest_dir: Path,
        dest_filename: str,
        storage_backend=None,
        tenant_slug: Optional[str] = None,
        storage_key_prefix: str = "",
    ) -> None:
        """
        Archive a file to permanent storage (StorageBackend or local filesystem).

        In MT mode with a storage_backend, uses put() to store in tenant namespace.
        In ST mode (no storage_backend), copies to local dest_dir via shutil.

        Args:
            source_path: Path to the source file.
            dest_dir: Local destination directory (used in ST/local mode).
            dest_filename: Destination filename.
            storage_backend: StorageBackend instance (None=local filesystem).
            tenant_slug: Tenant identifier (required when storage_backend is set).
            storage_key_prefix: Key prefix for storage (e.g., "kb/emails/").
        """
        if storage_backend and tenant_slug:
            storage_backend.put(
                tenant_slug,
                f"{storage_key_prefix}{dest_filename}",
                source_path.read_bytes(),
            )
            logger.info(
                f"Archived {dest_filename} to storage backend "
                f"({tenant_slug}/{storage_key_prefix}{dest_filename})"
            )
        else:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / dest_filename
            if not dest.exists():
                import shutil

                shutil.copy2(source_path, dest)
                logger.info(f"Archived {dest_filename} to {dest}")

    def _process_for_kb(
        self, email: EmailMessage, mail_message: MailMessage
    ) -> ProcessingResult:
        """
        Process email for KB ingestion using default (ST) components.

        Thin wrapper around _process_for_kb_with() using self.* and settings.*.

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage for attachment extraction

        Returns:
            ProcessingResult with ingestion outcome.
        """
        return self._process_for_kb_with(
            email=email,
            mail_message=mail_message,
            kb_manager=self.kb_manager,
            doc_processor=self.doc_processor,
            kb_emails_path=settings.kb_emails_path,
            kb_documents_path=settings.kb_documents_path,
            temp_dir=settings.email_temp_dir,
            instance_name=settings.instance_name,
            organization=settings.organization,
        )

    def _process_for_kb_with(
        self,
        email: EmailMessage,
        mail_message: MailMessage,
        kb_manager: KnowledgeBaseManager,
        doc_processor: DocumentProcessor,
        kb_emails_path: Path,
        kb_documents_path: Path,
        temp_dir: Path,
        instance_name: str,
        organization: str,
        storage_backend=None,
        tenant_slug: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Process email for KB ingestion with explicit component injection.

        Used by both ST (via _process_for_kb wrapper) and MT (direct call
        with tenant-specific components).

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage for attachment extraction
            kb_manager: KnowledgeBaseManager for this tenant
            doc_processor: DocumentProcessor for this tenant
            kb_emails_path: Path to save email copies
            kb_documents_path: Path to save document copies
            temp_dir: Temporary directory for attachments
            instance_name: Instance name for acknowledgment emails
            organization: Organization name for acknowledgment emails
            storage_backend: StorageBackend for MT file archival (None=local)
            tenant_slug: Tenant identifier for storage (None=ST mode)

        Returns:
            ProcessingResult with ingestion outcome.
        """
        message_id = email.message_id
        attachments_processed = 0
        chunks_created = 0
        duplicates_skipped = 0
        processed_files: List[AttachmentInfo] = []

        try:
            # Extract attachments
            attachments = self.attachment_handler.extract_attachments(
                mail_message, message_id
            )

            if not attachments:
                # If no attachments but email has body, process body as document
                body_text = email.get_body(prefer_text=True)
                if body_text and body_text.strip():
                    logger.info(
                        f"No attachments in message {message_id}, processing email body as document"
                    )
                    temp_file = None
                    try:
                        # Save email body to temporary text file
                        import tempfile

                        temp_dir.mkdir(parents=True, exist_ok=True)
                        temp_file = tempfile.NamedTemporaryFile(
                            mode="w",
                            suffix=".txt",
                            prefix=f"email_{message_id}_",
                            delete=False,
                            dir=str(temp_dir),
                        )
                        temp_file.write(body_text)
                        temp_file.close()

                        # Check if email body content already exists in KB
                        body_file_path = Path(temp_file.name)
                        body_hash = doc_processor.compute_file_hash(body_file_path)

                        if kb_manager.document_exists(body_hash):
                            logger.info(
                                f"Email body content from {email.sender.email} already in KB (hash: {body_hash[:8]}...)"
                            )

                            # Still persist email body for future reingestion
                            date_str = (
                                email.date.strftime("%Y-%m-%d")
                                if email.date
                                else "unknown-date"
                            )
                            sender_name = email.sender.email.split("@")[0]
                            subject_clean = (
                                email.subject[:50] if email.subject else "No Subject"
                            )
                            subject_clean = "".join(
                                c
                                for c in subject_clean
                                if c.isalnum() or c in (" ", "-", "_")
                            ).strip()
                            descriptive_filename = f"Email from {sender_name} on {date_str} - {subject_clean}.txt"

                            self._archive_file(
                                source_path=body_file_path,
                                dest_dir=kb_emails_path,
                                dest_filename=descriptive_filename,
                                storage_backend=storage_backend,
                                tenant_slug=tenant_slug,
                                storage_key_prefix="kb/emails/",
                            )

                            # Clean up temp file
                            body_file_path.unlink(missing_ok=True)

                            self.message_tracker.mark_processed(
                                message_id=message_id,
                                sender=email.sender.email,
                                subject=email.subject,
                                status="success",
                                attachment_count=0,
                                chunks_created=0,
                            )

                            return ProcessingResult(
                                message_id=message_id,
                                success=True,
                                action="kb_ingestion",
                                attachments_processed=0,
                                chunks_created=0,
                            )

                        # Process email body as text document
                        date_str = (
                            email.date.strftime("%Y-%m-%d")
                            if email.date
                            else "unknown-date"
                        )
                        sender_name = email.sender.email.split("@")[0]
                        subject_clean = (
                            email.subject[:50] if email.subject else "No Subject"
                        )
                        subject_clean = "".join(
                            c
                            for c in subject_clean
                            if c.isalnum() or c in (" ", "-", "_")
                        ).strip()
                        descriptive_filename = f"Email from {sender_name} on {date_str} - {subject_clean}.txt"

                        nodes = doc_processor.process_document(
                            file_path=Path(temp_file.name),
                            source_type="email",
                            extra_metadata={
                                "filename": descriptive_filename,
                                "sender": email.sender.email,
                                "subject": email.subject,
                                "date": str(email.date) if email.date else None,
                            },
                        )

                        # Add to knowledge base
                        kb_manager.add_nodes(nodes)
                        chunks_created = len(nodes)

                        logger.info(
                            f"Successfully added email body to KB: {chunks_created} chunks created"
                        )

                        # Persist email body to kb/emails/ for future reingestion
                        self._archive_file(
                            source_path=Path(temp_file.name),
                            dest_dir=kb_emails_path,
                            dest_filename=descriptive_filename,
                            storage_backend=storage_backend,
                            tenant_slug=tenant_slug,
                            storage_key_prefix="kb/emails/",
                        )

                        # Clean up temp file
                        Path(temp_file.name).unlink(missing_ok=True)

                        self.message_tracker.mark_processed(
                            message_id=message_id,
                            sender=email.sender.email,
                            subject=email.subject,
                            status="success",
                            attachment_count=0,
                            chunks_created=chunks_created,
                        )

                        # Send acknowledgment email to the contributor
                        if chunks_created > 0:
                            self._send_kb_acknowledgment(
                                email,
                                0,
                                chunks_created,
                                instance_name=instance_name,
                                organization=organization,
                            )

                        return ProcessingResult(
                            message_id=message_id,
                            success=True,
                            action="kb_ingestion",
                            attachments_processed=0,
                            chunks_created=chunks_created,
                        )

                    except Exception as e:
                        logger.error(f"Error processing email body: {e}", exc_info=True)
                        # Clean up temp file on error
                        if temp_file and Path(temp_file.name).exists():
                            Path(temp_file.name).unlink(missing_ok=True)
                        # Fall through to skip KB ingestion

                logger.info(
                    f"No valid attachments or body text in message {message_id}, skipping KB ingestion"
                )
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="success",
                    attachment_count=0,
                    chunks_created=0,
                )
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="kb_ingestion",
                    attachments_processed=0,
                    chunks_created=0,
                )

            logger.info(f"Processing {len(attachments)} attachments from {message_id}")

            # Process each attachment
            for attachment in attachments:
                try:
                    # Compute file hash and get file modification time
                    file_hash = doc_processor.compute_file_hash(attachment.filepath)
                    file_stat = attachment.filepath.stat()
                    file_mtime = file_stat.st_mtime

                    # Check if document with same content already exists
                    if kb_manager.document_exists(file_hash):
                        logger.info(
                            f"Document {attachment.filename} already in KB (hash: {file_hash[:8]}...), skipping"
                        )
                        duplicates_skipped += 1
                        continue

                    # Check if document with same filename but different content exists
                    existing_doc = kb_manager.get_document_by_filename(
                        attachment.filename
                    )
                    if existing_doc:
                        existing_hash = existing_doc.get("file_hash")
                        existing_mtime = existing_doc.get("file_mtime", 0)

                        # Different content, check timestamps
                        if file_mtime > existing_mtime:
                            # New version is newer, replace old version
                            logger.info(
                                f"Replacing older version of {attachment.filename} "
                                f"(old: {existing_hash[:8]}..., new: {file_hash[:8]}...)"
                            )
                            chunks_deleted = kb_manager.delete_document_by_filename(
                                attachment.filename
                            )
                            logger.info(
                                f"Deleted {chunks_deleted} chunks from old version"
                            )
                        else:
                            # New version is older, skip
                            logger.info(
                                f"Skipping older version of {attachment.filename} "
                                f"(existing version is newer)"
                            )
                            duplicates_skipped += 1
                            continue

                    # Process document into text nodes
                    extra_metadata = {
                        "email_sender": email.sender.email,
                        "email_subject": email.subject,
                        "email_date": str(email.date) if email.date else "",
                        "message_id": message_id,
                    }

                    nodes = doc_processor.process_document(
                        file_path=attachment.filepath,
                        source_type="attachment",
                        extra_metadata=extra_metadata,
                    )

                    if nodes:
                        # Add to knowledge base
                        kb_manager.add_nodes(nodes)
                        chunks_created += len(nodes)
                        attachments_processed += 1
                        processed_files.append(attachment)
                        logger.info(
                            f"Added {attachment.filename} to KB: {len(nodes)} chunks"
                        )

                        # Persist attachment to kb/documents/ for future reingestion
                        if storage_backend and tenant_slug:
                            # MT mode: use storage backend directly
                            self._archive_file(
                                source_path=attachment.filepath,
                                dest_dir=kb_documents_path,
                                dest_filename=attachment.filename,
                                storage_backend=storage_backend,
                                tenant_slug=tenant_slug,
                                storage_key_prefix="kb/documents/",
                            )
                        else:
                            # ST mode: local filesystem with collision handling
                            kb_documents_path.mkdir(parents=True, exist_ok=True)
                            persistent_path = kb_documents_path / attachment.filename
                            if persistent_path.exists():
                                from datetime import datetime

                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                stem = persistent_path.stem
                                suffix = persistent_path.suffix
                                persistent_path = (
                                    kb_documents_path / f"{stem}_{timestamp}{suffix}"
                                )
                            import shutil

                            shutil.copy2(attachment.filepath, persistent_path)
                            logger.info(
                                f"Saved attachment to {persistent_path} for future reingestion"
                            )

                    else:
                        logger.warning(f"No chunks created from {attachment.filename}")

                except Exception as e:
                    logger.error(
                        f"Error processing attachment {attachment.filename}: {e}",
                        exc_info=True,
                    )
                    # Continue with other attachments

            # Track processing
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="success",
                attachment_count=attachments_processed,
                chunks_created=chunks_created,
            )

            logger.info(
                f"KB ingestion complete: {attachments_processed}/{len(attachments)} "
                f"attachments processed, {chunks_created} chunks created, "
                f"{duplicates_skipped} duplicates skipped"
            )

            # Send acknowledgment email to the contributor
            if chunks_created > 0 or duplicates_skipped > 0:
                self._send_kb_acknowledgment(
                    email,
                    attachments_processed,
                    chunks_created,
                    duplicates_skipped,
                    instance_name=instance_name,
                    organization=organization,
                )

            return ProcessingResult(
                message_id=message_id,
                success=True,
                action="kb_ingestion",
                attachments_processed=attachments_processed,
                chunks_created=chunks_created,
            )

        except Exception as e:
            logger.error(f"Error in KB ingestion for {message_id}: {e}", exc_info=True)
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="error",
                error_message=str(e),
                attachment_count=attachments_processed,
                chunks_created=chunks_created,
            )
            return ProcessingResult(
                message_id=message_id,
                success=False,
                error=str(e),
                action="kb_ingestion",
                attachments_processed=attachments_processed,
                chunks_created=chunks_created,
            )

        finally:
            # Archive attachments to permanent documents folder before cleanup
            # In MT mode with storage_backend, archival is done inline above
            if attachments:
                if not (storage_backend and tenant_slug):
                    logger.info(
                        f"Archiving {len(attachments)} attachments to documents folder"
                    )
                    self.attachment_handler.archive_attachments(attachments)
                # Cleanup temp files after archival
                self.attachment_handler.cleanup_attachments(attachments)

    def _process_query(self, email: EmailMessage) -> ProcessingResult:
        """
        Process email as a query using default (ST) components.

        Thin wrapper around _process_query_with() using self.* and settings.*.

        Args:
            email: Parsed EmailMessage

        Returns:
            ProcessingResult with query outcome.
        """
        return self._process_query_with(
            email=email,
            query_handler=self.query_handler,
            conv_manager=conversation_manager,
            email_sender=self.email_sender,
            instance_name=settings.instance_name,
            organization=settings.organization,
            from_address=settings.email_target_address,
            from_name=settings.email_display_name,
        )

    def _process_query_with(
        self,
        email: EmailMessage,
        query_handler: "QueryHandler",
        conv_manager,
        email_sender: EmailSender,
        instance_name: str,
        organization: str,
        from_address: str,
        from_name: str,
    ) -> ProcessingResult:
        """
        Process email as a query with explicit component injection.

        Used by both ST (via _process_query wrapper) and MT (direct call
        with tenant-specific components).

        Args:
            email: Parsed EmailMessage
            query_handler: QueryHandler to process the query
            conv_manager: ConversationManager for thread tracking
            email_sender: EmailSender for sending replies
            instance_name: Instance name for email formatting
            organization: Organization name for email formatting
            from_address: Sender address for reply emails
            from_name: Sender display name for reply emails

        Returns:
            ProcessingResult with query outcome.
        """
        message_id = email.message_id

        logger.info(f"Processing query from {email.sender.email}: {email.subject}")

        try:
            # Extract thread ID for conversation tracking
            thread_id = conv_manager.extract_thread_id_from_email(
                message_id=email.message_id,
                in_reply_to=email.in_reply_to,
                references=email.references,
            )
            logger.debug(f"Thread ID: {thread_id}")

            # Get conversation history for context
            conversation_context = conv_manager.format_conversation_context(
                thread_id=thread_id,
                max_messages=10,
            )

            # Extract query text from email body
            query_text = email.get_body(prefer_text=True)

            if not query_text or not query_text.strip():
                logger.warning(f"Empty query body in message {message_id}")
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message="Empty query body",
                )
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Empty query body",
                    action="query",
                )

            # Check if sender is admin (ST only — MT handles permissions upstream)
            is_admin = self.admin_validator.is_allowed(email.sender.email)
            if is_admin:
                logger.info(f"Admin user detected: {email.sender.email}")

            # Check if this is a confirmation email (ST-only feature)
            if is_admin and not self.tenant_email_router:
                search_text = f"{email.subject or ''} {query_text}".upper()
                if "CONFIRM" in search_text:
                    logger.info(
                        f"Detected confirmation request from admin {email.sender.email}"
                    )
                    return self._handle_confirmation(
                        email, message_id, query_text, email.subject or ""
                    )

            # Check for "add user" admin command (ST only)
            if is_admin and not self.tenant_email_router:
                from src.email.admin_commands import detect_add_user_command

                if detect_add_user_command(email.subject or "", query_text):
                    logger.info(
                        f"Detected add-user command from admin {email.sender.email}"
                    )
                    return self._handle_add_user_command(
                        email,
                        message_id,
                        query_text,
                        email_sender=email_sender,
                        instance_name=instance_name,
                        from_address=from_address,
                        from_name=from_name,
                    )

            # Process query through RAG engine with conversation context
            logger.debug(f"Querying RAG engine for message {message_id}")
            result = query_handler.process_query(
                query_text=query_text,
                user_email=email.sender.email,
                is_admin=is_admin,
                is_email_request=True,
                context={
                    "message_id": message_id,
                    "subject": email.subject,
                    "date": str(email.date) if email.date else None,
                    "conversation_history": conversation_context,
                },
            )

            # Store user query in conversation database
            conv_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.QUERY,
                content=query_text,
                sender=email.sender.email,
                subject=email.subject,
                channel=ChannelType.EMAIL,
                timestamp=email.date,
                original_query=result.get("original_query"),
                optimized_query=result.get("optimized_query"),
            )
            logger.debug(f"Stored user query in conversation {thread_id}")

            if not result["success"]:
                logger.error(
                    f"RAG query failed for {message_id}: {result.get('error')}"
                )
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message=result.get("error", "Query processing failed"),
                )
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error=result.get("error"),
                    action="query",
                )

            # Prepare reply subject line
            if not email.subject.lower().startswith("re:"):
                reply_subject = f"Re: {email.subject}"
            else:
                reply_subject = email.subject

            # Store assistant reply in conversation database
            reply_message_id = conv_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.REPLY,
                content=result["response"],
                sender=from_address,
                subject=reply_subject,
                channel=ChannelType.EMAIL,
                sources_used=result.get("sources"),
                retrieval_metadata=result.get("metadata"),
            )
            logger.debug(
                f"Stored assistant reply in conversation {thread_id}, message_id={reply_message_id}"
            )

            # Format response email with feedback links
            subject, plain_text, html_body = format_response_email(
                response_text=result["response"],
                sources=result["sources"],
                instance_name=instance_name,
                original_subject=email.subject,
                message_id=reply_message_id,
            )

            # Check if tool already sent an email (e.g., confirmation email)
            skip_reply = result.get("metadata", {}).get("skip_email_reply", False)
            if skip_reply:
                logger.info(
                    f"Skipping automatic email reply - tool already sent email to {email.sender.email}"
                )
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="success",
                )
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="query",
                )

            # Get attachments from result (if any)
            attachments = result.get("attachments", [])
            if attachments:
                logger.info(f"Including {len(attachments)} attachments in reply")

            # Send reply email with tenant identity
            logger.info(f"Sending reply to {email.sender.email}")
            send_success = email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=plain_text,
                body_html=html_body,
                in_reply_to=message_id,
                references=[message_id],
                attachments=attachments,
                from_address=from_address,
                from_name=from_name,
            )

            if not send_success:
                logger.error(f"Failed to send reply email for {message_id}")
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message="Failed to send reply email",
                )
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Failed to send reply email",
                    action="query",
                )

            # Track successful processing
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="success",
                attachment_count=0,
                chunks_created=0,
            )

            logger.info(f"Successfully processed query and sent reply for {message_id}")
            return ProcessingResult(
                message_id=message_id,
                success=True,
                action="query",
            )

        except Exception as e:
            logger.error(f"Error processing query {message_id}: {e}", exc_info=True)
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="error",
                error_message=str(e),
            )
            return ProcessingResult(
                message_id=message_id,
                success=False,
                error=str(e),
                action="query",
            )

    def _send_kb_acknowledgment(
        self,
        email: EmailMessage,
        attachments_processed: int,
        chunks_created: int,
        duplicates_skipped: int = 0,
        instance_name: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> None:
        """
        Send acknowledgment email after successful KB ingestion.

        Args:
            email: Original EmailMessage that was processed
            attachments_processed: Number of attachments successfully added
            chunks_created: Number of text chunks created
            duplicates_skipped: Number of duplicate documents skipped
            instance_name: Override instance name (for MT mode)
            organization: Override organization (for MT mode)
        """
        inst_name = instance_name or settings.instance_name
        org = organization or settings.organization

        try:
            # Format summary of what was added
            if attachments_processed > 0:
                content_summary = f"{attachments_processed} document(s)"
            else:
                content_summary = "email content"

            # Build duplicate info section
            duplicate_text = ""
            duplicate_html = ""
            if duplicates_skipped > 0:
                duplicate_text = f"\n- Duplicates skipped: {duplicates_skipped} (already in knowledge base)"
                duplicate_html = f"\n<li><strong>Duplicates skipped:</strong> {duplicates_skipped} (already in knowledge base)</li>"

            # Build acknowledgment message
            subject = f"Re: {email.subject}"

            body_text = f"""Thank you for contributing to the {inst_name} knowledge base.

The following material has been successfully processed:
- Source: {content_summary}
- Text chunks created: {chunks_created}
- Received from: {email.sender.email}{duplicate_text}

{"This content is now available for queries from authorized users." if chunks_created > 0 else "Note: All documents were already present in the knowledge base."}

---
{inst_name}
{org}"""

            body_html = f"""<p>Thank you for contributing to the <strong>{inst_name}</strong> knowledge base.</p>

<p>The following material has been successfully processed:</p>
<ul>
<li><strong>Source:</strong> {content_summary}</li>
<li><strong>Text chunks created:</strong> {chunks_created}</li>
<li><strong>Received from:</strong> {email.sender.email}</li>{duplicate_html}
</ul>

<p>{"This content is now available for queries from authorized users." if chunks_created > 0 else "Note: All documents were already present in the knowledge base."}</p>

<hr>
<p><em>{inst_name}</em><br>
<em>{org}</em></p>"""

            # Send acknowledgment
            self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=email.message_id,
            )

            logger.info(f"Sent KB acknowledgment to {email.sender.email}")

        except Exception as e:
            logger.error(
                f"Failed to send KB acknowledgment to {email.sender.email}: {e}"
            )

    def _send_rejection_email(
        self,
        email: EmailMessage,
        rejection_type: str,
        instance_name: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> None:
        """
        Send rejection email to non-whitelisted sender.

        Args:
            email: Original EmailMessage that was rejected
            rejection_type: Type of rejection ("query" or "teach")
            instance_name: Override instance name (for MT mode)
            organization: Override organization (for MT mode)
        """
        inst_name = instance_name or settings.instance_name
        org = organization or settings.organization

        try:
            subject = f"Re: {email.subject}"

            if rejection_type == "query":
                body_text = f"""Thank you for your message to {inst_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to query the knowledge base.

If you believe you should have access, please contact the administrator at {org}.

---
{inst_name}
{org}"""

                body_html = f"""<p>Thank you for your message to <strong>{inst_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to query the knowledge base.</p>

<p>If you believe you should have access, please contact the administrator at <em>{org}</em>.</p>

<hr>
<p><em>{inst_name}</em><br>
<em>{org}</em></p>"""

            else:  # rejection_type == "teach"
                body_text = f"""Thank you for your message to {inst_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to add content to the knowledge base.

If you believe you should have access, please contact the administrator at {org}.

---
{inst_name}
{org}"""

                body_html = f"""<p>Thank you for your message to <strong>{inst_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to add content to the knowledge base.</p>

<p>If you believe you should have access, please contact the administrator at <em>{org}</em>.</p>

<hr>
<p><em>{inst_name}</em><br>
<em>{org}</em></p>"""

            # Send rejection message
            self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=email.message_id,
            )

            logger.info(
                f"Sent {rejection_type} rejection email to {email.sender.email}"
            )

        except Exception as e:
            logger.error(f"Failed to send rejection email to {email.sender.email}: {e}")

    def process_all_unread(self, limit: Optional[int] = None) -> List[ProcessingResult]:
        """
        Process all unread emails in inbox.

        Args:
            limit: Maximum number of messages to process (None = all)

        Returns:
            List of ProcessingResult for all messages.
        """
        logger.info("Starting processing of unread emails")

        # Ensure connected
        if not self.email_client.is_connected():
            logger.info("Connecting to email server")
            self.email_client.connect()

        # Fetch unread messages
        messages = self.email_client.fetch_unread(limit=limit)
        logger.info(f"Found {len(messages)} unread messages")

        if not messages:
            return []

        # Process each message
        results = []
        for idx, message in enumerate(messages, 1):
            logger.info(f"Processing message {idx}/{len(messages)}")
            result = self.process_message(message, mark_seen=True)
            results.append(result)

        # Summary
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        ingested = sum(1 for r in results if r.action == "kb_ingestion")
        queries = sum(1 for r in results if r.action == "query")
        rejected = sum(1 for r in results if r.action == "rejected")

        logger.info(
            f"Processing complete: {len(results)} messages processed "
            f"({successful} success, {failed} failed) - "
            f"{ingested} ingested, {queries} queries, {rejected} rejected"
        )

        return results

    def cleanup_old_temp_files(self, days: int = 7) -> int:
        """
        Clean up old temporary attachment files.

        Args:
            days: Delete files older than this many days

        Returns:
            Number of files deleted.
        """
        return self.attachment_handler.cleanup_old_temp_files(days=days)

    def get_processing_stats(self, days: int = 30) -> dict:
        """
        Get processing statistics.

        Args:
            days: Number of days to include in stats

        Returns:
            Dictionary with statistics.
        """
        return self.message_tracker.get_stats(days=days)

    def _handle_add_user_command(
        self,
        email: EmailMessage,
        message_id: str,
        query_text: str,
        email_sender: EmailSender,
        instance_name: str,
        from_address: str,
        from_name: str,
    ) -> ProcessingResult:
        """
        Handle an add-user admin command in single-tenant mode.

        Args:
            email: Parsed email message.
            message_id: Unique message identifier.
            query_text: Email body text.
            email_sender: EmailSender for replies.
            instance_name: Instance name for formatting.
            from_address: Sender address for reply.
            from_name: Sender display name for reply.

        Returns:
            ProcessingResult with command outcome.
        """
        from src.api.admin.whitelist_manager import WhitelistManager
        from src.email.admin_commands import parse_add_user_command
        from src.email.email_sender import send_welcome_email

        cmd = parse_add_user_command(email.subject or "", query_text)
        if not cmd:
            # Could not parse — fall through to normal RAG processing
            logger.debug(
                "Add-user command detected but could not be parsed, falling through"
            )
            return self._process_query_with(
                email=email,
                query_handler=self.query_handler,
                conv_manager=conversation_manager,
                email_sender=email_sender,
                instance_name=instance_name,
                organization=settings.organization,
                from_address=from_address,
                from_name=from_name,
            )

        # Reject admin role assignment via email
        if cmd.error == "admin_role_requested":
            reply_body = (
                "I can't assign the admin role via email for security reasons. "
                f"Please use the admin panel: {settings.web_base_url}/admin"
            )
            email_sender.send_reply(
                to_address=email.sender.email,
                subject=f"Re: {email.subject or 'Add user'}",
                body_text=reply_body,
                body_html=None,
                in_reply_to=message_id,
                from_address=from_address,
                from_name=from_name,
            )
            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="success",
            )
            return ProcessingResult(
                message_id=message_id, success=True, action="admin_command"
            )

        # Execute the command
        from src.email.admin_commands import execute_add_user_st

        wm = WhitelistManager()
        success, msg = execute_add_user_st(cmd, wm, self.reload_whitelists)

        # Reply to admin
        email_sender.send_reply(
            to_address=email.sender.email,
            subject=f"Re: {email.subject or 'Add user'}",
            body_text=msg,
            body_html=None,
            in_reply_to=message_id,
            from_address=from_address,
            from_name=from_name,
        )

        # Send welcome email to the new user (if actually added)
        if success and "already" not in msg:
            send_welcome_email(
                sender_instance=email_sender,
                to_email=cmd.email,
                role=cmd.role,
                instance_name=instance_name,
            )

        self.message_tracker.mark_processed(
            message_id=message_id,
            sender=email.sender.email,
            subject=email.subject,
            status="success" if success else "error",
            error_message=None if success else msg,
        )
        return ProcessingResult(
            message_id=message_id,
            success=success,
            action="admin_command",
            error=None if success else msg,
        )

    def _handle_add_user_command_mt(
        self,
        email: EmailMessage,
        message_id: str,
        body_text: str,
        tenant_id: str,
        tenant_slug: str,
        email_sender: EmailSender,
        instance_name: str,
        organization: str,
        from_address: str,
        from_name: str,
    ) -> ProcessingResult:
        """
        Handle an add-user admin command in multi-tenant mode.

        Args:
            email: Parsed email message.
            message_id: Unique message identifier.
            body_text: Email body text.
            tenant_id: Target tenant ID.
            tenant_slug: Target tenant slug.
            email_sender: EmailSender for replies.
            instance_name: Instance name for formatting.
            organization: Organization name.
            from_address: Sender address for reply.
            from_name: Sender display name for reply.

        Returns:
            ProcessingResult with command outcome.
        """
        from src.email.admin_commands import (
            execute_add_user_mt,
            parse_add_user_command,
        )
        from src.email.email_sender import send_welcome_email

        cmd = parse_add_user_command(email.subject or "", body_text)
        if not cmd:
            logger.debug("MT: Add-user command detected but could not be parsed")
            return ProcessingResult(
                message_id=message_id,
                success=False,
                action="admin_command",
                error="Could not parse add-user command",
            )

        # Reject admin role assignment via email
        if cmd.error == "admin_role_requested":
            reply_body = (
                "I can't assign the admin role via email for security reasons. "
                "Please use the admin panel to manage administrator roles."
            )
            email_sender.send_reply(
                to_address=email.sender.email,
                subject=f"Re: {email.subject or 'Add user'}",
                body_text=reply_body,
                body_html=None,
                in_reply_to=message_id,
                from_address=from_address,
                from_name=from_name,
            )
            return ProcessingResult(
                message_id=message_id, success=True, action="admin_command"
            )

        # Execute the command
        db_manager = self.tenant_email_router._db_manager
        success, msg = execute_add_user_mt(cmd, tenant_id, tenant_slug, db_manager)

        # Reply to admin
        email_sender.send_reply(
            to_address=email.sender.email,
            subject=f"Re: {email.subject or 'Add user'}",
            body_text=msg,
            body_html=None,
            in_reply_to=message_id,
            from_address=from_address,
            from_name=from_name,
        )

        # Send welcome email to the new user (if actually added)
        if success and "already" not in msg:
            send_welcome_email(
                sender_instance=email_sender,
                to_email=cmd.email,
                role=cmd.role,
                instance_name=instance_name,
                organization=organization,
            )

        return ProcessingResult(
            message_id=message_id,
            success=success,
            action="admin_command",
            error=None if success else msg,
        )

    def _handle_confirmation(
        self, email: EmailMessage, message_id: str, query_text: str, subject: str = ""
    ) -> ProcessingResult:
        """
        Handle whitelist modification confirmation emails.

        Args:
            email: Parsed email message
            message_id: Unique message identifier
            query_text: Email body text
            subject: Email subject line

        Returns:
            ProcessingResult with confirmation processing outcome
        """
        # Lazy import to avoid circular dependency
        from src.rag.tools.whitelist_tools import (
            _add_to_whitelist_file,
            _remove_from_whitelist_file,
        )

        try:
            # Extract confirmation token from anywhere in subject or body
            # Search for pattern: "CONFIRM <token>" or just the token format
            import re

            # Combine subject and body for token search
            combined_text = f"{subject} {query_text}"

            # Look for "CONFIRM <token>" pattern (case-insensitive)
            match = re.search(
                r"CONFIRM\s+([A-Za-z0-9_-]{20,})", combined_text, re.IGNORECASE
            )
            if match:
                action_id = match.group(1)
            else:
                # Look for any token-like string (base64url format, 20+ chars)
                match = re.search(r"\b([A-Za-z0-9_-]{20,})\b", combined_text)
                if match:
                    action_id = match.group(1)
                else:
                    error_msg = "Could not find confirmation token in email. Please reply to the confirmation email or include the full token."
                    logger.warning(
                        f"No confirmation token found in email from {email.sender.email}"
                    )

                    # Send error reply
                    subject_reply = (
                        f"Re: {email.subject}"
                        if email.subject
                        else "Confirmation Error"
                    )
                    self.email_sender.send_reply(
                        to_address=email.sender.email,
                        subject=subject_reply,
                        body_text=(
                            "Error: Could not find confirmation token in your email.\n\n"
                            "Please reply to the original confirmation email, or include the full confirmation token.\n\n"
                            "Example: Just reply to the confirmation email, or type: CONFIRM <your-token-here>"
                        ),
                        body_html=None,
                    )

                    self.message_tracker.mark_processed(
                        message_id=message_id,
                        sender=email.sender.email,
                        subject=email.subject,
                        status="error",
                        error_message=error_msg,
                    )

                    return ProcessingResult(
                        message_id=message_id,
                        success=False,
                        error=error_msg,
                        action="confirmation",
                    )

            logger.info(
                f"Processing confirmation for action {action_id} from {email.sender.email}"
            )

            # Get pending action
            pending_mgr = get_pending_action_manager()
            action = pending_mgr.get_pending_action(action_id)

            if not action:
                error_msg = f"Invalid or expired confirmation token: {action_id}"
                logger.warning(error_msg)

                # Send error reply
                subject = (
                    f"Re: {email.subject}" if email.subject else "Confirmation Error"
                )
                self.email_sender.send_reply(
                    to_address=email.sender.email,
                    subject=subject,
                    body_text=(
                        f"Error: The confirmation token is invalid or has expired.\n\n"
                        f"Token: {action_id}\n\n"
                        f"Confirmation tokens expire after 24 hours. Please make a new request."
                    ),
                    body_html=None,
                )

                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message=error_msg,
                )

                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error=error_msg,
                    action="confirmation",
                )

            # Verify the requester matches
            if action.requested_by.lower() != email.sender.email.lower():
                error_msg = (
                    f"Confirmation mismatch: action requested by {action.requested_by}, "
                    f"but confirmed by {email.sender.email}"
                )
                logger.warning(error_msg)

                subject = (
                    f"Re: {email.subject}" if email.subject else "Confirmation Error"
                )
                self.email_sender.send_reply(
                    to_address=email.sender.email,
                    subject=subject,
                    body_text=(
                        f"Error: You can only confirm actions that you requested.\n\n"
                        f"This action was requested by: {action.requested_by}"
                    ),
                    body_html=None,
                )

                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message=error_msg,
                )

                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error=error_msg,
                    action="confirmation",
                )

            # Execute the pending action
            logger.info(
                f"Executing confirmed action {action.action_id}: {action.action_type} "
                f"for {action.email_to_modify}"
            )

            try:
                # Execute based on action type
                if action.action_type == "add_teach":
                    whitelist_file = Path(settings.email_teach_whitelist_file)
                    whitelist_file.parent.mkdir(parents=True, exist_ok=True)
                    _add_to_whitelist_file(whitelist_file, action.email_to_modify)
                    result_msg = f"Successfully added '{action.email_to_modify}' to the teach whitelist."

                elif action.action_type == "remove_teach":
                    whitelist_file = Path(settings.email_teach_whitelist_file)
                    _remove_from_whitelist_file(whitelist_file, action.email_to_modify)
                    result_msg = f"Successfully removed '{action.email_to_modify}' from the teach whitelist."

                elif action.action_type == "add_query":
                    whitelist_file = Path(settings.email_query_whitelist_file)
                    whitelist_file.parent.mkdir(parents=True, exist_ok=True)
                    _add_to_whitelist_file(whitelist_file, action.email_to_modify)
                    result_msg = f"Successfully added '{action.email_to_modify}' to the query whitelist."

                elif action.action_type == "remove_query":
                    whitelist_file = Path(settings.email_query_whitelist_file)
                    _remove_from_whitelist_file(whitelist_file, action.email_to_modify)
                    result_msg = f"Successfully removed '{action.email_to_modify}' from the query whitelist."

                else:
                    raise ValueError(f"Unknown action type: {action.action_type}")

                # Remove pending action
                pending_mgr.remove_action(action_id)

                logger.info(f"Confirmed action executed successfully: {result_msg}")

                # Send success confirmation
                subject = (
                    f"Re: {email.subject}" if email.subject else "Action Confirmed"
                )
                self.email_sender.send_reply(
                    to_address=email.sender.email,
                    subject=subject,
                    body_text=(
                        f"✓ {result_msg}\n\n"
                        f"Action ID: {action.action_id}\n"
                        f"Action Type: {action.action_type}\n"
                        f"Email Modified: {action.email_to_modify}"
                    ),
                    body_html=None,
                )

                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="success",
                )

                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="confirmation",
                    chunks_created=0,
                )

            except Exception as e:
                error_msg = f"Error executing confirmed action: {str(e)}"
                logger.error(error_msg, exc_info=True)

                # Send error reply
                subject = f"Re: {email.subject}" if email.subject else "Action Failed"
                self.email_sender.send_reply(
                    to_address=email.sender.email,
                    subject=subject,
                    body_text=(
                        f"Error executing confirmed action:\n\n{str(e)}\n\n"
                        f"Action ID: {action.action_id}\n"
                        f"Please contact support if this issue persists."
                    ),
                    body_html=None,
                )

                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="error",
                    error_message=error_msg,
                )

                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error=error_msg,
                    action="confirmation",
                )

        except Exception as e:
            error_msg = f"Error processing confirmation: {str(e)}"
            logger.error(error_msg, exc_info=True)

            self.message_tracker.mark_processed(
                message_id=message_id,
                sender=email.sender.email,
                subject=email.subject,
                status="error",
                error_message=error_msg,
            )

            return ProcessingResult(
                message_id=message_id,
                success=False,
                error=error_msg,
                action="confirmation",
            )


# Global email processor instance (lazy initialization to avoid circular imports)
_email_processor_instance = None


def get_email_processor() -> EmailProcessor:
    """
    Get the global email processor instance.

    Uses lazy initialization to avoid circular import issues.

    Returns:
        Global EmailProcessor instance.
    """
    global _email_processor_instance
    if _email_processor_instance is None:
        _email_processor_instance = EmailProcessor()
    return _email_processor_instance
