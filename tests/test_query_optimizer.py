"""
Unit tests for query_optimizer module.

Tests query optimization, expansion, rewriting, and context-aware enhancement.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.rag.query_optimizer import QueryOptimizer


class TestQueryOptimizer:
    """Test suite for QueryOptimizer class."""

    @pytest.fixture
    def mock_settings(self):
        """Mock settings for query optimizer."""
        with patch("src.rag.query_optimizer.settings") as mock:
            mock.query_optimization_enabled = True
            mock.query_optimization_model = "test-model"
            mock.query_optimization_max_tokens = 500
            mock.query_optimization_temperature = 0.3
            mock.query_optimization_timeout = 10
            mock.openrouter_api_key = "test-key"
            mock.openrouter_api_base = "https://api.example.com/v1"
            mock.openrouter_model = "default-model"
            yield mock

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        with patch("src.rag.query_optimizer.OpenAIClient") as mock:
            client_instance = MagicMock()
            mock.return_value = client_instance

            # Default mock response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = "optimized query"
            mock_response.usage = MagicMock()
            mock_response.usage.prompt_tokens = 50
            mock_response.usage.completion_tokens = 20
            client_instance.chat.completions.create.return_value = mock_response

            yield client_instance

    @pytest.fixture
    def optimizer(self, mock_settings, mock_openai_client):
        """Create a QueryOptimizer instance for testing."""
        return QueryOptimizer()

    def test_optimizer_initialization_enabled(self, mock_settings, mock_openai_client):
        """Test optimizer initialization when enabled."""
        optimizer = QueryOptimizer()

        assert optimizer.enabled is True
        assert optimizer.model == "test-model"
        assert optimizer.max_tokens == 500
        assert optimizer.temperature == 0.3
        assert optimizer.timeout == 10
        assert optimizer.client is not None

    def test_optimizer_initialization_disabled(self, mock_settings):
        """Test optimizer initialization when disabled."""
        mock_settings.query_optimization_enabled = False

        with patch("src.rag.query_optimizer.OpenAIClient"):
            optimizer = QueryOptimizer()

        assert optimizer.enabled is False
        assert optimizer.client is None

    def test_optimizer_uses_default_model(self, mock_settings, mock_openai_client):
        """Test that optimizer falls back to default model when not specified."""
        mock_settings.query_optimization_model = None
        mock_settings.openrouter_model = "fallback-model"

        optimizer = QueryOptimizer()

        assert optimizer.model == "fallback-model"

    def test_optimize_query_basic(self, optimizer, mock_openai_client):
        """Test basic query optimization."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "What is the company vacation policy?"
        )
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 50
        mock_response.usage.completion_tokens = 20
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("vacation policy?")

        assert result == "What is the company vacation policy?"
        assert mock_openai_client.chat.completions.create.called

    def test_optimize_query_with_conversation_history(
        self, optimizer, mock_openai_client
    ):
        """Test query optimization with conversation history."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "What is the sick leave policy?"
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        conversation_history = (
            "User: Tell me about vacation policy\nAssistant: The vacation policy is..."
        )

        result = optimizer.optimize_query("What about sick days?", conversation_history)

        assert result == "What is the sick leave policy?"

        # Verify conversation history was included in prompt
        call_args = mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        prompt = messages[0]["content"]
        assert "vacation policy" in prompt

    def test_optimize_query_expansion(self, optimizer, mock_openai_client):
        """Test query expansion with synonyms and related terms."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "What is the policy for vehicle, car, automobile parking?"
        )
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("car parking policy")

        assert "vehicle" in result or "automobile" in result
        assert len(result) > len("car parking policy")

    def test_optimize_query_rewriting(self, optimizer, mock_openai_client):
        """Test query rewriting for clarity."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "What is the policy regarding vacation time?"
        )
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("what policy vacation?")

        assert "What is" in result
        assert "policy" in result
        assert len(result) > 10  # Should be a proper sentence

    def test_optimize_query_disabled(self, mock_settings, mock_openai_client):
        """Test that optimization is skipped when disabled."""
        mock_settings.query_optimization_enabled = False
        optimizer = QueryOptimizer()

        result = optimizer.optimize_query("test query")

        assert result == "test query"
        assert not mock_openai_client.chat.completions.create.called

    def test_optimize_query_empty(self, optimizer, mock_openai_client):
        """Test handling of empty queries."""
        result = optimizer.optimize_query("")

        assert result == ""
        assert not mock_openai_client.chat.completions.create.called

    def test_optimize_query_too_short(self, optimizer, mock_openai_client):
        """Test that very short queries are skipped."""
        result = optimizer.optimize_query("hi")

        assert result == "hi"
        assert not mock_openai_client.chat.completions.create.called

    def test_optimize_query_api_error(self, optimizer, mock_openai_client):
        """Test fallback on API error."""
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        result = optimizer.optimize_query("test query")

        # Should return original query on error
        assert result == "test query"

    def test_optimize_query_timeout(self, optimizer, mock_openai_client):
        """Test handling of API timeout."""
        from openai import APITimeoutError

        mock_openai_client.chat.completions.create.side_effect = APITimeoutError(
            "Timeout"
        )

        result = optimizer.optimize_query("test query")

        # Should return original query on timeout
        assert result == "test query"

    def test_validate_optimization_empty_result(self, optimizer):
        """Test validation rejects empty optimized queries."""
        assert optimizer._validate_optimization("test query", "") is False
        assert optimizer._validate_optimization("test query", "   ") is False

    def test_validate_optimization_too_short(self, optimizer):
        """Test validation rejects very short optimized queries."""
        assert optimizer._validate_optimization("test query", "ab") is False

    def test_validate_optimization_too_long(self, optimizer):
        """Test validation rejects unreasonably long optimized queries."""
        original = "short query"
        optimized = "x" * 600  # Longer than 500 char limit

        assert optimizer._validate_optimization(original, optimized) is False

    def test_validate_optimization_length_ratio(self, optimizer):
        """Test validation rejects queries that expand too much."""
        original = "test"
        optimized = "x" * 200  # More than 5x original length

        assert optimizer._validate_optimization(original, optimized) is False

    def test_validate_optimization_contains_explanation(self, optimizer):
        """Test validation rejects queries with explanation text."""
        original = "test query"

        # Test various explanation patterns
        explanations = [
            "Here is the optimized query: test query",
            "Here's the optimized query: test query",
            "The optimized query is: test query",
            "Optimized query: test query",
            "I've optimized your query: test query",
            "I have optimized the query: test query",
        ]

        for explanation in explanations:
            assert optimizer._validate_optimization(original, explanation) is False

    def test_validate_optimization_rejects_explanation_with_quotes(
        self, optimizer, mock_openai_client
    ):
        """Test that validation rejects explanations even with quoted content."""
        original = "test"
        optimized_with_quotes = 'Here is the optimized query: "What is the test?"'

        # This should be rejected because it contains explanation text
        result = optimizer._validate_optimization(original, optimized_with_quotes)

        # The validation should fail because of explanation pattern
        assert result is False

    def test_validate_optimization_valid_query(self, optimizer):
        """Test validation accepts valid optimized queries."""
        original = "test query"
        optimized = "What is the test query about?"

        assert optimizer._validate_optimization(original, optimized) is True

    def test_build_optimization_prompt_basic(self, optimizer):
        """Test building basic optimization prompt."""
        prompt = optimizer._build_optimization_prompt("test query", None)

        assert "query optimization assistant" in prompt.lower()
        assert "expand the query" in prompt.lower()
        assert "rewrite for clarity" in prompt.lower()
        assert "enhance with context" in prompt.lower()
        assert "test query" in prompt
        assert "Original query: test query" in prompt

    def test_build_optimization_prompt_with_history(self, optimizer):
        """Test building prompt with conversation history."""
        history = "User: previous question\nAssistant: previous answer"
        prompt = optimizer._build_optimization_prompt("follow-up question", history)

        assert "Conversation history" in prompt
        assert "previous question" in prompt
        assert "previous answer" in prompt
        assert "follow-up question" in prompt

    def test_call_llm_success(self, optimizer, mock_openai_client):
        """Test successful LLM API call."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "optimized query result"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer._call_llm("test prompt")

        assert result == "optimized query result"

        # Verify API call parameters
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args[1]["model"] == "test-model"
        assert call_args[1]["max_tokens"] == 500
        assert call_args[1]["temperature"] == 0.3
        assert "HTTP-Referer" in call_args[1]["extra_headers"]

    def test_call_llm_strips_whitespace(self, optimizer, mock_openai_client):
        """Test that LLM response is stripped of whitespace."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "  optimized query  \n"
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer._call_llm("test prompt")

        assert result == "optimized query"

    def test_call_llm_error(self, optimizer, mock_openai_client):
        """Test LLM API call error handling."""
        from openai import OpenAIError

        mock_openai_client.chat.completions.create.side_effect = OpenAIError(
            "API Error"
        )

        with pytest.raises(OpenAIError):
            optimizer._call_llm("test prompt")

    def test_optimize_query_no_change_returns_original(
        self, optimizer, mock_openai_client
    ):
        """Test that optimizer can return original query unchanged."""
        # LLM decides the query is already optimal
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "test query"
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("test query")

        assert result == "test query"

    def test_optimize_query_validation_failure_returns_original(
        self, optimizer, mock_openai_client
    ):
        """Test that validation failure returns original query."""
        # LLM returns invalid response (too long)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "x" * 1000  # Too long
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("short")

        # Should fall back to original due to validation failure
        assert result == "short"

    def test_optimizer_with_custom_parameters(self, mock_settings, mock_openai_client):
        """Test optimizer initialization with custom parameters."""
        optimizer = QueryOptimizer(
            model="custom-model", max_tokens=1000, temperature=0.5, timeout=20
        )

        assert optimizer.model == "custom-model"
        assert optimizer.max_tokens == 1000
        assert optimizer.temperature == 0.5
        assert optimizer.timeout == 20

    def test_optimize_query_logs_optimization(self, optimizer, mock_openai_client):
        """Test that optimization is logged."""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "optimized result"
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        with patch("src.rag.query_optimizer.logger") as mock_logger:
            optimizer.optimize_query("original")

            # Should log optimization attempt
            assert mock_logger.info.called

    def test_optimize_query_preserves_meaning(self, optimizer, mock_openai_client):
        """Test that optimization preserves query meaning."""
        # Simulate a good optimization (reasonable length to pass validation)
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "What is the vacation policy?"
        mock_response.usage = None
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = optimizer.optimize_query("vacation days")

        assert "vacation" in result.lower()
        assert len(result) > len("vacation days")
