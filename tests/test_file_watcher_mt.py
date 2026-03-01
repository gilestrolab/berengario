"""
Tests for FileWatcher multi-tenancy guard.

Verifies FileWatcher raises RuntimeError in MT mode and works normally in ST mode.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestFileWatcherMTGuard:
    """Test FileWatcher behavior in multi-tenant vs single-tenant mode."""

    @patch("src.document_processing.file_watcher.settings")
    def test_file_watcher_raises_in_mt_mode(self, mock_settings):
        """FileWatcher should raise RuntimeError when multi_tenant=True."""
        mock_settings.multi_tenant = True

        from src.document_processing.file_watcher import FileWatcher

        with pytest.raises(RuntimeError, match="not supported in multi-tenant mode"):
            FileWatcher(
                watch_path=Path("/tmp/test_docs"),
                document_processor=MagicMock(),
                kb_manager=MagicMock(),
            )

    @patch("src.document_processing.file_watcher.Observer")
    @patch("src.document_processing.file_watcher.settings")
    def test_file_watcher_works_in_st_mode(self, mock_settings, mock_observer_cls):
        """FileWatcher should initialize normally when multi_tenant=False."""
        mock_settings.multi_tenant = False
        mock_settings.documents_path = Path("/tmp/test_docs")

        from src.document_processing.file_watcher import FileWatcher

        mock_dp = MagicMock()
        mock_kb = MagicMock()

        watcher = FileWatcher(
            watch_path=Path("/tmp/test_docs"),
            document_processor=mock_dp,
            kb_manager=mock_kb,
        )

        assert watcher.watch_path == Path("/tmp/test_docs")
        assert watcher.document_processor is mock_dp
        assert watcher.kb_manager is mock_kb
