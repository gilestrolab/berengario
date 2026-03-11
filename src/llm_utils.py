"""Shared LLM utilities with fallback model support."""

import logging
from typing import Optional

from openai import OpenAI as OpenAIClient
from openai.types.chat import ChatCompletion

from src.config import settings

logger = logging.getLogger(__name__)


def llm_call_with_fallback(
    client: OpenAIClient,
    model: str,
    fallback_model: Optional[str] = None,
    **kwargs,
) -> ChatCompletion:
    """
    Make an LLM API call with automatic fallback to a secondary model.

    Tries the primary model first. If it fails with a server/overload error,
    retries once with the fallback model (if configured).

    Args:
        client: OpenAI-compatible client instance.
        model: Primary model name.
        fallback_model: Fallback model name (default: from settings).
        **kwargs: Additional arguments passed to chat.completions.create().

    Returns:
        Chat completion response.

    Raises:
        The original exception if no fallback is configured or fallback also fails.
    """
    if fallback_model is None:
        fallback_model = settings.openrouter_fallback_model

    try:
        return client.chat.completions.create(model=model, **kwargs)
    except Exception as e:
        if not fallback_model or fallback_model == model:
            raise

        error_str = str(e)
        # Retry on server errors (5xx), rate limits (429), or timeout
        is_retriable = any(
            indicator in error_str
            for indicator in [
                "500",
                "502",
                "503",
                "504",
                "429",
                "timeout",
                "overloaded",
            ]
        )
        if not is_retriable:
            raise

        logger.warning(
            f"Primary model {model} failed ({error_str[:100]}), "
            f"falling back to {fallback_model}"
        )
        return client.chat.completions.create(model=fallback_model, **kwargs)
