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
        """
        self.email_client = email_client or EmailClient()
        self.parser = parser or EmailParser()
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

        logger.info(
            "EmailProcessor initialized with hierarchical whitelists (admin > teacher > querier)"
        )

    def process_message(
        self, mail_message: MailMessage, mark_seen: bool = True
    ) -> ProcessingResult:
        """
        Process a single email message.

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

            # Check if already processed
            if self.message_tracker.is_processed(message_id):
                logger.info(f"Message {message_id} already processed, skipping")
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="duplicate",
                )

            # Determine action based on recipient type and check appropriate whitelist
            if self.parser.should_process_as_query(email):
                # Direct message (To: bot) = query - check query whitelist
                if not self.query_validator.is_allowed(email.sender.email):
                    logger.warning(
                        f"Message {message_id} from {email.sender.email} rejected "
                        f"(not in query whitelist)"
                    )
                    # Send rejection email to the sender
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
                result = self._process_query(email)
            elif self.parser.should_process_for_kb(email):
                # CC'd/BCC'd/forwarded = KB ingestion - check teach whitelist
                if not self.teach_validator.is_allowed(email.sender.email):
                    logger.warning(
                        f"Message {message_id} from {email.sender.email} rejected "
                        f"(not in teach whitelist)"
                    )
                    # Send rejection email to the sender
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
                result = self._process_for_kb(email, mail_message)
            else:
                # Should not happen, but handle gracefully
                logger.warning(
                    f"Message {message_id} doesn't match any processing criteria"
                )
                result = ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="skipped",
                )

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

    def _process_for_kb(
        self, email: EmailMessage, mail_message: MailMessage
    ) -> ProcessingResult:
        """
        Process email for knowledge base ingestion.

        Extracts attachments, processes them into text chunks, and adds to KB.
        Implements hash-based deduplication to prevent reingesting identical content:
        - Computes SHA-256 hash of each attachment and email body
        - Checks if hash already exists in knowledge base
        - Skips processing if document already exists
        - Sends acknowledgment email including duplicate count

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage for attachment extraction

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

                        temp_file = tempfile.NamedTemporaryFile(
                            mode="w",
                            suffix=".txt",
                            prefix=f"email_{message_id}_",
                            delete=False,
                            dir=str(settings.email_temp_dir),
                        )
                        temp_file.write(body_text)
                        temp_file.close()

                        # Check if email body content already exists in KB
                        body_file_path = Path(temp_file.name)
                        body_hash = self.doc_processor.compute_file_hash(body_file_path)

                        if self.kb_manager.document_exists(body_hash):
                            logger.info(
                                f"Email body content from {email.sender.email} already in KB (hash: {body_hash[:8]}...)"
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
                        # Create descriptive filename
                        date_str = (
                            email.date.strftime("%Y-%m-%d")
                            if email.date
                            else "unknown-date"
                        )
                        sender_name = email.sender.email.split("@")[
                            0
                        ]  # Get name part of email
                        subject_clean = (
                            email.subject[:50] if email.subject else "No Subject"
                        )
                        # Remove invalid filename characters
                        subject_clean = "".join(
                            c
                            for c in subject_clean
                            if c.isalnum() or c in (" ", "-", "_")
                        ).strip()
                        descriptive_filename = f"Email from {sender_name} on {date_str} - {subject_clean}.txt"

                        nodes = self.doc_processor.process_document(
                            file_path=Path(temp_file.name),
                            source_type="email",
                            extra_metadata={
                                "filename": descriptive_filename,  # Override temp filename
                                "sender": email.sender.email,
                                "subject": email.subject,
                                "date": str(email.date) if email.date else None,
                            },
                        )

                        # Add to knowledge base
                        self.kb_manager.add_nodes(nodes)
                        chunks_created = len(nodes)

                        logger.info(
                            f"Successfully added email body to KB: {chunks_created} chunks created"
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
                            self._send_kb_acknowledgment(email, 0, chunks_created)

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
                    file_hash = self.doc_processor.compute_file_hash(
                        attachment.filepath
                    )
                    file_stat = attachment.filepath.stat()
                    file_mtime = file_stat.st_mtime

                    # Check if document with same content already exists
                    if self.kb_manager.document_exists(file_hash):
                        logger.info(
                            f"Document {attachment.filename} already in KB (hash: {file_hash[:8]}...), skipping"
                        )
                        duplicates_skipped += 1
                        continue

                    # Check if document with same filename but different content exists
                    existing_doc = self.kb_manager.get_document_by_filename(
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
                            chunks_deleted = (
                                self.kb_manager.delete_document_by_filename(
                                    attachment.filename
                                )
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

                    nodes = self.doc_processor.process_document(
                        file_path=attachment.filepath,
                        source_type="email",
                        extra_metadata=extra_metadata,
                    )

                    if nodes:
                        # Add to knowledge base
                        self.kb_manager.add_nodes(nodes)
                        chunks_created += len(nodes)
                        attachments_processed += 1
                        processed_files.append(attachment)
                        logger.info(
                            f"Added {attachment.filename} to KB: {len(nodes)} chunks"
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
                    email, attachments_processed, chunks_created, duplicates_skipped
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
            if attachments:
                logger.info(
                    f"Archiving {len(attachments)} attachments to documents folder"
                )
                self.attachment_handler.archive_attachments(attachments)
                # Cleanup temp files after archival
                self.attachment_handler.cleanup_attachments(attachments)

    def _process_query(self, email: EmailMessage) -> ProcessingResult:
        """
        Process email as a query and send automated RAG response.

        Args:
            email: Parsed EmailMessage

        Returns:
            ProcessingResult with query outcome.
        """
        message_id = email.message_id

        logger.info(f"Processing query from {email.sender.email}: {email.subject}")

        try:
            # Extract thread ID for conversation tracking
            thread_id = conversation_manager.extract_thread_id_from_email(
                message_id=email.message_id,
                in_reply_to=email.in_reply_to,
                references=email.references,
            )
            logger.debug(f"Thread ID: {thread_id}")

            # Get conversation history for context
            conversation_context = conversation_manager.format_conversation_context(
                thread_id=thread_id,
                max_messages=10,  # Last 10 messages for context
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

            # Store user query in conversation database
            conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.QUERY,
                content=query_text,
                sender=email.sender.email,
                subject=email.subject,
                channel=ChannelType.EMAIL,
                timestamp=email.date,
            )
            logger.debug(f"Stored user query in conversation {thread_id}")

            # Check if sender is admin
            is_admin = self.admin_validator.is_allowed(email.sender.email)
            if is_admin:
                logger.info(f"Admin user detected: {email.sender.email}")

            # Check if this is a confirmation email (search anywhere in subject or body)
            if is_admin:
                # Search for confirmation token in subject + body
                search_text = f"{email.subject or ''} {query_text}".upper()
                if "CONFIRM" in search_text:
                    logger.info(
                        f"Detected confirmation request from admin {email.sender.email}"
                    )
                    return self._handle_confirmation(
                        email, message_id, query_text, email.subject or ""
                    )

            # Process query through RAG engine with conversation context
            logger.debug(f"Querying RAG engine for message {message_id}")
            result = self.query_handler.process_query(
                query_text=query_text,
                user_email=email.sender.email,
                is_admin=is_admin,
                is_email_request=True,  # Email requests require confirmation for whitelist changes
                context={
                    "message_id": message_id,
                    "subject": email.subject,
                    "date": str(email.date) if email.date else None,
                    "conversation_history": conversation_context,  # Add conversation context
                },
            )

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

            # Format response email
            subject, plain_text, html_body = format_response_email(
                response_text=result["response"],
                sources=result["sources"],
                instance_name=settings.instance_name,
                original_subject=email.subject,
            )

            # Check if tool already sent an email (e.g., confirmation email)
            skip_reply = result.get("metadata", {}).get("skip_email_reply", False)
            if skip_reply:
                logger.info(
                    f"Skipping automatic email reply - tool already sent email to {email.sender.email}"
                )
                # Mark as processed successfully
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

            # Send reply email
            logger.info(f"Sending reply to {email.sender.email}")
            send_success = self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=plain_text,
                body_html=html_body,
                in_reply_to=message_id,
                references=[message_id],
                attachments=attachments,
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

            # Store assistant reply in conversation database
            conversation_manager.add_message(
                thread_id=thread_id,
                message_type=MessageType.REPLY,
                content=result["response"],
                sender=settings.email_target_address,
                subject=subject,
                channel=ChannelType.EMAIL,
            )
            logger.debug(f"Stored assistant reply in conversation {thread_id}")

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
    ) -> None:
        """
        Send acknowledgment email after successful KB ingestion.

        Args:
            email: Original EmailMessage that was processed
            attachments_processed: Number of attachments successfully added
            chunks_created: Number of text chunks created
            duplicates_skipped: Number of duplicate documents skipped
        """
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

            body_text = f"""Thank you for contributing to the {settings.instance_name} knowledge base.

The following material has been successfully processed:
- Source: {content_summary}
- Text chunks created: {chunks_created}
- Received from: {email.sender.email}{duplicate_text}

{"This content is now available for queries from authorized users." if chunks_created > 0 else "Note: All documents were already present in the knowledge base."}

---
{settings.instance_name}
{settings.organization}"""

            body_html = f"""<p>Thank you for contributing to the <strong>{settings.instance_name}</strong> knowledge base.</p>

<p>The following material has been successfully processed:</p>
<ul>
<li><strong>Source:</strong> {content_summary}</li>
<li><strong>Text chunks created:</strong> {chunks_created}</li>
<li><strong>Received from:</strong> {email.sender.email}</li>{duplicate_html}
</ul>

<p>{"This content is now available for queries from authorized users." if chunks_created > 0 else "Note: All documents were already present in the knowledge base."}</p>

<hr>
<p><em>{settings.instance_name}</em><br>
<em>{settings.organization}</em></p>"""

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

    def _send_rejection_email(self, email: EmailMessage, rejection_type: str) -> None:
        """
        Send rejection email to non-whitelisted sender.

        Args:
            email: Original EmailMessage that was rejected
            rejection_type: Type of rejection ("query" or "teach")
        """
        try:
            subject = f"Re: {email.subject}"

            if rejection_type == "query":
                body_text = f"""Thank you for your message to {settings.instance_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to query the knowledge base.

If you believe you should have access, please contact the administrator at {settings.organization}.

---
{settings.instance_name}
{settings.organization}"""

                body_html = f"""<p>Thank you for your message to <strong>{settings.instance_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to query the knowledge base.</p>

<p>If you believe you should have access, please contact the administrator at <em>{settings.organization}</em>.</p>

<hr>
<p><em>{settings.instance_name}</em><br>
<em>{settings.organization}</em></p>"""

            else:  # rejection_type == "teach"
                body_text = f"""Thank you for your message to {settings.instance_name}.

Unfortunately, your email address ({email.sender.email}) is not authorized to add content to the knowledge base.

If you believe you should have access, please contact the administrator at {settings.organization}.

---
{settings.instance_name}
{settings.organization}"""

                body_html = f"""<p>Thank you for your message to <strong>{settings.instance_name}</strong>.</p>

<p>Unfortunately, your email address (<code>{email.sender.email}</code>) is not authorized to add content to the knowledge base.</p>

<p>If you believe you should have access, please contact the administrator at <em>{settings.organization}</em>.</p>

<hr>
<p><em>{settings.instance_name}</em><br>
<em>{settings.organization}</em></p>"""

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
