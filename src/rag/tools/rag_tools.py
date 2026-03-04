"""
RAG search tools for explicit knowledge base queries.

Makes KB search an explicit tool choice in the ReAct reasoning loop,
allowing the agent to decide WHEN to search the KB vs other actions.
"""

import logging
from typing import Any, Dict

from src.config import settings

from .base import ParameterType, Tool, ToolParameter, register_tool

logger = logging.getLogger(__name__)


def rag_search(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Search the knowledge base for relevant documents.

    Args:
        query: The search query
        top_k: Number of top documents to retrieve (default: 5)

    Returns:
        Dictionary containing:
            - success: Boolean indicating success
            - documents: List of retrieved documents with text, score, filename
            - query: The original query
            - num_results: Number of documents returned
            - error: Error message (if failed)
    """
    try:
        from src.document_processing.kb_manager import KnowledgeBaseManager

        from .context import get_kb_manager

        # Validate parameters
        if not query or not query.strip():
            raise ValueError("Search query cannot be empty")

        if top_k < 1:
            top_k = 5
            logger.warning("Adjusted top_k to 5 (minimum: 1)")

        logger.info(f"Searching knowledge base: '{query}' (top_k={top_k})")

        # Use context KB manager (MT mode) or create default (ST mode)
        kb_manager = get_kb_manager() or KnowledgeBaseManager()

        # Build LLM matching RAGEngine config so LlamaIndex doesn't fall back
        # to its default gpt-3.5-turbo (which may not exist on the API proxy)
        from llama_index.llms.openai import OpenAI as LlamaOpenAI

        llm = LlamaOpenAI(
            model="gpt-4",  # Dummy for validation
            api_key=settings.openrouter_api_key,
            api_base=settings.openrouter_api_base,
            temperature=0.1,
            is_chat_model=True,
            additional_kwargs={"model": settings.openrouter_model},
        )
        query_engine = kb_manager.get_query_engine(top_k=top_k, llm=llm)

        # Execute query
        response = query_engine.query(query)

        # Extract documents from source nodes
        documents = []
        if hasattr(response, "source_nodes"):
            for node in response.source_nodes:
                documents.append(
                    {
                        "text": node.text,
                        "score": getattr(node, "score", 0.0),
                        "filename": node.metadata.get("filename", "unknown"),
                        "page": node.metadata.get("page", None),
                        "chunk_id": node.metadata.get("chunk_id", None),
                    }
                )

        logger.info(f"Knowledge base search returned {len(documents)} documents")

        return {
            "success": True,
            "documents": documents,
            "query": query,
            "num_results": len(documents),
        }

    except Exception as e:
        error_msg = f"Knowledge base search failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "documents": [],
            "query": query,
            "num_results": 0,
        }


# Tool definition
rag_search_tool = Tool(
    name="rag_search",
    description="Search the knowledge base for relevant information. Use this to find information from uploaded documents, policies, procedures, and other stored content. This is the primary tool for answering questions based on organizational knowledge.",
    parameters=[
        ToolParameter(
            name="query",
            type=ParameterType.STRING,
            description="The search query. Be specific and include relevant keywords.",
            required=True,
        ),
        ToolParameter(
            name="top_k",
            type=ParameterType.INTEGER,
            description=f"Number of top documents to retrieve (default: {settings.top_k_retrieval})",
            required=False,
        ),
    ],
    function=rag_search,
    returns_attachment=False,
)

# Register tool
register_tool(rag_search_tool)
