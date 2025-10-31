"""
Bulk ingestion script to re-process documents from the documents folder.

This script processes all documents in data/documents/ and adds them to the
knowledge base with the current embedding configuration.
"""

import logging
from pathlib import Path

from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Process all documents in the documents folder."""
    documents_path = Path(settings.documents_path)

    if not documents_path.exists():
        logger.error(f"Documents path does not exist: {documents_path}")
        return

    # Get all files
    files = list(documents_path.glob('*'))
    files = [f for f in files if f.is_file() and not f.name.startswith('.')]

    if not files:
        logger.warning(f"No documents found in {documents_path}")
        return

    logger.info(f"Found {len(files)} documents to process")
    logger.info(f"Embedding model: {settings.openai_embedding_model}")
    logger.info(f"Chunk size: {settings.chunk_size}, overlap: {settings.chunk_overlap}")

    # Initialize processors
    doc_processor = DocumentProcessor(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap
    )
    kb_manager = KnowledgeBaseManager()

    # Process each document
    total_chunks = 0
    successful = 0
    failed = 0

    for i, file_path in enumerate(files, 1):
        logger.info(f"\n[{i}/{len(files)}] Processing: {file_path.name}")

        try:
            # Check if already exists
            file_hash = doc_processor.compute_file_hash(file_path)
            if kb_manager.document_exists(file_hash):
                logger.info(f"  ✓ Document already in KB, skipping: {file_path.name}")
                successful += 1
                continue

            # Process document
            nodes = doc_processor.process_document(
                file_path=file_path,
                source_type="manual"
            )

            if not nodes:
                logger.warning(f"  ⚠ No chunks created for {file_path.name}")
                failed += 1
                continue

            # Add to knowledge base
            kb_manager.add_nodes(nodes)
            total_chunks += len(nodes)
            successful += 1

            logger.info(f"  ✓ Added {len(nodes)} chunks to KB")

        except Exception as e:
            logger.error(f"  ✗ Failed to process {file_path.name}: {e}")
            failed += 1

    # Summary
    logger.info("\n" + "="*60)
    logger.info("INGESTION COMPLETE")
    logger.info("="*60)
    logger.info(f"Total documents: {len(files)}")
    logger.info(f"Successful: {successful}")
    logger.info(f"Failed: {failed}")
    logger.info(f"Total chunks added: {total_chunks}")
    logger.info(f"KB now has {kb_manager.get_document_count()} total chunks")
    logger.info("="*60)


if __name__ == "__main__":
    main()
