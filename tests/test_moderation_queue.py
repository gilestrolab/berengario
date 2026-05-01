"""
Tests for the teach-attempt moderation queue.

Covers:
- Querier teach attempts queue a PendingTeachSubmission row, archive
  attachments via the storage backend, and trigger acknowledgement +
  admin notification emails (instead of being silently dropped).
- The PendingTeachSubmission ORM model (defaults, to_dict).
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_email():
    email = MagicMock()
    email.message_id = "<mod-msg-1@example.com>"
    email.sender.email = "querier@example.com"
    email.subject = "Please add this to KB"
    email.is_cced = False
    email.in_reply_to = None
    email.references = []
    email.date = None
    email.get_body.return_value = "Here is some material I'd like added."
    return email


@pytest.fixture
def mock_mail_message():
    msg = MagicMock()
    msg.uid = "456"
    return msg


@pytest.fixture
def mock_attachment(tmp_path: Path):
    f = tmp_path / "submission.pdf"
    f.write_bytes(b"%PDF-1.7 fake pdf body")
    att = MagicMock()
    att.filename = "submission.pdf"
    att.filepath = f
    att.size = f.stat().st_size
    att.mime_type = "application/pdf"
    att.extension = "pdf"
    return att


@pytest.fixture
def storage_backend():
    backend = MagicMock()
    backend.put = MagicMock()
    backend.get = MagicMock()
    backend.delete = MagicMock()
    return backend


@pytest.fixture
def mock_components():
    comp = MagicMock()
    comp.context.instance_name = "Acme Assistant"
    comp.context.organization = "Acme Corp"
    comp.context.email_display_name = "Acme Assistant"

    inserted: list = []

    class _CtxSession:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def add(self, obj):
            inserted.append(obj)

    comp.conversation_manager.db_manager.get_session = MagicMock(
        side_effect=lambda: _CtxSession()
    )
    comp._inserted_rows = inserted
    return comp


@pytest.fixture
def mock_router(mock_components):
    router = MagicMock()
    router.check_permission.side_effect = lambda role, action: {
        ("admin", "teach"): True,
        ("teacher", "teach"): True,
        ("querier", "teach"): False,
        ("admin", "query"): True,
        ("teacher", "query"): True,
        ("querier", "query"): True,
    }.get((role, action), False)
    router.get_components.return_value = mock_components
    router.get_tenant_admin_emails.return_value = ["admin@example.com"]
    return router


@pytest.fixture
def processor(mock_router, mock_attachment, storage_backend):
    from src.email.email_processor import EmailProcessor

    proc = EmailProcessor(
        email_client=MagicMock(),
        parser=MagicMock(),
        attachment_handler=MagicMock(),
        message_tracker=MagicMock(),
        email_sender=MagicMock(),
        tenant_email_router=mock_router,
        storage_backend=storage_backend,
    )
    proc.attachment_handler.extract_attachments.return_value = [mock_attachment]
    proc.attachment_handler.cleanup_attachments = MagicMock()
    return proc


class TestQueriedTeachQueueing:
    def test_querier_teach_queues_submission(
        self,
        processor,
        mock_router,
        mock_components,
        mock_mail_message,
        mock_email,
        storage_backend,
    ):
        """Querier emails teach address → row queued, emails sent, ingestion skipped."""
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
            }
        ]

        result = processor.process_message(mock_mail_message)

        assert result.success
        # Submission row inserted
        assert len(mock_components._inserted_rows) == 1
        row = mock_components._inserted_rows[0]
        assert row.submitter_email == "querier@example.com"
        assert row.subject == "Please add this to KB"
        assert len(row.attachment_keys) == 1
        assert row.attachment_keys[0]["filename"] == "submission.pdf"
        assert row.attachment_keys[0]["key"].startswith("moderation/")
        assert row.attachment_keys[0]["key"].endswith("/submission.pdf")

        # Storage backend received the file bytes
        storage_backend.put.assert_called_once()
        put_args, put_kwargs = storage_backend.put.call_args
        assert put_args[0] == "acme"
        assert put_args[1].startswith("moderation/")
        assert put_args[2] == b"%PDF-1.7 fake pdf body"

        # Two emails: ack to submitter + admin notification
        assert processor.email_sender.send_reply.call_count == 2
        recipients = [
            call.kwargs.get("to_address") or call.args[0]
            for call in processor.email_sender.send_reply.call_args_list
        ]
        assert "querier@example.com" in recipients
        assert "admin@example.com" in recipients

        # KB ingestion path NOT taken
        mock_components.kb_manager.add_nodes.assert_not_called()

        # Cleanup ran
        processor.attachment_handler.cleanup_attachments.assert_called_once()

    def test_disabled_flag_falls_back_to_silent_skip(
        self,
        processor,
        mock_router,
        mock_mail_message,
        mock_email,
        monkeypatch,
        mock_components,
    ):
        """When TEACH_MODERATION_ENABLED=false, querier teach is silently skipped."""
        from src.email import email_processor as ep_module

        monkeypatch.setattr(ep_module.settings, "teach_moderation_enabled", False)

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
            }
        ]

        result = processor.process_message(mock_mail_message)

        assert not result.success
        # No row inserted, no emails sent
        assert mock_components._inserted_rows == []
        processor.email_sender.send_reply.assert_not_called()


class TestPendingTeachSubmissionModel:
    def test_defaults_and_to_dict(self):
        from src.email.db_models import (
            PendingSubmissionStatus,
            PendingTeachSubmission,
        )

        before = datetime.utcnow()
        sub = PendingTeachSubmission(
            id="abc-123",
            submitter_email="alice@example.com",
            subject="Resource",
            body_text="hello",
            attachment_keys=[{"filename": "a.pdf", "key": "moderation/abc-123/a.pdf"}],
            original_message_id="<m1@x>",
        )
        d = sub.to_dict()
        assert d["id"] == "abc-123"
        assert d["submitter_email"] == "alice@example.com"
        assert d["status"] == "pending"
        assert d["promoted_to_teacher"] is False
        assert d["attachment_keys"] == [
            {"filename": "a.pdf", "key": "moderation/abc-123/a.pdf"}
        ]
        # created_at auto-defaults to ~now
        assert sub.created_at >= before
        assert sub.status == PendingSubmissionStatus.PENDING
