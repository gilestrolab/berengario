"""
Tests for DescriptionGenerator tenant-scoped DB support.

Tests that DescriptionGenerator uses the injected db_manager when provided,
and falls back to the global default when not.
"""

from unittest.mock import MagicMock, patch

from src.email.db_models import DocumentDescription


class TestDescriptionGeneratorDBScoping:
    """Test that DescriptionGenerator respects injected db_manager."""

    def _make_generator(self, db_manager=None):
        """Create a DescriptionGenerator with mocked LLM client."""
        with patch("src.document_processing.description_generator.OpenAI"):
            from src.document_processing.description_generator import (
                DescriptionGenerator,
            )

            return DescriptionGenerator(db_manager=db_manager)

    def test_uses_injected_db_manager(self):
        """Test that save_description uses the injected db_manager."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Return no existing description
        mock_session.query.return_value.filter.return_value.first.return_value = None

        gen = self._make_generator(db_manager=mock_db)
        gen.save_description(
            file_path="test.pdf",
            filename="test.pdf",
            description="A test document.",
            chunk_count=5,
        )

        mock_db.get_session.assert_called_once()
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    def test_falls_back_to_global_db_manager(self):
        """Test that default db_manager is used when none injected."""
        with (
            patch("src.document_processing.description_generator.OpenAI"),
            patch("src.email.db_manager.db_manager") as mock_global_db,
        ):
            from src.document_processing.description_generator import (
                DescriptionGenerator,
            )

            gen = DescriptionGenerator()
            # The generator should have stored the global db_manager
            assert gen._db_manager is mock_global_db

    def test_get_all_descriptions_uses_injected_db(self):
        """Test that get_all_descriptions queries the injected DB."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.all.return_value = []

        gen = self._make_generator(db_manager=mock_db)
        result = gen.get_all_descriptions()

        mock_db.get_session.assert_called_once()
        assert result == []

    def test_get_description_uses_injected_db(self):
        """Test that get_description queries the injected DB."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.filter.return_value.first.return_value = None

        gen = self._make_generator(db_manager=mock_db)
        result = gen.get_description("test.pdf")

        mock_db.get_session.assert_called_once()
        assert result is None

    def test_save_description_updates_existing(self):
        """Test that save_description updates when description exists."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_session.return_value.__enter__ = MagicMock(
            return_value=mock_session
        )
        mock_db.get_session.return_value.__exit__ = MagicMock(return_value=False)

        # Return existing description
        existing = MagicMock(spec=DocumentDescription)
        mock_session.query.return_value.filter.return_value.first.return_value = (
            existing
        )

        gen = self._make_generator(db_manager=mock_db)
        gen.save_description(
            file_path="test.pdf",
            filename="test.pdf",
            description="Updated description.",
            chunk_count=10,
        )

        assert existing.description == "Updated description."
        assert existing.chunk_count == 10
        mock_session.commit.assert_called_once()
