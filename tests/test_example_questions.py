"""
Tests for example_questions tenant-scoped file path support.

Tests that save/load functions use the provided file_path when given,
and fall back to the default ST path when not.
"""

import json
from pathlib import Path

from src.rag.example_questions import (
    DEFAULT_QUESTIONS_FILE,
    _resolve_file,
    load_example_questions,
    save_example_questions,
)


class TestResolveFile:
    """Test file path resolution helper."""

    def test_returns_default_when_none(self):
        """Test that None resolves to the default ST path."""
        result = _resolve_file(None)
        assert result == DEFAULT_QUESTIONS_FILE

    def test_returns_custom_path_when_provided(self):
        """Test that a custom path is returned as-is."""
        custom = Path("/tmp/tenant/config/example_questions.json")
        result = _resolve_file(custom)
        assert result == custom


class TestSaveExampleQuestions:
    """Test saving example questions with optional file_path."""

    def test_save_to_default_path(self, tmp_path):
        """Test saving to default path (ST mode)."""
        target = tmp_path / "config" / "example_questions.json"
        questions = ["What is X?", "How does Y work?"]

        save_example_questions(questions, file_path=target)

        assert target.exists()
        data = json.loads(target.read_text())
        assert data["questions"] == questions
        assert data["count"] == 2

    def test_save_to_tenant_path(self, tmp_path):
        """Test saving to a tenant-specific path (MT mode)."""
        tenant_path = tmp_path / "tenants" / "acme" / "config" / "questions.json"
        questions = ["Tenant question 1?", "Tenant question 2?"]

        save_example_questions(questions, file_path=tenant_path)

        assert tenant_path.exists()
        data = json.loads(tenant_path.read_text())
        assert data["questions"] == questions

    def test_creates_parent_dirs(self, tmp_path):
        """Test that parent directories are created automatically."""
        deep_path = tmp_path / "a" / "b" / "c" / "questions.json"
        save_example_questions(["Q?"], file_path=deep_path)
        assert deep_path.exists()


class TestLoadExampleQuestions:
    """Test loading example questions with optional file_path."""

    def test_load_from_custom_path(self, tmp_path):
        """Test loading from a tenant-specific path."""
        target = tmp_path / "questions.json"
        data = {"questions": ["Q1?", "Q2?"], "count": 2, "generated_at": None}
        target.write_text(json.dumps(data))

        result = load_example_questions(file_path=target)
        assert result["questions"] == ["Q1?", "Q2?"]
        assert result["count"] == 2

    def test_raises_file_not_found_for_missing_path(self, tmp_path):
        """Test that FileNotFoundError is raised for missing file."""
        missing = tmp_path / "nonexistent.json"

        try:
            load_example_questions(file_path=missing)
            assert False, "Expected FileNotFoundError"
        except FileNotFoundError:
            pass

    def test_tenant_paths_are_isolated(self, tmp_path):
        """Test that different tenant paths don't interfere."""
        tenant_a = tmp_path / "tenant_a" / "questions.json"
        tenant_b = tmp_path / "tenant_b" / "questions.json"

        save_example_questions(["Tenant A question?"], file_path=tenant_a)
        save_example_questions(["Tenant B question?"], file_path=tenant_b)

        result_a = load_example_questions(file_path=tenant_a)
        result_b = load_example_questions(file_path=tenant_b)

        assert result_a["questions"] == ["Tenant A question?"]
        assert result_b["questions"] == ["Tenant B question?"]
