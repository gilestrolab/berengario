"""
Knowledge Base Manager for vector database operations.

Handles ChromaDB storage, retrieval, and updates.
"""

import logging
from pathlib import Path
from typing import List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.schema import TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.chroma import ChromaVectorStore

from src.config import settings

logger = logging.getLogger(__name__)


class KnowledgeBaseManager:
    """
    Manages the knowledge base using ChromaDB as vector store.

    Handles document storage, retrieval, and index management.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        collection_name: str = "dols_kb",
    ):
        """
        Initialize the Knowledge Base Manager.

        Args:
            db_path: Path to ChromaDB storage directory.
            collection_name: Name of the ChromaDB collection.
        """
        self.db_path = db_path or settings.chroma_db_path
        self.collection_name = collection_name

        # Ensure DB directory exists
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize embedding model (uses Naga.ac via OpenAI-compatible API)
        self.embed_model = OpenAIEmbedding(
            model=settings.openai_embedding_model,
            api_key=settings.openai_api_key,
            api_base=settings.openai_api_base,
        )

        # Initialize ChromaDB client
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,
            ),
        )

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name
        )

        # Initialize vector store
        self.vector_store = ChromaVectorStore(chroma_collection=self.collection)

        # Initialize storage context
        self.storage_context = StorageContext.from_defaults(
            vector_store=self.vector_store
        )

        # Initialize or load index
        self._initialize_index()

        logger.info(
            f"KnowledgeBaseManager initialized with {self.get_document_count()} documents"
        )

    def _initialize_index(self) -> None:
        """
        Initialize or load the vector store index.

        Creates a new index if none exists, otherwise loads existing index.
        """
        try:
            # Try to load existing index
            self.index = VectorStoreIndex.from_vector_store(
                vector_store=self.vector_store,
                embed_model=self.embed_model,
            )
            logger.info("Loaded existing vector index")
        except Exception as e:
            # Create new index if loading fails
            logger.info(f"Creating new vector index: {e}")
            self.index = VectorStoreIndex(
                nodes=[],
                storage_context=self.storage_context,
                embed_model=self.embed_model,
            )

    def add_nodes(self, nodes: List[TextNode]) -> None:
        """
        Add text nodes to the knowledge base.

        Args:
            nodes: List of TextNode objects to add.

        Raises:
            Exception: If adding nodes fails.
        """
        if not nodes:
            logger.warning("No nodes to add")
            return

        try:
            # Insert nodes into index
            self.index.insert_nodes(nodes)
            logger.info(f"Added {len(nodes)} nodes to knowledge base")
        except Exception as e:
            logger.error(f"Failed to add nodes to knowledge base: {e}")
            raise

    def document_exists(self, file_hash: str) -> bool:
        """
        Check if a document with given hash already exists in KB.

        Args:
            file_hash: SHA-256 hash of the document file.

        Returns:
            True if document exists, False otherwise.
        """
        try:
            # Query collection for documents with this hash
            results = self.collection.get(where={"file_hash": file_hash})
            return len(results["ids"]) > 0
        except Exception as e:
            logger.error(f"Error checking document existence: {e}")
            return False

    def get_document_content(self, file_hash: str) -> str:
        """
        Get the full text content of a document by reconstructing from chunks.

        Args:
            file_hash: SHA-256 hash of the document.

        Returns:
            Concatenated text from all chunks.

        Raises:
            Exception: If retrieval fails.
        """
        try:
            # Get all chunks with this hash
            results = self.collection.get(
                where={"file_hash": file_hash}, include=["documents", "metadatas"]
            )

            if not results["documents"]:
                logger.warning(f"No content found for hash {file_hash}")
                return ""

            # Concatenate all chunk texts
            # Note: Chunks may have overlap, but this gives the full content
            full_text = "\n\n".join(results["documents"])
            logger.info(
                f"Retrieved {len(results['documents'])} chunks for hash {file_hash}"
            )

            return full_text
        except Exception as e:
            logger.error(f"Failed to get document content: {e}")
            raise

    def get_document_chunks(self, file_hash: str) -> List[TextNode]:
        """
        Get all chunks for a document as TextNode objects.

        Args:
            file_hash: SHA-256 hash of the document.

        Returns:
            List of TextNode objects containing the document chunks.

        Raises:
            Exception: If retrieval fails.
        """
        try:
            # Get all chunks with this hash
            # Note: ids are always returned by default
            results = self.collection.get(
                where={"file_hash": file_hash}, include=["documents", "metadatas"]
            )

            if not results["documents"]:
                logger.warning(f"No chunks found for hash {file_hash}")
                return []

            # Convert to TextNode objects
            chunks = []
            for i, (doc_id, text, metadata) in enumerate(
                zip(results["ids"], results["documents"], results["metadatas"])
            ):
                node = TextNode(id_=doc_id, text=text, metadata=metadata)
                chunks.append(node)

            logger.info(f"Retrieved {len(chunks)} chunks for hash {file_hash}")
            return chunks

        except Exception as e:
            logger.error(f"Failed to get document chunks: {e}")
            raise

    def delete_document_by_hash(self, file_hash: str) -> int:
        """
        Delete all nodes associated with a document hash.

        Args:
            file_hash: SHA-256 hash of the document to delete.

        Returns:
            Number of nodes deleted.

        Raises:
            Exception: If deletion fails.
        """
        try:
            # Get all nodes with this hash
            results = self.collection.get(where={"file_hash": file_hash})
            node_ids = results["ids"]

            if not node_ids:
                logger.info(f"No nodes found for hash {file_hash}")
                return 0

            # Delete nodes
            self.collection.delete(ids=node_ids)
            logger.info(f"Deleted {len(node_ids)} nodes for hash {file_hash}")

            return len(node_ids)
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise

    def get_document_by_filename(self, filename: str) -> Optional[dict]:
        """
        Get document metadata by filename.

        Args:
            filename: Name of the file.

        Returns:
            Dictionary with document metadata (file_hash, file_mtime, etc.)
            or None if document not found.
        """
        try:
            # Get nodes with this filename
            results = self.collection.get(
                where={"filename": filename}, include=["metadatas"], limit=1
            )

            if not results["metadatas"]:
                return None

            # Return first metadata (all chunks have same document metadata)
            return results["metadatas"][0]

        except Exception as e:
            logger.error(f"Error getting document by filename: {e}")
            return None

    def delete_document_by_filename(self, filename: str) -> int:
        """
        Delete all nodes associated with a filename.

        Args:
            filename: Name of the file to delete.

        Returns:
            Number of nodes deleted.

        Raises:
            Exception: If deletion fails.
        """
        try:
            # Get all nodes with this filename
            results = self.collection.get(where={"filename": filename})
            node_ids = results["ids"]

            if not node_ids:
                logger.info(f"No nodes found for filename {filename}")
                return 0

            # Delete nodes
            self.collection.delete(ids=node_ids)
            logger.info(f"Deleted {len(node_ids)} nodes for filename {filename}")

            return len(node_ids)
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise

    def get_document_by_url_hash(self, url_hash: str) -> Optional[dict]:
        """
        Get web document metadata by URL hash.

        Args:
            url_hash: SHA-256 hash of the normalized URL.

        Returns:
            Dictionary with document metadata (url_hash, source_url, last_crawled, etc.)
            or None if document not found.
        """
        try:
            # Get nodes with this url_hash
            results = self.collection.get(
                where={"url_hash": url_hash}, include=["metadatas"], limit=1
            )

            if not results["metadatas"]:
                return None

            # Return first metadata (all chunks have same document metadata)
            return results["metadatas"][0]

        except Exception as e:
            logger.error(f"Error getting document by url_hash: {e}")
            return None

    def get_crawled_urls(self) -> List[dict]:
        """
        Get list of all crawled web URLs in the knowledge base.

        Returns:
            List of dictionaries containing web document metadata:
            - source_url: Original URL
            - url_hash: SHA-256 hash of normalized URL
            - content_hash: SHA-256 hash of content
            - last_crawled: Unix timestamp of last crawl
            - crawl_depth: Depth at which URL was crawled
        """
        try:
            # Check if collection is empty first
            if self.collection.count() == 0:
                logger.info("Collection is empty, no crawled URLs")
                return []

            # Get all documents with source_type="web"
            results = self.collection.get(
                where={"source_type": "web"}, include=["metadatas"]
            )

            # Handle None or empty results
            if not results or not results.get("metadatas"):
                logger.info("No documents with source_type='web' found")
                return []

            # Extract unique URLs by url_hash
            unique_urls = {}
            for metadata in results["metadatas"]:
                if not metadata:  # Skip None metadata
                    continue

                url_hash = metadata.get("url_hash")
                if url_hash and url_hash not in unique_urls:
                    unique_urls[url_hash] = {
                        "source_url": metadata.get("source_url"),
                        "url_hash": url_hash,
                        "content_hash": metadata.get("content_hash"),
                        "last_crawled": metadata.get("last_crawled"),
                        "crawl_depth": metadata.get("crawl_depth"),
                    }

            # Sort by last_crawled (most recent first)
            url_list = list(unique_urls.values())
            url_list.sort(key=lambda x: x.get("last_crawled", 0), reverse=True)

            logger.info(f"Found {len(url_list)} unique crawled URLs")
            return url_list

        except Exception as e:
            logger.error(f"Error getting crawled URLs: {e}", exc_info=True)
            return []

    def delete_document_by_url_hash(self, url_hash: str) -> int:
        """
        Delete all nodes associated with a URL hash.

        Args:
            url_hash: SHA-256 hash of the normalized URL to delete.

        Returns:
            Number of nodes deleted.

        Raises:
            Exception: If deletion fails.
        """
        try:
            # Get all nodes with this url_hash
            results = self.collection.get(where={"url_hash": url_hash})
            node_ids = results["ids"]

            if not node_ids:
                logger.info(f"No nodes found for url_hash {url_hash}")
                return 0

            # Delete nodes
            self.collection.delete(ids=node_ids)
            logger.info(f"Deleted {len(node_ids)} nodes for url_hash {url_hash}")

            return len(node_ids)
        except Exception as e:
            logger.error(f"Failed to delete web document: {e}")
            raise

    def get_document_count(self) -> int:
        """
        Get the total number of nodes in the knowledge base.

        Returns:
            Number of nodes stored.
        """
        try:
            return self.collection.count()
        except Exception as e:
            logger.error(f"Error getting document count: {e}")
            return 0

    def get_unique_documents(self) -> List[dict]:
        """
        Get list of unique documents in the knowledge base.

        Returns:
            List of dictionaries containing document metadata.
        """
        try:
            # Get all documents
            results = self.collection.get(include=["metadatas"])

            # Extract unique documents by file_hash
            unique_docs = {}
            for metadata in results["metadatas"]:
                file_hash = metadata.get("file_hash")
                if file_hash and file_hash not in unique_docs:
                    unique_docs[file_hash] = {
                        "filename": metadata.get("filename"),
                        "file_hash": file_hash,
                        "source_type": metadata.get("source_type"),
                        "file_type": metadata.get("file_type"),
                        # Include email metadata if available
                        "sender": metadata.get("sender"),
                        "subject": metadata.get("subject"),
                        "date": metadata.get("date"),
                    }

            return list(unique_docs.values())
        except Exception as e:
            logger.error(f"Error getting unique documents: {e}")
            return []

    def clear_all(self) -> None:
        """
        Clear all documents from the knowledge base.

        WARNING: This operation is irreversible.

        Raises:
            Exception: If clearing fails.
        """
        try:
            # Delete the collection
            self.chroma_client.delete_collection(name=self.collection_name)

            # Recreate the collection
            self.collection = self.chroma_client.create_collection(
                name=self.collection_name
            )

            # Reinitialize vector store and index
            self.vector_store = ChromaVectorStore(chroma_collection=self.collection)
            self.storage_context = StorageContext.from_defaults(
                vector_store=self.vector_store
            )
            self._initialize_index()

            logger.info("Cleared all documents from knowledge base")
        except Exception as e:
            logger.error(f"Failed to clear knowledge base: {e}")
            raise

    def get_query_engine(self, top_k: Optional[int] = None, llm=None):
        """
        Get a query engine for the knowledge base.

        Args:
            top_k: Number of top results to retrieve (default from settings).
            llm: LLM to use for query engine (optional).

        Returns:
            LlamaIndex query engine.
        """
        k = top_k or settings.top_k_retrieval

        query_engine = self.index.as_query_engine(
            similarity_top_k=k,
            embed_model=self.embed_model,
            llm=llm,
        )

        return query_engine
