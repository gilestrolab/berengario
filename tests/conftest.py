"""
Pytest configuration and shared fixtures.

Provides common fixtures and setup for all tests.
"""

import os
from unittest.mock import patch

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, LLMMetadata
from llama_index.core.embeddings import BaseEmbedding
from llama_index.core.llms import LLM


class MockEmbedding(BaseEmbedding):
    """Mock embedding model for testing."""

    def _get_query_embedding(self, query: str):
        """Return mock embedding for query."""
        return [0.1] * 384

    def _get_text_embedding(self, text: str):
        """Return mock embedding for text."""
        return [0.1] * 384

    async def _aget_query_embedding(self, query: str):
        """Return mock embedding for query (async)."""
        return [0.1] * 384

    async def _aget_text_embedding(self, text: str):
        """Return mock embedding for text (async)."""
        return [0.1] * 384


class MockLLM(LLM):
    """Mock LLM for testing."""

    api_key: str = "test-api-key"

    @property
    def metadata(self):
        """Return mock metadata."""
        return LLMMetadata(
            model_name="mock-llm",
            context_window=4096,
            num_output=512,
        )

    def chat(self, messages, **kwargs):
        """Return mock chat response."""
        return ChatResponse(
            message=ChatMessage(role="assistant", content="Mock response"),
            raw={"content": "Mock response"},
        )

    def complete(self, prompt: str, **kwargs):
        """Return mock completion."""
        return "Mock completion"

    def stream_chat(self, messages, **kwargs):
        """Return mock chat stream."""
        yield ChatResponse(
            message=ChatMessage(role="assistant", content="Mock response"),
            raw={"content": "Mock response"},
        )

    def stream_complete(self, prompt: str, **kwargs):
        """Return mock completion stream."""
        yield "Mock completion"

    async def achat(self, messages, **kwargs):
        """Return mock async chat response."""
        return ChatResponse(
            message=ChatMessage(role="assistant", content="Mock response"),
            raw={"content": "Mock response"},
        )

    async def acomplete(self, prompt: str, **kwargs):
        """Return mock async completion."""
        return "Mock completion"

    async def astream_chat(self, messages, **kwargs):
        """Return mock async chat stream."""
        yield ChatResponse(
            message=ChatMessage(role="assistant", content="Mock response"),
            raw={"content": "Mock response"},
        )

    async def astream_complete(self, prompt: str, **kwargs):
        """Return mock async completion stream."""
        yield "Mock completion"


@pytest.fixture(autouse=True)
def mock_openai_api():
    """
    Mock OpenAI API calls for all tests.

    This prevents actual API calls during testing.
    """
    with (
        patch("openai.OpenAI"),
        patch(
            "llama_index.embeddings.openai.OpenAIEmbedding",
            return_value=MockEmbedding(),
        ),
        patch("llama_index.llms.openai.OpenAI", return_value=MockLLM()),
    ):
        yield


@pytest.fixture(autouse=True)
def set_test_env_vars():
    """
    Set required environment variables for testing.

    Prevents config errors when .env file is missing.
    """
    test_env = {
        "OPENAI_API_KEY": "test-api-key",
        "OPENAI_API_BASE": "https://api.openai.com/v1",
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "OPENROUTER_API_BASE": "https://openrouter.ai/api/v1",
        "IMAP_SERVER": "test.imap.server",
        "IMAP_PORT": "993",
        "IMAP_USER": "test@example.com",
        "IMAP_PASSWORD": "test-password",
        "SMTP_SERVER": "test.smtp.server",
        "SMTP_PORT": "587",
        "SMTP_USER": "test@example.com",
        "SMTP_PASSWORD": "test-password",
        "EMAIL_TARGET_ADDRESS": "test@example.com",
    }

    # Store original values
    original_env = {}
    for key, value in test_env.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original values
    for key, value in original_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
