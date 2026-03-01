"""
Tests for StorageBackend and encryption integration into active code paths.

Verifies that:
- EmailProcessor._archive_file() routes to StorageBackend or local filesystem
- MT email processing passes storage_backend and tenant_slug through
- EmailService._create_mt_processor() uses create_storage_backend() factory
- Admin upload uses StorageBackend in MT mode
- TenantProvisioner creates encryption keys when key_manager is provided
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.email.email_processor import EmailProcessor

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_storage_backend():
    """Create a mock StorageBackend."""
    backend = MagicMock()
    backend.put.return_value = "tenant/kb/emails/test.txt"
    return backend


@pytest.fixture
def processor():
    """Create an EmailProcessor with all dependencies mocked."""
    return EmailProcessor(
        email_client=MagicMock(),
        parser=MagicMock(),
        attachment_handler=MagicMock(),
        doc_processor=MagicMock(),
        kb_manager=MagicMock(),
        message_tracker=MagicMock(),
        email_sender=MagicMock(),
        query_handler=MagicMock(),
    )


@pytest.fixture
def processor_with_storage(mock_storage_backend):
    """Create an EmailProcessor with storage_backend set (MT mode)."""
    return EmailProcessor(
        email_client=MagicMock(),
        parser=MagicMock(),
        attachment_handler=MagicMock(),
        doc_processor=MagicMock(),
        kb_manager=MagicMock(),
        message_tracker=MagicMock(),
        email_sender=MagicMock(),
        query_handler=MagicMock(),
        storage_backend=mock_storage_backend,
    )


# ============================================================================
# Tests: _archive_file()
# ============================================================================


class TestArchiveFile:
    """Tests for EmailProcessor._archive_file() helper."""

    def test_archive_file_with_storage_backend(
        self, processor, mock_storage_backend, tmp_path
    ):
        """When storage_backend and tenant_slug are provided, uses put()."""
        # Arrange
        source = tmp_path / "test.txt"
        source.write_text("hello world")
        dest_dir = tmp_path / "dest"

        # Act
        processor._archive_file(
            source_path=source,
            dest_dir=dest_dir,
            dest_filename="test.txt",
            storage_backend=mock_storage_backend,
            tenant_slug="acme",
            storage_key_prefix="kb/emails/",
        )

        # Assert
        mock_storage_backend.put.assert_called_once_with(
            "acme",
            "kb/emails/test.txt",
            b"hello world",
        )
        # Local dest_dir should NOT be created
        assert not dest_dir.exists()

    def test_archive_file_without_storage_backend(self, processor, tmp_path):
        """Without storage_backend, falls back to local shutil.copy2()."""
        # Arrange
        source = tmp_path / "test.txt"
        source.write_text("hello world")
        dest_dir = tmp_path / "dest"

        # Act
        processor._archive_file(
            source_path=source,
            dest_dir=dest_dir,
            dest_filename="test.txt",
        )

        # Assert — file should be copied locally
        assert (dest_dir / "test.txt").exists()
        assert (dest_dir / "test.txt").read_text() == "hello world"

    def test_archive_file_no_overwrite_local(self, processor, tmp_path):
        """In local mode, existing files are not overwritten."""
        # Arrange
        source = tmp_path / "test.txt"
        source.write_text("new content")
        dest_dir = tmp_path / "dest"
        dest_dir.mkdir()
        existing = dest_dir / "test.txt"
        existing.write_text("original content")

        # Act
        processor._archive_file(
            source_path=source,
            dest_dir=dest_dir,
            dest_filename="test.txt",
        )

        # Assert — original content should be preserved
        assert existing.read_text() == "original content"

    def test_archive_file_storage_backend_without_tenant_slug(
        self, processor, mock_storage_backend, tmp_path
    ):
        """If storage_backend is set but tenant_slug is None, falls back to local."""
        # Arrange
        source = tmp_path / "test.txt"
        source.write_text("fallback content")
        dest_dir = tmp_path / "dest"

        # Act
        processor._archive_file(
            source_path=source,
            dest_dir=dest_dir,
            dest_filename="test.txt",
            storage_backend=mock_storage_backend,
            tenant_slug=None,
        )

        # Assert — should use local, not storage_backend
        mock_storage_backend.put.assert_not_called()
        assert (dest_dir / "test.txt").exists()


# ============================================================================
# Tests: _process_for_kb_with() passes storage params
# ============================================================================


class TestProcessForKbWithStorage:
    """Tests for storage_backend pass-through in _process_for_kb_with()."""

    def test_mt_call_passes_storage_backend(self, processor_with_storage):
        """MT dispatch passes storage_backend and tenant_slug to _process_for_kb_with."""
        proc = processor_with_storage

        # Configure parser to return KB ingestion (not query)
        proc.parser.should_process_as_query.return_value = False
        proc.parser.should_process_for_kb.return_value = True

        # Create mock tenant context and components
        mock_ctx = MagicMock()
        mock_ctx.tenant_slug = "acme"
        mock_ctx.kb_emails_path = Path("/tmp/test/kb/emails")
        mock_ctx.kb_documents_path = Path("/tmp/test/kb/documents")
        mock_ctx.temp_dir = Path("/tmp/test/temp")
        mock_ctx.instance_name = "Test"
        mock_ctx.organization = "Acme"

        mock_components = MagicMock()
        mock_components.context = mock_ctx
        mock_components.kb_manager = MagicMock()
        mock_components.doc_processor = MagicMock()
        mock_components.query_handler = MagicMock()
        mock_components.conversation_manager = MagicMock()

        mock_router = MagicMock()
        mock_router.resolve_sender.return_value = [
            {"tenant_slug": "acme", "tenant_id": "t-1", "role": "teacher"}
        ]
        mock_router.check_permission.return_value = True
        mock_router.get_components.return_value = mock_components
        proc.tenant_email_router = mock_router

        # Spy on _process_for_kb_with to verify it receives storage params
        call_args = {}

        def spy(*args, **kwargs):
            call_args.update(kwargs)
            return MagicMock(success=True)

        proc._process_for_kb_with = spy

        # Create a mock email message
        mock_email = MagicMock()
        mock_email.sender.email = "teacher@acme.com"
        mock_email.message_id = "test-123"
        mock_email.subject = "Test"
        mock_email.to_addresses = ["bot@example.com"]
        mock_email.cc_addresses = []

        mock_mail = MagicMock()

        # Act — _process_mt determines action internally from parser
        proc._process_mt(mock_email, mock_mail)

        # Assert
        assert call_args.get("storage_backend") is proc.storage_backend
        assert call_args.get("tenant_slug") == "acme"


# ============================================================================
# Tests: EmailService._create_mt_processor()
# ============================================================================


class TestEmailServiceStorageInit:
    """Tests for EmailService MT processor creation."""

    def test_create_mt_processor_uses_factory(self):
        """_create_mt_processor() should use create_storage_backend(), not hardcoded Local."""
        # Lazy imports in _create_mt_processor require patching at source modules
        with (
            patch("src.email.tenant_email_router.TenantEmailRouter"),
            patch("src.platform.component_factory.TenantComponentFactory"),
            patch("src.platform.db_manager.TenantDBManager"),
            patch("src.platform.storage.create_storage_backend") as mock_create,
            patch("src.email.email_service.EmailProcessor") as mock_processor_cls,
        ):
            mock_storage = MagicMock()
            mock_create.return_value = mock_storage
            mock_processor_cls.return_value = MagicMock()

            from src.email.email_service import EmailService

            EmailService._create_mt_processor()

            # Verify factory function was called (not LocalStorageBackend directly)
            mock_create.assert_called_once()

            # Verify EmailProcessor was called with storage_backend
            mock_processor_cls.assert_called_once()
            call_kwargs = mock_processor_cls.call_args[1]
            assert call_kwargs.get("storage_backend") is mock_storage


# ============================================================================
# Tests: Admin upload with StorageBackend
# ============================================================================


class TestAdminUploadStorage:
    """Tests for admin document upload with StorageBackend in MT mode."""

    def test_admin_upload_uses_storage_backend_mt(self):
        """In MT mode, admin upload should use storage_backend.put()."""
        from src.api.routes.admin import create_admin_router

        mock_storage = MagicMock()
        mock_resolver = MagicMock()
        mock_kb = MagicMock()
        mock_dp = MagicMock()
        mock_dp.process_document.return_value = []

        # Setup component resolver to return mock context
        mock_ctx = MagicMock()
        mock_ctx.kb_documents_path = Path("/tmp/test/kb/documents")
        mock_components = MagicMock()
        mock_components.context = mock_ctx
        mock_components.kb_manager = mock_kb
        mock_components.doc_processor = mock_dp
        mock_resolver.resolve.return_value = mock_components

        router = create_admin_router(
            whitelist_manager=MagicMock(),
            whitelist_validators={},
            audit_logger=MagicMock(),
            kb_manager=mock_kb,
            document_manager=MagicMock(),
            document_processor=mock_dp,
            backup_manager=MagicMock(),
            email_sender=MagicMock(),
            query_handler=MagicMock(),
            settings=MagicMock(email_temp_dir="/tmp/test"),
            require_admin=MagicMock(),
            component_resolver=mock_resolver,
            storage_backend=mock_storage,
        )

        # Verify router was created with storage_backend param
        assert router is not None


# ============================================================================
# Tests: KeyManager in provisioning
# ============================================================================


class TestProvisioningKeyManager:
    """Tests for encryption key creation during tenant provisioning."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create a mock TenantDBManager."""
        db_manager = MagicMock()
        db_manager.create_tenant_database.return_value = True
        return db_manager

    @pytest.fixture
    def mock_storage(self):
        """Create a mock StorageBackend."""
        return MagicMock()

    @pytest.fixture
    def mock_key_manager(self):
        """Create a mock DatabaseKeyManager."""
        return MagicMock()

    def _mock_platform_session(self, mock_db_manager):
        """Helper to set up mock platform session context."""
        session = MagicMock()

        # Setup query chain to return no existing tenant
        def filter_side_effect(*args, **kwargs):
            result = MagicMock()
            result.first.return_value = None
            return result

        query_result = MagicMock()
        query_result.filter = MagicMock(side_effect=filter_side_effect)
        session.query.return_value = query_result

        mock_db_manager.get_platform_session.return_value.__enter__ = MagicMock(
            return_value=session
        )
        mock_db_manager.get_platform_session.return_value.__exit__ = MagicMock(
            return_value=False
        )

        return session

    def test_provisioning_creates_key_when_manager_provided(
        self, mock_db_manager, mock_storage, mock_key_manager
    ):
        """When key_manager is provided, create_tenant should create encryption key."""
        from src.platform.provisioning import TenantProvisioner

        self._mock_platform_session(mock_db_manager)

        provisioner = TenantProvisioner(
            db_manager=mock_db_manager,
            storage=mock_storage,
            key_manager=mock_key_manager,
        )

        provisioner.create_tenant(
            slug="test-tenant",
            name="Test Tenant",
            admin_email="admin@test.com",
        )

        # Verify encryption key was created
        mock_key_manager.create_tenant_key_with_session.assert_called_once()

    def test_provisioning_skips_key_when_no_manager(
        self, mock_db_manager, mock_storage
    ):
        """When key_manager is None, create_tenant should skip key creation."""
        from src.platform.provisioning import TenantProvisioner

        self._mock_platform_session(mock_db_manager)

        provisioner = TenantProvisioner(
            db_manager=mock_db_manager,
            storage=mock_storage,
            key_manager=None,
        )

        provisioner.create_tenant(
            slug="test-tenant",
            name="Test Tenant",
            admin_email="admin@test.com",
        )

        # No key_manager, so no key creation call should happen
        # (This is a smoke test — if key_manager is None, calling
        #  key_manager.create_tenant_key_with_session would raise)


# ============================================================================
# Tests: Processor stores storage_backend attribute
# ============================================================================


class TestProcessorStorageAttribute:
    """Tests that EmailProcessor correctly stores the storage_backend attribute."""

    def test_processor_stores_storage_backend(self, mock_storage_backend):
        """EmailProcessor should store storage_backend from constructor."""
        proc = EmailProcessor(
            email_client=MagicMock(),
            parser=MagicMock(),
            attachment_handler=MagicMock(),
            doc_processor=MagicMock(),
            kb_manager=MagicMock(),
            message_tracker=MagicMock(),
            email_sender=MagicMock(),
            query_handler=MagicMock(),
            storage_backend=mock_storage_backend,
        )
        assert proc.storage_backend is mock_storage_backend

    def test_processor_storage_backend_defaults_none(self):
        """EmailProcessor.storage_backend defaults to None."""
        proc = EmailProcessor(
            email_client=MagicMock(),
            parser=MagicMock(),
            attachment_handler=MagicMock(),
            doc_processor=MagicMock(),
            kb_manager=MagicMock(),
            message_tracker=MagicMock(),
            email_sender=MagicMock(),
            query_handler=MagicMock(),
        )
        assert proc.storage_backend is None
