"""
Query optimization module for improving RAG retrieval accuracy.

Uses LLM-based optimization to enhance user queries through:
- Query expansion (adding synonyms and related terms)
- Query rewriting (improving clarity and grammar)
- Context-aware enhancement (leveraging conversation history)
"""

import logging
from typing import Optional

from openai import OpenAI as OpenAIClient
from openai import OpenAIError

from src.config import settings

logger = logging.getLogger(__name__)


class QueryOptimizer:
    """
    LLM-based query optimizer for improving RAG retrieval.

    Transparently optimizes user queries before they reach the RAG engine
    to improve semantic matching and retrieval accuracy.
    """

    def __init__(
        self,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        timeout: Optional[int] = None,
    ):
        """
        Initialize the query optimizer.

        Args:
            model: LLM model to use (default from settings).
            max_tokens: Maximum tokens for response (default from settings).
            temperature: Temperature for LLM (default from settings).
            timeout: API timeout in seconds (default from settings).
        """
        self.enabled = settings.query_optimization_enabled
        # Use provided model, or configured optimization model, or fall back to main LLM model
        self.model = (
            model or settings.query_optimization_model or settings.openrouter_model
        )
        self.max_tokens = max_tokens or settings.query_optimization_max_tokens
        self.temperature = temperature or settings.query_optimization_temperature
        self.timeout = timeout or settings.query_optimization_timeout

        if self.enabled:
            # Initialize OpenAI client for LLM calls
            self.client = OpenAIClient(
                api_key=settings.openrouter_api_key,
                base_url=settings.openrouter_api_base,
                timeout=self.timeout,
            )
            logger.info(
                f"QueryOptimizer initialized with model {self.model} (enabled={self.enabled})"
            )
        else:
            self.client = None
            logger.info("QueryOptimizer disabled by configuration")

    def optimize_query(
        self, query_text: str, conversation_history: Optional[str] = None
    ) -> str:
        """
        Optimize a user query for better RAG retrieval.

        Args:
            query_text: Original user query.
            conversation_history: Optional conversation history for context.

        Returns:
            Optimized query text (or original if optimization fails/disabled).
        """
        # Return original query if optimization is disabled
        if not self.enabled:
            logger.debug("Query optimization disabled, returning original query")
            return query_text

        # Skip optimization for very short queries (< 3 chars)
        if len(query_text.strip()) < 3:
            logger.debug("Query too short for optimization, returning original")
            return query_text

        try:
            logger.info(f"Optimizing query: {query_text[:100]}...")

            # Build optimization prompt
            optimization_prompt = self._build_optimization_prompt(
                query_text, conversation_history
            )

            # Call LLM to optimize
            optimized_query = self._call_llm(optimization_prompt)

            # Validate optimization result
            if self._validate_optimization(query_text, optimized_query):
                logger.info(f"Query optimized successfully: {optimized_query[:100]}...")
                return optimized_query
            else:
                logger.warning("Optimization validation failed, using original query")
                return query_text

        except Exception as e:
            logger.error(f"Query optimization failed: {e}", exc_info=True)
            # Fallback to original query on any error
            return query_text

    def _build_optimization_prompt(
        self, query_text: str, conversation_history: Optional[str] = None
    ) -> str:
        """
        Build the optimization prompt for the LLM.

        Args:
            query_text: Original user query.
            conversation_history: Optional conversation history.

        Returns:
            Formatted optimization prompt.
        """
        prompt = """You are a query optimization assistant. Your task is to improve user queries for better semantic search and document retrieval.

Your optimization should:
1. **Expand the query** - Add relevant synonyms, related terms, and contextual keywords
2. **Rewrite for clarity** - Fix grammar, spelling, and improve sentence structure
3. **Enhance with context** - Use conversation history to resolve ambiguity and add missing context

Guidelines:
- Keep the core intent and meaning of the original query
- Do NOT add information that wasn't implied or mentioned
- Output ONLY the optimized query, no explanations or commentary
- If the query is already well-formed, you may keep it mostly unchanged
- For follow-up questions, incorporate relevant context from conversation history

"""

        # Add conversation history if available
        if conversation_history:
            prompt += f"""Conversation history (for context):
{conversation_history}

"""

        prompt += f"""Original query: {query_text}

Optimized query:"""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        """
        Make LLM API call for optimization.

        Args:
            prompt: Optimization prompt.

        Returns:
            LLM response (optimized query).

        Raises:
            OpenAIError: If API call fails.
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                extra_headers={
                    "HTTP-Referer": "https://github.com/gilestrolab/berengar.io"
                },
            )

            optimized_query = response.choices[0].message.content.strip()

            # Log token usage
            if hasattr(response, "usage") and response.usage:
                logger.debug(
                    f"Optimization API usage: {response.usage.prompt_tokens} prompt + "
                    f"{response.usage.completion_tokens} completion tokens"
                )

            return optimized_query

        except OpenAIError as e:
            logger.error(f"LLM API call failed: {e}")
            raise

    def _validate_optimization(self, original: str, optimized: str) -> bool:
        """
        Validate that the optimized query is reasonable.

        Args:
            original: Original query text.
            optimized: Optimized query text.

        Returns:
            True if optimization is valid, False otherwise.
        """
        # Check if optimized query is empty or too short
        if not optimized or len(optimized.strip()) < 3:
            logger.warning("Optimized query too short or empty")
            return False

        # Check if optimized query is unreasonably long (likely hallucinated)
        # Allow up to 5x the original length, but cap at 500 chars
        max_length = min(len(original) * 5, 500)
        if len(optimized) > max_length:
            logger.warning(
                f"Optimized query too long ({len(optimized)} chars vs {len(original)} original)"
            )
            return False

        # Check for suspicious patterns (LLM explaining instead of optimizing)
        suspicious_patterns = [
            "Here is the optimized",
            "Here's the optimized",
            "The optimized query is:",
            "Optimized query:",
            "I've optimized",
            "I have optimized",
        ]

        optimized_lower = optimized.lower()
        if any(pattern.lower() in optimized_lower for pattern in suspicious_patterns):
            logger.warning("Optimized query contains explanation text")
            # Try to extract just the query if it's quoted
            if '"' in optimized:
                parts = optimized.split('"')
                if len(parts) >= 3:
                    # Use the content between first pair of quotes
                    extracted = parts[1].strip()
                    if extracted and len(extracted) >= 3:
                        logger.info("Extracted query from explanation text")
                        return True
            return False

        # Validation passed
        return True
