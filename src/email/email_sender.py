"""
Email sender module for sending automated replies via SMTP.

Handles SMTP connection, email composition, and sending with proper error handling.
"""

import base64
import email.utils
import logging
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional

import markdown

from src.config import settings

logger = logging.getLogger(__name__)


def generate_feedback_token(message_id: int, tenant_slug: Optional[str] = None) -> str:
    """
    Generate a URL-safe token from a message ID and optional tenant slug.

    Args:
        message_id: Database ID of the conversation message
        tenant_slug: Tenant slug for multi-tenant mode (optional)

    Returns:
        Base64-encoded token for use in feedback URLs
    """
    payload = f"{tenant_slug}:{message_id}" if tenant_slug else str(message_id)
    token = base64.urlsafe_b64encode(payload.encode()).decode()
    return token


def decode_feedback_token(token: str) -> tuple[Optional[int], Optional[str]]:
    """
    Decode a feedback token to get the message ID and optional tenant slug.

    Args:
        token: Base64-encoded token

    Returns:
        Tuple of (message_id, tenant_slug). tenant_slug is None for
        legacy single-tenant tokens.
    """
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        if ":" in decoded:
            slug, mid = decoded.rsplit(":", 1)
            return int(mid), slug
        return int(decoded), None
    except (ValueError, Exception) as e:
        logger.warning(f"Failed to decode feedback token: {e}")
        return None, None


def generate_feedback_urls(
    message_id: int,
    base_url: Optional[str] = None,
    tenant_slug: Optional[str] = None,
) -> Dict[str, str]:
    """
    Generate feedback URLs for thumbs up/down.

    Args:
        message_id: Database ID of the conversation message
        base_url: Base URL for the web interface (defaults to settings)
        tenant_slug: Tenant slug for multi-tenant mode (optional)

    Returns:
        Dictionary with 'positive' and 'negative' URLs
    """
    # Use settings base URL if not provided
    if not base_url:
        base_url = settings.web_base_url

    token = generate_feedback_token(message_id, tenant_slug=tenant_slug)

    return {
        "positive": f"{base_url}/feedback?token={token}&rating=positive",
        "negative": f"{base_url}/feedback?token={token}&rating=negative",
    }


def load_custom_footer(
    instance_name: str,
    message_id: Optional[int] = None,
    custom_footer_file=None,
    organization: Optional[str] = None,
    tenant_slug: Optional[str] = None,
) -> tuple[str, str]:
    """
    Load custom footer or use default, optionally with feedback links.

    Args:
        instance_name: Name of the instance for default footer
        message_id: Optional message ID for generating feedback links
        custom_footer_file: Optional path to custom footer file. If None,
            reads from settings.email_custom_footer_file.
        organization: Organization name for footer signature.

    Returns:
        Tuple of (plain_text_footer, html_footer)
    """
    # Generate feedback section if message_id provided
    feedback_plain = ""
    feedback_html = ""

    if message_id:
        feedback_urls = generate_feedback_urls(message_id, tenant_slug=tenant_slug)
        feedback_plain = f"\n\nWas this response helpful?\nYes: {feedback_urls['positive']}\nNo: {feedback_urls['negative']}"

        feedback_html = f"""
    <div style="margin-top: 20px; padding: 10px 0; border-top: 1px solid #ccc; font-size: 13px; color: #666;">
        <p style="margin: 0;">Was this response helpful?
        <a href="{feedback_urls['positive']}" style="color: #337ab7; text-decoration: underline; margin-left: 8px;">Yes</a> |
        <a href="{feedback_urls['negative']}" style="color: #337ab7; text-decoration: underline;">No</a></p>
    </div>"""

    # Resolve footer file: explicit param takes priority, then settings
    footer_file = custom_footer_file
    if footer_file is None:
        footer_file = settings.email_custom_footer_file

    if footer_file and footer_file.exists():
        try:
            with open(footer_file, "r", encoding="utf-8") as f:
                footer_text = f.read().strip()

            if footer_text:
                # Plain text version
                plain_footer = f"\n\n---\n{footer_text}{feedback_plain}"

                # HTML version (convert newlines to <br>)
                html_footer = f'<div class="footer">{footer_text.replace(chr(10), "<br>")}</div>{feedback_html}'

                logger.info(f"Loaded custom footer from {footer_file}")
                return plain_footer, html_footer
        except Exception as e:
            logger.warning(f"Failed to load custom footer file: {e}")

    # Default footer
    org_line_plain = f"\n{organization}" if organization else ""
    org_line_html = f"\n        <p><em>{organization}</em></p>" if organization else ""
    plain_footer = f"\n\n---\nThis response was generated by {instance_name}.{org_line_plain}\nIf you have follow-up questions, simply reply to this email.{feedback_plain}"
    html_footer = f"""<div class="footer">
        <p>This response was generated by <strong>{instance_name}</strong>.</p>{org_line_html}
        <p>If you have follow-up questions, simply reply to this email.</p>
    </div>{feedback_html}"""

    return plain_footer, html_footer


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

    @staticmethod
    def _format_message_id(msg_id: str) -> str:
        """
        Ensure Message-ID is properly formatted with angle brackets.

        Args:
            msg_id: Message ID string

        Returns:
            Message ID enclosed in angle brackets if not already.
        """
        if not msg_id:
            return msg_id
        msg_id = msg_id.strip()
        # Add angle brackets if not present
        if not msg_id.startswith("<"):
            msg_id = "<" + msg_id
        if not msg_id.endswith(">"):
            msg_id = msg_id + ">"
        return msg_id

    def send_reply(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        in_reply_to: Optional[str] = None,
        references: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, any]]] = None,
        from_address: Optional[str] = None,
        from_name: Optional[str] = None,
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
            attachments: List of attachments, each dict with 'content' (bytes or str),
                        'filename' (str), and optional 'content_type' (str)
            from_address: Override sender address (for multi-tenant)
            from_name: Override sender display name (for multi-tenant)

        Returns:
            True if email sent successfully, False otherwise.
        """
        effective_from = from_address or self.from_address
        effective_name = from_name or self.from_name

        try:
            # Create message - use "mixed" if attachments, otherwise "alternative"
            if attachments:
                msg = MIMEMultipart("mixed")
            else:
                msg = MIMEMultipart("alternative")

            msg["From"] = f"{effective_name} <{effective_from}>"
            msg["To"] = to_address
            msg["Subject"] = subject
            msg["Date"] = email.utils.formatdate(localtime=True)
            msg["Message-ID"] = email.utils.make_msgid(
                domain=effective_from.split("@")[1]
            )

            # Add threading headers for proper conversation grouping
            # Ensure Message-IDs are properly formatted with angle brackets (RFC 5322)
            if in_reply_to:
                formatted_in_reply_to = self._format_message_id(in_reply_to)
                msg["In-Reply-To"] = formatted_in_reply_to
                logger.info(f"Setting In-Reply-To header: {formatted_in_reply_to}")
            if references:
                # Format each reference and join with space
                formatted_refs = [self._format_message_id(ref) for ref in references]
                msg["References"] = " ".join(formatted_refs)
                logger.info(f"Setting References header: {' '.join(formatted_refs)}")

            logger.info(f"Sending email with Subject: {subject}")

            # Create body container (for text alternatives)
            if attachments:
                body_container = MIMEMultipart("alternative")
            else:
                body_container = msg

            # Attach plain text version
            text_part = MIMEText(body_text, "plain", "utf-8")
            body_container.attach(text_part)

            # Attach HTML version if provided
            if body_html:
                html_part = MIMEText(body_html, "html", "utf-8")
                body_container.attach(html_part)

            # Attach body container if we have attachments
            if attachments:
                msg.attach(body_container)

            # Attach files
            if attachments:
                for attachment in attachments:
                    content = attachment.get("content")
                    filename = attachment.get("filename", "attachment")
                    content_type = attachment.get(
                        "content_type", "application/octet-stream"
                    )

                    # Convert string content to bytes if needed
                    if isinstance(content, str):
                        content = content.encode("utf-8")

                    part = MIMEBase(*content_type.split("/", 1))
                    part.set_payload(content)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition", f'attachment; filename="{filename}"'
                    )
                    msg.attach(part)

                    logger.debug(f"Attached file: {filename} ({content_type})")

            # Connect to SMTP server
            logger.info(
                f"Connecting to SMTP server: {self.smtp_server}:{self.smtp_port}"
            )

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
            logger.info(
                f"Testing SMTP connection to {self.smtp_server}:{self.smtp_port}"
            )

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
    message_id: Optional[int] = None,
    organization: Optional[str] = None,
    response_format: Optional[str] = None,
    tenant_slug: Optional[str] = None,
) -> tuple[str, str, str]:
    """
    Format RAG response into email-friendly text and HTML.

    Supports three formats based on EMAIL_RESPONSE_FORMAT setting:
    - 'text': Plain text only
    - 'markdown': Markdown syntax in plain text
    - 'html': Styled HTML (default)

    Args:
        response_text: RAG-generated response text
        sources: List of source documents with metadata
        instance_name: Name of the RAG instance
        original_subject: Original email subject
        message_id: Optional database message ID for feedback links
        organization: Organization name for footer signature.
        response_format: Email format override (html/markdown/text).
        tenant_slug: Tenant slug for multi-tenant feedback tokens.

    Returns:
        Tuple of (subject, plain_text_body, html_body).
    """
    # Prepare subject line
    if not original_subject.lower().startswith("re:"):
        subject = f"Re: {original_subject}"
    else:
        subject = original_subject

    # Load custom footer with optional feedback links
    plain_footer, html_footer = load_custom_footer(
        instance_name,
        message_id,
        organization=organization,
        tenant_slug=tenant_slug,
    )

    # Get email format: explicit parameter > global settings
    email_format = (response_format or settings.email_response_format).lower()

    # Format based on selected format
    if email_format == "text":
        # Plain text only format
        plain_text, html_body = _format_text_email(response_text, sources, plain_footer)
    elif email_format == "markdown":
        # Markdown format
        plain_text, html_body = _format_markdown_email(
            response_text, sources, plain_footer
        )
    else:  # html (default)
        # HTML format with styling
        plain_text, html_body = _format_html_email(
            response_text, sources, plain_footer, html_footer
        )

    return subject, plain_text, html_body


def _format_text_email(
    response_text: str, sources: List[dict], plain_footer: str
) -> tuple[str, str]:
    """Format email as plain text."""
    # Format sources
    sources_text = ""
    if sources:
        sources_text = "\n\nSources:\n"
        for idx, source in enumerate(sources, 1):
            filename = source.get("filename", "Unknown document")
            score = source.get("score", 0)
            sources_text += f"{idx}. {filename} (relevance: {score:.2f})\n"

    # Plain text body
    plain_text = f"{response_text}{sources_text}{plain_footer}"

    # Minimal HTML fallback for compatibility
    html_body = f"<html><body><pre>{plain_text}</pre></body></html>"

    return plain_text, html_body


def _format_markdown_email(
    response_text: str, sources: List[dict], plain_footer: str
) -> tuple[str, str]:
    """Format email with markdown syntax."""
    # Format sources in markdown
    sources_text = ""
    if sources:
        sources_text = "\n\n## Sources\n\n"
        for idx, source in enumerate(sources, 1):
            filename = source.get("filename", "Unknown document")
            score = source.get("score", 0)
            sources_text += f"{idx}. **{filename}** (relevance: {score:.2f})\n"

    # Plain text body with markdown
    plain_text = f"{response_text}{sources_text}{plain_footer}"

    # Minimal HTML fallback
    html_body = f"<html><body><pre>{plain_text}</pre></body></html>"

    return plain_text, html_body


def _format_html_email(
    response_text: str,
    sources: List[dict],
    plain_footer: str,
    html_footer: str,
) -> tuple[str, str]:
    """Format email with styled HTML."""

    def format_source_display(source: dict) -> tuple[str, str]:
        """
        Format source information for display.

        Returns:
            Tuple of (plain_text_line, html_line)
        """
        # Check if this is an email source with metadata
        sender = source.get("sender")
        subject = source.get("subject")
        score = source.get("score", 0)

        if sender and subject:
            # Email source - show sender and subject
            plain = f'Email from {sender}: "{subject}" (relevance: {score:.2f})'
            html = f'<strong>Email from {sender}:</strong> "{subject}" <span style="color: #8C8279;">(relevance: {score:.2f})</span>'
        elif subject:
            # Has subject but no sender
            plain = f'Email: "{subject}" (relevance: {score:.2f})'
            html = f'<strong>Email:</strong> "{subject}" <span style="color: #8C8279;">(relevance: {score:.2f})</span>'
        else:
            # File source - show filename
            filename = source.get("filename", "Unknown document")
            plain = f"{filename} (relevance: {score:.2f})"
            html = f'<strong>{filename}</strong> <span style="color: #8C8279;">(relevance: {score:.2f})</span>'

        return plain, html

    # Format sources for plain text
    sources_text = ""
    if sources:
        sources_text = "\n\nSources:\n"
        for idx, source in enumerate(sources, 1):
            plain, _ = format_source_display(source)
            sources_text += f"{idx}. {plain}\n"

    # Plain text version
    plain_text = f"{response_text}{sources_text}{plain_footer}"

    # Format sources for HTML
    sources_html = ""
    if sources:
        sources_html = "<h3>Sources:</h3><ul>"
        for source in sources:
            _, html = format_source_display(source)
            sources_html += f"<li>{html}</li>"
        sources_html += "</ul>"

    # Convert markdown response to HTML
    response_html = markdown.markdown(
        response_text, extensions=["extra", "nl2br", "sane_lists"]
    )

    # Build HTML version with styling
    html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #2E2E2E;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .response {{
            margin-bottom: 20px;
        }}
        .response h3 {{
            margin-top: 0;
            color: #2E2E2E;
        }}
        .response strong {{
            color: #2A2520;
        }}
        .sources {{
            margin-bottom: 20px;
        }}
        .sources h3 {{
            margin-top: 0;
            color: #2E2E2E;
        }}
        .sources ul {{
            margin: 10px 0;
            padding-left: 20px;
        }}
        .footer {{
            border-top: 1px solid #D5C9B8;
            padding-top: 15px;
            margin-top: 20px;
            font-size: 0.9em;
            color: #8C8279;
        }}
    </style>
</head>
<body>
    <div class="response">
        {response_html}
    </div>

    {f'<div class="sources">{sources_html}</div>' if sources else ''}

    {html_footer}
</body>
</html>
"""

    return plain_text, html_body


def format_welcome_email(
    to_email: str,
    role: str,
    instance_name: str,
    organization: str = "",
    instance_description: str = "",
    query_address: str = "",
    teach_address: Optional[str] = None,
    web_base_url: str = "",
    admin_emails: Optional[List[str]] = None,
) -> tuple[str, str, str]:
    """
    Format a welcome email for a newly enrolled user.

    Content varies by role (cumulative):
    - All roles: greeting, what Berengario is, how to ask questions
    - Teacher (teacher + admin): how to add to KB
    - Admin (admin only): admin panel access
    - Non-admin roles: admin contact info (if provided)

    When teach_address is configured, teaching instructions reference
    the teach address instead of the query address.

    Args:
        to_email: Recipient email address.
        role: User role (querier, teacher, admin).
        instance_name: Name of the instance.
        organization: Organization name (optional).
        instance_description: Instance/team description (optional, shown in signature).
        query_address: Email address for queries.
        teach_address: Dedicated teach address (optional).
        web_base_url: Base URL for web interface.
        admin_emails: List of admin email addresses (shown to non-admin roles).

    Returns:
        Tuple of (subject, plain_text, html_body).
    """
    role = role.lower()
    org_text = f" at {organization}" if organization else ""
    subject = f"Welcome to {instance_name}"

    # The address used for KB ingestion: teach address if set, otherwise query address
    kb_address = teach_address or query_address

    # Filter admin list: exclude domain wildcards, the recipient, and bot addresses
    # Bot addresses (query/teach) are not human contacts — they're catch-all routed
    bot_addresses = {
        addr.lower() for addr in [query_address, teach_address, kb_address] if addr
    }
    admin_contacts = []
    if admin_emails and role != "admin":
        admin_contacts = [
            e
            for e in admin_emails
            if not e.startswith("@")
            and e.lower() != to_email.lower()
            and e.lower() not in bot_addresses
        ]

    # --- Build plain text ---
    sections_plain = []

    # Greeting & intro
    role_label = {
        "querier": "member",
        "teacher": "contributor",
        "admin": "administrator",
    }
    friendly_role = role_label.get(role, role)

    sections_plain.append(
        f"Hello!\n\n"
        f"You've been added to {instance_name}{org_text} as a {friendly_role}. "
        f"Welcome aboard!\n\n"
        f"{instance_name} is an AI-powered knowledge base assistant. "
        f"It learns from documents and emails shared with it, and can answer "
        f"questions based on that knowledge."
    )

    # Asking questions (all roles)
    if query_address:
        sections_plain.append(
            "ASKING QUESTIONS\n\n"
            f"You can ask {instance_name} anything about the knowledge base:\n\n"
            f"  - By email: just send your question to {query_address}\n"
            f"  - On the web: visit {web_base_url}\n\n"
            f"Write naturally, as you would to a colleague. "
            f"{instance_name} will reply with an answer and cite its sources."
        )

    # Teaching (teacher + admin)
    if role in ("teacher", "admin"):
        if teach_address:
            teach_section = (
                "SHARING KNOWLEDGE\n\n"
                f"As a {friendly_role}, you can teach {instance_name} by sharing "
                f"documents and emails with {teach_address}. Simply include "
                f"this address in the To, CC, or BCC field of your email and "
                f"{instance_name} will process both the email content and any "
                f"attachments, adding them to the knowledge base.\n\n"
                f"Supported file types: PDF, DOCX, PPTX, TXT, CSV, XLS, and XLSX."
            )
        else:
            teach_section = (
                "SHARING KNOWLEDGE\n\n"
                f"As a {friendly_role}, you can teach {instance_name} by sharing "
                f"documents and emails. CC or BCC {query_address} on any email "
                f"you'd like to add to the knowledge base. {instance_name} will "
                f"process both the email content and any attachments.\n\n"
                f"Supported file types: PDF, DOCX, PPTX, TXT, CSV, XLS, and XLSX."
            )
        sections_plain.append(teach_section)

    # Admin
    if role == "admin":
        sections_plain.append(
            "ADMINISTRATION\n\n"
            f"As an administrator, you have access to the admin panel where you "
            f"can manage users, review the knowledge base, and configure the system.\n\n"
            f"  - Admin panel: {web_base_url}/admin"
        )

    # Admin contacts (for non-admin roles)
    if admin_contacts:
        contacts_list = ", ".join(admin_contacts)
        org_label = organization or instance_name
        sections_plain.append(
            "NEED HELP?\n\n"
            f"If you have questions about {org_label} or need assistance "
            f"with your account, you can reach your administrator"
            f"{'s' if len(admin_contacts) > 1 else ''}: {contacts_list}"
        )

    # Sign-off
    sections_plain.append(
        f"If you have any questions about how things work, just ask "
        f"{instance_name} — that's what it's here for!\n\n"
        f"Best,\nThe {instance_name} Team"
    )

    plain_text = "\n\n---\n\n".join(sections_plain)

    # --- Build HTML ---
    sections_html = []

    # Greeting & intro
    sections_html.append(
        f"<p>Hello!</p>"
        f"<p>You've been added to <strong>{instance_name}</strong>{org_text} "
        f"as a {friendly_role}. Welcome aboard!</p>"
        f"<p>{instance_name} is an AI-powered knowledge base assistant. "
        f"It learns from documents and emails shared with it, and can answer "
        f"questions based on that knowledge.</p>"
    )

    # Asking questions (all roles)
    if query_address:
        sections_html.append(
            f'<div style="background-color: #F7F2EA; border-radius: 8px; '
            f'padding: 16px 20px; margin: 16px 0;">'
            f'<h3 style="color: #2A2520; margin: 0 0 8px 0; font-size: 15px;">'
            f"Asking Questions</h3>"
            f'<p style="margin: 0 0 8px 0;">You can ask {instance_name} '
            f"anything about the knowledge base:</p>"
            f'<ul style="margin: 4px 0; padding-left: 20px;">'
            f"<li><strong>By email:</strong> send your question to "
            f'<a href="mailto:{query_address}" style="color: #5B8C7A;">'
            f"{query_address}</a></li>"
            f"<li><strong>On the web:</strong> visit "
            f'<a href="{web_base_url}" style="color: #5B8C7A;">'
            f"{web_base_url}</a></li>"
            f"</ul>"
            f'<p style="margin: 8px 0 0 0; font-size: 0.92em; color: #5C554D;">'
            f"Write naturally, as you would to a colleague. "
            f"{instance_name} will reply with an answer and cite its sources.</p>"
            f"</div>"
        )

    # Teaching (teacher + admin)
    if role in ("teacher", "admin"):
        if teach_address:
            teach_body = (
                f'<p style="margin: 0 0 8px 0;">As a {friendly_role}, you can '
                f"teach {instance_name} by sharing documents and emails with "
                f'<a href="mailto:{teach_address}" style="color: #5B8C7A;">'
                f"{teach_address}</a>. Simply include this address in the "
                f"<strong>To</strong>, <strong>CC</strong>, or <strong>BCC</strong> "
                f"field of your email and {instance_name} will process both the "
                f"email content and any attachments, adding them to the "
                f"knowledge base.</p>"
            )
        else:
            teach_body = (
                f'<p style="margin: 0 0 8px 0;">As a {friendly_role}, you can '
                f"teach {instance_name} by sharing documents and emails. "
                f"<strong>CC or BCC</strong> "
                f'<a href="mailto:{query_address}" style="color: #5B8C7A;">'
                f"{query_address}</a> on any email you'd like to add to the "
                f"knowledge base. {instance_name} will process both the email "
                f"content and any attachments.</p>"
            )

        sections_html.append(
            f'<div style="background-color: #F7F2EA; border-radius: 8px; '
            f'padding: 16px 20px; margin: 16px 0;">'
            f'<h3 style="color: #2A2520; margin: 0 0 8px 0; font-size: 15px;">'
            f"Sharing Knowledge</h3>"
            f"{teach_body}"
            f'<p style="margin: 8px 0 0 0; font-size: 0.92em; color: #5C554D;">'
            f"Supported file types: PDF, DOCX, PPTX, TXT, CSV, XLS, and XLSX.</p>"
            f"</div>"
        )

    # Admin
    if role == "admin":
        sections_html.append(
            f'<div style="background-color: #F7F2EA; border-radius: 8px; '
            f'padding: 16px 20px; margin: 16px 0;">'
            f'<h3 style="color: #2A2520; margin: 0 0 8px 0; font-size: 15px;">'
            f"Administration</h3>"
            f'<p style="margin: 0 0 8px 0;">As an administrator, you have '
            f"access to the admin panel where you can manage users, review the "
            f"knowledge base, and configure the system.</p>"
            f'<p style="margin: 0;"><a href="{web_base_url}/admin" '
            f'style="display: inline-block; padding: 8px 20px; '
            f"background-color: #5B8C7A; color: white; text-decoration: none; "
            f'border-radius: 5px; font-weight: bold;">'
            f"Open Admin Panel</a></p>"
            f"</div>"
        )

    # Admin contacts (for non-admin roles)
    if admin_contacts:
        org_label = organization or instance_name
        contacts_html = ", ".join(
            f'<a href="mailto:{e}" style="color: #5B8C7A;">{e}</a>'
            for e in admin_contacts
        )
        sections_html.append(
            f'<div style="background-color: #F0EDE8; border-radius: 8px; '
            f'padding: 16px 20px; margin: 16px 0;">'
            f'<h3 style="color: #2A2520; margin: 0 0 8px 0; font-size: 15px;">'
            f"Need Help?</h3>"
            f'<p style="margin: 0;">If you have questions about {org_label} '
            f"or need assistance with your account, you can reach your "
            f"administrator{'s' if len(admin_contacts) > 1 else ''}: "
            f"{contacts_html}</p>"
            f"</div>"
        )

    # Sign-off
    sections_html.append(
        f"<p>If you have any questions about how things work, just ask "
        f"{instance_name} — that's what it's here for!</p>"
    )

    html_sections = "\n".join(sections_html)

    # Logo URL — referenced from the web server
    logo_url = f"{web_base_url}/static/berengario_owl.png" if web_base_url else ""
    logo_html = ""
    if logo_url:
        logo_html = (
            f'<img src="{logo_url}" alt="{instance_name}" '
            f'style="width: 48px; height: auto; vertical-align: middle; '
            f'margin-right: 12px; border-radius: 4px;">'
        )

    # Build signature subtitle from description and organization
    subtitle_parts = []
    if instance_description:
        subtitle_parts.append(instance_description)
    if organization:
        subtitle_parts.append(organization)
    signature_subtitle = (
        " · ".join(subtitle_parts)
        if subtitle_parts
        else "AI-powered Knowledge Base Assistant"
    )

    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
</head>
<body style="font-family: Arial, Helvetica, sans-serif; line-height: 1.6; color: #2E2E2E; max-width: 640px; margin: 0 auto; padding: 20px;">
    {html_sections}
    <div style="border-top: 1px solid #D5C9B8; padding-top: 16px; margin-top: 28px;">
        <table cellpadding="0" cellspacing="0" border="0">
            <tr>
                <td style="vertical-align: middle; padding-right: 12px;">
                    {logo_html}
                </td>
                <td style="vertical-align: middle;">
                    <span style="font-weight: bold; color: #2A2520; font-size: 14px;">{instance_name}</span><br>
                    <span style="font-size: 12px; color: #8C8279;">{signature_subtitle}</span>
                </td>
            </tr>
        </table>
    </div>
</body>
</html>"""

    return subject, plain_text, html_body


def fetch_tenant_welcome_params(
    tenant_id: str,
    db_session=None,
) -> dict:
    """
    Fetch tenant details needed for welcome emails from the platform DB.

    Queries the Tenant and TenantUser tables to build a dict of keyword
    arguments suitable for passing to send_welcome_email().

    Args:
        tenant_id: UUID of the tenant.
        db_session: An open SQLAlchemy session to the platform DB.
            If None, opens (and closes) one via PlatformDBManager.

    Returns:
        Dict with keys: instance_name, organization, instance_description,
        admin_emails. Values default gracefully on errors.
    """
    from src.platform.models import Tenant, TenantUser, TenantUserRole

    result = {
        "instance_name": None,
        "organization": "",
        "instance_description": "",
        "admin_emails": None,
        "query_address": None,
        "teach_address": None,
    }

    own_session = False
    try:
        if db_session is None:
            from src.platform.db_manager import PlatformDBManager

            platform_db = PlatformDBManager()
            db_session = platform_db.get_platform_session().__enter__()
            own_session = True

        tenant = db_session.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant:
            result["instance_name"] = tenant.name
            result["organization"] = tenant.organization or ""
            result["instance_description"] = tenant.description or ""
            if tenant.email_address:
                result["query_address"] = tenant.email_address
                # Derive teach address from platform domain
                domain = tenant.email_address.split("@", 1)[-1]
                result["teach_address"] = f"teach@{domain}"

        admins = (
            db_session.query(TenantUser.email)
            .filter(
                TenantUser.tenant_id == tenant_id,
                TenantUser.role == TenantUserRole.ADMIN,
            )
            .all()
        )
        result["admin_emails"] = [a.email for a in admins]
    except Exception:
        logger.debug(f"Could not fetch tenant welcome params for {tenant_id}")
    finally:
        if own_session and db_session:
            try:
                db_session.close()
            except Exception:
                pass

    return result


def send_welcome_email(
    sender_instance: "EmailSender",
    to_email: str,
    role: str,
    instance_name: Optional[str] = None,
    organization: Optional[str] = None,
    instance_description: Optional[str] = None,
    query_address: Optional[str] = None,
    teach_address: Optional[str] = None,
    web_base_url: Optional[str] = None,
    admin_emails: Optional[List[str]] = None,
) -> bool:
    """
    Send a welcome email to a newly enrolled user.

    Non-critical: catches all exceptions and returns False on failure.
    Respects the welcome_email_enabled setting.

    Args:
        sender_instance: EmailSender to use for sending.
        to_email: Recipient email address.
        role: User role (querier, teacher, admin).
        instance_name: Name of instance (defaults to settings).
        organization: Organization name (defaults to settings).
        instance_description: Instance/team description (defaults to settings).
        query_address: Query email address (defaults to settings).
        teach_address: Teach email address (defaults to settings).
        web_base_url: Web base URL (defaults to settings).
        admin_emails: List of admin emails to show as contacts (optional).

    Returns:
        True if sent successfully, False otherwise.
    """
    try:
        if not settings.welcome_email_enabled:
            logger.debug("Welcome emails disabled, skipping")
            return False

        # Fill defaults from settings
        # Only default instance_description when instance_name is also defaulting
        # (ST mode). In MT mode, callers pass instance_name=tenant.name and the
        # tenant name already serves as the team identifier in the signature.
        if instance_name is None:
            instance_description = instance_description or settings.instance_description
        instance_name = instance_name or settings.instance_name
        organization = organization or settings.organization
        query_address = query_address or settings.email_target_address
        teach_address = teach_address or settings.email_teach_address
        web_base_url = web_base_url or settings.web_base_url

        subject, plain_text, html_body = format_welcome_email(
            to_email=to_email,
            role=role,
            instance_name=instance_name,
            organization=organization,
            instance_description=instance_description,
            query_address=query_address,
            teach_address=teach_address,
            web_base_url=web_base_url,
            admin_emails=admin_emails,
        )

        result = sender_instance.send_reply(
            to_address=to_email,
            subject=subject,
            body_text=plain_text,
            body_html=html_body,
        )

        if result:
            logger.info(f"Welcome email sent to {to_email} (role: {role})")
        else:
            logger.warning(f"Failed to send welcome email to {to_email}")

        return result

    except Exception as e:
        logger.warning(f"Error sending welcome email to {to_email}: {e}")
        return False


# Global email sender instance
email_sender = EmailSender()
