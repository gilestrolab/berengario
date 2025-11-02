"""
RAG (Retrieval-Augmented Generation) engine for query processing.

Handles query execution, context retrieval, and response generation.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from llama_index.core import PromptTemplate
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.llms.openai import OpenAI
from openai import OpenAI as OpenAIClient

from src.config import settings
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.rag.tools import get_registry, ToolExecutor

logger = logging.getLogger(__name__)


def get_system_prompt(instance_name: str, instance_description: str, organization: str = "", include_tools: bool = False) -> str:
    """
    Generate system prompt based on instance configuration.

    Args:
        instance_name: Name of the instance.
        instance_description: Description of the instance's purpose.
        organization: Organization name (optional).
        include_tools: Whether to include tool descriptions in the prompt.

    Returns:
        Formatted system prompt.
    """
    org_text = f" at {organization}" if organization else ""

    base_prompt = f"""You are {instance_name}, {instance_description}{org_text}.

Your role is to help users by answering questions based on the knowledge base documentation.

Guidelines:
1. Provide accurate, helpful answers based on the provided context
2. If the context doesn't contain enough information, acknowledge this clearly
3. Cite specific sources when providing information
4. Be professional and concise
5. Reference relevant documents or policies when answering
6. If uncertain, acknowledge the limitation"""

    # Add tool information if function calling is enabled
    if include_tools:
        registry = get_registry()
        tools = registry.list_tools()
        if tools:
            base_prompt += "\n\nAvailable Tools:\n"
            base_prompt += "You have access to the following tools to help users:\n\n"
            for tool in tools:
                base_prompt += f"- {tool.name}: {tool.description}\n"
            base_prompt += "\n\nTool Usage Guidelines:"
            base_prompt += "\n- ALWAYS create a calendar event (.ics file) when your response mentions a specific future date, deadline, or scheduled event"
            base_prompt += "\n- Use create_calendar_event for single events with dates, times, and locations mentioned in the response"
            base_prompt += "\n- Use export tools (CSV, JSON) when users request data exports or when providing structured information that would benefit from a downloadable format"
            base_prompt += "\n- Proactively generate attachments to enhance user experience - don't wait to be asked"

    # Append custom prompt from file if specified
    if settings.rag_custom_prompt_file and settings.rag_custom_prompt_file.exists():
        try:
            with open(settings.rag_custom_prompt_file, 'r', encoding='utf-8') as f:
                custom_prompt = f.read().strip()
            if custom_prompt:
                base_prompt += f"\n\n{custom_prompt}"
                logger.info(f"Appended custom prompt from {settings.rag_custom_prompt_file}")
        except Exception as e:
            logger.warning(f"Failed to load custom prompt file: {e}")

    # Add context and query sections
    full_prompt = f"""{base_prompt}

Context information is provided below:
---------------------
{{context_str}}
---------------------

Based on the context above, please answer the following query:
Query: {{query_str}}

Answer:"""

    return full_prompt


class RAGEngine:
    """
    RAG engine for processing queries using the knowledge base.

    Retrieves relevant context and generates responses using LLM.
    """

    def __init__(
        self,
        kb_manager: Optional[KnowledgeBaseManager] = None,
        llm_model: Optional[str] = None,
        enable_function_calling: bool = True,
    ):
        """
        Initialize the RAG engine.

        Args:
            kb_manager: Knowledge base manager instance.
            llm_model: LLM model name (default from settings).
            enable_function_calling: Whether to enable function calling for tools.
        """
        self.kb_manager = kb_manager or KnowledgeBaseManager()
        self.llm_model = llm_model or settings.openrouter_model
        self.enable_function_calling = enable_function_calling

        # Initialize LLM (uses OpenAI-compatible API like Naga.ac)
        # WORKAROUND: Use "gpt-4" to pass validation, but actual model is sent to API
        # The custom api_base will route to the correct model (self.llm_model)
        self.llm = OpenAI(
            model="gpt-4",  # Dummy model name for validation
            api_key=settings.openrouter_api_key,
            api_base=settings.openrouter_api_base,
            temperature=0.1,  # Low temperature for factual responses
            context_window=200000,  # Large context window
            max_tokens=4096,
            is_chat_model=True,
            default_headers={
                "HTTP-Referer": "https://github.com/imperial-dols/dols-gpt",
            },
            # Additional model parameters to override in API calls
            additional_kwargs={"model": self.llm_model},  # Pass actual model in API calls
        )

        # Initialize tool system for function calling
        if self.enable_function_calling:
            self.tool_registry = get_registry()
            self.tool_executor = ToolExecutor(self.tool_registry)
            self.tools = self.tool_registry.get_openai_functions()

            # Create OpenAI client for function calling
            self.openai_client = OpenAIClient(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_api_base,
            )
            logger.info(f"Function calling enabled with {len(self.tools)} tools")
        else:
            self.tool_registry = None
            self.tool_executor = None
            self.tools = []
            self.openai_client = None

        # Create custom prompt template based on instance configuration
        system_prompt = get_system_prompt(
            settings.instance_name,
            settings.instance_description,
            settings.organization,
            include_tools=self.enable_function_calling,
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

    def _check_for_function_calls(self, query_text: str, conversation_history: Optional[str] = None) -> Dict[str, Any]:
        """
        Check if the query requires any function calls.

        Args:
            query_text: The user's query.
            conversation_history: Optional conversation history for context.

        Returns:
            Dictionary containing:
                - has_tool_calls: Whether tools were called
                - tool_response: LLM-generated response based on tool results (if tools were called)
                - attachments: List of attachments from tools
        """
        if not self.enable_function_calling or not self.tools:
            return {"has_tool_calls": False, "tool_response": None, "attachments": []}

        try:
            # Build system prompt with conversation context if available
            system_content = f"You are {settings.instance_name}. Analyze the user's request and determine if you need to use any tools."

            if conversation_history:
                system_content += f"\n\n{conversation_history}"

            # Make initial call to check for function calls
            messages = [
                {
                    "role": "system",
                    "content": system_content,
                },
                {"role": "user", "content": query_text},
            ]

            response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                tools=[{"type": "function", "function": tool} for tool in self.tools],
                tool_choice="auto",
                extra_headers={"HTTP-Referer": "https://github.com/imperial-dols/dols-gpt"},
            )

            message = response.choices[0].message

            # Check if there are tool calls
            if not hasattr(message, "tool_calls") or not message.tool_calls:
                # No tools called, but check if this is an administrative query
                # (whitelist management, clarification requests, etc.)
                # If so, use the LLM's response directly without RAG retrieval
                if message.content:
                    query_lower = query_text.lower()
                    response_lower = message.content.lower()

                    # Check if query is about user/whitelist management
                    admin_query_keywords = ["whitelist", "add to", "remove from", "list of users", "grant access", "revoke access"]
                    is_admin_query = any(keyword in query_lower for keyword in admin_query_keywords)

                    # Check if response suggests administrative action or clarification
                    admin_response_keywords = ["confirmation required", "please specify", "which whitelist", "clarification", "ambiguous"]
                    is_admin_response = any(keyword in response_lower for keyword in admin_response_keywords)

                    if is_admin_query or is_admin_response:
                        logger.info("Administrative query/response detected - using direct LLM response without sources")
                        return {
                            "has_tool_calls": True,  # Treat as tool-related (no sources)
                            "tool_response": message.content,
                            "attachments": [],
                        }

                return {"has_tool_calls": False, "tool_response": None, "attachments": []}

            # Execute function calls
            function_calls = []
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                function_calls.append({"name": function_name, "arguments": arguments, "id": tool_call.id})
                logger.info(f"Function call requested: {function_name}")

            # Execute all function calls
            execution_result = self.tool_executor.execute_function_calls(function_calls)

            logger.info(
                f"Executed {len(function_calls)} function calls: "
                f"{execution_result['success_count']} successful, "
                f"{execution_result['error_count']} failed"
            )

            # Pass tool results back to LLM to generate final response
            messages.append({
                "role": "assistant",
                "content": message.content,
                "tool_calls": message.tool_calls,
            })

            # Add tool responses and check if any tool sent an email
            email_already_sent = False
            for i, call in enumerate(function_calls):
                result = execution_result['results'][i]
                # Check if this tool already sent an email (e.g., confirmation email)
                if result.get('success') and result.get('result', {}).get('email_sent'):
                    email_already_sent = True
                    logger.info(f"Tool {call['name']} already sent email - will skip automatic reply")

                tool_response_content = json.dumps(result.get('result', result.get('error', 'Unknown error')))
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": tool_response_content,
                })

            # Get final response from LLM based on tool results
            final_response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                extra_headers={"HTTP-Referer": "https://github.com/imperial-dols/dols-gpt"},
            )

            tool_response_text = final_response.choices[0].message.content

            return {
                "has_tool_calls": True,
                "tool_response": tool_response_text,
                "attachments": execution_result.get("attachments", []),
                "skip_email_reply": email_already_sent,  # Flag to indicate email was already sent by tool
            }

        except Exception as e:
            logger.error(f"Error checking for function calls: {e}", exc_info=True)
            return {"has_tool_calls": False, "tool_response": None, "attachments": []}

    def query(
        self,
        query_text: str,
        top_k: Optional[int] = None,
        conversation_history: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Execute a query against the knowledge base.

        Args:
            query_text: The query string.
            top_k: Number of top results to retrieve (overrides default).
            conversation_history: Optional conversation history for multi-turn context.

        Returns:
            Dictionary containing:
                - response: Generated response text
                - sources: List of source documents
                - attachments: List of attachments from tool calls
                - metadata: Additional metadata

        Raises:
            Exception: If query execution fails.
        """
        if not query_text.strip():
            raise ValueError("Query text cannot be empty")

        logger.info(f"Processing query: {query_text[:100]}...")

        try:
            # Check for function calls and generate attachments
            function_result = self._check_for_function_calls(query_text, conversation_history)
            attachments = function_result.get("attachments", [])

            # If tools were called, use the tool response instead of RAG query
            if function_result.get("has_tool_calls"):
                response_text = function_result.get("tool_response", "Tool executed successfully.")
                sources = []
                logger.info("Using tool response instead of RAG query")
            else:
                # Update top_k if provided
                if top_k:
                    self.query_engine.retriever.similarity_top_k = top_k

                # Build query with conversation history if available
                full_query = query_text
                if conversation_history:
                    full_query = f"{conversation_history}\n\nCurrent query: {query_text}"
                    logger.debug("Added conversation history to RAG query")

                # Execute query
                response = self.query_engine.query(full_query)
                response_text = str(response)

                # Extract source information
                sources = []
                if hasattr(response, "source_nodes"):
                    # Build all sources first
                    all_sources = []
                    for node in response.source_nodes:
                        source_info = {
                            "filename": node.metadata.get("filename", "Unknown"),
                            "score": node.score,
                            "text_preview": node.text[:200] + "..."
                            if len(node.text) > 200
                            else node.text,
                            "source_type": node.metadata.get("source_type", "Unknown"),
                            # Additional metadata for emails
                            "sender": node.metadata.get("sender"),
                            "subject": node.metadata.get("subject"),
                            "date": node.metadata.get("date"),
                        }
                        all_sources.append(source_info)

                    # Deduplicate sources by filename/subject, keeping highest score
                    # Use filename for files, subject for emails
                    logger.info(f"Before deduplication: {len(all_sources)} source nodes")
                    seen = {}
                    for source in all_sources:
                        # Create unique key based on source type
                        if source.get("subject") and source.get("sender"):
                            # Email source - use subject+sender as key
                            key = (source["subject"], source["sender"])
                        else:
                            # File source - use filename as key
                            key = source["filename"]

                        # Keep only the highest scoring source for each unique document
                        if key not in seen or source["score"] > seen[key]["score"]:
                            seen[key] = source

                    # Convert back to list, sorted by score (highest first)
                    sources = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
                    logger.info(f"After deduplication: {len(sources)} unique sources from {len(seen)} unique keys")

            result = {
                "response": response_text,
                "sources": sources,
                "attachments": attachments,
                "metadata": {
                    "model": self.llm_model,
                    "num_sources": len(sources),
                    "num_attachments": len(attachments),
                    "query_length": len(query_text),
                    "skip_email_reply": function_result.get("skip_email_reply", False),
                },
            }

            logger.info(
                f"Query processed successfully with {len(sources)} sources "
                f"and {len(attachments)} attachments"
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
