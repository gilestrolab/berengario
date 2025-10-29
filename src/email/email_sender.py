"""
Email sender module for sending automated replies via SMTP.

Handles SMTP connection, email composition, and sending with proper error handling.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional

from src.config import settings

logger = logging.getLogger(__name__)


class EmailSender:
    """
    Handles sending email responses via SMTP.

    Supports TLS/SSL connections and HTML/plain text email composition.

    Attributes:
        smtp_server: SMTP server address
        smtp_port: SMTP server port
        smtp_user: SMTP username
        smtp_password: SMTP password
        use_tls: Whether to use TLS encryption
        from_address: Sender email address
        from_name: Sender display name
    """

    def __init__(
        self,
        smtp_server: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        use_tls: Optional[bool] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
    ):
        """
        Initialize email sender.

        Args:
            smtp_server: SMTP server address (defaults to settings)
            smtp_port: SMTP port (defaults to settings)
            smtp_user: SMTP username (defaults to settings)
            smtp_password: SMTP password (defaults to settings)
            use_tls: Use TLS encryption (defaults to settings)
            from_address: Sender email address (defaults to settings)
            from_name: Sender display name (defaults to settings)
        """
        self.smtp_server = smtp_server or settings.smtp_server
        self.smtp_port = smtp_port or settings.smtp_port
        self.smtp_user = smtp_user or settings.smtp_user
        self.smtp_password = smtp_password or settings.smtp_password
        self.use_tls = use_tls if use_tls is not None else settings.smtp_use_tls
        self.from_address = from_address or settings.email_target_address
        self.from_name = from_name or settings.email_display_name

        logger.info(
            f"EmailSender initialized: {self.smtp_server}:{self.smtp_port} "
            f"(TLS: {self.use_tls})"
        )

    def send_reply(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[List[str]] = None,
    ) -> bool:
        """
        Send an email reply.

        Args:
            to_address: Recipient email address
            subject: Email subject line
            body_text: Plain text email body
            body_html: HTML email body (optional)
            in_reply_to: Message-ID of email being replied to
            references: List of message IDs in conversation thread

        Returns:
            True if email sent successfully, False otherwise.
        """
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["From"] = f"{self.from_name} <{self.from_address}>"
            msg["To"] = to_address
            msg["Subject"] = subject

            # Add threading headers for proper conversation grouping
            if in_reply_to:
                msg["In-Reply-To"] = in_reply_to
            if references:
                msg["References"] = " ".join(references)

            # Attach plain text version
            text_part = MIMEText(body_text, "plain", "utf-8")
            msg.attach(text_part)

            # Attach HTML version if provided
            if body_html:
                html_part = MIMEText(body_html, "html", "utf-8")
                msg.attach(html_part)

            # Connect to SMTP server
            logger.info(f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}")

            if self.use_tls:
                # Use STARTTLS (port 587)
                smtp = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
            else:
                # Direct connection (port 25 or 465 for SSL)
                smtp = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)

            # Authenticate
            logger.debug(f"Authenticating as {self.smtp_user}")
            smtp.login(self.smtp_user, self.smtp_password)

            # Send email
            smtp.send_message(msg)
            smtp.quit()

            logger.info(f"Successfully sent email to {to_address}: {subject}")
            return True

        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error sending email: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending email: {e}", exc_info=True)
            return False

    def test_connection(self) -> bool:
        """
        Test SMTP connection and authentication.

        Returns:
            True if connection successful, False otherwise.
        """
        try:
            logger.info(f"Testing SMTP connection to {self.smtp_server}:{self.smtp_port}")

            if self.use_tls:
                smtp = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
            else:
                smtp = smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30)

            smtp.login(self.smtp_user, self.smtp_password)
            smtp.quit()

            logger.info("SMTP connection test successful")
            return True

        except Exception as e:
            logger.error(f"SMTP connection test failed: {e}")
            return False


def format_response_email(
    response_text: str,
    sources: List[dict],
    instance_name: str,
    original_subject: str,
) -> tuple[str, str, str]:
    """
    Format RAG response into email-friendly text and HTML.

    Args:
        response_text: RAG-generated response text
        sources: List of source documents with metadata
        instance_name: Name of the RAG instance
        original_subject: Original email subject

    Returns:
        Tuple of (subject, plain_text_body, html_body).
    """
    # Prepare subject line
    if not original_subject.lower().startswith("re:"):
        subject = f"Re: {original_subject}"
    else:
        subject = original_subject

    # Format sources section
    if sources:
        sources_text = "\n\nSources:\n"
        sources_html = "<h3>Sources:</h3><ul>"

        for idx, source in enumerate(sources, 1):
            filename = source.get("filename", "Unknown document")
            score = source.get("score", 0)

            sources_text += f"{idx}. {filename} (relevance: {score:.2f})\n"
            sources_html += f"<li><strong>{filename}</strong> (relevance: {score:.2f})</li>"

        sources_html += "</ul>"
    else:
        sources_text = ""
        sources_html = ""

    # Build plain text version
    plain_text = f"""{response_text}{sources_text}

---
This response was generated by {instance_name}.
If you have follow-up questions, simply reply to this email.
"""

    # Build HTML version
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .response {{
            background-color: #f9f9f9;
            border-left: 4px solid #4CAF50;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .sources {{
            background-color: #f0f7ff;
            border-left: 4px solid #2196F3;
            padding: 15px;
            margin-bottom: 20px;
        }}
        .sources h3 {{
            margin-top: 0;
            color: #2196F3;
        }}
        .sources ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .footer {{
            border-top: 1px solid #ddd;
            padding-top: 15px;
            margin-top: 20px;
            font-size: 0.9em;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="response">
        {response_text.replace(chr(10), '<br>')}
    </div>

    {f'<div class="sources">{sources_html}</div>' if sources else ''}

    <div class="footer">
        <p>This response was generated by <strong>{instance_name}</strong>.</p>
        <p>If you have follow-up questions, simply reply to this email.</p>
    </div>
</body>
</html>
"""

    return subject, plain_text, html_body


# Global email sender instance
email_sender = EmailSender()
