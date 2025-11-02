"""
Email parser with whitelist validation and HTML conversion.

This module provides parsing of email messages with support for:
- Header extraction (From, To, CC, Subject, Date, Message-ID)
- Body extraction (text/plain preferred, text/html fallback)
- HTML to text conversion
- Sender whitelist validation
- Processing logic:
  - Direct emails (To: bot) → Query (send reply)
  - CC/BCC/Forwarded → KB ingestion (add to knowledge base)
"""

import logging
import re
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime
from typing import List, Optional, Tuple

import html2text
from imap_tools import MailMessage
from pydantic import BaseModel, Field, field_validator

from src.config import settings

logger = logging.getLogger(__name__)


class EmailAddress(BaseModel):
    """
    Represents a parsed email address with name and email.

    Attributes:
        name: Display name (e.g., "Alice Smith")
        email: Email address (e.g., "alice@example.com")
    """

    name: str = Field(default="", description="Display name")
    email: str = Field(..., description="Email address")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """
        Validate email address format.

        Args:
            v: Email address string.

        Returns:
            Validated email address.

        Raises:
            ValueError: If email format is invalid.
        """
        email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        if not re.match(email_pattern, v):
            raise ValueError(f"Invalid email address: {v}")
        return v.lower().strip()

    def __str__(self) -> str:
        """String representation."""
        if self.name:
            return f"{self.name} <{self.email}>"
        return self.email


class EmailMessage(BaseModel):
    """
    Parsed email message with validation.

    Attributes:
        message_id: Unique message identifier
        sender: Sender email address
        to: List of recipient addresses
        cc: List of CC addresses
        subject: Email subject
        date: Email date
        body_text: Plain text body
        body_html: HTML body (if available)
        is_whitelisted: Whether sender is whitelisted
        is_cced: Whether this is a CC'd message
        attachment_count: Number of attachments
    """

    message_id: str = Field(..., description="Message ID")
    sender: EmailAddress = Field(..., description="Sender address")
    to: List[EmailAddress] = Field(default_factory=list, description="To addresses")
    cc: List[EmailAddress] = Field(default_factory=list, description="CC addresses")
    subject: str = Field(default="", description="Email subject")
    date: Optional[datetime] = Field(default=None, description="Email date")
    body_text: str = Field(default="", description="Plain text body")
    body_html: str = Field(default="", description="HTML body")
    is_whitelisted: bool = Field(default=False, description="Sender is whitelisted")
    is_cced: bool = Field(default=False, description="Is CC'd message")
    attachment_count: int = Field(default=0, description="Number of attachments")
    in_reply_to: Optional[str] = Field(
        default=None, description="In-Reply-To header for threading"
    )
    references: Optional[str] = Field(
        default=None, description="References header for threading"
    )

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, v: str) -> str:
        """
        Clean subject line.

        Args:
            v: Subject string.

        Returns:
            Cleaned subject.
        """
        # Remove excessive whitespace
        return " ".join(v.split()).strip()

    def get_body(self, prefer_text: bool = True) -> str:
        """
        Get email body, preferring text or HTML.

        Args:
            prefer_text: If True, prefer plain text over HTML

        Returns:
            Email body as plain text.
        """
        if prefer_text:
            return self.body_text if self.body_text else self.body_html
        else:
            return self.body_html if self.body_html else self.body_text

    def has_body(self) -> bool:
        """
        Check if email has any body content.

        Returns:
            True if body text or HTML exists.
        """
        return bool(self.body_text or self.body_html)

    def __str__(self) -> str:
        """String representation."""
        return f"Email from {self.sender.email}: {self.subject}"


class EmailParser:
    """
    Parses email messages with whitelist validation.

    This class converts imap-tools MailMessage objects into parsed EmailMessage
    models with:
    - Header extraction
    - Body extraction and HTML conversion
    - Sender whitelist validation
    - CC detection

    Attributes:
        target_address: Target email address for KB contributions
        validator: Whitelist validator instance
        html_converter: HTML to text converter
    """

    def __init__(
        self,
        target_address: Optional[str] = None,
        validator=None,
    ):
        """
        Initialize email parser.

        Args:
            target_address: Target email for KB contributions (defaults to settings)
            validator: Whitelist validator (optional, only used for logging is_whitelisted field)
        """
        self.target_address = (target_address or settings.email_target_address).lower()
        self.validator = validator

        # Configure forwarded email detection
        self.forward_to_kb_enabled = settings.forward_to_kb_enabled
        self.forward_prefixes = [
            prefix.strip().lower()
            for prefix in settings.forward_subject_prefixes.split(",")
            if prefix.strip()
        ]

        # Configure HTML to text converter
        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = False
        self.html_converter.ignore_images = True
        self.html_converter.ignore_emphasis = False
        self.html_converter.body_width = 0  # No line wrapping
        self.html_converter.single_line_break = False

        logger.info(f"EmailParser initialized for target: {self.target_address}")
        if self.forward_to_kb_enabled:
            logger.info(
                f"Forwarded email detection enabled with prefixes: {self.forward_prefixes}"
            )

    def parse_email_address(self, address_str: str) -> Optional[EmailAddress]:
        """
        Parse email address string.

        Args:
            address_str: Email address string (e.g., "Alice <alice@example.com>")

        Returns:
            EmailAddress object or None if parsing fails.
        """
        try:
            name, email = parseaddr(address_str)
            if not email:
                logger.warning(f"No email found in: {address_str}")
                return None

            # Clean name
            name = name.strip('" ')

            return EmailAddress(name=name, email=email)

        except Exception as e:
            logger.error(f"Error parsing email address '{address_str}': {e}")
            return None

    def parse_email_list(self, addresses) -> List[EmailAddress]:
        """
        Parse comma-separated list of email addresses.

        Args:
            addresses: Comma-separated email addresses (string or tuple)

        Returns:
            List of EmailAddress objects.
        """
        if not addresses:
            return []

        # Handle tuple of addresses (from imap-tools)
        if isinstance(addresses, (tuple, list)):
            result = []
            for addr in addresses:
                if addr:  # Skip empty entries
                    parsed = self.parse_email_address(str(addr).strip())
                    if parsed:
                        result.append(parsed)
            return result

        # Handle string (comma-separated)
        result = []
        for addr in str(addresses).split(","):
            parsed = self.parse_email_address(addr.strip())
            if parsed:
                result.append(parsed)

        return result

    def html_to_text(self, html: str) -> str:
        """
        Convert HTML to plain text.

        Args:
            html: HTML content

        Returns:
            Plain text content.
        """
        if not html:
            return ""

        try:
            text = self.html_converter.handle(html)
            # Clean up excessive newlines
            text = re.sub(r"\n{3,}", "\n\n", text)
            return text.strip()

        except Exception as e:
            logger.error(f"Error converting HTML to text: {e}")
            return ""

    def strip_signature(self, text: str) -> str:
        """
        Remove email signature from body text.

        Detects and removes common signature patterns:
        - Standard signature delimiter (-- )
        - "Sent from..." lines
        - Common closing phrases followed by contact info

        Args:
            text: Email body text

        Returns:
            Text with signature removed.
        """
        if not text:
            return text

        lines = text.split("\n")

        # Find signature start position
        sig_start = None

        for i, line in enumerate(lines):
            line_stripped = line.strip()

            # Standard signature delimiter
            if line_stripped == "--" or line_stripped == "-- ":
                sig_start = i
                break

            # "Sent from..." patterns
            if line_stripped.lower().startswith(
                ("sent from", "get outlook for", "download")
            ):
                sig_start = i
                break

            # Common signature starters (must be followed by mostly empty or short lines)
            signature_starters = [
                "best regards",
                "best",
                "regards",
                "cheers",
                "thanks",
                "thank you",
                "sincerely",
                "yours",
                "kind regards",
                "warm regards",
                "cordially",
                "respectfully",
                "with appreciation",
                "many thanks",
            ]

            if any(
                line_stripped.lower().startswith(starter)
                for starter in signature_starters
            ):
                # Check if this looks like a signature (followed by short lines or empty lines)
                if i < len(lines) - 1:
                    remaining_lines = lines[i + 1 :]
                    non_empty = [l for l in remaining_lines[:5] if l.strip()]
                    # If most remaining lines are short (< 50 chars), likely a signature
                    if len(non_empty) <= 3 or all(
                        len(l.strip()) < 50 for l in non_empty[:3]
                    ):
                        sig_start = i
                        break

        # Return text before signature
        if sig_start is not None:
            body_without_sig = "\n".join(lines[:sig_start]).strip()
            logger.debug(f"Stripped signature starting at line {sig_start}")
            return body_without_sig

        return text

    def extract_body(self, message: MailMessage) -> Tuple[str, str]:
        """
        Extract body text and HTML from message.

        Prefers text/plain, falls back to text/html with conversion.
        Automatically strips email signatures from body text.

        Args:
            message: MailMessage object from imap-tools

        Returns:
            Tuple of (body_text, body_html).
        """
        body_text = ""
        body_html = ""

        try:
            # Try to get plain text
            if message.text:
                body_text = message.text.strip()

            # Try to get HTML
            if message.html:
                body_html = message.html.strip()

            # If no plain text but have HTML, convert it
            if not body_text and body_html:
                body_text = self.html_to_text(body_html)
                logger.debug("Converted HTML to text for body")

            # Strip signature from body text
            if body_text:
                body_text = self.strip_signature(body_text)

        except Exception as e:
            logger.error(f"Error extracting body: {e}")

        return body_text, body_html

    def is_cced_message(self, to_addresses: List[EmailAddress]) -> bool:
        """
        Check if message is CC'd (target not in To: field).

        Args:
            to_addresses: List of To: addresses

        Returns:
            True if target address is NOT in To: field.
        """
        target_lower = self.target_address.lower()
        for addr in to_addresses:
            if addr.email.lower() == target_lower:
                return False  # Target is in To: field
        return True  # Target not in To: field (must be CC'd)

    def is_forwarded(self, subject: str) -> bool:
        """
        Check if email subject indicates forwarded message.

        Uses configurable subject prefixes (case-insensitive) to detect
        forwarded emails. Default prefixes are "fw" and "fwd" but can be
        customized for different languages (e.g., "i" for Italian, "rv" for Spanish).

        Args:
            subject: Email subject line

        Returns:
            True if subject starts with a forwarding prefix.
        """
        if not self.forward_to_kb_enabled or not subject:
            return False

        # Normalize subject (lowercase, strip whitespace)
        subject_normalized = subject.lower().strip()

        # Check each prefix with common variations
        for prefix in self.forward_prefixes:
            # Check for "prefix:" at start (e.g., "fw:", "fwd:")
            if subject_normalized.startswith(f"{prefix}:"):
                logger.debug(f"Detected forwarded email with prefix '{prefix}:'")
                return True

        return False

    def parse(self, message: MailMessage) -> Optional[EmailMessage]:
        """
        Parse imap-tools MailMessage into EmailMessage model.

        Args:
            message: MailMessage from imap-tools

        Returns:
            EmailMessage object or None if parsing fails.

        Raises:
            ValueError: If required fields are missing.
        """
        try:
            # Parse message ID - prefer the actual Message-ID header over IMAP UID
            # The Message-ID header is what email clients use for threading
            message_id = message.headers.get("message-id", [""])[0] or message.uid
            if not message_id:
                raise ValueError("Message has no ID")

            logger.info(f"Extracted Message-ID from email: {message_id}")

            # Extract threading headers for conversation tracking
            in_reply_to = message.headers.get("in-reply-to", [""])[0] or None
            references = message.headers.get("references", [""])[0] or None

            if in_reply_to:
                logger.debug(f"In-Reply-To: {in_reply_to}")
            if references:
                logger.debug(f"References: {references}")

            # Parse sender
            sender = self.parse_email_address(message.from_)
            if not sender:
                raise ValueError("Invalid sender address")

            # Check whitelist (for logging only - actual validation done by EmailProcessor)
            is_whitelisted = (
                self.validator.is_allowed(sender.email) if self.validator else False
            )
            if not is_whitelisted and self.validator:
                logger.debug(
                    f"Message from {sender.email} not in parser's whitelist (check EmailProcessor validators)"
                )

            # Parse recipients
            to_addresses = self.parse_email_list(message.to or "")
            cc_addresses = self.parse_email_list(message.cc or "")

            # Check if CC'd
            is_cced = self.is_cced_message(to_addresses)

            # Parse date
            try:
                date = message.date if message.date else None
            except Exception as e:
                logger.warning(f"Error parsing date: {e}")
                date = None

            # Extract body
            body_text, body_html = self.extract_body(message)

            # Count attachments
            attachment_count = len(message.attachments) if message.attachments else 0

            # Create EmailMessage
            email_message = EmailMessage(
                message_id=message_id,
                sender=sender,
                to=to_addresses,
                cc=cc_addresses,
                subject=message.subject or "",
                date=date,
                body_text=body_text,
                body_html=body_html,
                is_whitelisted=is_whitelisted,
                is_cced=is_cced,
                attachment_count=attachment_count,
                in_reply_to=in_reply_to,
                references=references,
            )

            logger.info(
                f"Parsed email: {email_message.message_id} from {sender.email} "
                f"(whitelisted={is_whitelisted}, cc'd={is_cced})"
            )

            return email_message

        except Exception as e:
            logger.error(f"Error parsing message: {e}", exc_info=True)
            return None

    def should_process_as_query(self, email: EmailMessage) -> bool:
        """
        Determine if email should be processed as a query (send reply).

        Queries are direct messages sent TO the bot account (not CC'd),
        excluding forwarded emails when forward detection is enabled.

        Args:
            email: Parsed EmailMessage

        Returns:
            True if should be treated as query, False for KB ingestion.
        """
        # Check if this is a forwarded email (if enabled)
        if self.is_forwarded(email.subject):
            # Forwarded emails are KB contributions, not queries
            return False

        # Direct messages (To: field) are queries - user expects a reply
        if not email.is_cced:
            return True

        # CC'd/BCC'd messages are KB contributions
        return False

    def should_process_for_kb(self, email: EmailMessage) -> bool:
        """
        Determine if email should be processed for KB ingestion.

        KB ingestion requires:
        - Whitelisted sender
        - CC'd, BCC'd, or forwarded (not direct To: recipient)

        Args:
            email: Parsed EmailMessage

        Returns:
            True if should ingest into KB.
        """
        if not email.is_whitelisted:
            return False

        # Forwarded emails (when enabled) are always KB contributions
        if self.is_forwarded(email.subject):
            return True

        # CC'd/BCC'd messages are KB contributions
        if email.is_cced:
            return True

        # Direct messages (To: field) are queries - user expects a reply
        return False
