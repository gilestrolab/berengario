"""
File watcher for monitoring the Documents folder for changes.

Monitors for new, modified, and deleted files and triggers KB updates.
"""

import logging
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from src.config import settings
from src.document_processing.document_processor import (
    SUPPORTED_EXTENSIONS,
    DocumentProcessor,
)
from src.document_processing.kb_manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)


class DocumentEventHandler(FileSystemEventHandler):
    """
    Handles file system events for document files.

    Processes new, modified, and deleted documents.
    """

    def __init__(
        self,
        document_processor: DocumentProcessor,
        kb_manager: KnowledgeBaseManager,
    ):
        """
        Initialize the event handler.

        Args:
            document_processor: Document processor instance.
            kb_manager: Knowledge base manager instance.
        """
        super().__init__()
        self.document_processor = document_processor
        self.kb_manager = kb_manager
        self.supported_extensions = SUPPORTED_EXTENSIONS

    def _is_supported_file(self, path: Path) -> bool:
        """
        Check if file is a supported document type.

        Args:
            path: Path to the file.

        Returns:
            True if file is supported, False otherwise.
        """
        return path.suffix.lower() in self.supported_extensions

    def on_created(self, event: FileSystemEvent) -> None:
        """
        Handle file creation event.

        Args:
            event: File system event object.
        """
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if not self._is_supported_file(file_path):
            return

        logger.info(f"New file detected: {file_path.name}")

        try:
            # Process the document
            nodes = self.document_processor.process_document(
                file_path, source_type="manual"
            )

            if nodes:
                # Add to knowledge base
                self.kb_manager.add_nodes(nodes)
                logger.info(
                    f"Successfully added {file_path.name} to knowledge base "
                    f"({len(nodes)} chunks)"
                )
        except Exception as e:
            logger.error(f"Failed to process new file {file_path.name}: {e}")

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Handle file modification event.

        Args:
            event: File system event object.
        """
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if not self._is_supported_file(file_path):
            return

        logger.info(f"File modified: {file_path.name}")

        try:
            # Compute file hash
            file_hash = self.document_processor.compute_file_hash(file_path)

            # Check if already in KB (same hash = no actual content change)
            if self.kb_manager.document_exists(file_hash):
                logger.info(f"File {file_path.name} hash unchanged, skipping update")
                return

            # Delete old version from KB
            deleted_count = self.kb_manager.delete_document_by_filename(file_path.name)
            if deleted_count > 0:
                logger.info(f"Removed {deleted_count} old chunks for {file_path.name}")

            # Process updated document
            nodes = self.document_processor.process_document(
                file_path, source_type="manual"
            )

            if nodes:
                # Add updated version to knowledge base
                self.kb_manager.add_nodes(nodes)
                logger.info(
                    f"Successfully updated {file_path.name} in knowledge base "
                    f"({len(nodes)} chunks)"
                )
        except Exception as e:
            logger.error(f"Failed to process modified file {file_path.name}: {e}")

    def on_deleted(self, event: FileSystemEvent) -> None:
        """
        Handle file deletion event.

        Args:
            event: File system event object.
        """
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if not self._is_supported_file(file_path):
            return

        logger.info(f"File deleted: {file_path.name}")

        try:
            # Remove from knowledge base
            deleted_count = self.kb_manager.delete_document_by_filename(file_path.name)
            if deleted_count > 0:
                logger.info(
                    f"Removed {file_path.name} from knowledge base "
                    f"({deleted_count} chunks)"
                )
            else:
                logger.warning(f"File {file_path.name} not found in knowledge base")
        except Exception as e:
            logger.error(f"Failed to remove deleted file {file_path.name}: {e}")


class FileWatcher:
    """
    Watches the Documents folder for file system changes.

    Monitors for new, modified, and deleted documents and updates KB accordingly.
    """

    def __init__(
        self,
        watch_path: Optional[Path] = None,
        document_processor: Optional[DocumentProcessor] = None,
        kb_manager: Optional[KnowledgeBaseManager] = None,
    ):
        """
        Initialize the file watcher.

        Args:
            watch_path: Path to watch for changes (default from settings).
            document_processor: Document processor instance.
            kb_manager: Knowledge base manager instance.

        Raises:
            RuntimeError: If multi-tenant mode is enabled.
        """
        if settings.multi_tenant:
            raise RuntimeError(
                "FileWatcher is not supported in multi-tenant mode. "
                "Documents are ingested via email or admin upload."
            )

        self.watch_path = watch_path or settings.documents_path
        self.document_processor = document_processor or DocumentProcessor()
        self.kb_manager = kb_manager or KnowledgeBaseManager()

        # Create event handler
        self.event_handler = DocumentEventHandler(
            document_processor=self.document_processor,
            kb_manager=self.kb_manager,
        )

        # Create observer
        self.observer = Observer()
        self.observer.schedule(
            self.event_handler,
            str(self.watch_path),
            recursive=True,
        )

        logger.info(f"FileWatcher initialized for path: {self.watch_path}")

    def start(self) -> None:
        """
        Start watching for file changes.

        Runs in a background thread.
        """
        logger.info("Starting file watcher...")
        self.observer.start()
        logger.info("File watcher started")

    def stop(self) -> None:
        """
        Stop watching for file changes.

        Waits for observer thread to finish.
        """
        logger.info("Stopping file watcher...")
        self.observer.stop()
        self.observer.join()
        logger.info("File watcher stopped")

    def run_forever(self) -> None:
        """
        Start the watcher and run indefinitely.

        Blocks until interrupted (Ctrl+C).
        """
        self.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def initial_scan(self) -> None:
        """
        Perform initial scan of the watch directory.

        Processes all existing documents that aren't already in KB.
        """
        logger.info(f"Performing initial scan of {self.watch_path}")

        try:
            # Get all nodes from directory
            nodes = self.document_processor.process_directory(
                self.watch_path, source_type="manual"
            )

            # Filter out documents already in KB
            new_nodes = []
            for node in nodes:
                file_hash = node.metadata.get("file_hash")
                if file_hash and not self.kb_manager.document_exists(file_hash):
                    new_nodes.append(node)

            if new_nodes:
                # Add new documents to KB
                self.kb_manager.add_nodes(new_nodes)
                logger.info(
                    f"Initial scan complete: Added {len(new_nodes)} new chunks "
                    f"from {len(set(n.metadata.get('filename') for n in new_nodes))} documents"
                )
            else:
                logger.info("Initial scan complete: No new documents to add")

        except Exception as e:
            logger.error(f"Error during initial scan: {e}")
