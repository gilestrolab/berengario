"""
RAG (Retrieval-Augmented Generation) engine for query processing.

Handles query execution, context retrieval, and response generation.
"""

import json
import logging
from typing import Any, Dict, Optional

from llama_index.core import PromptTemplate
from llama_index.llms.openai import OpenAI
from openai import OpenAI as OpenAIClient

from src.config import settings
from src.document_processing.kb_manager import KnowledgeBaseManager
from src.rag.tools import ToolExecutor, get_registry

logger = logging.getLogger(__name__)


def get_system_prompt(
    instance_name: str,
    instance_description: str,
    organization: str = "",
    include_tools: bool = False,
    custom_prompt_text: Optional[str] = None,
) -> str:
    """
    Generate system prompt based on instance configuration.

    Args:
        instance_name: Name of the instance.
        instance_description: Description of the instance's purpose.
        organization: Organization name (optional).
        include_tools: Whether to include tool descriptions in the prompt.
        custom_prompt_text: Custom prompt text to append. When provided,
            used instead of reading from settings.rag_custom_prompt_file.

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

    # Append custom prompt: prefer provided text, fall back to file
    if custom_prompt_text:
        base_prompt += f"\n\n{custom_prompt_text}"
        logger.info("Appended custom prompt from tenant context")
    elif settings.rag_custom_prompt_file and settings.rag_custom_prompt_file.exists():
        try:
            with open(settings.rag_custom_prompt_file, "r", encoding="utf-8") as f:
                custom_prompt = f.read().strip()
            if custom_prompt:
                base_prompt += f"\n\n{custom_prompt}"
                logger.info(
                    f"Appended custom prompt from {settings.rag_custom_prompt_file}"
                )
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
        enable_function_calling: bool = False,
        tenant_context: Optional["TenantContext"] = None,  # noqa: F821
    ):
        """
        Initialize the RAG engine.

        Args:
            kb_manager: Knowledge base manager instance.
            llm_model: LLM model name (default from settings).
            enable_function_calling: Whether to enable function calling for tools.
            tenant_context: Optional tenant context for multi-tenant config.
                When provided, overrides instance_name/description/organization/
                custom_prompt/top_k from global settings.
        """
        self.kb_manager = kb_manager or KnowledgeBaseManager()
        self.llm_model = llm_model or settings.openrouter_model
        self.enable_function_calling = enable_function_calling
        self.tenant_context = tenant_context

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
                "HTTP-Referer": "https://github.com/gilestrolab/berengario",
            },
            # Additional model parameters to override in API calls
            additional_kwargs={
                "model": self.llm_model
            },  # Pass actual model in API calls
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
        # Use tenant context when available, otherwise fall back to global settings
        ctx = self.tenant_context
        system_prompt = get_system_prompt(
            instance_name=ctx.instance_name if ctx else settings.instance_name,
            instance_description=(
                ctx.instance_description if ctx else settings.instance_description
            ),
            organization=ctx.organization if ctx else settings.organization,
            include_tools=self.enable_function_calling,
            custom_prompt_text=ctx.custom_prompt if ctx else None,
        )
        self.prompt_template = PromptTemplate(system_prompt)

        # Get query engine from KB manager (pass our LLM)
        top_k = ctx.top_k_retrieval if ctx else settings.top_k_retrieval
        self.query_engine = self.kb_manager.get_query_engine(top_k=top_k, llm=self.llm)

        # Update query engine with custom prompt
        self.query_engine.update_prompts(
            {"response_synthesizer:text_qa_template": self.prompt_template}
        )

        logger.info(f"RAGEngine initialized with model {self.llm_model}")

    def _query_with_fallback(self, query_text: str):
        """Run LlamaIndex query, falling back to secondary model on server errors."""
        try:
            return self.query_engine.query(query_text)
        except Exception as e:
            fallback = settings.openrouter_fallback_model
            if not fallback or fallback == self.llm_model:
                raise

            error_str = str(e)
            is_retriable = any(
                ind in error_str
                for ind in ["500", "502", "503", "504", "429", "timeout", "overloaded"]
            )
            if not is_retriable:
                raise

            logger.warning(
                f"Primary model {self.llm_model} failed ({error_str[:100]}), "
                f"retrying with fallback model {fallback}"
            )

            # Swap LLM to fallback model and rebuild query engine
            fallback_llm = OpenAI(
                model="gpt-4",
                api_key=settings.openrouter_api_key,
                api_base=settings.openrouter_api_base,
                temperature=0.1,
                context_window=200000,
                max_tokens=4096,
                is_chat_model=True,
                default_headers={
                    "HTTP-Referer": "https://github.com/gilestrolab/berengario",
                },
                additional_kwargs={"model": fallback},
            )
            ctx = self.tenant_context
            top_k = ctx.top_k_retrieval if ctx else settings.top_k_retrieval
            fallback_engine = self.kb_manager.get_query_engine(
                top_k=top_k, llm=fallback_llm
            )
            fallback_engine.update_prompts(
                {"response_synthesizer:text_qa_template": self.prompt_template}
            )
            return fallback_engine.query(query_text)

    def _check_for_function_calls(
        self, query_text: str, conversation_history: Optional[str] = None
    ) -> Dict[str, Any]:
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
                extra_headers={
                    "HTTP-Referer": "https://github.com/gilestrolab/berengario"
                },
            )

            message = response.choices[0].message

            # Check if there are tool calls
            if not hasattr(message, "tool_calls") or not message.tool_calls:
                # No tools were called — proceed to normal RAG retrieval
                return {
                    "has_tool_calls": False,
                    "tool_response": None,
                    "attachments": [],
                }

            # Execute function calls
            function_calls = []
            for tool_call in message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                function_calls.append(
                    {"name": function_name, "arguments": arguments, "id": tool_call.id}
                )
                logger.info(f"Function call requested: {function_name}")

            # Execute all function calls
            execution_result = self.tool_executor.execute_function_calls(function_calls)

            logger.info(
                f"Executed {len(function_calls)} function calls: "
                f"{execution_result['success_count']} successful, "
                f"{execution_result['error_count']} failed"
            )

            # Pass tool results back to LLM to generate final response
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": message.tool_calls,
                }
            )

            # Add tool responses and check if any tool sent an email
            email_already_sent = False
            for i, call in enumerate(function_calls):
                result = execution_result["results"][i]
                # Check if this tool already sent an email (e.g., confirmation email)
                if result.get("success") and result.get("result", {}).get("email_sent"):
                    email_already_sent = True
                    logger.info(
                        f"Tool {call['name']} already sent email - will skip automatic reply"
                    )

                tool_result_data = result.get(
                    "result", result.get("error", "Unknown error")
                )
                tool_response_content = json.dumps(tool_result_data, default=str)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call["id"],
                        "content": tool_response_content,
                    }
                )

            # Get final response from LLM based on tool results
            final_response = self.openai_client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                extra_headers={
                    "HTTP-Referer": "https://github.com/gilestrolab/berengario"
                },
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
            # Step 1: ALWAYS run RAG retrieval first — this is the primary response path
            if top_k:
                self.query_engine.retriever.similarity_top_k = top_k

            full_query = query_text
            if conversation_history:
                full_query = f"{conversation_history}\n\nCurrent query: {query_text}"
                logger.debug("Added conversation history to RAG query")

            response = self._query_with_fallback(full_query)
            response_text = str(response)

            # Extract source information
            sources = []
            if hasattr(response, "source_nodes"):
                all_sources = []
                for node in response.source_nodes:
                    source_info = {
                        "filename": node.metadata.get("filename", "Unknown"),
                        "score": node.score,
                        "text_preview": (
                            node.text[:200] + "..."
                            if len(node.text) > 200
                            else node.text
                        ),
                        "source_type": node.metadata.get("source_type", "Unknown"),
                        "sender": node.metadata.get("sender"),
                        "subject": node.metadata.get("subject"),
                        "date": node.metadata.get("date"),
                    }
                    all_sources.append(source_info)

                # Deduplicate sources by filename/subject, keeping highest score
                logger.info(f"Before deduplication: {len(all_sources)} source nodes")
                seen = {}
                for source in all_sources:
                    if source.get("subject") and source.get("sender"):
                        key = (source["subject"], source["sender"])
                    else:
                        key = source["filename"]
                    if key not in seen or source["score"] > seen[key]["score"]:
                        seen[key] = source

                sources = sorted(seen.values(), key=lambda x: x["score"], reverse=True)
                logger.info(
                    f"After deduplication: {len(sources)} unique sources from {len(seen)} unique keys"
                )

            # Step 2: Check for tool calls (calendar, exports) — attachments only
            # The RAG response text and sources are ALWAYS the primary answer.
            # Tools can only ADD attachments (calendar files, exports) alongside.
            attachments = []
            skip_email_reply = False
            if self.enable_function_calling and self.tools:
                function_result = self._check_for_function_calls(
                    query_text, conversation_history
                )
                if function_result.get("has_tool_calls"):
                    attachments = function_result.get("attachments", [])
                    skip_email_reply = function_result.get("skip_email_reply", False)
                    if attachments:
                        logger.info(
                            f"Tool produced {len(attachments)} attachment(s) — "
                            "appending to RAG response"
                        )

            result = {
                "response": response_text,
                "sources": sources,
                "attachments": attachments,
                "metadata": {
                    "model": self.llm_model,
                    "num_sources": len(sources),
                    "num_attachments": len(attachments),
                    "query_length": len(query_text),
                    "skip_email_reply": skip_email_reply,
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
