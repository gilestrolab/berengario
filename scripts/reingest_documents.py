#!/usr/bin/env python3
"""
Reingest all documents from data/documents into ChromaDB.
Run this inside the Docker container.
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import after logging setup
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.document_processing.document_processor import DocumentProcessor

def main():
    """Process all documents from data/documents directory."""

    logger.info("="*60)
    logger.info("Berengario Knowledge Base Reingestion")
    logger.info("="*60)

    # Initialize components
    kb_manager = KnowledgeBaseManager()
    doc_processor = DocumentProcessor()

    # Find all documents
    docs_path = Path('data/documents')
    if not docs_path.exists():
        logger.error(f"Documents directory not found: {docs_path}")
        sys.exit(1)

    # Supported file types
    extensions = ['*.pdf', '*.docx', '*.txt', '*.csv']
    all_files = []
    for ext in extensions:
        all_files.extend(docs_path.glob(ext))

    # Filter out directories and sort
    all_files = sorted([f for f in all_files if f.is_file()])

    logger.info(f"Found {len(all_files)} documents to process")
    logger.info("")

    # Process each document
    total_chunks = 0
    successful = 0
    failed = 0

    for file_path in all_files:
        logger.info(f"Processing: {file_path.name}")

        try:
            # Process file to get chunks
            chunks = doc_processor.process_file(str(file_path))

            if chunks:
                # Add to knowledge base
                kb_manager.add_document(str(file_path), chunks)
                total_chunks += len(chunks)
                successful += 1
                logger.info(f"  ✓ Added {len(chunks)} chunks")
            else:
                logger.warning(f"  ⚠ No chunks extracted")
                failed += 1

        except Exception as e:
            logger.error(f"  ✗ Error processing {file_path.name}: {e}")
            failed += 1

    logger.info("")
    logger.info("="*60)
    logger.info("Reingestion Complete")
    logger.info("="*60)
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total documents: {len(all_files)}")
    logger.info(f"Total chunks: {total_chunks}")
    logger.info("="*60)

    # Verify KB state
    kb_docs = kb_manager.get_all_documents()
    logger.info(f"Knowledge base now contains {len(kb_docs)} documents")

if __name__ == "__main__":
    main()
