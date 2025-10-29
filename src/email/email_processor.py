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
from typing import List, Optional, Tuple

from imap_tools import MailMessage

from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.email.attachment_handler import AttachmentHandler, AttachmentInfo
from src.email.email_client import EmailClient
from src.email.email_parser import EmailMessage, EmailParser
from src.email.email_sender import EmailSender, format_response_email
from src.email.message_tracker import MessageTracker
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
        query_handler: Optional[QueryHandler] = None,
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
        """
        self.email_client = email_client or EmailClient()
        self.parser = parser or EmailParser()
        self.attachment_handler = attachment_handler or AttachmentHandler()
        self.doc_processor = doc_processor or DocumentProcessor()
        self.kb_manager = kb_manager or KnowledgeBaseManager()
        self.message_tracker = message_tracker or MessageTracker()
        self.email_sender = email_sender or EmailSender()
        self.query_handler = query_handler or QueryHandler()

        logger.info("EmailProcessor initialized")

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

            # Check whitelist
            if not email.is_whitelisted:
                logger.warning(
                    f"Message {message_id} from {email.sender.email} rejected (not whitelisted)"
                )
                self.message_tracker.mark_processed(
                    message_id=message_id,
                    sender=email.sender.email,
                    subject=email.subject,
                    status="rejected",
                    error_message="Sender not whitelisted",
                )
                if mark_seen:
                    self.email_client.mark_seen(mail_message.uid)
                return ProcessingResult(
                    message_id=message_id,
                    success=True,
                    action="rejected",
                )

            # Determine action based on recipient type
            if self.parser.should_process_as_query(email):
                # Direct message (To: bot) = query (send reply)
                result = self._process_query(email)
            elif self.parser.should_process_for_kb(email):
                # CC'd/BCC'd/forwarded = KB ingestion (add to knowledge base)
                result = self._process_for_kb(email, mail_message)
            else:
                # Should not happen, but handle gracefully
                logger.warning(f"Message {message_id} doesn't match any processing criteria")
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
                if 'email' in locals():
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

        Args:
            email: Parsed EmailMessage
            mail_message: Raw MailMessage for attachment extraction

        Returns:
            ProcessingResult with ingestion outcome.
        """
        message_id = email.message_id
        attachments_processed = 0
        chunks_created = 0
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
                            mode='w',
                            suffix='.txt',
                            prefix=f'email_{message_id}_',
                            delete=False,
                            dir=str(settings.email_temp_dir)
                        )
                        temp_file.write(body_text)
                        temp_file.close()

                        # Process email body as text document
                        from pathlib import Path
                        nodes = self.doc_processor.process_document(
                            file_path=Path(temp_file.name),
                            source_type="email",
                            extra_metadata={
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
                    # Check if document already exists in KB
                    file_hash = self.doc_processor.compute_file_hash(attachment.filepath)
                    if self.kb_manager.document_exists(file_hash):
                        logger.info(
                            f"Document {attachment.filename} already in KB (hash: {file_hash[:8]}...)"
                        )
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
                f"attachments, {chunks_created} chunks"
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
            # Cleanup attachments
            if attachments:
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

            # Process query through RAG engine
            logger.debug(f"Querying RAG engine for message {message_id}")
            result = self.query_handler.process_query(
                query_text=query_text,
                user_email=email.sender.email,
                context={
                    "message_id": message_id,
                    "subject": email.subject,
                    "date": str(email.date) if email.date else None,
                },
            )

            if not result["success"]:
                logger.error(f"RAG query failed for {message_id}: {result.get('error')}")
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

            # Send reply email
            logger.info(f"Sending reply to {email.sender.email}")
            send_success = self.email_sender.send_reply(
                to_address=email.sender.email,
                subject=subject,
                body_text=plain_text,
                body_html=html_body,
                in_reply_to=message_id,
                references=[message_id],
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


# Global email processor instance
email_processor = EmailProcessor()
