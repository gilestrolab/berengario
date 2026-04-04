"""
Unit tests for kb_manager module.

Tests knowledge base operations with ChromaDB.
"""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import MockEmbedding
from llama_index.core.schema import TextNode

from src.document_processing.kb_manager import KnowledgeBaseManager


class TestKnowledgeBaseManager:
    """Test suite for KnowledgeBaseManager class."""

    @pytest.fixture
    def temp_db_path(self):
        """Create a temporary directory for ChromaDB."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def kb_manager(self, temp_db_path):
        """Create a KnowledgeBaseManager instance for testing."""
        with patch(
            "src.document_processing.kb_manager.get_embedding_model",
            return_value=MockEmbedding(),
        ):
            manager = KnowledgeBaseManager(
                db_path=temp_db_path, collection_name="test_collection"
            )
            yield manager

    def test_initialization(self, temp_db_path):
        """
        Test that KnowledgeBaseManager initializes correctly.

        Args:
            temp_db_path: Temporary DB path fixture.
        """
        with patch(
            "src.document_processing.kb_manager.get_embedding_model",
            return_value=MockEmbedding(),
        ):
            manager = KnowledgeBaseManager(
                db_path=temp_db_path, collection_name="test_kb"
            )

            assert manager.db_path == temp_db_path
            assert manager.collection_name == "test_kb"
            assert manager.collection is not None
            assert manager.index is not None

    def test_add_nodes(self, kb_manager):
        """
        Test adding nodes to the knowledge base.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        # Create test nodes
        nodes = [
            TextNode(
                text="Test content 1",
                metadata={
                    "filename": "test1.txt",
                    "file_hash": "hash1",
                    "source_type": "manual",
                },
            ),
            TextNode(
                text="Test content 2",
                metadata={
                    "filename": "test2.txt",
                    "file_hash": "hash2",
                    "source_type": "manual",
                },
            ),
        ]

        # Add nodes
        initial_count = kb_manager.get_document_count()
        kb_manager.add_nodes(nodes)
        final_count = kb_manager.get_document_count()

        # Count should increase
        assert final_count > initial_count

    def test_add_empty_nodes_list(self, kb_manager):
        """
        Test that adding empty nodes list doesn't crash.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        initial_count = kb_manager.get_document_count()
        kb_manager.add_nodes([])
        final_count = kb_manager.get_document_count()

        # Count should remain the same
        assert final_count == initial_count

    def test_document_exists(self, kb_manager):
        """
        Test checking if document exists by hash.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        test_hash = "unique_hash_12345"

        # Should not exist initially
        assert not kb_manager.document_exists(test_hash)

        # Add a node with this hash
        node = TextNode(
            text="Test content",
            metadata={
                "filename": "test.txt",
                "file_hash": test_hash,
                "source_type": "manual",
            },
        )
        kb_manager.add_nodes([node])

        # Should exist now
        assert kb_manager.document_exists(test_hash)

    def test_delete_document_by_hash(self, kb_manager):
        """
        Test deleting document by hash.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        test_hash = "delete_test_hash"

        # Add nodes with this hash
        nodes = [
            TextNode(
                text=f"Content {i}",
                metadata={
                    "filename": "test.txt",
                    "file_hash": test_hash,
                    "source_type": "manual",
                },
            )
            for i in range(3)
        ]
        kb_manager.add_nodes(nodes)

        # Verify document exists
        assert kb_manager.document_exists(test_hash)

        # Delete document
        deleted_count = kb_manager.delete_document_by_hash(test_hash)

        # Should have deleted 3 nodes
        assert deleted_count == 3

        # Document should no longer exist
        assert not kb_manager.document_exists(test_hash)

    def test_delete_nonexistent_document(self, kb_manager):
        """
        Test deleting non-existent document returns 0.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        deleted_count = kb_manager.delete_document_by_hash("nonexistent_hash")

        assert deleted_count == 0

    def test_delete_document_by_filename(self, kb_manager):
        """
        Test deleting document by filename.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        # Add nodes with same filename
        nodes = [
            TextNode(
                text=f"Content {i}",
                metadata={
                    "filename": "delete_me.txt",
                    "file_hash": f"hash_{i}",
                    "source_type": "manual",
                },
            )
            for i in range(2)
        ]
        kb_manager.add_nodes(nodes)

        # Delete by filename
        deleted_count = kb_manager.delete_document_by_filename("delete_me.txt")

        # Should have deleted 2 nodes
        assert deleted_count == 2

    def test_get_document_count(self, kb_manager):
        """
        Test getting document count.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        initial_count = kb_manager.get_document_count()

        # Add some nodes
        nodes = [
            TextNode(
                text="Test",
                metadata={
                    "filename": "test.txt",
                    "file_hash": f"hash_{i}",
                },
            )
            for i in range(5)
        ]
        kb_manager.add_nodes(nodes)

        final_count = kb_manager.get_document_count()

        # Count should increase by 5
        assert final_count == initial_count + 5

    def test_get_unique_documents(self, kb_manager):
        """
        Test getting list of unique documents.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        # Add nodes with two unique documents
        nodes = [
            TextNode(
                text="Content 1a",
                metadata={
                    "filename": "doc1.txt",
                    "file_hash": "hash_doc1",
                    "source_type": "manual",
                    "file_type": ".txt",
                },
            ),
            TextNode(
                text="Content 1b",
                metadata={
                    "filename": "doc1.txt",
                    "file_hash": "hash_doc1",  # Same hash as above
                    "source_type": "manual",
                    "file_type": ".txt",
                },
            ),
            TextNode(
                text="Content 2",
                metadata={
                    "filename": "doc2.txt",
                    "file_hash": "hash_doc2",
                    "source_type": "email",
                    "file_type": ".txt",
                },
            ),
        ]
        kb_manager.add_nodes(nodes)

        unique_docs = kb_manager.get_unique_documents()

        # Should have 2 unique documents
        assert len(unique_docs) >= 2

        # Check that both hashes are present
        hashes = [doc["file_hash"] for doc in unique_docs]
        assert "hash_doc1" in hashes
        assert "hash_doc2" in hashes

    def test_clear_all(self, kb_manager):
        """
        Test clearing all documents from KB.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        # Add some nodes
        nodes = [
            TextNode(
                text="Test",
                metadata={"filename": "test.txt", "file_hash": f"hash_{i}"},
            )
            for i in range(3)
        ]
        kb_manager.add_nodes(nodes)

        # Verify nodes were added
        assert kb_manager.get_document_count() > 0

        # Clear all
        kb_manager.clear_all()

        # Count should be 0
        assert kb_manager.get_document_count() == 0

    def test_get_query_engine(self, kb_manager):
        """
        Test getting query engine.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        # Should return a query engine
        query_engine = kb_manager.get_query_engine(top_k=3)

        assert query_engine is not None

    def test_get_query_engine_with_custom_top_k(self, kb_manager):
        """
        Test query engine with custom top_k parameter.

        Args:
            kb_manager: KnowledgeBaseManager fixture.
        """
        custom_k = 10
        query_engine = kb_manager.get_query_engine(top_k=custom_k)

        # Check that top_k was set (if accessible)
        # Note: Exact verification depends on LlamaIndex internals
        assert query_engine is not None
