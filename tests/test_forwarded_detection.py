"""
Unit tests for forwarded email detection.

Tests the configurable forwarded email detection feature.
"""

import pytest
from src.email.email_parser import EmailParser, EmailAddress, EmailMessage


@pytest.fixture
def parser_with_forward():
    """EmailParser with forwarded detection enabled."""
    return EmailParser()


@pytest.fixture
def parser_without_forward():
    """EmailParser with forwarded detection disabled."""
    # Temporarily override settings
    from src.config import settings

    original = settings.forward_to_kb_enabled
    settings.forward_to_kb_enabled = False
    parser = EmailParser()
    settings.forward_to_kb_enabled = original
    return parser


class TestForwardedDetection:
    """Tests for is_forwarded method."""

    def test_detect_fw_prefix(self, parser_with_forward):
        """Test detection of 'Fw:' prefix."""
        assert parser_with_forward.is_forwarded("Fw: Important message") is True

    def test_detect_fwd_prefix(self, parser_with_forward):
        """Test detection of 'Fwd:' prefix."""
        assert parser_with_forward.is_forwarded("Fwd: Important message") is True

    def test_case_insensitive_fw(self, parser_with_forward):
        """Test case-insensitive detection."""
        assert parser_with_forward.is_forwarded("fw: message") is True
        assert parser_with_forward.is_forwarded("FW: message") is True
        assert parser_with_forward.is_forwarded("Fw: message") is True
        assert parser_with_forward.is_forwarded("fW: message") is True

    def test_case_insensitive_fwd(self, parser_with_forward):
        """Test case-insensitive detection."""
        assert parser_with_forward.is_forwarded("fwd: message") is True
        assert parser_with_forward.is_forwarded("FWD: message") is True
        assert parser_with_forward.is_forwarded("Fwd: message") is True

    def test_not_forwarded_regular_subject(self, parser_with_forward):
        """Test regular subject is not detected as forwarded."""
        assert parser_with_forward.is_forwarded("Regular subject") is False
        assert parser_with_forward.is_forwarded("Meeting tomorrow") is False

    def test_not_forwarded_fw_in_middle(self, parser_with_forward):
        """Test 'fw' in middle of subject is not detected."""
        assert parser_with_forward.is_forwarded("Software update") is False
        assert parser_with_forward.is_forwarded("New firmware") is False

    def test_not_forwarded_without_colon(self, parser_with_forward):
        """Test 'fw' or 'fwd' without colon is not detected."""
        assert parser_with_forward.is_forwarded("Fw something") is False
        assert parser_with_forward.is_forwarded("Fwd message") is False

    def test_empty_subject(self, parser_with_forward):
        """Test empty subject is not detected as forwarded."""
        assert parser_with_forward.is_forwarded("") is False
        assert parser_with_forward.is_forwarded(None) is False

    def test_whitespace_handling(self, parser_with_forward):
        """Test whitespace is handled correctly."""
        assert parser_with_forward.is_forwarded("  Fw: message") is True
        assert parser_with_forward.is_forwarded("Fwd:   message") is True

    def test_detection_disabled(self, parser_without_forward):
        """Test no detection when feature is disabled."""
        assert parser_without_forward.is_forwarded("Fw: message") is False
        assert parser_without_forward.is_forwarded("Fwd: message") is False


class TestForwardedProcessingLogic:
    """Tests for processing logic with forwarded emails."""

    def test_forwarded_to_bot_treated_as_kb(self, parser_with_forward):
        """Test forwarded email sent To: bot is treated as KB content."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="123",
            sender=sender,
            subject="Fw: Important document",
            is_whitelisted=True,
            is_cced=False,  # Direct to bot
            attachment_count=0,
        )

        # Should NOT be processed as query
        assert parser_with_forward.should_process_as_query(email) is False
        # Should be processed for KB
        assert parser_with_forward.should_process_for_kb(email) is True

    def test_forwarded_cced_treated_as_kb(self, parser_with_forward):
        """Test forwarded email CC'd to bot is treated as KB content."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="123",
            sender=sender,
            subject="Fwd: Team update",
            is_whitelisted=True,
            is_cced=True,
            attachment_count=0,
        )

        # Should NOT be processed as query
        assert parser_with_forward.should_process_as_query(email) is False
        # Should be processed for KB
        assert parser_with_forward.should_process_for_kb(email) is True

    def test_forwarded_not_whitelisted_rejected(self, parser_with_forward):
        """Test forwarded email from non-whitelisted sender is rejected."""
        sender = EmailAddress(email="spam@example.com")
        email = EmailMessage(
            message_id="123",
            sender=sender,
            subject="Fw: Spam message",
            is_whitelisted=False,
            is_cced=False,
            attachment_count=0,
        )

        # Should NOT be processed as query
        assert parser_with_forward.should_process_as_query(email) is False
        # Should NOT be processed for KB (not whitelisted)
        assert parser_with_forward.should_process_for_kb(email) is False

    def test_regular_direct_email_is_query(self, parser_with_forward):
        """Test regular direct email (not forwarded) is still a query."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="123",
            sender=sender,
            subject="What is the vacation policy?",
            is_whitelisted=True,
            is_cced=False,  # Direct to bot
            attachment_count=0,
        )

        # Should be processed as query
        assert parser_with_forward.should_process_as_query(email) is True
        # Should NOT be processed for KB
        assert parser_with_forward.should_process_for_kb(email) is False

    def test_forwarded_detection_disabled_direct_is_query(self, parser_without_forward):
        """Test when disabled, forwarded emails To: bot are treated as queries."""
        sender = EmailAddress(email="alice@example.com")
        email = EmailMessage(
            message_id="123",
            sender=sender,
            subject="Fw: Document",
            is_whitelisted=True,
            is_cced=False,  # Direct to bot
            attachment_count=0,
        )

        # Should be processed as query (detection disabled)
        assert parser_without_forward.should_process_as_query(email) is True
        # Should NOT be processed for KB
        assert parser_without_forward.should_process_for_kb(email) is False


class TestCustomForwardPrefixes:
    """Tests for custom forward prefixes."""

    def test_custom_prefixes_italian(self):
        """Test Italian forwarding prefix 'I:'."""
        from src.config import settings

        original = settings.forward_subject_prefixes
        settings.forward_subject_prefixes = "i,inoltro"

        parser = EmailParser()

        assert parser.is_forwarded("I: Messaggio importante") is True
        assert parser.is_forwarded("Inoltro: Documento") is True
        assert parser.is_forwarded("i: test") is True

        # Restore original
        settings.forward_subject_prefixes = original

    def test_custom_prefixes_spanish(self):
        """Test Spanish forwarding prefix 'RV:'."""
        from src.config import settings

        original = settings.forward_subject_prefixes
        settings.forward_subject_prefixes = "rv,reen"

        parser = EmailParser()

        assert parser.is_forwarded("RV: Mensaje") is True
        assert parser.is_forwarded("Reen: Documento") is True
        assert parser.is_forwarded("rv: test") is True

        # Restore original
        settings.forward_subject_prefixes = original

    def test_multiple_custom_prefixes(self):
        """Test multiple custom prefixes."""
        from src.config import settings

        original = settings.forward_subject_prefixes
        settings.forward_subject_prefixes = "fw,fwd,i,rv,tr"

        parser = EmailParser()

        assert parser.is_forwarded("Fw: English") is True
        assert parser.is_forwarded("I: Italian") is True
        assert parser.is_forwarded("RV: Spanish") is True
        assert parser.is_forwarded("TR: French") is True

        # Restore original
        settings.forward_subject_prefixes = original

    def test_empty_prefix_list(self):
        """Test empty prefix list disables detection."""
        from src.config import settings

        original = settings.forward_subject_prefixes
        settings.forward_subject_prefixes = ""

        parser = EmailParser()

        assert parser.is_forwarded("Fw: message") is False
        assert parser.is_forwarded("Fwd: message") is False

        # Restore original
        settings.forward_subject_prefixes = original
