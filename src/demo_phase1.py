#!/usr/bin/env python3
"""
RAGInbox - Main CLI interface.

This script provides the command-line interface for RAGInbox functionality:
1. Document processing from the Documents folder
2. Adding documents to the knowledge base
3. Querying the knowledge base
4. File watching for automatic updates

Usage:
    raginbox --mode process
    raginbox --mode query --query "Your question"
    raginbox --mode watch
"""

import argparse
import logging

from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.file_watcher import FileWatcher
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.rag.query_handler import QueryHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def initialize_kb() -> tuple[DocumentProcessor, KnowledgeBaseManager]:
    """
    Initialize document processor and knowledge base manager.

    Returns:
        Tuple of (DocumentProcessor, KnowledgeBaseManager).
    """
    logger.info("Initializing document processor and knowledge base...")

    processor = DocumentProcessor()
    kb_manager = KnowledgeBaseManager()

    logger.info(
        f"Knowledge base initialized with {kb_manager.get_document_count()} chunks"
    )

    return processor, kb_manager


def process_documents(
    processor: DocumentProcessor, kb_manager: KnowledgeBaseManager
) -> None:
    """
    Process all documents in the Documents folder.

    Args:
        processor: Document processor instance.
        kb_manager: Knowledge base manager instance.
    """
    logger.info(f"Processing documents from {settings.documents_path}")

    # Get all existing hashes
    existing_docs = kb_manager.get_unique_documents()
    existing_hashes = {doc["file_hash"] for doc in existing_docs}

    # Process directory
    all_nodes = processor.process_directory(settings.documents_path)

    # Filter out already processed documents
    new_nodes = [
        node
        for node in all_nodes
        if node.metadata.get("file_hash") not in existing_hashes
    ]

    if new_nodes:
        logger.info(f"Adding {len(new_nodes)} new chunks to knowledge base...")
        kb_manager.add_nodes(new_nodes)

        # Get unique filenames
        unique_files = set(node.metadata["filename"] for node in new_nodes)
        logger.info(f"Successfully added {len(unique_files)} new documents")
    else:
        logger.info("No new documents to add (all already in KB)")

    # Print stats
    total_chunks = kb_manager.get_document_count()
    unique_docs = kb_manager.get_unique_documents()

    logger.info("\nKnowledge Base Stats:")
    logger.info(f"  Total chunks: {total_chunks}")
    logger.info(f"  Unique documents: {len(unique_docs)}")

    if unique_docs:
        logger.info("\nDocuments in KB:")
        for doc in unique_docs:
            logger.info(
                f"  - {doc['filename']} ({doc['source_type']}, {doc['file_type']})"
            )


def query_kb(query_handler: QueryHandler, query_text: str) -> None:
    """
    Query the knowledge base.

    Args:
        query_handler: Query handler instance.
        query_text: The query string.
    """
    logger.info(f"\nProcessing query: {query_text}")

    result = query_handler.process_query(query_text)

    if result["success"]:
        logger.info(f"\nResponse:\n{result['response']}\n")

        if result["sources"]:
            logger.info(f"Sources ({len(result['sources'])}):")
            for i, source in enumerate(result["sources"], 1):
                logger.info(
                    f"  {i}. {source['filename']} " f"(score: {source['score']:.2f})"
                )
    else:
        logger.error(f"Query failed: {result['error']}")


def run_file_watcher(
    processor: DocumentProcessor, kb_manager: KnowledgeBaseManager
) -> None:
    """
    Start the file watcher to monitor for new documents.

    Args:
        processor: Document processor instance.
        kb_manager: Knowledge base manager instance.
    """
    logger.info("Starting file watcher...")
    logger.info(f"Monitoring: {settings.documents_path}")
    logger.info("Press Ctrl+C to stop\n")

    watcher = FileWatcher(
        document_processor=processor,
        kb_manager=kb_manager,
    )

    try:
        watcher.run_forever()
    except KeyboardInterrupt:
        logger.info("\nStopping file watcher...")
        watcher.stop()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="RAGInbox: Email-integrated RAG Knowledge Base System"
    )
    parser.add_argument(
        "--mode",
        choices=["process", "query", "watch"],
        default="process",
        help="Mode: process documents, query KB, or watch for changes",
    )
    parser.add_argument(
        "--query",
        type=str,
        help="Query string (required for query mode)",
    )

    args = parser.parse_args()

    # Initialize components
    processor, kb_manager = initialize_kb()

    if args.mode == "process":
        # Process all documents
        process_documents(processor, kb_manager)

    elif args.mode == "query":
        if not args.query:
            logger.error("Query mode requires --query argument")
            return

        # Initialize query handler
        query_handler = QueryHandler()

        # Process query
        query_kb(query_handler, args.query)

    elif args.mode == "watch":
        # Run file watcher
        run_file_watcher(processor, kb_manager)


if __name__ == "__main__":
    main()
