"""
Unit tests for enhancement_processor module.

Tests document enhancement, narrative expansion, and Q&A generation.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.document_processing.enhancement_processor import EnhancementProcessor


class TestEnhancementProcessor:
    """Test suite for EnhancementProcessor class."""

    @pytest.fixture
    def mock_openai_client(self):
        """Create a mock OpenAI client."""
        with patch(
            "src.document_processing.enhancement_processor.OpenAIClient"
        ) as mock:
            client_instance = MagicMock()
            mock.return_value = client_instance

            # Mock completion response
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message.content = (
                "This is a test enhancement response."
            )
            client_instance.chat.completions.create.return_value = mock_response

            yield client_instance

    @pytest.fixture
    def processor(self, mock_openai_client):
        """Create an EnhancementProcessor instance for testing."""
        return EnhancementProcessor(llm_model="test-model", max_tokens=1000)

    def test_should_enhance_csv(self, processor):
        """Test that CSV files are marked for enhancement."""
        assert processor.should_enhance(".csv") is True
        assert processor.should_enhance(".CSV") is True

    def test_should_enhance_excel(self, processor):
        """Test that Excel files are marked for enhancement."""
        assert processor.should_enhance(".xlsx") is True
        assert processor.should_enhance(".xls") is True
        assert processor.should_enhance(".XLSX") is True

    def test_should_not_enhance_pdf(self, processor):
        """Test that PDF files are not marked for enhancement."""
        assert processor.should_enhance(".pdf") is False
        assert processor.should_enhance(".PDF") is False

    def test_should_not_enhance_docx(self, processor):
        """Test that DOCX files are not marked for enhancement."""
        assert processor.should_enhance(".docx") is False

    def test_should_not_enhance_txt(self, processor):
        """Test that TXT files are not marked for enhancement."""
        assert processor.should_enhance(".txt") is False

    def test_expand_structured_data(self, processor, mock_openai_client):
        """Test narrative expansion for structured data."""
        test_text = """Name,Age,Department
Alice,25,Engineering
Bob,30,Marketing"""

        # Mock LLM response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = (
            "This dataset contains employee information with 2 records."
        )
        mock_openai_client.chat.completions.create.return_value = mock_response

        narrative = processor.expand_structured_data(test_text, ".csv")

        # Verify API was called
        assert mock_openai_client.chat.completions.create.called
        assert "employee information" in narrative.lower()

        # Verify prompt includes the data
        call_args = mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        user_message = [m for m in messages if m["role"] == "user"][0]
        assert "Alice" in user_message["content"]
        assert ".csv" in user_message["content"]

    def test_expand_structured_data_truncation(self, processor, mock_openai_client):
        """Test that very long text is truncated."""
        # Create text longer than 12000 characters
        long_text = "A" * 15000

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Summary of long data."
        mock_openai_client.chat.completions.create.return_value = mock_response

        _narrative = processor.expand_structured_data(long_text, ".csv")

        # Verify API was called
        assert mock_openai_client.chat.completions.create.called

        # Verify input was truncated
        call_args = mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        user_message = [m for m in messages if m["role"] == "user"][0]
        assert "truncated" in user_message["content"]

    def test_generate_qa_pairs(self, processor, mock_openai_client):
        """Test Q&A pair generation."""
        test_text = """Name: Alice
Age: 25
Department: Engineering"""

        # Mock LLM response with Q&A format
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[
            0
        ].message.content = """Q: What is Alice's age?
A: Alice is 25 years old.

Q: What department does Alice work in?
A: Alice works in the Engineering department."""
        mock_openai_client.chat.completions.create.return_value = mock_response

        qa_pairs = processor.generate_qa_pairs(test_text, ".csv")

        # Verify API was called
        assert mock_openai_client.chat.completions.create.called
        assert "Q:" in qa_pairs
        assert "A:" in qa_pairs
        assert "Alice" in qa_pairs

        # Verify prompt is correct
        call_args = mock_openai_client.chat.completions.create.call_args
        assert call_args[1]["temperature"] == 0.2  # Low temp for factual Q&A

    def test_generate_qa_pairs_truncation(self, processor, mock_openai_client):
        """Test that Q&A generation truncates long text."""
        long_text = "Data" * 5000

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Q: Test? A: Test."
        mock_openai_client.chat.completions.create.return_value = mock_response

        _qa_pairs = processor.generate_qa_pairs(long_text, ".xlsx")

        # Verify input was truncated
        call_args = mock_openai_client.chat.completions.create.call_args
        messages = call_args[1]["messages"]
        user_message = [m for m in messages if m["role"] == "user"][0]
        assert "truncated" in user_message["content"]

    def test_enhance_document_both_types(self, processor, mock_openai_client):
        """Test enhancing document with both narrative and Q&A."""
        test_text = "Name,Value\nTest,123"

        # Mock responses for both calls
        responses = [
            # First call (narrative)
            MagicMock(
                choices=[
                    MagicMock(message=MagicMock(content="This is narrative expansion."))
                ]
            ),
            # Second call (Q&A)
            MagicMock(
                choices=[MagicMock(message=MagicMock(content="Q: What? A: Test."))]
            ),
        ]
        mock_openai_client.chat.completions.create.side_effect = responses

        result = processor.enhance_document(
            test_text, ".csv", enhancement_types=["narrative", "qa"]
        )

        # Verify both enhancements were applied
        assert result["enhancement_count"] == 2
        assert "Narrative Summary" in result["enhanced_text"]
        assert "Q&A Pairs" in result["enhanced_text"]
        assert "narrative expansion" in result["narrative"]
        assert "Q:" in result["qa_pairs"]
        assert len(result["enhanced_text"]) > 0

    def test_enhance_document_narrative_only(self, processor, mock_openai_client):
        """Test enhancing document with narrative only."""
        test_text = "Data"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Narrative only."
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = processor.enhance_document(
            test_text, ".csv", enhancement_types=["narrative"]
        )

        # Verify only narrative was generated
        assert result["enhancement_count"] == 1
        assert "Narrative Summary" in result["enhanced_text"]
        assert "Q&A Pairs" not in result["enhanced_text"]
        assert result["narrative"] == "Narrative only."
        assert result["qa_pairs"] == ""

    def test_enhance_document_qa_only(self, processor, mock_openai_client):
        """Test enhancing document with Q&A only."""
        test_text = "Data"

        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Q: Test? A: Yes."
        mock_openai_client.chat.completions.create.return_value = mock_response

        result = processor.enhance_document(test_text, ".csv", enhancement_types=["qa"])

        # Verify only Q&A was generated
        assert result["enhancement_count"] == 1
        assert "Q&A Pairs" in result["enhanced_text"]
        assert "Narrative Summary" not in result["enhanced_text"]
        assert result["narrative"] == ""
        assert result["qa_pairs"] == "Q: Test? A: Yes."

    def test_enhance_document_default_types(self, processor, mock_openai_client):
        """Test that default enhancement types include both narrative and Q&A."""
        test_text = "Data"

        # Mock responses
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="Narrative."))]),
            MagicMock(choices=[MagicMock(message=MagicMock(content="Q: A:"))]),
        ]
        mock_openai_client.chat.completions.create.side_effect = responses

        # Call without specifying types (should use default)
        result = processor.enhance_document(test_text, ".csv")

        # Should have both enhancements
        assert result["enhancement_count"] == 2

    def test_enhance_document_api_error_handling(self, processor, mock_openai_client):
        """Test that API errors are handled gracefully."""
        test_text = "Data"

        # Mock API error
        mock_openai_client.chat.completions.create.side_effect = Exception("API Error")

        result = processor.enhance_document(
            test_text, ".csv", enhancement_types=["narrative"]
        )

        # Should return empty result without crashing
        assert result["enhancement_count"] == 0
        assert result["enhanced_text"] == ""
        assert result["narrative"] == ""

    def test_enhance_document_partial_failure(self, processor, mock_openai_client):
        """Test that partial enhancement works when one type fails."""
        test_text = "Data"

        # First call succeeds, second fails
        responses = [
            MagicMock(choices=[MagicMock(message=MagicMock(content="Narrative OK"))]),
            Exception("Q&A failed"),
        ]
        mock_openai_client.chat.completions.create.side_effect = responses

        result = processor.enhance_document(
            test_text, ".csv", enhancement_types=["narrative", "qa"]
        )

        # Should have narrative but not Q&A
        assert result["enhancement_count"] == 1
        assert result["narrative"] == "Narrative OK"
        assert result["qa_pairs"] == ""
