"""
Knowledge Base CLI commands.

Manages documents in the RAGInbox knowledge base (ChromaDB).
"""

import logging

import typer

from src.cli.utils import (
    confirm_destructive,
    console,
    create_progress,
    create_table,
    format_bytes,
    format_count,
    handle_error,
    print_error,
    print_header,
    print_info,
    print_key_value,
    print_success,
    print_warning,
)
from src.config import settings
from src.document_processing.document_processor import DocumentProcessor
from src.document_processing.kb_manager import KnowledgeBaseManager

# Initialize KB manager instance
kb_manager = KnowledgeBaseManager()

# Setup logging
logger = logging.getLogger(__name__)

# Create Typer app for KB commands
app = typer.Typer(help="Knowledge Base operations")


@app.command("list")
def list_documents():
    """
    List all documents in the knowledge base.

    Displays a table with filename, hash, chunks, source type, and file type.
    """
    try:
        print_header("Knowledge Base Documents")

        # Get documents from KB
        documents = kb_manager.get_unique_documents()

        if not documents:
            print_info("No documents found in knowledge base")
            return

        # Create table
        table = create_table(
            f"Documents ({len(documents)} total)",
            ["Filename", "Hash (short)", "Chunks", "Source", "Type"],
        )

        # Add rows
        for doc in documents:
            filename = doc.get("filename", "Unknown")
            file_hash = doc.get("file_hash", "")
            chunks = str(doc.get("chunks", "?"))
            source_type = doc.get("source_type", "unknown")
            file_type = doc.get("file_type", "?")

            # Shorten hash for display
            short_hash = file_hash[:12] + "..." if len(file_hash) > 12 else file_hash

            table.add_row(filename, short_hash, chunks, source_type, file_type)

        console.print(table)
        print_success(f"Listed {format_count(len(documents), 'document')}")

    except Exception as e:
        handle_error(e, "listing documents")


@app.command("stats")
def show_stats():
    """
    Show knowledge base statistics.

    Displays total documents, chunks, and other metadata.
    """
    try:
        print_header("Knowledge Base Statistics")

        # Get documents
        documents = kb_manager.get_unique_documents()
        total_docs = len(documents)

        # Count by source type
        by_source = {}
        by_type = {}
        total_chunks = 0

        for doc in documents:
            source = doc.get("source_type", "unknown")
            file_type = doc.get("file_type", "unknown")
            chunks = doc.get("chunks", 0)

            by_source[source] = by_source.get(source, 0) + 1
            by_type[file_type] = by_type.get(file_type, 0) + 1
            total_chunks += chunks

        # Display stats
        print_key_value("Total Documents", str(total_docs))
        print_key_value("Total Chunks", str(total_chunks))

        if total_docs > 0:
            avg_chunks = total_chunks / total_docs
            print_key_value("Avg Chunks/Doc", f"{avg_chunks:.1f}")

        console.print()
        console.print("  [bold cyan]By Source Type:[/bold cyan]")
        for source, count in sorted(by_source.items()):
            print_key_value(f"  {source}", str(count), key_width=15)

        console.print()
        console.print("  [bold cyan]By File Type:[/bold cyan]")
        for ftype, count in sorted(by_type.items()):
            print_key_value(f"  {ftype}", str(count), key_width=15)

        # KB storage info
        kb_path = settings.chroma_db_path
        if kb_path.exists():
            # Calculate directory size
            total_size = sum(
                f.stat().st_size for f in kb_path.rglob("*") if f.is_file()
            )
            console.print()
            print_key_value("Storage Path", str(kb_path))
            print_key_value("Storage Size", format_bytes(total_size))

        print_success("Statistics displayed successfully")

    except Exception as e:
        handle_error(e, "getting statistics")


@app.command("reingest")
def reingest_documents():
    """
    Reingest all documents from data/documents/ directory.

    Processes all supported files (PDF, DOCX, TXT, CSV) and adds them to the KB.
    Shows progress with a progress bar.
    """
    try:
        print_header("Reingesting Documents")

        # Get documents directory
        documents_path = settings.documents_path

        if not documents_path.exists():
            print_error(f"Documents directory not found: {documents_path}")
            raise typer.Exit(1)

        # Find all supported files
        supported_extensions = {".pdf", ".docx", ".txt", ".csv"}
        files = [
            f
            for f in documents_path.rglob("*")
            if f.is_file() and f.suffix.lower() in supported_extensions
        ]

        if not files:
            print_warning("No supported documents found in documents directory")
            return

        print_info(f"Found {format_count(len(files), 'document')} to process")
        console.print()

        # Initialize processor
        processor = DocumentProcessor()

        # Process files with progress bar
        success_count = 0
        error_count = 0
        total_chunks = 0

        with create_progress() as progress:
            task = progress.add_task(
                f"Processing {len(files)} documents...", total=len(files)
            )

            for file_path in files:
                try:
                    # Process document
                    nodes = processor.process_document(
                        file_path,
                        source_type="file",
                    )

                    # Add to KB
                    if nodes:
                        kb_manager.add_nodes(nodes)
                        success_count += 1
                        total_chunks += len(nodes)
                        logger.info(f"Processed {file_path.name}: {len(nodes)} chunks")
                    else:
                        logger.warning(f"No chunks extracted from {file_path.name}")
                        error_count += 1

                except Exception as e:
                    logger.error(f"Error processing {file_path.name}: {e}")
                    error_count += 1

                progress.update(task, advance=1)

        # Summary
        console.print()
        print_success("Reingest complete!")
        print_key_value("Successful", str(success_count))
        print_key_value("Errors", str(error_count))
        print_key_value("Total Chunks", str(total_chunks))

    except Exception as e:
        handle_error(e, "reingesting documents")


@app.command("delete")
def delete_document(
    hash: str = typer.Argument(..., help="File hash (SHA-256) of document to delete"),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Delete a document from the knowledge base by its hash.

    Use 'kb list' to find document hashes.
    """
    try:
        # Get document info first
        documents = kb_manager.get_unique_documents()
        doc = next(
            (d for d in documents if d.get("file_hash", "").startswith(hash)), None
        )

        if not doc:
            print_error(f"Document not found with hash: {hash}")
            raise typer.Exit(1)

        filename = doc.get("filename", "Unknown")
        full_hash = doc.get("file_hash", hash)

        # Confirm deletion
        if not force:
            if not confirm_destructive("delete", f"'{filename}'"):
                return

        # Delete from KB
        chunks_removed = kb_manager.delete_document_by_hash(full_hash)

        print_success(f"Deleted '{filename}' ({chunks_removed} chunks removed)")

    except Exception as e:
        handle_error(e, "deleting document")


@app.command("clear")
def clear_knowledge_base(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Clear the entire knowledge base.

    WARNING: This will delete ALL documents and cannot be undone!
    """
    try:
        # Get current stats
        documents = kb_manager.get_unique_documents()
        doc_count = len(documents)

        if doc_count == 0:
            print_info("Knowledge base is already empty")
            return

        # Confirm deletion
        if not force:
            print_warning(
                f"This will delete ALL {doc_count} documents from the knowledge base!"
            )
            if not confirm_destructive("clear", "the entire knowledge base"):
                return

        # Clear KB
        kb_manager.clear()

        print_success(f"Knowledge base cleared ({doc_count} documents removed)")

    except Exception as e:
        handle_error(e, "clearing knowledge base")


@app.command("regenerate-descriptions")
def regenerate_descriptions(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt"),
):
    """
    Regenerate AI descriptions for all documents in the knowledge base.

    Uses LLM to create fresh 2-sentence summaries for each document.
    """
    try:
        from src.document_processing.description_generator import DescriptionGenerator

        print_header("Regenerate Document Descriptions")

        # Get all unique documents
        documents = kb_manager.get_unique_documents()

        if not documents:
            print_info("No documents found in knowledge base")
            return

        # Confirm operation
        if not force:
            console.print()
            print_warning(
                f"This will regenerate descriptions for {len(documents)} documents using LLM."
            )
            print_warning("This may take several minutes and will incur LLM API costs.")
            console.print()
            if not confirm_destructive(
                "regenerate descriptions for", f"{len(documents)} documents"
            ):
                return

        # Initialize description generator
        desc_gen = DescriptionGenerator()

        # Regenerate descriptions
        success_count = 0
        error_count = 0

        console.print()
        with create_progress() as progress:
            task = progress.add_task(
                f"Regenerating descriptions for {len(documents)} documents...",
                total=len(documents),
            )

            for doc in documents:
                filename = doc.get("filename", "Unknown")
                file_hash = doc.get("file_hash")

                try:
                    # Get chunks for this document
                    chunks = kb_manager.get_document_chunks(file_hash)

                    if not chunks:
                        logger.warning(f"No chunks found for {filename}")
                        error_count += 1
                        progress.update(task, advance=1)
                        continue

                    # Generate new description
                    description = desc_gen.generate_description(chunks)

                    # Get file info from metadata
                    metadata = chunks[0].metadata if chunks else {}
                    file_path = metadata.get("file_path", filename)
                    file_size = metadata.get("file_size")
                    file_type = doc.get("file_type")

                    # Save description
                    desc_gen.save_description(
                        file_path=file_path,
                        filename=filename,
                        description=description,
                        chunk_count=len(chunks),
                        file_size=file_size,
                        file_type=file_type,
                    )

                    success_count += 1
                    logger.info(f"Regenerated description for {filename}")

                except Exception as e:
                    logger.error(f"Error regenerating description for {filename}: {e}")
                    error_count += 1

                progress.update(task, advance=1)

        # Summary
        console.print()
        print_success("Description regeneration complete!")
        print_key_value("Successful", str(success_count))
        print_key_value("Errors", str(error_count))

    except Exception as e:
        handle_error(e, "regenerating descriptions")


@app.command("query")
def query_kb(
    query: str = typer.Argument(..., help="Question to ask the knowledge base"),
    show_sources: bool = typer.Option(
        True, "--sources/--no-sources", help="Show source documents"
    ),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of sources to retrieve"),
):
    """
    Query the knowledge base with a question.

    Example:
        raginbox-cli kb query "When is the FYP examination week?"
    """
    try:
        from src.rag.query_handler import QueryHandler

        print_header("Knowledge Base Query")
        console.print(f"[bold]Question:[/bold] {query}")
        console.print()

        # Create query handler
        handler = QueryHandler()

        # Process query
        with console.status("[bold cyan]Searching knowledge base...", spinner="dots"):
            result = handler.process_query(
                query_text=query, user_email="cli@localhost", context={"top_k": top_k}
            )

        if not result["success"]:
            print_error(f"Query failed: {result.get('error', 'Unknown error')}")
            raise typer.Exit(1)

        # Display response
        console.print()
        console.print("[bold cyan]Response:[/bold cyan]")
        console.print()
        console.print(result["response"])
        console.print()

        # Display sources if requested
        if show_sources and result.get("sources"):
            console.print("[bold cyan]Sources:[/bold cyan]")
            console.print()

            for i, source in enumerate(result["sources"], 1):
                filename = source.get("filename", "Unknown")
                score = source.get("score", 0)

                console.print(f"[bold]{i}. {filename}[/bold] (relevance: {score:.3f})")

                # Show metadata if available
                metadata = source.get("metadata", {})
                if metadata:
                    if metadata.get("sender"):
                        console.print(f"   From: {metadata['sender']}")
                    if metadata.get("subject"):
                        console.print(f"   Subject: {metadata['subject']}")
                    if metadata.get("date"):
                        console.print(f"   Date: {metadata['date']}")

                # Show text excerpt
                text = source.get("content", "")
                if text:
                    # Truncate long excerpts
                    excerpt = text[:300] + "..." if len(text) > 300 else text
                    console.print(f"   [dim]{excerpt}[/dim]")

                console.print()

        print_success("Query complete")

    except Exception as e:
        handle_error(e, "querying knowledge base")
