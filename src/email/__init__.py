"""
Email processing package for Berengario.

Handles IMAP inbox monitoring, email parsing, attachment extraction,
query processing with RAG, and automated email responses.
"""

from src.email.attachment_handler import AttachmentHandler, attachment_handler
from src.email.email_client import EmailClient
from src.email.email_parser import EmailParser
from src.email.email_processor import EmailProcessor
from src.email.email_sender import EmailSender, email_sender, format_response_email
from src.email.message_tracker import MessageTracker

__all__ = [
    "AttachmentHandler",
    "attachment_handler",
    "EmailClient",
    "EmailParser",
    "EmailProcessor",
    "EmailSender",
    "email_sender",
    "format_response_email",
    "MessageTracker",
]
