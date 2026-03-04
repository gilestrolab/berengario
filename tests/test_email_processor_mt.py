"""
Unit tests for email processing.

Tests the dispatch path in EmailProcessor: sender resolution,
permission checking, tenant-specific component injection, and
partial failure handling.
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.email.email_processor import EmailProcessor


@pytest.fixture
def mock_email():
    """Create a mock parsed EmailMessage."""
    email = MagicMock()
    email.message_id = "<test-msg-1@example.com>"
    email.sender.email = "alice@example.com"
    email.subject = "Test Subject"
    email.is_cced = False
    email.in_reply_to = None
    email.references = []
    email.date = None
    email.get_body.return_value = "What is the vacation policy?"
    return email


@pytest.fixture
def mock_mail_message():
    """Create a mock MailMessage from imap-tools."""
    msg = MagicMock()
    msg.uid = "123"
    return msg


@pytest.fixture
def mock_router():
    """Create a mock TenantEmailRouter."""
    router = MagicMock()
    router.check_permission.side_effect = lambda role, action: {
        ("admin", "query"): True,
        ("admin", "teach"): True,
        ("teacher", "query"): True,
        ("teacher", "teach"): True,
        ("querier", "query"): True,
        ("querier", "teach"): False,
    }.get((role, action), False)
    return router


@pytest.fixture
def mock_components():
    """Create mock TenantComponents."""
    components = MagicMock()
    components.context.instance_name = "Acme Assistant"
    components.context.organization = "Acme Corp"
    components.context.kb_emails_path = Path("/tmp/acme/kb/emails")
    components.context.kb_documents_path = Path("/tmp/acme/kb/documents")
    components.context.temp_dir = Path("/tmp/acme/temp")
    return components


@pytest.fixture
def processor(mock_router):
    """Create an EmailProcessor with mocked dependencies."""
    return EmailProcessor(
        email_client=MagicMock(),
        parser=MagicMock(),
        attachment_handler=MagicMock(),
        message_tracker=MagicMock(),
        email_sender=MagicMock(),
        tenant_email_router=mock_router,
    )


class TestDispatch:
    """Test dispatch in process_message."""

    def test_has_router(self, processor, mock_router):
        """Processor should have the router set."""
        assert processor.tenant_email_router is mock_router

    def test_routes_query_to_single_tenant(
        self, processor, mock_router, mock_mail_message, mock_email, mock_components
    ):
        """Should route a query to the resolved tenant."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = True
        processor.parser.should_process_for_kb.return_value = False

        mock_router.resolve_sender.return_value = [
            {
                "tenant_slug": "acme",
                "tenant_id": "t-1",
                "role": "teacher",
                "tenant_name": "Acme",
            }
        ]
        mock_router.get_components.return_value = mock_components

        # Mock the query handler to return a successful result
        mock_components.query_handler.process_query.return_value = {
            "success": True,
            "response": "The vacation policy is...",
            "sources": [],
            "original_query": "vacation?",
            "optimized_query": "vacation policy?",
        }
        mock_components.conversation_manager.add_message.return_value = 42
        mock_components.conversation_manager.extract_thread_id_from_email.return_value = (
            "thread-1"
        )
        mock_components.conversation_manager.format_conversation_context.return_value = (
            ""
        )
        processor.email_sender.send_reply.return_value = True

        result = processor.process_message(mock_mail_message)

        assert result.success
        assert result.action == "query"
        mock_router.resolve_sender.assert_called_once_with("alice@example.com")
        mock_router.get_components.assert_called_once_with("acme")

    def test_routes_to_multiple_tenants_kb(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Should process KB ingestion for all matching tenants."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = False
        processor.parser.should_process_for_kb.return_value = True

        mock_router.resolve_sender.return_value = [
            {
                "tenant_slug": "acme",
                "tenant_id": "t-1",
                "role": "teacher",
                "tenant_name": "Acme",
            },
            {
                "tenant_slug": "globex",
                "tenant_id": "t-2",
                "role": "admin",
                "tenant_name": "Globex",
            },
        ]

        # Each tenant gets its own components
        mock_comp_a = MagicMock()
        mock_comp_a.context.instance_name = "Acme"
        mock_comp_a.context.organization = "Acme Corp"
        mock_comp_a.context.kb_emails_path = Path("/tmp/acme/kb/emails")
        mock_comp_a.context.kb_documents_path = Path("/tmp/acme/kb/docs")
        mock_comp_a.context.temp_dir = Path("/tmp/acme/temp")

        mock_comp_b = MagicMock()
        mock_comp_b.context.instance_name = "Globex"
        mock_comp_b.context.organization = "Globex Inc"
        mock_comp_b.context.kb_emails_path = Path("/tmp/globex/kb/emails")
        mock_comp_b.context.kb_documents_path = Path("/tmp/globex/kb/docs")
        mock_comp_b.context.temp_dir = Path("/tmp/globex/temp")

        mock_router.get_components.side_effect = lambda slug: {
            "acme": mock_comp_a,
            "globex": mock_comp_b,
        }[slug]

        # Mock attachment handler to return no attachments (body processing)
        processor.attachment_handler.extract_attachments.return_value = []
        mock_email.get_body.return_value = ""  # No body either - simplest case

        result = processor.process_message(mock_mail_message)

        # Both tenants processed
        assert mock_router.get_components.call_count == 2
        assert result.success

    def test_sender_not_found_rejected(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Should reject if sender not found in any tenant."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = True
        processor.parser.should_process_for_kb.return_value = False

        mock_router.resolve_sender.return_value = []

        result = processor.process_message(mock_mail_message)

        assert not result.success
        assert result.action == "rejected"
        processor.message_tracker.mark_processed.assert_called()

    def test_querier_cannot_teach(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Should skip tenant where querier tries to teach."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = False
        processor.parser.should_process_for_kb.return_value = True

        mock_router.resolve_sender.return_value = [
            {
                "tenant_slug": "acme",
                "tenant_id": "t-1",
                "role": "querier",
                "tenant_name": "Acme",
            },
        ]

        result = processor.process_message(mock_mail_message)

        # Querier can't teach, no tenants processed successfully
        mock_router.get_components.assert_not_called()
        assert not result.success

    def test_duplicate_detection_global(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Duplicate detection should happen globally, before dispatch."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = True

        result = processor.process_message(mock_mail_message)

        assert result.action == "duplicate"
        assert result.success
        # Router should NOT be called for duplicates
        mock_router.resolve_sender.assert_not_called()

    def test_partial_failure(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Should succeed if at least one tenant processes OK."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = True
        processor.parser.should_process_for_kb.return_value = False

        mock_router.resolve_sender.return_value = [
            {
                "tenant_slug": "acme",
                "tenant_id": "t-1",
                "role": "admin",
                "tenant_name": "Acme",
            },
            {
                "tenant_slug": "globex",
                "tenant_id": "t-2",
                "role": "teacher",
                "tenant_name": "Globex",
            },
        ]

        # First tenant succeeds, second fails
        def mock_get_components(slug):
            if slug == "acme":
                comp = MagicMock()
                comp.context.instance_name = "Acme"
                comp.context.organization = "Acme Corp"
                comp.query_handler.process_query.return_value = {
                    "success": True,
                    "response": "Answer",
                    "sources": [],
                }
                comp.conversation_manager.extract_thread_id_from_email.return_value = (
                    "t1"
                )
                comp.conversation_manager.format_conversation_context.return_value = ""
                comp.conversation_manager.add_message.return_value = 1
                return comp
            else:
                raise ValueError("Globex DB unavailable")

        mock_router.get_components.side_effect = mock_get_components
        processor.email_sender.send_reply.return_value = True

        result = processor.process_message(mock_mail_message)

        # Should succeed because acme processed OK
        assert result.success
        assert result.action == "query"

    def test_skipped_action(
        self, processor, mock_router, mock_mail_message, mock_email
    ):
        """Should handle messages that don't match query or KB criteria."""
        processor.parser.parse.return_value = mock_email
        processor.message_tracker.is_processed.return_value = False
        processor.parser.should_process_as_query.return_value = False
        processor.parser.should_process_for_kb.return_value = False

        result = processor.process_message(mock_mail_message)

        assert result.success
        assert result.action == "skipped"
        mock_router.resolve_sender.assert_not_called()

    def test_parse_error(self, processor, mock_mail_message):
        """Should return parse_error when parser returns None."""
        processor.parser.parse.return_value = None
        result = processor.process_message(mock_mail_message)
        assert result.action == "parse_error"
        assert not result.success


class TestProcessQueryWith:
    """Test _process_query_with() parameterized method."""

    def test_query_uses_injected_components(self, processor, mock_email):
        """_process_query_with should use injected query_handler and conv_manager."""
        mock_qh = MagicMock()
        mock_cm = MagicMock()
        mock_sender = MagicMock()

        mock_cm.extract_thread_id_from_email.return_value = "thread-1"
        mock_cm.format_conversation_context.return_value = ""
        mock_qh.process_query.return_value = {
            "success": True,
            "response": "The answer",
            "sources": [],
            "original_query": "q",
            "optimized_query": "q",
        }
        mock_cm.add_message.return_value = 99
        mock_sender.send_reply.return_value = True

        result = processor._process_query_with(
            email=mock_email,
            query_handler=mock_qh,
            conv_manager=mock_cm,
            email_sender=mock_sender,
            instance_name="Test Bot",
            organization="Test Org",
            from_address="bot@test.com",
            from_name="Test Bot",
        )

        assert result.success
        assert result.action == "query"
        mock_qh.process_query.assert_called_once()
        mock_cm.add_message.assert_called()
        mock_sender.send_reply.assert_called_once()

        # Verify from_address/from_name passed through
        call_kwargs = mock_sender.send_reply.call_args
        assert call_kwargs.kwargs.get("from_address") == "bot@test.com"
        assert call_kwargs.kwargs.get("from_name") == "Test Bot"
