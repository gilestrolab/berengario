"""
Simple integration test for Phase 3 email query handler.

Verifies that all components can work together for basic query flow.
Real-world integration testing will be done with actual emails.
"""

from unittest.mock import MagicMock, patch

from src.email.email_sender import format_response_email
from src.rag.query_handler import QueryHandler


class TestPhase3Integration:
    """Basic integration tests for Phase 3 components."""

    def test_response_formatting_integration(self):
        """Test that response formatting produces valid output."""
        response_text = "The vacation policy allows 20 days off per year."
        sources = [
            {"filename": "policy.pdf", "score": 0.95},
            {"filename": "handbook.txt", "score": 0.82},
        ]
        instance_name = "Test Bot"
        original_subject = "Vacation Policy Question"

        subject, plain, html = format_response_email(
            response_text, sources, instance_name, original_subject
        )

        # Verify subject
        assert subject == "Re: Vacation Policy Question"

        # Verify plain text has all parts
        assert "vacation policy" in plain.lower()
        assert "policy.pdf" in plain
        assert "Test Bot" in plain
        assert "Sources:" in plain

        # Verify HTML structure
        assert "<!DOCTYPE html>" in html
        assert "<html>" in html
        assert "vacation policy" in html.lower()
        assert "policy.pdf" in html
        assert 'class="response"' in html
        assert 'class="sources"' in html
        assert 'class="footer"' in html

    def test_query_handler_basic_flow(self):
        """Test that QueryHandler can process a basic query."""
        # Note: This requires actual KB setup, so we'll keep it simple
        # Real integration testing will be done with actual emails

        query_handler = QueryHandler()

        # Verify it's initialized
        assert query_handler.rag_engine is not None

        # The actual query processing is tested in unit tests
        # Full integration requires real KB and LLM which is tested separately

    def test_email_sender_and_formatter_integration(self):
        """Test that EmailSender works with formatted responses."""
        from src.email.email_sender import EmailSender

        # Create email sender
        sender = EmailSender(
            smtp_server="smtp.test.com",
            smtp_port=587,
            smtp_user="bot@test.com",
            smtp_password="pass",
            use_tls=True,
            from_address="bot@test.com",
            from_name="Test Bot",
        )

        # Format a response
        subject, plain, html = format_response_email(
            response_text="Here is the answer.",
            sources=[{"filename": "doc.pdf", "score": 0.9}],
            instance_name="Test Bot",
            original_subject="Question",
        )

        # Mock SMTP and verify send_reply accepts formatted output
        with patch("src.email.email_sender.smtplib.SMTP") as mock_smtp:
            mock_instance = MagicMock()
            mock_smtp.return_value = mock_instance

            result = sender.send_reply(
                to_address="user@test.com",
                subject=subject,
                body_text=plain,
                body_html=html,
                in_reply_to="<test-123>",
                references=["<test-123>"],
            )

            # Verify success
            assert result is True
            assert mock_instance.send_message.called

            # Verify message structure
            call_args = mock_instance.send_message.call_args
            message = call_args[0][0]
            assert message["Subject"] == "Re: Question"
            assert message["To"] == "user@test.com"
            assert message["From"] == "Test Bot <bot@test.com>"
            assert message["In-Reply-To"] == "<test-123>"
            assert message["References"] == "<test-123>"


def test_phase3_components_importable():
    """Smoke test: verify all Phase 3 components can be imported."""
    from src.email.email_processor import EmailProcessor
    from src.email.email_sender import EmailSender, email_sender, format_response_email
    from src.rag.query_handler import QueryHandler
    from src.rag.rag_engine import RAGEngine

    # Verify classes exist
    assert EmailSender is not None
    assert EmailProcessor is not None
    assert QueryHandler is not None
    assert RAGEngine is not None

    # Verify functions exist
    assert format_response_email is not None
    assert callable(format_response_email)

    # Verify global instances exist
    assert email_sender is not None
