"""
Document enhancement processor for converting dry structured data into narrative content.

Uses LLM to expand tables, generate Q&A pairs, and create semantic-rich content
for better RAG retrieval.
"""

import logging
from typing import Dict, List, Optional

from openai import OpenAI as OpenAIClient

from src.config import settings

logger = logging.getLogger(__name__)


class EnhancementProcessor:
    """
    Processes and enhances structured documents for improved RAG retrieval.

    Converts dry tabular data into narrative text and generates Q&A pairs
    to improve semantic search capabilities.
    """

    def __init__(
        self,
        llm_model: Optional[str] = None,
        max_tokens: int = 4000,
    ):
        """
        Initialize the enhancement processor.

        Args:
            llm_model: LLM model name (default from settings).
            max_tokens: Maximum tokens to use for enhancement.
        """
        self.llm_model = llm_model or settings.openrouter_model
        self.max_tokens = max_tokens

        # Initialize OpenAI-compatible client (OpenRouter)
        self.client = OpenAIClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_api_base,
        )

        logger.info(f"EnhancementProcessor initialized with model: {self.llm_model}")

    def enhance_document(
        self,
        text: str,
        file_type: str,
        enhancement_types: Optional[List[str]] = None,
    ) -> Dict[str, any]:
        """
        Enhance document with LLM-generated content.

        Args:
            text: Document text to enhance.
            file_type: File extension (e.g., '.csv', '.xlsx').
            enhancement_types: List of enhancement types to apply
                              ('narrative', 'qa'). Default: both.

        Returns:
            Dictionary with enhanced content:
            {
                'enhanced_text': str,  # Full enhanced text to append
                'narrative': str,      # Narrative expansion (if requested)
                'qa_pairs': str,       # Q&A pairs (if requested)
                'enhancement_count': int  # Number of enhancements applied
            }
        """
        if enhancement_types is None:
            enhancement_types = ["narrative", "qa"]

        logger.info(
            f"Enhancing {file_type} document with: {', '.join(enhancement_types)}"
        )

        enhanced_parts = []
        result = {
            "enhanced_text": "",
            "narrative": "",
            "qa_pairs": "",
            "enhancement_count": 0,
        }

        # Generate narrative expansion for structured data
        if "narrative" in enhancement_types:
            try:
                narrative = self.expand_structured_data(text, file_type)
                if narrative:
                    enhanced_parts.append(f"--- Narrative Summary ---\n{narrative}")
                    result["narrative"] = narrative
                    result["enhancement_count"] += 1
                    logger.info("Successfully generated narrative expansion")
            except Exception as e:
                logger.error(f"Failed to generate narrative: {e}")

        # Generate Q&A pairs
        if "qa" in enhancement_types:
            try:
                qa_pairs = self.generate_qa_pairs(text, file_type)
                if qa_pairs:
                    enhanced_parts.append(f"--- Q&A Pairs ---\n{qa_pairs}")
                    result["qa_pairs"] = qa_pairs
                    result["enhancement_count"] += 1
                    logger.info("Successfully generated Q&A pairs")
            except Exception as e:
                logger.error(f"Failed to generate Q&A pairs: {e}")

        # Combine all enhancements
        if enhanced_parts:
            result["enhanced_text"] = "\n\n".join(enhanced_parts)

        logger.info(
            f"Enhancement complete: {result['enhancement_count']} enhancements applied"
        )

        return result

    def expand_structured_data(self, text: str, file_type: str) -> str:
        """
        Convert structured data into narrative text using LLM.

        Args:
            text: Structured data text (table format).
            file_type: File extension (e.g., '.csv', '.xlsx').

        Returns:
            Narrative description of the data.
        """
        # Truncate text if too long to avoid token limits
        max_input_chars = 12000  # Roughly 3000 tokens
        if len(text) > max_input_chars:
            text = text[:max_input_chars] + "\n... (truncated)"
            logger.warning("Input text truncated to fit token limits")

        prompt = f"""You are analyzing structured data from a {file_type} file. Convert this dry, tabular data into a rich, descriptive narrative that explains:
1. What the data represents and its overall purpose
2. Key patterns, trends, or relationships in the data
3. Important values, dates, or entities mentioned
4. The context and significance of the information

Make the narrative readable and semantic-rich to improve information retrieval. Focus on the "what" and "why" rather than just repeating the raw data.

Structured Data:
{text}

Narrative Description:"""

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data analyst who converts structured data into clear, descriptive narratives.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Low temperature for factual descriptions
                max_tokens=self.max_tokens // 2,  # Reserve tokens for Q&A
            )

            narrative = response.choices[0].message.content.strip()
            return narrative

        except Exception as e:
            logger.error(f"Error generating narrative: {e}")
            raise

    def generate_qa_pairs(self, text: str, file_type: str) -> str:
        """
        Generate question-answer pairs from document content.

        Args:
            text: Document text.
            file_type: File extension (e.g., '.csv', '.xlsx').

        Returns:
            Formatted Q&A pairs as text.
        """
        # Truncate text if too long
        max_input_chars = 12000
        if len(text) > max_input_chars:
            text = text[:max_input_chars] + "\n... (truncated)"
            logger.warning("Input text truncated for Q&A generation")

        prompt = f"""Based on the following {file_type} document content, generate 5-10 factual question-answer pairs that capture the key information.

Make questions specific and answerable from the content. Format each pair as:
Q: [Question]
A: [Answer]

Focus on important facts, dates, names, values, and relationships in the data.

Document Content:
{text}

Q&A Pairs:"""

        try:
            response = self.client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a question generation expert who creates factual Q&A pairs from documents.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,  # Very low temperature for factual Q&A
                max_tokens=self.max_tokens // 2,
            )

            qa_pairs = response.choices[0].message.content.strip()
            return qa_pairs

        except Exception as e:
            logger.error(f"Error generating Q&A pairs: {e}")
            raise

    @staticmethod
    def generate_contextual_header(
        filename: str,
        file_type: str,
        source_type: str = "file",
        extra_metadata: Optional[Dict] = None,
    ) -> str:
        """
        Generate a contextual header string for a document chunk.

        Prepended to each chunk before embedding to improve retrieval accuracy
        by providing document-level context.

        Args:
            filename: Name of the source file.
            file_type: File extension (e.g., '.pdf', '.docx').
            source_type: Source of the document ('manual', 'email', 'web').
            extra_metadata: Additional metadata (subject, sender, etc.).

        Returns:
            Contextual header string.
        """
        header_parts = [f"Document: {filename}"]

        if source_type == "web":
            source_url = (extra_metadata or {}).get("source_url")
            if source_url:
                header_parts.append(f"Source: {source_url}")
            else:
                header_parts.append("Source: Web page")
        elif source_type == "email":
            if extra_metadata:
                if extra_metadata.get("subject"):
                    header_parts.append(f"Email subject: {extra_metadata['subject']}")
                if extra_metadata.get("sender"):
                    header_parts.append(f"From: {extra_metadata['sender']}")

        header_parts.append(f"Type: {file_type.lstrip('.')}")

        return " | ".join(header_parts)

    def should_enhance(self, file_type: str) -> bool:
        """
        Determine if a file should be enhanced based on type.

        Args:
            file_type: File extension (e.g., '.csv', '.xlsx', '.pdf').

        Returns:
            True if file should be enhanced (structured data types).
        """
        # Only enhance structured data formats
        structured_formats = {".csv", ".xls", ".xlsx"}
        return file_type.lower() in structured_formats
