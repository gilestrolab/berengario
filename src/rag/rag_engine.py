"""
RAG (Retrieval-Augmented Generation) engine for query processing.

Handles query execution, context retrieval, and response generation.
"""

import logging
from typing import Dict, List, Optional

from llama_index.core import PromptTemplate
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.llms.openai import OpenAI

from src.config import settings
from src.document_processing.kb_manager import KnowledgeBaseManager

logger = logging.getLogger(__name__)


def get_system_prompt(instance_name: str, instance_description: str, organization: str = "") -> str:
    """
    Generate system prompt based on instance configuration.

    Args:
        instance_name: Name of the instance.
        instance_description: Description of the instance's purpose.
        organization: Organization name (optional).

    Returns:
        Formatted system prompt.
    """
    org_text = f" at {organization}" if organization else ""

    return f"""You are {instance_name}, {instance_description}{org_text}.

Your role is to help users by answering questions based on the knowledge base documentation.

Guidelines:
1. Provide accurate, helpful answers based on the provided context
2. If the context doesn't contain enough information, acknowledge this clearly
3. Cite specific sources when providing information
4. Be professional and concise
5. Reference relevant documents or policies when answering
6. If uncertain, acknowledge the limitation

Context information is provided below:
---------------------
{{context_str}}
---------------------

Based on the context above, please answer the following query:
Query: {{query_str}}

Answer:"""


class RAGEngine:
    """
    RAG engine for processing queries using the knowledge base.

    Retrieves relevant context and generates responses using LLM.
    """

    def __init__(
        self,
        kb_manager: Optional[KnowledgeBaseManager] = None,
        llm_model: Optional[str] = None,
    ):
        """
        Initialize the RAG engine.

        Args:
            kb_manager: Knowledge base manager instance.
            llm_model: LLM model name (default from settings).
        """
        self.kb_manager = kb_manager or KnowledgeBaseManager()
        self.llm_model = llm_model or settings.openrouter_model

        # Initialize LLM (uses Naga.ac with non-OpenAI models)
        # Provide context_window to bypass OpenAI model validation
        self.llm = OpenAI(
            model=self.llm_model,
            api_key=settings.openrouter_api_key,
            api_base=settings.openrouter_api_base,
            temperature=0.1,  # Low temperature for factual responses
            context_window=200000,  # Claude 3.5 Sonnet context window
            max_tokens=4096,
            is_chat_model=True,
            default_headers={"HTTP-Referer": "https://github.com/imperial-dols/dols-gpt"},
        )

        # Create custom prompt template based on instance configuration
        system_prompt = get_system_prompt(
            settings.instance_name,
            settings.instance_description,
            settings.organization,
        )
        self.prompt_template = PromptTemplate(system_prompt)

        # Get query engine from KB manager (pass our LLM)
        self.query_engine = self.kb_manager.get_query_engine(
            top_k=settings.top_k_retrieval, llm=self.llm
        )

        # Update query engine with custom prompt
        self.query_engine.update_prompts(
            {"response_synthesizer:text_qa_template": self.prompt_template}
        )

        logger.info(f"RAGEngine initialized with model {self.llm_model}")

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
    ) -> Dict[str, any]:
        """
        Execute a query against the knowledge base.

        Args:
            query_text: The query string.
            top_k: Number of top results to retrieve (overrides default).

        Returns:
            Dictionary containing:
                - response: Generated response text
                - sources: List of source documents
                - metadata: Additional metadata

        Raises:
            Exception: If query execution fails.
        """
        if not query_text.strip():
            raise ValueError("Query text cannot be empty")

        logger.info(f"Processing query: {query_text[:100]}...")

        try:
            # Update top_k if provided
            if top_k:
                self.query_engine.retriever.similarity_top_k = top_k

            # Execute query
            response = self.query_engine.query(query_text)

            # Extract source information
            sources = []
            if hasattr(response, "source_nodes"):
                for node in response.source_nodes:
                    source_info = {
                        "filename": node.metadata.get("filename", "Unknown"),
                        "score": node.score,
                        "text_preview": node.text[:200] + "..."
                        if len(node.text) > 200
                        else node.text,
                        "source_type": node.metadata.get("source_type", "Unknown"),
                    }
                    sources.append(source_info)

            result = {
                "response": str(response),
                "sources": sources,
                "metadata": {
                    "model": self.llm_model,
                    "num_sources": len(sources),
                    "query_length": len(query_text),
                },
            }

            logger.info(
                f"Query processed successfully with {len(sources)} sources"
            )

            return result

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            raise

    def format_response_for_email(self, result: Dict[str, any]) -> str:
        """
        Format query result for email response.

        Args:
            result: Query result dictionary from query() method.

        Returns:
            Formatted text suitable for email body.
        """
        response_text = result["response"]
        sources = result["sources"]

        # Build email body
        email_body = f"{response_text}\n\n"

        if sources:
            email_body += "---\n\n"
            email_body += "Sources:\n"
            for i, source in enumerate(sources, 1):
                email_body += f"{i}. {source['filename']}"
                if "score" in source:
                    email_body += f" (relevance: {source['score']:.2f})"
                email_body += "\n"

        email_body += "\n---\n"
        email_body += (
            "This response was generated by DoLS-GPT. "
            "Please verify critical information with official sources.\n"
        )

        return email_body

    def format_response_for_web(self, result: Dict[str, any]) -> Dict[str, any]:
        """
        Format query result for web frontend.

        Args:
            result: Query result dictionary from query() method.

        Returns:
            Dictionary formatted for JSON response.
        """
        return {
            "answer": result["response"],
            "sources": [
                {
                    "filename": s["filename"],
                    "relevance": f"{s['score']:.2f}" if "score" in s else "N/A",
                    "preview": s.get("text_preview", ""),
                }
                for s in result["sources"]
            ],
            "metadata": result["metadata"],
        }

    def get_kb_stats(self) -> Dict[str, any]:
        """
        Get statistics about the knowledge base.

        Returns:
            Dictionary containing KB statistics.
        """
        try:
            total_chunks = self.kb_manager.get_document_count()
            unique_docs = self.kb_manager.get_unique_documents()

            return {
                "total_chunks": total_chunks,
                "unique_documents": len(unique_docs),
                "documents": unique_docs,
            }
        except Exception as e:
            logger.error(f"Error getting KB stats: {e}")
            return {
                "total_chunks": 0,
                "unique_documents": 0,
                "documents": [],
                "error": str(e),
            }
