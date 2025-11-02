"""
Unit tests for email parser.

Tests email parsing, whitelist integration, and HTML conversion.
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest
from imap_tools import MailMessage

from src.email.email_parser import (
    EmailAddress,
    EmailMessage,
    EmailParser,
)


@pytest.fixture
def mock_settings():
    """Mock settings for email configuration."""
    with patch("src.email.email_parser.settings") as mock:
        mock.email_target_address = "bot@example.com"
        yield mock


@pytest.fixture
def mock_validator():
    """Mock whitelist validator."""
    mock = MagicMock()
    mock.is_allowed.return_value = True  # Default: allow all
    return mock


@pytest.fixture
def parser(mock_settings, mock_validator):
    """Email parser with mock validator."""
    return EmailParser(validator=mock_validator)


def create_mock_mail_message(
    uid="12345",
    from_="Alice <alice@example.com>",
    to="bot@example.com",
    cc="",
    subject="Test Subject",
    text="Plain text body",
    html="",
    attachments=None,
    date=None,
):
    """
    Create a mock MailMessage object.

    Args:
        uid: Message UID
        from_: From address
        to: To addresses
        cc: CC addresses
        subject: Subject line
        text: Plain text body
        html: HTML body
        attachments: List of attachments
        date: Message date

    Returns:
        Mock MailMessage object.
    """
    msg = MagicMock(spec=MailMessage)
    msg.uid = uid
    msg.from_ = from_
    msg.to = to
    msg.cc = cc
    msg.subject = subject
    msg.text = text
    msg.html = html
    msg.attachments = attachments or []
    msg.date = date or datetime(2024, 1, 15, 10, 30, 0)
    msg.headers.get.return_value = [uid]
    return msg


class TestEmailAddress:
    """Tests for EmailAddress model."""

    def test_create_with_name(self):
        """Test creating email address with name."""
        addr = EmailAddress(name="Alice Smith", email="alice@example.com")

        assert addr.name == "Alice Smith"
        assert addr.email == "alice@example.com"

    def test_create_without_name(self):
        """Test creating email address without name."""
        addr = EmailAddress(email="alice@example.com")

        assert addr.name == ""
        assert addr.email == "alice@example.com"

    def test_email_validation_valid(self):
        """Test email validation with valid address."""
        addr = EmailAddress(email="alice@example.com")
        assert addr.email == "alice@example.com"

    def test_email_validation_invalid(self):
        """Test email validation with invalid address."""
        with pytest.raises(ValueError):
            EmailAddress(email="invalid-email")

    def test_email_lowercase(self):
        """Test email is converted to lowercase."""
        addr = EmailAddress(email="ALICE@EXAMPLE.COM")
        assert addr.email == "alice@example.com"

    def test_string_representation_with_name(self):
        """Test string representation with name."""
        addr = EmailAddress(name="Alice Smith", email="alice@example.com")
        assert str(addr) == "Alice Smith <alice@example.com>"

    def test_string_representation_without_name(self):
        """Test string representation without name."""
        addr = EmailAddress(email="alice@example.com")
        assert str(addr) == "alice@example.com"


class TestEmailMessage:
    """Tests for EmailMessage model."""

    def test_create_minimal(self):
        """Test creating email message with minimal fields."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(message_id="12345", sender=sender)

        assert msg.message_id == "12345"
        assert msg.sender.email == "alice@example.com"
        assert len(msg.to) == 0
        assert msg.subject == ""

    def test_create_complete(self):
        """Test creating email message with all fields."""
        sender = EmailAddress(email="alice@example.com")
        to = [EmailAddress(email="bot@example.com")]
        cc = [EmailAddress(email="charlie@example.com")]

        msg = EmailMessage(
            message_id="12345",
            sender=sender,
            to=to,
            cc=cc,
            subject="Test",
            body_text="Body text",
            is_whitelisted=True,
            is_cced=False,
            attachment_count=2,
        )

        assert msg.message_id == "12345"
        assert len(msg.to) == 1
        assert len(msg.cc) == 1
        assert msg.subject == "Test"
        assert msg.is_whitelisted is True
        assert msg.attachment_count == 2

    def test_clean_subject(self):
        """Test subject cleaning removes excessive whitespace."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(
            message_id="12345", sender=sender, subject="  Test   Subject  "
        )

        assert msg.subject == "Test Subject"

    def test_get_body_prefer_text(self):
        """Test get_body prefers text over HTML."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(
            message_id="12345",
            sender=sender,
            body_text="Plain text",
            body_html="<p>HTML</p>",
        )

        assert msg.get_body(prefer_text=True) == "Plain text"

    def test_get_body_prefer_html(self):
        """Test get_body prefers HTML over text."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(
            message_id="12345",
            sender=sender,
            body_text="Plain text",
            body_html="<p>HTML</p>",
        )

        assert msg.get_body(prefer_text=False) == "<p>HTML</p>"

    def test_get_body_fallback_to_html(self):
        """Test get_body falls back to HTML when no text."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(
            message_id="12345",
            sender=sender,
            body_text="",
            body_html="<p>HTML</p>",
        )

        assert msg.get_body(prefer_text=True) == "<p>HTML</p>"

    def test_has_body_true(self):
        """Test has_body returns True when body exists."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(message_id="12345", sender=sender, body_text="Text")

        assert msg.has_body() is True

    def test_has_body_false(self):
        """Test has_body returns False when no body."""
        sender = EmailAddress(email="alice@example.com")
        msg = EmailMessage(message_id="12345", sender=sender)

        assert msg.has_body() is False


class TestEmailParser:
    """Tests for EmailParser class."""

    def test_init_with_defaults(self, mock_settings, mock_validator):
        """Test initializing parser with defaults."""
        parser = EmailParser(validator=mock_validator)

        assert parser.target_address == "bot@example.com"
        assert parser.validator is mock_validator

    def test_init_with_custom_target(self, mock_settings, mock_validator):
        """Test initializing with custom target address."""
        parser = EmailParser(
            target_address="custom@example.com", validator=mock_validator
        )

        assert parser.target_address == "custom@example.com"

    def test_parse_email_address_with_name(self, parser):
        """Test parsing email address with name."""
        addr = parser.parse_email_address("Alice Smith <alice@example.com>")

        assert addr is not None
        assert addr.name == "Alice Smith"
        assert addr.email == "alice@example.com"

    def test_parse_email_address_without_name(self, parser):
        """Test parsing email address without name."""
        addr = parser.parse_email_address("alice@example.com")

        assert addr is not None
        assert addr.name == ""
        assert addr.email == "alice@example.com"

    def test_parse_email_address_with_quotes(self, parser):
        """Test parsing email address with quoted name."""
        addr = parser.parse_email_address('"Smith, Alice" <alice@example.com>')

        assert addr is not None
        assert addr.name == "Smith, Alice"
        assert addr.email == "alice@example.com"

    def test_parse_email_address_invalid(self, parser):
        """Test parsing invalid email address."""
        addr = parser.parse_email_address("invalid")

        assert addr is None

    def test_parse_email_list(self, parser):
        """Test parsing comma-separated email list."""
        addresses = parser.parse_email_list(
            "Alice <alice@example.com>, bob@example.com, Charlie <charlie@example.com>"
        )

        assert len(addresses) == 3
        assert addresses[0].email == "alice@example.com"
        assert addresses[1].email == "bob@example.com"
        assert addresses[2].email == "charlie@example.com"

    def test_parse_email_list_empty(self, parser):
        """Test parsing empty email list."""
        addresses = parser.parse_email_list("")

        assert len(addresses) == 0

    def test_html_to_text(self, parser):
        """Test HTML to text conversion."""
        html = "<p>Hello <strong>world</strong>!</p><p>Second paragraph</p>"
        text = parser.html_to_text(html)

        assert "Hello" in text
        assert "world" in text
        assert "Second paragraph" in text

    def test_html_to_text_with_links(self, parser):
        """Test HTML to text with links."""
        html = '<p>Check <a href="http://example.com">this link</a></p>'
        text = parser.html_to_text(html)

        assert "this link" in text
        assert "example.com" in text

    def test_html_to_text_empty(self, parser):
        """Test HTML to text with empty input."""
        text = parser.html_to_text("")

        assert text == ""

    def test_extract_body_text_only(self, parser):
        """Test extracting body with text only."""
        msg = create_mock_mail_message(text="Plain text", html="")

        body_text, body_html = parser.extract_body(msg)

        assert body_text == "Plain text"
        assert body_html == ""

    def test_extract_body_html_only(self, parser):
        """Test extracting body with HTML only (converts to text)."""
        msg = create_mock_mail_message(text="", html="<p>HTML body</p>")

        body_text, body_html = parser.extract_body(msg)

        assert "HTML body" in body_text  # Converted from HTML
        assert body_html == "<p>HTML body</p>"

    def test_extract_body_both(self, parser):
        """Test extracting body with both text and HTML."""
        msg = create_mock_mail_message(text="Plain text", html="<p>HTML body</p>")

        body_text, body_html = parser.extract_body(msg)

        assert body_text == "Plain text"
        assert body_html == "<p>HTML body</p>"

    def test_is_cced_message_direct(self, parser):
        """Test is_cced returns False for direct message."""
        to_addresses = [
            EmailAddress(email="bot@example.com"),  # Target in To: field
            EmailAddress(email="alice@example.com"),
        ]

        is_cced = parser.is_cced_message(to_addresses)

        assert is_cced is False

    def test_is_cced_message_cced(self, parser):
        """Test is_cced returns True for CC'd message."""
        to_addresses = [
            EmailAddress(email="alice@example.com"),
            EmailAddress(email="bob@example.com"),
        ]  # Target NOT in To: field

        is_cced = parser.is_cced_message(to_addresses)

        assert is_cced is True

    def test_is_cced_message_case_insensitive(self, parser):
        """Test is_cced is case insensitive."""
        to_addresses = [EmailAddress(email="BOT@EXAMPLE.COM")]

        is_cced = parser.is_cced_message(to_addresses)

        assert is_cced is False  # Should match despite case

    def test_parse_success(self, parser, mock_validator):
        """Test successful parsing of email."""
        mock_validator.is_allowed.return_value = True

        msg = create_mock_mail_message(
            uid="12345",
            from_="Alice <alice@example.com>",
            to="bot@example.com",
            cc="charlie@example.com",
            subject="Test Subject",
            text="Body text",
            attachments=[Mock(), Mock()],  # 2 attachments
        )

        email = parser.parse(msg)

        assert email is not None
        assert email.message_id == "12345"
        assert email.sender.email == "alice@example.com"
        assert len(email.to) == 1
        assert len(email.cc) == 1
        assert email.subject == "Test Subject"
        assert email.body_text == "Body text"
        assert email.is_whitelisted is True
        assert email.is_cced is False  # Target in To: field
        assert email.attachment_count == 2

    def test_parse_not_whitelisted(self, parser, mock_validator):
        """Test parsing email from non-whitelisted sender."""
        mock_validator.is_allowed.return_value = False

        msg = create_mock_mail_message(from_="spam@spam.com")

        email = parser.parse(msg)

        assert email is not None
        assert email.is_whitelisted is False

    def test_parse_cced_message(self, parser, mock_validator):
        """Test parsing CC'd message."""
        msg = create_mock_mail_message(
            to="alice@example.com", cc="bot@example.com"  # Target in CC, not To
        )

        email = parser.parse(msg)

        assert email is not None
        assert email.is_cced is True

    def test_parse_missing_message_id(self, parser):
        """Test parsing fails with missing message ID."""
        msg = create_mock_mail_message(uid="")
        msg.headers.get.return_value = [""]

        email = parser.parse(msg)

        assert email is None

    def test_parse_invalid_sender(self, parser):
        """Test parsing fails with invalid sender."""
        msg = create_mock_mail_message(from_="invalid")

        email = parser.parse(msg)

        assert email is None

    def test_should_process_as_query_cced_no_attachments(self, parser):
        """Test CC'd message without attachments is NOT a query (KB ingestion)."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=True,
            attachment_count=0,
        )

        assert parser.should_process_as_query(email) is False

    def test_should_process_as_query_direct_message(self, parser):
        """Test direct message (To: bot) IS a query."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=False,
            attachment_count=0,
        )

        assert parser.should_process_as_query(email) is True

    def test_should_process_as_query_cced_with_attachments(self, parser):
        """Test CC'd message with attachments is NOT a query (KB ingestion)."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=True,
            attachment_count=2,
        )

        assert parser.should_process_as_query(email) is False

    def test_should_process_for_kb_whitelisted_direct(self, parser):
        """Test whitelisted direct message should NOT be processed for KB (it's a query)."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=False,
            attachment_count=0,
        )

        assert parser.should_process_for_kb(email) is False

    def test_should_process_for_kb_not_whitelisted(self, parser):
        """Test non-whitelisted message should not be processed for KB."""
        sender = EmailAddress(email="spam@spam.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=False,
            is_cced=False,
            attachment_count=0,
        )

        assert parser.should_process_for_kb(email) is False

    def test_should_process_for_kb_cced_with_attachments(self, parser):
        """Test CC'd message with attachments should be processed for KB."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=True,
            attachment_count=2,
        )

        assert parser.should_process_for_kb(email) is True

    def test_should_process_for_kb_cced_no_attachments(self, parser):
        """Test CC'd message without attachments SHOULD be processed for KB."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="12345",
            sender=sender,
            is_whitelisted=True,
            is_cced=True,
            attachment_count=0,
        )

        assert parser.should_process_for_kb(email) is True

    def test_parse_with_multiple_recipients(self, parser):
        """Test parsing email with multiple To: recipients."""
        msg = create_mock_mail_message(
            to="bot@example.com, alice@example.com, bob@example.com"
        )

        email = parser.parse(msg)

        assert email is not None
        assert len(email.to) == 3

    def test_parse_with_date(self, parser):
        """Test parsing email with date."""
        test_date = datetime(2024, 1, 15, 10, 30, 0)
        msg = create_mock_mail_message(date=test_date)

        email = parser.parse(msg)

        assert email is not None
        assert email.date == test_date

    def test_parse_with_no_subject(self, parser):
        """Test parsing email with no subject."""
        msg = create_mock_mail_message(subject=None)

        email = parser.parse(msg)

        assert email is not None
        assert email.subject == ""
