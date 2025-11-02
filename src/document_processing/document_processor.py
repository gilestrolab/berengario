"""
Document processor for parsing and chunking various document formats.

Supports: PDF, DOCX, TXT, CSV, and other text-based formats.
"""

import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from docx import Document as DocxDocument
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode
from pypdf import PdfReader

from src.config import settings

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """
    Processes documents from various formats into chunked text nodes.

    Handles PDF, DOCX, TXT, CSV and other common document formats.
    """

    def __init__(
        self,
        chunk_size: int = settings.chunk_size,
        chunk_overlap: int = settings.chunk_overlap,
    ):
        """
        Initialize the document processor.

        Args:
            chunk_size: Size of each text chunk in characters.
            chunk_overlap: Overlap between consecutive chunks.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Convert characters to tokens (roughly 1 token = 4 characters)
        # SentenceSplitter uses tokens, not characters
        chunk_size_tokens = chunk_size // 4
        chunk_overlap_tokens = chunk_overlap // 4

        self.splitter = SentenceSplitter(
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
        )

    def compute_file_hash(self, file_path: Path) -> str:
        """
        Compute SHA-256 hash of a file for deduplication.

        Args:
            file_path: Path to the file.

        Returns:
            Hex string of the file hash.
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def extract_text_from_pdf(self, file_path: Path) -> str:
        """
        Extract text from PDF file.

        Args:
            file_path: Path to PDF file.

        Returns:
            Extracted text content.

        Raises:
            Exception: If PDF reading fails.
        """
        try:
            reader = PdfReader(file_path)
            text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text.append(page_text)
            return "\n\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {e}")
            raise

    def extract_text_from_docx(self, file_path: Path) -> str:
        """
        Extract text from DOCX file.

        Args:
            file_path: Path to DOCX file.

        Returns:
            Extracted text content.

        Raises:
            Exception: If DOCX reading fails.
        """
        try:
            doc = DocxDocument(file_path)
            text = []
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    text.append(paragraph.text)
            return "\n\n".join(text)
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {e}")
            raise

    def extract_text_from_txt(self, file_path: Path) -> str:
        """
        Extract text from plain text file.

        Args:
            file_path: Path to text file.

        Returns:
            File content as string.

        Raises:
            Exception: If file reading fails.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding if UTF-8 fails
            try:
                with open(file_path, "r", encoding="latin-1") as f:
                    return f.read()
            except Exception as e:
                logger.error(f"Error reading text file {file_path}: {e}")
                raise
        except Exception as e:
            logger.error(f"Error reading text file {file_path}: {e}")
            raise

    def extract_text_from_csv(self, file_path: Path) -> str:
        """
        Extract text from CSV file.

        Args:
            file_path: Path to CSV file.

        Returns:
            CSV content formatted as text optimized for semantic search.

        Raises:
            Exception: If CSV reading fails.
        """
        try:
            # Try reading with headers first
            df = pd.read_csv(file_path)

            # Check if the file likely has no real headers (too many unnamed columns)
            unnamed_cols = [col for col in df.columns if 'Unnamed' in str(col)]
            if len(unnamed_cols) > len(df.columns) / 2:
                # Re-read without treating first row as header
                df = pd.read_csv(file_path, header=None)
                has_headers = False
            else:
                has_headers = True

            # Convert DataFrame to a semantic-search-friendly format
            lines = []

            # Add filename as context
            lines.append(f"Document: {file_path.name}")
            lines.append("")

            if has_headers:
                # Format with column names for each row
                for idx, row in df.iterrows():
                    # Skip completely empty rows
                    if row.isna().all():
                        lines.append("")
                        continue

                    row_lines = []
                    for col_name, value in row.items():
                        if pd.notna(value) and str(value).strip():
                            row_lines.append(f"{col_name}: {value}")

                    if row_lines:
                        lines.extend(row_lines)
                        lines.append("")  # Empty line between rows
            else:
                # Format as simple rows (for CSVs without headers)
                for idx, row in df.iterrows():
                    # Skip rows with only empty/zero values
                    row_values = [str(val) for val in row if pd.notna(val) and str(val).strip() and str(val) != '0']

                    if not row_values:
                        lines.append("")  # Preserve spacing for term breaks
                        continue

                    # Check if first column looks like a section header (contains month/term)
                    first_val = str(row[0]).strip() if pd.notna(row[0]) else ""

                    if len(row_values) == 1 or 'term' in first_val.lower():
                        # Section header
                        lines.append(first_val)
                        lines.append("")
                    else:
                        # Regular data row - format as "Date: Event [Notes]"
                        date_col = first_val
                        event_col = str(row[1]).strip() if len(row) > 1 and pd.notna(row[1]) else ""
                        notes_col = str(row[2]).strip() if len(row) > 2 and pd.notna(row[2]) else ""

                        if event_col:
                            line = f"Date: {date_col} - Event: {event_col}"
                            if notes_col:
                                line += f" - Notes: {notes_col}"
                            lines.append(line)

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error reading CSV file {file_path}: {e}")
            raise

    def extract_text(self, file_path: Path) -> str:
        """
        Extract text from file based on extension.

        Args:
            file_path: Path to the file.

        Returns:
            Extracted text content.

        Raises:
            ValueError: If file format is not supported.
            Exception: If extraction fails.
        """
        suffix = file_path.suffix.lower()

        if suffix == ".pdf":
            return self.extract_text_from_pdf(file_path)
        elif suffix == ".docx":
            return self.extract_text_from_docx(file_path)
        elif suffix == ".txt":
            return self.extract_text_from_txt(file_path)
        elif suffix == ".csv":
            return self.extract_text_from_csv(file_path)
        else:
            # Try to read as text file
            try:
                return self.extract_text_from_txt(file_path)
            except Exception:
                raise ValueError(f"Unsupported file format: {suffix}")

    def process_document(
        self,
        file_path: Path,
        source_type: str = "manual",
        extra_metadata: Optional[Dict] = None,
    ) -> List[TextNode]:
        """
        Process a document file into chunked text nodes.

        Args:
            file_path: Path to the document file.
            source_type: Source of the document ('manual' or 'email').
            extra_metadata: Additional metadata to attach to nodes.

        Returns:
            List of TextNode objects with text chunks and metadata.

        Raises:
            Exception: If document processing fails.
        """
        logger.info(f"Processing document: {file_path}")

        try:
            # Extract text from file
            text = self.extract_text(file_path)

            if not text.strip():
                logger.warning(f"No text extracted from {file_path}")
                return []

            # Compute file hash for deduplication
            file_hash = self.compute_file_hash(file_path)

            # Get file modification timestamp for versioning
            file_stat = file_path.stat()
            file_mtime = file_stat.st_mtime
            file_size = file_stat.st_size

            # Create base metadata
            metadata = {
                "filename": file_path.name,
                "file_path": str(file_path),
                "file_hash": file_hash,
                "file_mtime": file_mtime,  # Modification timestamp for versioning
                "file_size": file_size,
                "source_type": source_type,
                "file_type": file_path.suffix.lower(),
            }

            # Add extra metadata if provided
            if extra_metadata:
                metadata.update(extra_metadata)

            # Create Document object for LlamaIndex
            document = Document(text=text, metadata=metadata)

            # Split into chunks
            nodes = self.splitter.get_nodes_from_documents([document])

            logger.info(
                f"Successfully processed {file_path.name}: {len(nodes)} chunks created"
            )

            return nodes

        except Exception as e:
            logger.error(f"Failed to process document {file_path}: {e}")
            raise

    def process_directory(
        self,
        directory_path: Path,
        source_type: str = "manual",
    ) -> List[TextNode]:
        """
        Process all supported documents in a directory.

        Args:
            directory_path: Path to the directory containing documents.
            source_type: Source of the documents ('manual' or 'email').

        Returns:
            List of all TextNode objects from all documents.
        """
        logger.info(f"Processing directory: {directory_path}")

        all_nodes = []
        supported_extensions = {".pdf", ".docx", ".txt", ".csv"}

        for file_path in directory_path.rglob("*"):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                try:
                    nodes = self.process_document(file_path, source_type=source_type)
                    all_nodes.extend(nodes)
                except Exception as e:
                    logger.error(f"Skipping {file_path} due to error: {e}")
                    continue

        logger.info(
            f"Processed {len(all_nodes)} chunks from directory {directory_path}"
        )

        return all_nodes
