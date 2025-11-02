"""
Document Description Generator.

Generates 2-sentence summaries of documents using LLM for display in the admin panel.
"""

import logging
from typing import List, Optional
from datetime import datetime

from openai import OpenAI
from llama_index.core.schema import TextNode

from src.config import settings
from src.email.db_manager import db_manager
from src.email.db_models import DocumentDescription

logger = logging.getLogger(__name__)


class DescriptionGenerator:
    """
    Generates AI-powered descriptions for ingested documents.

    Uses LLM to create concise 2-sentence summaries based on the
    first few chunks of each document.
    """

    def __init__(self):
        """Initialize the description generator with LLM client."""
        # Use OpenRouter for LLM calls
        self.client = OpenAI(
            base_url=settings.openrouter_api_base,
            api_key=settings.openrouter_api_key,
        )
        self.model = settings.openrouter_model

        logger.info("DescriptionGenerator initialized")

    def generate_description(self, chunks: List[TextNode], max_chunks: int = 3) -> str:
        """
        Generate a 2-sentence description from document chunks.

        Args:
            chunks: List of document chunks (TextNode objects)
            max_chunks: Maximum number of chunks to use (default: 3)

        Returns:
            2-sentence description of the document
        """
        if not chunks:
            return "Document contains no extractable content."

        # Get first few chunks for context
        sample_chunks = chunks[:max_chunks]
        combined_text = "\n\n".join([node.text for node in sample_chunks])

        # Limit text length to avoid token limits
        max_chars = 4000
        if len(combined_text) > max_chars:
            combined_text = combined_text[:max_chars] + "..."

        # Create prompt for LLM
        prompt = f"""Based on the following excerpt from a document, provide a concise 2-sentence summary that describes what this document is about. Be specific and informative.

Document excerpt:
{combined_text}

Provide only the 2-sentence summary, nothing else:"""

        try:
            # Call LLM to generate description
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that creates concise document summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,  # Lower temperature for more consistent summaries
                max_tokens=150,  # Limit to keep it concise
            )

            description = response.choices[0].message.content.strip()
            logger.info(f"Generated description: {description[:100]}...")

            return description

        except Exception as e:
            logger.error(f"Error generating description with LLM: {e}")
            # Fallback: use first sentence of first chunk
            fallback = sample_chunks[0].text.split(".")[0] + "."
            if len(fallback) > 200:
                fallback = fallback[:197] + "..."
            return fallback + " (Auto-generated summary)"

    def save_description(
        self,
        file_path: str,
        filename: str,
        description: str,
        chunk_count: int,
        file_size: Optional[int] = None,
        file_type: Optional[str] = None,
    ) -> DocumentDescription:
        """
        Save document description to database.

        Args:
            file_path: Relative path to the document file
            filename: Name of the file
            description: Generated description
            chunk_count: Number of chunks created
            file_size: Size of file in bytes
            file_type: File extension (e.g., 'pdf', 'docx')

        Returns:
            Created or updated DocumentDescription object
        """
        with db_manager.get_session() as session:
            # Check if description already exists
            existing = (
                session.query(DocumentDescription)
                .filter(DocumentDescription.file_path == file_path)
                .first()
            )

            if existing:
                # Update existing description
                existing.description = description
                existing.chunk_count = chunk_count
                existing.file_size = file_size
                existing.file_type = file_type
                existing.updated_at = datetime.utcnow()
                session.add(existing)
                session.commit()
                session.refresh(existing)

                logger.info(f"Updated description for: {filename}")
                return existing
            else:
                # Create new description
                doc_desc = DocumentDescription(
                    file_path=file_path,
                    filename=filename,
                    description=description,
                    file_size=file_size,
                    file_type=file_type,
                    chunk_count=chunk_count,
                )
                session.add(doc_desc)
                session.commit()
                session.refresh(doc_desc)

                logger.info(f"Saved description for: {filename}")
                return doc_desc

    def generate_and_save(
        self,
        file_path: str,
        filename: str,
        chunks: List[TextNode],
        file_size: Optional[int] = None,
        file_type: Optional[str] = None,
    ) -> DocumentDescription:
        """
        Generate and save description in one step.

        Args:
            file_path: Relative path to the document file
            filename: Name of the file
            chunks: List of document chunks
            file_size: Size of file in bytes
            file_type: File extension

        Returns:
            Created DocumentDescription object
        """
        description = self.generate_description(chunks)

        return self.save_description(
            file_path=file_path,
            filename=filename,
            description=description,
            chunk_count=len(chunks),
            file_size=file_size,
            file_type=file_type,
        )

    def get_description(self, file_path: str) -> Optional[DocumentDescription]:
        """
        Retrieve description for a file.

        Args:
            file_path: Relative path to the document file

        Returns:
            DocumentDescription object or None if not found
        """
        with db_manager.get_session() as session:
            return (
                session.query(DocumentDescription)
                .filter(DocumentDescription.file_path == file_path)
                .first()
            )

    def get_all_descriptions(self) -> List[DocumentDescription]:
        """
        Retrieve all document descriptions.

        Returns:
            List of DocumentDescription objects
        """
        with db_manager.get_session() as session:
            descriptions = session.query(DocumentDescription).all()
            # Convert to dicts to avoid detached instance issues
            return [
                {
                    "id": desc.id,
                    "file_path": desc.file_path,
                    "filename": desc.filename,
                    "description": desc.description,
                    "file_size": desc.file_size,
                    "file_type": desc.file_type,
                    "chunk_count": desc.chunk_count,
                    "created_at": (
                        desc.created_at.isoformat() if desc.created_at else None
                    ),
                    "updated_at": (
                        desc.updated_at.isoformat() if desc.updated_at else None
                    ),
                }
                for desc in descriptions
            ]


# Global instance
description_generator = DescriptionGenerator()
