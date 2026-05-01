"""
Email processor that integrates all email handling components.

This module orchestrates:
- Email fetching (IMAP client)
- Email parsing and sender resolution via TenantEmailRouter
- Attachment extraction
- Document processing into knowledge base (per-tenant)
- Message tracking
- Query handling (per-tenant)
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
)
from src.email.email_client import EmailClient
from src.email.email_parser import EmailMessage, EmailParser
from src.email.email_sender import EmailSender, format_response_email
from src.email.message_tracker import MessageTracker

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
    2. Parse emails and resolve sender to tenant(s) via TenantEmailRouter
    3. Extract attachments
    4. Process into tenant-specific knowledge base
    5. Track processed messages (global dedup)
    6. Handle queries with tenant-specific RAG

    Attributes:
        email_client: IMAP client for fetching emails
        parser: Email parser
        attachment_handler: Attachment extractor
        message_tracker: Message tracking database (global)
        email_sender: Email sender for replies
        tenant_email_router: Router for sender→tenant resolution and permission checks
        storage_backend: StorageBackend for file archival
    """

    def __init__(
        self,
        email_client: Optional[EmailClient] = None,
        parser: Optional[EmailParser] = None,
        attachment_handler: Optional[AttachmentHandler] = None,
        message_tracker: Optional[MessageTracker] = None,
        email_sender: Optional[EmailSender] = None,
        tenant_email_router: "TenantEmailRouter" = None,
        storage_backend=None,
    ):
        """
        Initialize email processor with components.

        Args:
            email_client: Email client (creates new if None)
            parser: Email parser (creates new if None)
            attachment_handler: Attachment handler (creates new if None)
            message_tracker: Message tracker (creates new if None)
            email_sender: Email sender (creates new if None)
            tenant_email_router: Router for tenant resolution and permission checks
            storage_backend: StorageBackend for file archival (None=local filesystem)
        """
        self.email_client = email_client or EmailClient()
        self.attachment_handler = attachment_handler or AttachmentHandler()
        self.message_tracker = message_tracker or MessageTracker()
        self.email_sender = email_sender or EmailSender()
        self.parser = parser or EmailParser()

        # Tenant router and storage
        self.tenant_email_router = tenant_email_router
        self.storage_backend = storage_backend

        logger.info("EmailProcessor initialized with TenantEmailRouter")

    def process_message(
        self, mail_message: MailMessage, mark_seen: bool = True
    ) -> ProcessingResult:
        """
        Process a single email message.

        Resolves sender to tenant(s) via TenantEmailRouter, checks permissions,
        and processes with tenant-specific components.

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
                f"(cc'd={email.is_cced})"
            )

            # Check if already processed (global dedup)
            if self.message_tracker.is_processed(message_id):
                logger.info(f"Message {message_id} already processed, skipping")
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="duplicate",
                )

            # Process via tenant router
            result = self._process(email, mail_message)

            # Mark as seen if requested
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

    def _process(
        self,
        email: EmailMessage,
        mail_message: MailMessage,
    ) -> ProcessingResult:
        """
        Process email by resolving sender to tenant(s) and dispatching.

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
                f"Message {message_id} doesn't match any processing criteria"
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
            logger.warning(f"Sender {email.sender.email} not found in any tenant")
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
                if (
                    action == "teach"
                    and role == "querier"
                    and settings.teach_moderation_enabled
                ):
                    try:
                        components = router.get_components(tenant_slug)
                        ctx = components.context
                        self._queue_for_moderation(
                            email=email,
                            mail_message=mail_message,
                            mapping=mapping,
                            components=components,
                            from_address=settings.email_target_address,
                            from_name=ctx.email_display_name or ctx.instance_name,
                            instance_name=ctx.instance_name,
                            admin_emails=router.get_tenant_admin_emails(
                                mapping["tenant_id"]
                            ),
                        )
                        successes += 1
                    except Exception as e:
                        logger.error(
                            f"Failed to queue moderation for tenant "
                            f"'{tenant_slug}': {e}",
                            exc_info=True,
                        )
                        failures += 1
                    continue

                logger.info(
                    f"Sender {email.sender.email} has role '{role}' in "
                    f"tenant '{tenant_slug}' — insufficient for '{action}', skipping"
                )
                continue

            try:
                components = router.get_components(tenant_slug)
                ctx = components.context
                is_admin_user = role == "admin"

                if is_query:
                    # Check billing query limit before processing
                    try:
                        self._check_email_query_limit(router, tenant_slug, components)
                    except ValueError as limit_err:
                        logger.warning(
                            "Query limit exceeded for tenant %s: %s",
                            tenant_slug,
                            limit_err,
                        )
                        self._send_limit_exceeded_email(
                            email, str(limit_err), self.email_sender
                        )
                        result = ProcessingResult(
                            message_id=email.message_id,
                            success=False,
                            error=str(limit_err),
                            action="query_limit_exceeded",
                        )
                        failures += 1
                        continue

                    result = self._process_query_with(
                        email=email,
                        query_handler=components.query_handler,
                        conv_manager=components.conversation_manager,
                        email_sender=self.email_sender,
                        instance_name=ctx.instance_name,
                        organization=ctx.organization,
                        from_address=settings.email_target_address,
                        from_name=ctx.email_display_name or ctx.instance_name,
                        is_admin=is_admin_user,
                        email_response_format=ctx.email_response_format,
                        tenant_slug=ctx.tenant_slug,
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
                        from_address=settings.email_target_address,
                        from_name=ctx.email_display_name or ctx.instance_name,
                        conversation_manager=components.conversation_manager,
                    )

                if result.success:
                    successes += 1
                else:
                    failures += 1
                    logger.warning(
                        f"Failed processing for tenant '{tenant_slug}': "
                        f"{result.error}"
                    )

            except Exception as e:
                failures += 1
                logger.error(
                    f"Error processing for tenant '{tenant_slug}': {e}",
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
            f"Message {message_id} processed for "
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
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
        conversation_manager=None,
    ) -> ProcessingResult:
        """
        Process email for KB ingestion with tenant-specific components.

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
                        # Clean URLs/mailto links for better KB chunking
                        from src.email.email_parser import EmailParser

                        clean_body = EmailParser.clean_text_for_kb(body_text)
                        temp_file.write(clean_body)
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

                        # Generate document description
                        self._generate_description(
                            file_path=descriptive_filename,
                            filename=descriptive_filename,
                            nodes=nodes,
                            file_type="txt",
                            conversation_manager=conversation_manager,
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

                        # Send acknowledgment email to the contributor
                        if chunks_created > 0:
                            self._send_kb_acknowledgment(
                                email,
                                0,
                                chunks_created,
                                instance_name=instance_name,
                                organization=organization,
                                from_address=from_address,
                                from_name=from_name,
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

                        # Generate document description
                        file_ext = Path(attachment.filename).suffix.lstrip(".")
                        file_size = (
                            attachment.filepath.stat().st_size
                            if attachment.filepath.exists()
                            else None
                        )
                        self._generate_description(
                            file_path=attachment.filename,
                            filename=attachment.filename,
                            nodes=nodes,
                            file_size=file_size,
                            file_type=file_ext,
                            conversation_manager=conversation_manager,
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
                    from_address=from_address,
                    from_name=from_name,
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
        is_admin: bool = False,
        email_response_format: Optional[str] = None,
        tenant_slug: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Process email as a query with tenant-specific components.

        Args:
            email: Parsed EmailMessage
            query_handler: QueryHandler to process the query
            conv_manager: ConversationManager for thread tracking
            email_sender: EmailSender for sending replies
            instance_name: Instance name for email formatting
            organization: Organization name for email formatting
            from_address: Sender address for reply emails
            from_name: Sender display name for reply emails
            is_admin: Whether the sender has admin role in the tenant

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
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Empty query body",
                    action="query",
                )

            if is_admin:
                logger.info(f"Admin user detected: {email.sender.email}")

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
                error_msg = result.get("error", "")
                logger.error(f"RAG query failed for {message_id}: {error_msg}")

                # Alert admins if this looks like a model failure
                from src.llm_utils import is_model_error, send_model_failure_alert

                if is_model_error(str(error_msg)):
                    send_model_failure_alert(
                        error=str(error_msg),
                        model=settings.openrouter_model,
                        context=f"email query from {email.sender.email}, "
                        f"message_id={message_id}",
                    )

                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error=error_msg,
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
                organization=organization,
                response_format=email_response_format,
                tenant_slug=tenant_slug,
            )

            # Check if tool already sent an email (e.g., confirmation email)
            skip_reply = result.get("metadata", {}).get("skip_email_reply", False)
            if skip_reply:
                logger.info(
                    f"Skipping automatic email reply - tool already sent email to {email.sender.email}"
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
                return ProcessingResult(
                    message_id=message_id,
                    success=False,
                    error="Failed to send reply email",
                    action="query",
                )

            logger.info(f"Successfully processed query and sent reply for {message_id}")
            return ProcessingResult(
                message_id=message_id,
                success=True,
                action="query",
            )

        except Exception as e:
            logger.error(f"Error processing query {message_id}: {e}", exc_info=True)
            return ProcessingResult(
                message_id=message_id,
                success=False,
                error=str(e),
                action="query",
            )

    def _generate_description(
        self,
        file_path: str,
        filename: str,
        nodes,
        file_size: Optional[int] = None,
        file_type: Optional[str] = None,
        conversation_manager=None,
    ):
        """Generate and save a document description for the admin panel."""
        try:
            from src.document_processing.description_generator import (
                DescriptionGenerator,
            )

            # Use tenant-scoped DB if available
            tenant_db = None
            if conversation_manager:
                tenant_db = getattr(conversation_manager, "db_manager", None)

            desc_gen = DescriptionGenerator(db_manager=tenant_db)
            desc_gen.generate_and_save(
                file_path=file_path,
                filename=filename,
                chunks=nodes,
                file_size=file_size,
                file_type=file_type,
            )
            logger.info(f"Generated description for: {filename}")
        except Exception as e:
            # Don't fail ingestion if description generation fails
            logger.error(f"Error generating description for {filename}: {e}")

    def _send_kb_acknowledgment(
        self,
        email: EmailMessage,
        attachments_processed: int,
        chunks_created: int,
        duplicates_skipped: int = 0,
        instance_name: Optional[str] = None,
        organization: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
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
            from_address: Override sender email address (for MT mode)
            from_name: Override sender display name (for MT mode)
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
                from_address=from_address,
                from_name=from_name,
            )

            logger.info(f"Sent KB acknowledgment to {email.sender.email}")

        except Exception as e:
            logger.error(
                f"Failed to send KB acknowledgment to {email.sender.email}: {e}"
            )

    def _check_email_query_limit(self, router, tenant_slug, components):
        """Check billing query limit for email queries.

        Raises ValueError if limit exceeded.
        Non-billing errors are logged and silently ignored (don't block queries).
        """
        try:
            from src.billing.plans import check_query_limit
            from src.billing.router import _count_queries_this_month
            from src.platform.models import PlanTier, Tenant

            db_manager = router._db_manager
            with db_manager.get_platform_session() as db:
                tenant = db.query(Tenant).filter(Tenant.slug == tenant_slug).first()
                if not tenant or not isinstance(tenant.plan, PlanTier):
                    return
                queries = _count_queries_this_month(db_manager, tenant)
                check_query_limit(tenant.plan, tenant.subscription_status, queries)
        except ValueError:
            raise  # Re-raise limit exceeded errors
        except Exception as e:
            logger.debug("Billing check skipped for %s: %s", tenant_slug, e)

    def _send_limit_exceeded_email(self, email, message, email_sender):
        """Send a reply informing the user their query limit was exceeded."""
        try:
            subject = f"Re: {email.subject}"
            body_text = (
                f"Thank you for your message.\n\n{message}\n\n"
                "Please visit your admin panel to manage your subscription."
            )
            body_html = (
                f"<p>Thank you for your message.</p>"
                f"<p>{message}</p>"
                f"<p>Please visit your admin panel to manage your subscription.</p>"
            )
            email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=email.message_id,
            )
        except Exception as e:
            logger.error("Failed to send limit exceeded email: %s", e)

    def _queue_for_moderation(
        self,
        email: EmailMessage,
        mail_message: MailMessage,
        mapping: dict,
        components,
        from_address: Optional[str],
        from_name: Optional[str],
        instance_name: str,
        admin_emails: List[str],
    ) -> None:
        """
        Queue an unauthorized teach attempt for admin moderation.

        Extracts the email's attachments, stores them via the storage backend
        (or the local moderation directory in ST mode), inserts a
        PendingTeachSubmission row in the tenant DB, and sends two emails:
        an acknowledgement to the submitter and a notification to the tenant
        admins.

        Args:
            email: Parsed EmailMessage.
            mail_message: Raw MailMessage for attachment extraction.
            mapping: Resolved tenant mapping (tenant_slug, tenant_id, role).
            components: TenantComponents for the target tenant (used for tenant DB session).
            from_address: From-address for outgoing emails.
            from_name: From-name for outgoing emails.
            instance_name: Tenant display name.
            admin_emails: Admin recipients for the notification email.
        """
        import uuid
        from datetime import datetime

        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        submission_id = str(uuid.uuid4())
        tenant_slug = mapping["tenant_slug"]

        attachments = self.attachment_handler.extract_attachments(
            mail_message, email.message_id
        )

        attachment_records: List[dict] = []
        try:
            for att in attachments:
                key = f"moderation/{submission_id}/{att.filename}"
                data = att.filepath.read_bytes()
                if self.storage_backend and tenant_slug:
                    self.storage_backend.put(
                        tenant_slug,
                        key,
                        data,
                        metadata={
                            "submission_id": submission_id,
                            "submitter_email": email.sender.email,
                        },
                    )
                else:
                    local_dest = Path("data/moderation") / submission_id / att.filename
                    local_dest.parent.mkdir(parents=True, exist_ok=True)
                    local_dest.write_bytes(data)
                attachment_records.append(
                    {
                        "filename": att.filename,
                        "key": key,
                        "size": att.size,
                        "mime_type": att.mime_type,
                        "extension": att.extension,
                    }
                )

            body_text = email.get_body(prefer_text=True) or ""

            submission = PendingTeachSubmission(
                id=submission_id,
                submitter_email=email.sender.email,
                subject=email.subject,
                body_text=body_text,
                attachment_keys=attachment_records,
                original_message_id=email.message_id,
                status=PendingSubmissionStatus.PENDING,
                created_at=datetime.utcnow(),
            )

            with components.conversation_manager.db_manager.get_session() as session:
                session.add(submission)

            logger.info(
                "Queued moderation submission %s for tenant '%s' "
                "from %s with %d attachment(s)",
                submission_id,
                tenant_slug,
                email.sender.email,
                len(attachment_records),
            )

            self._send_moderation_acknowledgement(
                email=email,
                instance_name=instance_name,
                from_address=from_address,
                from_name=from_name,
            )

            if admin_emails:
                self._send_moderation_admin_notification(
                    email=email,
                    submission_id=submission_id,
                    attachment_records=attachment_records,
                    instance_name=instance_name,
                    admin_emails=admin_emails,
                    from_address=from_address,
                    from_name=from_name,
                )
            else:
                logger.warning(
                    "No tenant admins found for tenant '%s'; skipping notification",
                    tenant_slug,
                )
        finally:
            self.attachment_handler.cleanup_attachments(attachments)

    def _send_moderation_acknowledgement(
        self,
        email: EmailMessage,
        instance_name: str,
        from_address: Optional[str],
        from_name: Optional[str],
    ) -> None:
        """Tell the submitter their material is under admin review."""
        try:
            subject = f"Re: {email.subject}"
            body_text = (
                f"Thank you for your message to {instance_name}.\n\n"
                "Your material has been received and is awaiting review by an "
                "administrator. You will be notified once a decision has been "
                "made.\n\n"
                f"---\n{instance_name}"
            )
            body_html = (
                f"<p>Thank you for your message to <strong>{instance_name}</strong>.</p>"
                "<p>Your material has been received and is awaiting review by an "
                "administrator. You will be notified once a decision has been "
                "made.</p>"
                f"<hr><p><em>{instance_name}</em></p>"
            )
            self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=email.message_id,
                from_address=from_address,
                from_name=from_name,
            )
            logger.info("Sent moderation acknowledgement to %s", email.sender.email)
        except Exception as e:
            logger.error("Failed to send moderation acknowledgement: %s", e)

    def _send_moderation_admin_notification(
        self,
        email: EmailMessage,
        submission_id: str,
        attachment_records: List[dict],
        instance_name: str,
        admin_emails: List[str],
        from_address: Optional[str],
        from_name: Optional[str],
    ) -> None:
        """Notify tenant admins that a submission needs review."""
        try:
            admin_url = f"{settings.web_base_url.rstrip('/')}/admin#moderation"
            attachment_summary = (
                ", ".join(a["filename"] for a in attachment_records)
                if attachment_records
                else "(no attachments)"
            )
            subject = (
                f"[{instance_name}] Submission awaiting moderation "
                f"from {email.sender.email}"
            )
            body_text = (
                f"A user has submitted material to the knowledge base that "
                f"requires your review.\n\n"
                f"Submitter: {email.sender.email}\n"
                f"Subject: {email.subject}\n"
                f"Attachments: {attachment_summary}\n\n"
                f"Review and approve/reject in the admin panel:\n{admin_url}\n\n"
                f"---\n{instance_name}"
            )
            body_html = (
                "<p>A user has submitted material to the knowledge base that "
                "requires your review.</p>"
                f"<p><strong>Submitter:</strong> {email.sender.email}<br>"
                f"<strong>Subject:</strong> {email.subject}<br>"
                f"<strong>Attachments:</strong> {attachment_summary}</p>"
                f'<p><a href="{admin_url}">Review in the admin panel</a></p>'
                f"<hr><p><em>{instance_name}</em></p>"
            )
            for admin_email in admin_emails:
                self.email_sender.send_reply(
                    to_address=admin_email,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    from_address=from_address,
                    from_name=from_name,
                )
            logger.info(
                "Sent moderation notification for submission %s to %d admin(s)",
                submission_id,
                len(admin_emails),
            )
        except Exception as e:
            logger.error("Failed to send moderation admin notification: %s", e)

    def _send_rejection_email(
        self,
        email: EmailMessage,
        rejection_type: str,
        instance_name: Optional[str] = None,
        organization: Optional[str] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
    ) -> None:
        """
        Send rejection email to unauthorized sender.

        Args:
            email: Original EmailMessage that was rejected
            rejection_type: Type of rejection ("query" or "teach")
            instance_name: Override instance name (for MT mode)
            organization: Override organization (for MT mode)
            from_address: Override sender email address (for MT mode)
            from_name: Override sender display name (for MT mode)
        """
        inst_name = instance_name or settings.instance_name

        try:
            subject = f"Re: {email.subject}"

            if rejection_type == "query":
                body_text = f"""Thank you for your message to {inst_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to query the knowledge base.

If you believe you should have access, please contact your administrator.

---
{inst_name}"""

                body_html = f"""<p>Thank you for your message to <strong>{inst_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to query the knowledge base.</p>

<p>If you believe you should have access, please contact your administrator.</p>

<hr>
<p><em>{inst_name}</em></p>"""

            else:  # rejection_type == "teach"
                body_text = f"""Thank you for your message to {inst_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to add content to the knowledge base.

If you believe you should have access, please contact your administrator.

---
{inst_name}"""

                body_html = f"""<p>Thank you for your message to <strong>{inst_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to add content to the knowledge base.</p>

<p>If you believe you should have access, please contact your administrator.</p>

<hr>
<p><em>{inst_name}</em></p>"""

            # Send rejection message
            self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
                in_reply_to=email.message_id,
                from_address=from_address,
                from_name=from_name,
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
