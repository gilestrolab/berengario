"""Email processing package for RAGInbox."""

from src.email.attachment_handler import AttachmentHandler, attachment_handler
from src.email.email_client import EmailClient
from src.email.email_parser import EmailParser, email_parser
from src.email.email_processor import EmailProcessor, email_processor
from src.email.message_tracker import MessageTracker
from src.email.whitelist_validator import WhitelistValidator, whitelist_validator

__all__ = [
    "AttachmentHandler",
    "attachment_handler",
    "EmailClient",
    "EmailParser",
    "email_parser",
    "EmailProcessor",
    "email_processor",
    "MessageTracker",
    "WhitelistValidator",
    "whitelist_validator",
]
