"""
Unit tests for RAG engine module.

Tests system prompt generation and customization.
"""

from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from src.rag.rag_engine import get_system_prompt


class TestGetSystemPrompt:
    """Test suite for get_system_prompt function."""

    @patch("src.rag.rag_engine.settings")
    def test_basic_system_prompt(self, mock_settings):
        """Test basic system prompt generation without customization."""
        mock_settings.rag_custom_prompt_file = None

        prompt = get_system_prompt(
            instance_name="TestBot",
            instance_description="a test assistant",
            organization="Test Org",
        )

        # Check base prompt elements
        assert "You are TestBot" in prompt
        assert "a test assistant" in prompt
        assert "at Test Org" in prompt
        assert "Guidelines:" in prompt
        assert "context_str" in prompt
        assert "query_str" in prompt

    @patch("src.rag.rag_engine.settings")
    def test_system_prompt_without_organization(self, mock_settings):
        """Test system prompt generation without organization."""
        mock_settings.rag_custom_prompt_file = None

        prompt = get_system_prompt(
            instance_name="TestBot",
            instance_description="a test assistant",
            organization="",
        )

        # Should not have "at" when no organization
        assert "You are TestBot, a test assistant." in prompt
        assert "at " not in prompt.split("\n")[0]  # First line should not have "at"

    @patch("src.rag.rag_engine.settings")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="- Always use British English\n- Be detailed",
    )
    def test_system_prompt_with_custom_file(self, mock_file, mock_settings):
        """Test appending custom prompt from file."""
        mock_settings.rag_custom_prompt_file = Path("/tmp/custom_prompt.txt")

        with patch.object(Path, "exists", return_value=True):
            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Check base prompt is present
        assert "You are TestBot" in prompt
        assert "Guidelines:" in prompt

        # Check custom prompt is appended
        assert "Always use British English" in prompt
        assert "Be detailed" in prompt

        # Verify it's after the base prompt
        base_end = prompt.index("acknowledge the limitation")
        custom_start = prompt.index("Always use British English")
        assert custom_start > base_end

    @patch("src.rag.rag_engine.settings")
    def test_system_prompt_custom_file_not_exists(self, mock_settings):
        """Test fallback when custom prompt file doesn't exist."""
        mock_settings.rag_custom_prompt_file = Path("/nonexistent/prompt.txt")

        with patch.object(Path, "exists", return_value=False):
            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Should only have base prompt
        assert "You are TestBot" in prompt
        assert "Guidelines:" in prompt

    @patch("src.rag.rag_engine.settings")
    @patch("builtins.open", side_effect=PermissionError("No permission"))
    def test_system_prompt_custom_file_permission_error(
        self, mock_file, mock_settings
    ):
        """Test handling of permission error when reading custom prompt."""
        mock_settings.rag_custom_prompt_file = Path("/tmp/prompt.txt")

        with patch.object(Path, "exists", return_value=True):
            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Should fallback to base prompt
        assert "You are TestBot" in prompt
        assert "Guidelines:" in prompt

    @patch("src.rag.rag_engine.settings")
    @patch("builtins.open", new_callable=mock_open, read_data="   \n\n   ")
    def test_system_prompt_empty_custom_file(self, mock_file, mock_settings):
        """Test handling of empty custom prompt file."""
        mock_settings.rag_custom_prompt_file = Path("/tmp/prompt.txt")

        with patch.object(Path, "exists", return_value=True):
            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Should only have base prompt (empty after strip)
        assert "You are TestBot" in prompt
        assert "Guidelines:" in prompt

    @patch("src.rag.rag_engine.settings")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="Line 1\nLine 2\nLine 3",
    )
    def test_system_prompt_multiline_custom_prompt(self, mock_file, mock_settings):
        """Test custom prompt with multiple lines."""
        mock_settings.rag_custom_prompt_file = Path("/tmp/prompt.txt")

        with patch.object(Path, "exists", return_value=True):
            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Check all lines are present
        assert "Line 1" in prompt
        assert "Line 2" in prompt
        assert "Line 3" in prompt

    def test_system_prompt_has_required_placeholders(self):
        """Test that system prompt includes required template placeholders."""
        with patch("src.rag.rag_engine.settings") as mock_settings:
            mock_settings.rag_custom_prompt_file = None

            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="",
            )

        # Must have these placeholders for LlamaIndex
        assert "{context_str}" in prompt
        assert "{query_str}" in prompt

    def test_system_prompt_structure(self):
        """Test that system prompt has expected structure."""
        with patch("src.rag.rag_engine.settings") as mock_settings:
            mock_settings.rag_custom_prompt_file = None

            prompt = get_system_prompt(
                instance_name="TestBot",
                instance_description="a test assistant",
                organization="Test Org",
            )

        # Check structure sections
        assert "You are TestBot" in prompt
        assert "Your role is to help users" in prompt
        assert "Context information is provided below:" in prompt
        assert "Based on the context above" in prompt
        assert "Query:" in prompt
        assert "Answer:" in prompt
