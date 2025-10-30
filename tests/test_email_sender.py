"""
Unit tests for email sender module.

Tests SMTP email sending, response formatting, and error handling.
"""

import smtplib
from pathlib import Path
from unittest.mock import MagicMock, Mock, mock_open, patch

import pytest

from src.email.email_sender import (
    EmailSender,
    format_response_email,
    load_custom_footer,
)


class TestEmailSender:
    """Test suite for EmailSender class."""

    @pytest.fixture
    def sender(self):
        """Create EmailSender instance for testing."""
        return EmailSender(
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_user="bot@example.com",
            smtp_password="test_password",
            use_tls=True,
            from_address="bot@example.com",
            from_name="Test Bot",
        )

    def test_init_with_defaults(self):
        """Test EmailSender initialization with default settings."""
        with patch("src.email.email_sender.settings") as mock_settings:
            mock_settings.smtp_server = "smtp.test.com"
            mock_settings.smtp_port = 587
            mock_settings.smtp_user = "user@test.com"
            mock_settings.smtp_password = "password"
            mock_settings.smtp_use_tls = True
            mock_settings.email_target_address = "target@test.com"
            mock_settings.email_display_name = "Test Display"

            sender = EmailSender()

            assert sender.smtp_server == "smtp.test.com"
            assert sender.smtp_port == 587
            assert sender.smtp_user == "user@test.com"
            assert sender.use_tls is True

    def test_init_with_custom_values(self, sender):
        """Test EmailSender initialization with custom values."""
        assert sender.smtp_server == "smtp.example.com"
        assert sender.smtp_port == 587
        assert sender.smtp_user == "bot@example.com"
        assert sender.smtp_password == "test_password"
        assert sender.use_tls is True
        assert sender.from_address == "bot@example.com"
        assert sender.from_name == "Test Bot"

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_success(self, mock_smtp, sender):
        """Test successful email sending."""
        # Setup mock
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        # Send email
        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test Subject",
            body_text="Test body text",
        )

        # Assertions
        assert result is True
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_instance.ehlo.assert_called()
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("bot@example.com", "test_password")
        mock_instance.send_message.assert_called_once()
        mock_instance.quit.assert_called_once()

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_with_html(self, mock_smtp, sender):
        """Test sending email with both text and HTML."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test Subject",
            body_text="Plain text",
            body_html="<html><body>HTML body</body></html>",
        )

        assert result is True
        mock_instance.send_message.assert_called_once()

        # Check that message has both parts
        call_args = mock_instance.send_message.call_args
        message = call_args[0][0]
        assert message["Subject"] == "Test Subject"
        assert message["To"] == "user@example.com"
        assert message["From"] == "Test Bot <bot@example.com>"

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_with_threading_headers(self, mock_smtp, sender):
        """Test email with In-Reply-To and References headers."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Re: Original",
            body_text="Reply text",
            in_reply_to="<message-id-123>",
            references=["<message-id-123>", "<message-id-456>"],
        )

        assert result is True

        # Check threading headers
        call_args = mock_instance.send_message.call_args
        message = call_args[0][0]
        assert message["In-Reply-To"] == "<message-id-123>"
        assert message["References"] == "<message-id-123> <message-id-456>"

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_auth_failure(self, mock_smtp, sender):
        """Test handling of authentication failure."""
        mock_instance = MagicMock()
        mock_instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")
        mock_smtp.return_value = mock_instance

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test",
            body_text="Test",
        )

        assert result is False

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_smtp_exception(self, mock_smtp, sender):
        """Test handling of SMTP exception."""
        mock_instance = MagicMock()
        mock_instance.send_message.side_effect = smtplib.SMTPException("Server error")
        mock_smtp.return_value = mock_instance

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test",
            body_text="Test",
        )

        assert result is False

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_connection_error(self, mock_smtp, sender):
        """Test handling of connection error."""
        mock_smtp.side_effect = ConnectionRefusedError("Connection refused")

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test",
            body_text="Test",
        )

        assert result is False

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_timeout(self, mock_smtp, sender):
        """Test handling of timeout."""
        mock_smtp.side_effect = TimeoutError("Connection timeout")

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test",
            body_text="Test",
        )

        assert result is False

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_send_reply_without_tls(self, mock_smtp):
        """Test sending email without TLS."""
        sender = EmailSender(
            smtp_server="smtp.example.com",
            smtp_port=25,
            smtp_user="bot@example.com",
            smtp_password="password",
            use_tls=False,
            from_address="bot@example.com",
            from_name="Bot",
        )

        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        result = sender.send_reply(
            to_address="user@example.com",
            subject="Test",
            body_text="Test",
        )

        assert result is True
        # Should not call starttls
        mock_instance.starttls.assert_not_called()

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_test_connection_success(self, mock_smtp, sender):
        """Test successful connection test."""
        mock_instance = MagicMock()
        mock_smtp.return_value = mock_instance

        result = sender.test_connection()

        assert result is True
        mock_smtp.assert_called_once_with("smtp.example.com", 587, timeout=30)
        mock_instance.login.assert_called_once_with("bot@example.com", "test_password")
        mock_instance.quit.assert_called_once()

    @patch("src.email.email_sender.smtplib.SMTP")
    def test_test_connection_failure(self, mock_smtp, sender):
        """Test connection test failure."""
        mock_smtp.side_effect = Exception("Connection failed")

        result = sender.test_connection()

        assert result is False


class TestFormatResponseEmail:
    """Test suite for format_response_email function."""

    def test_format_basic_response(self):
        """Test basic response formatting."""
        response_text = "Here is the answer to your question."
        sources = []
        instance_name = "TestBot"
        original_subject = "What is the policy?"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Check subject
        assert subject == "Re: What is the policy?"

        # Check plain text
        assert "Here is the answer to your question." in plain
        assert "TestBot" in plain
        assert "If you have follow-up questions" in plain

        # Check HTML
        assert "<html>" in html
        assert "Here is the answer to your question." in html
        assert "TestBot" in html

    def test_format_with_existing_re_prefix(self):
        """Test that Re: prefix is not duplicated."""
        response_text = "Answer"
        sources = []
        instance_name = "TestBot"
        original_subject = "Re: Question"

        subject, _, _ = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        assert subject == "Re: Question"
        assert subject.count("Re:") == 1

    def test_format_with_sources(self):
        """Test response formatting with source citations."""
        response_text = "The policy states that..."
        sources = [
            {"filename": "policy.pdf", "score": 0.95},
            {"filename": "guidelines.docx", "score": 0.87},
            {"filename": "handbook.txt", "score": 0.72},
        ]
        instance_name = "TestBot"
        original_subject = "Policy question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Check sources in plain text
        assert "Sources:" in plain
        assert "1. policy.pdf (relevance: 0.95)" in plain
        assert "2. guidelines.docx (relevance: 0.87)" in plain
        assert "3. handbook.txt (relevance: 0.72)" in plain

        # Check sources in HTML
        assert "<h3>Sources:</h3>" in html
        assert "policy.pdf" in html
        assert "0.95" in html
        assert "<ul>" in html
        assert "<li>" in html

    def test_format_without_sources(self):
        """Test response formatting without sources."""
        response_text = "Answer text"
        sources = []
        instance_name = "TestBot"
        original_subject = "Question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Should not have sources section
        assert "Sources:" not in plain
        assert "<h3>Sources:</h3>" not in html

    def test_format_with_multiline_response(self):
        """Test formatting with multiline response text."""
        response_text = "Line 1\nLine 2\nLine 3"
        sources = []
        instance_name = "TestBot"
        original_subject = "Question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Check plain text preserves newlines
        assert "Line 1\nLine 2\nLine 3" in plain

        # Check HTML converts newlines to <br>
        assert "Line 1<br>Line 2<br>Line 3" in html

    def test_format_html_structure(self):
        """Test that HTML has proper structure."""
        response_text = "Response"
        sources = [{"filename": "doc.pdf", "score": 0.9}]
        instance_name = "TestBot"
        original_subject = "Question"

        _, _, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Check HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "<head>" in html
        assert "<style>" in html
        assert "<body>" in html
        assert "</body>" in html
        assert "</html>" in html

        # Check CSS classes
        assert "class=\"response\"" in html
        assert "class=\"sources\"" in html
        assert "class=\"footer\"" in html

    def test_format_with_special_characters(self):
        """Test formatting with special characters in response."""
        response_text = "Answer with <special> & \"quoted\" text"
        sources = []
        instance_name = "TestBot"
        original_subject = "Question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Plain text should have original characters
        assert "<special>" in plain
        assert "&" in plain
        assert "\"quoted\"" in plain

        # HTML should preserve the text (MIMEText handles escaping)
        assert "special" in html

    def test_format_with_empty_source_metadata(self):
        """Test handling of sources with missing metadata."""
        response_text = "Answer"
        sources = [
            {},  # No filename or score
            {"filename": "doc.pdf"},  # No score
            {"score": 0.8},  # No filename
        ]
        instance_name = "TestBot"
        original_subject = "Question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Should handle missing metadata gracefully
        assert "Unknown document" in plain
        assert "relevance: 0.00" in plain or "relevance: 0.80" in plain

    def test_format_instance_name_in_footer(self):
        """Test that instance name appears in footer."""
        response_text = "Answer"
        sources = []
        instance_name = "DoLS-GPT Assistant"
        original_subject = "Question"

        _, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Check instance name in both formats
        assert "DoLS-GPT Assistant" in plain
        assert "DoLS-GPT Assistant" in html

    def test_format_returns_three_values(self):
        """Test that function returns exactly three values."""
        response_text = "Answer"
        sources = []
        instance_name = "TestBot"
        original_subject = "Question"

        result = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], str)  # subject
        assert isinstance(result[1], str)  # plain text
        assert isinstance(result[2], str)  # HTML

    @patch("src.email.email_sender.settings")
    def test_format_text_email_format(self, mock_settings):
        """Test plain text email format."""
        mock_settings.email_response_format = "text"
        mock_settings.email_custom_footer_file = None

        response_text = "This is the answer."
        sources = [{"filename": "doc.pdf", "score": 0.9}]
        instance_name = "TestBot"
        original_subject = "Question"

        _, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Plain text should have simple formatting
        assert "This is the answer." in plain
        assert "Sources:\n1. doc.pdf (relevance: 0.90)" in plain
        assert "---" in plain

        # HTML should be minimal fallback
        assert "<pre>" in html

    @patch("src.email.email_sender.settings")
    def test_format_markdown_email_format(self, mock_settings):
        """Test markdown email format."""
        mock_settings.email_response_format = "markdown"
        mock_settings.email_custom_footer_file = None

        response_text = "This is the answer."
        sources = [{"filename": "doc.pdf", "score": 0.9}]
        instance_name = "TestBot"
        original_subject = "Question"

        _, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Plain text should have markdown syntax
        assert "This is the answer." in plain
        assert "## Sources" in plain
        assert "1. **doc.pdf** (relevance: 0.90)" in plain

        # HTML should be minimal fallback
        assert "<pre>" in html

    @patch("src.email.email_sender.settings")
    def test_format_html_email_format(self, mock_settings):
        """Test HTML email format (default)."""
        mock_settings.email_response_format = "html"
        mock_settings.email_custom_footer_file = None

        response_text = "This is the answer."
        sources = [{"filename": "doc.pdf", "score": 0.9}]
        instance_name = "TestBot"
        original_subject = "Question"

        _, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # HTML should be styled
        assert "<!DOCTYPE html>" in html
        assert "<style>" in html
        assert 'class="response"' in html
        assert 'class="sources"' in html
        assert "<h3>Sources:</h3>" in html


class TestLoadCustomFooter:
    """Test suite for load_custom_footer function."""

    @patch("src.email.email_sender.settings")
    def test_load_default_footer(self, mock_settings):
        """Test loading default footer when no custom file is configured."""
        mock_settings.email_custom_footer_file = None

        plain, html = load_custom_footer("TestBot")

        # Check default footer content
        assert "TestBot" in plain
        assert "If you have follow-up questions" in plain
        assert "<strong>TestBot</strong>" in html
        assert "If you have follow-up questions" in html

    @patch("src.email.email_sender.settings")
    @patch("builtins.open", new_callable=mock_open, read_data="Custom footer text\nLine 2")
    def test_load_custom_footer_success(self, mock_file, mock_settings):
        """Test successfully loading custom footer from file."""
        mock_settings.email_custom_footer_file = Path("/tmp/footer.txt")

        # Mock path.exists() to return True
        with patch.object(Path, "exists", return_value=True):
            plain, html = load_custom_footer("TestBot")

        # Check custom footer is used
        assert "Custom footer text" in plain
        assert "Line 2" in plain
        assert "---" in plain

        # Check HTML conversion (newlines to <br>)
        assert "Custom footer text<br>Line 2" in html
        assert 'class="footer"' in html

    @patch("src.email.email_sender.settings")
    def test_load_custom_footer_file_not_exists(self, mock_settings):
        """Test fallback to default when custom file doesn't exist."""
        mock_settings.email_custom_footer_file = Path("/nonexistent/footer.txt")

        # Mock path.exists() to return False
        with patch.object(Path, "exists", return_value=False):
            plain, html = load_custom_footer("TestBot")

        # Should fallback to default footer
        assert "TestBot" in plain
        assert "If you have follow-up questions" in plain

    @patch("src.email.email_sender.settings")
    @patch("builtins.open", side_effect=PermissionError("No permission"))
    def test_load_custom_footer_permission_error(self, mock_file, mock_settings):
        """Test handling of permission error when reading footer file."""
        mock_settings.email_custom_footer_file = Path("/tmp/footer.txt")

        with patch.object(Path, "exists", return_value=True):
            plain, html = load_custom_footer("TestBot")

        # Should fallback to default footer
        assert "TestBot" in plain
        assert "If you have follow-up questions" in plain

    @patch("src.email.email_sender.settings")
    @patch("builtins.open", new_callable=mock_open, read_data="   \n\n   ")
    def test_load_custom_footer_empty_file(self, mock_file, mock_settings):
        """Test handling of empty footer file."""
        mock_settings.email_custom_footer_file = Path("/tmp/footer.txt")

        with patch.object(Path, "exists", return_value=True):
            plain, html = load_custom_footer("TestBot")

        # Should fallback to default footer (empty after strip)
        assert "TestBot" in plain
        assert "If you have follow-up questions" in plain

    @patch("src.email.email_sender.settings")
    @patch("builtins.open", new_callable=mock_open, read_data="Footer with special chars: <>&\"'")
    def test_load_custom_footer_special_characters(self, mock_file, mock_settings):
        """Test footer with special HTML characters."""
        mock_settings.email_custom_footer_file = Path("/tmp/footer.txt")

        with patch.object(Path, "exists", return_value=True):
            plain, html = load_custom_footer("TestBot")

        # Plain text should preserve special characters
        assert "special chars: <>&\"'" in plain

        # HTML should have special characters (MIMEText handles escaping)
        assert "special chars" in html
