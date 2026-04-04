"""
Shared singleton clients to reduce per-tenant memory footprint.

These clients are stateless HTTP wrappers that use global API credentials.
Sharing them across tenants avoids holding redundant connection pools and
client objects per cached tenant stack.
"""

import logging
from typing import Dict, Optional, Tuple

from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI as LlamaOpenAI
from openai import OpenAI as OpenAIClient

from src.config import settings

logger = logging.getLogger(__name__)

# Embedding model cache keyed by (model, api_key, api_base).
# In normal operation all tenants resolve to the same key.
_embed_model_cache: Dict[Tuple[str, str, str], OpenAIEmbedding] = {}

# llama_index LLM cache keyed by model name (api_key/base are global).
_llama_llm_cache: Dict[str, LlamaOpenAI] = {}

# Raw OpenAI client singleton (for function calling and query optimization).
_openai_client: Optional[OpenAIClient] = None


def get_embedding_model(
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    api_base: Optional[str] = None,
) -> OpenAIEmbedding:
    """Return a shared OpenAIEmbedding for the given config.

    Falls back to global settings when args are None. Instances are cached
    so that all tenants with matching embedding config share one client.
    """
    resolved_model = model or settings.openai_embedding_model
    resolved_key = api_key or settings.openai_api_key
    resolved_base = api_base or settings.openai_api_base
    cache_key = (resolved_model, resolved_key, resolved_base)

    cached = _embed_model_cache.get(cache_key)
    if cached is not None:
        return cached

    instance = OpenAIEmbedding(
        model=resolved_model,
        api_key=resolved_key,
        api_base=resolved_base,
    )
    _embed_model_cache[cache_key] = instance
    logger.info(f"Created shared OpenAIEmbedding (model={resolved_model})")
    return instance


def get_llama_llm(llm_model: str) -> LlamaOpenAI:
    """Return a shared llama_index OpenAI LLM client for the given model.

    API key/base/temperature/context window come from global settings.
    The underlying OpenRouter routing uses `additional_kwargs={"model": ...}`
    so distinct tenant model choices get distinct cached instances.
    """
    cached = _llama_llm_cache.get(llm_model)
    if cached is not None:
        return cached

    instance = LlamaOpenAI(
        model="gpt-4",  # Dummy name for llama_index validation
        api_key=settings.openrouter_api_key,
        api_base=settings.openrouter_api_base,
        temperature=0.1,
        context_window=200000,
        max_tokens=4096,
        is_chat_model=True,
        default_headers={
            "HTTP-Referer": "https://github.com/gilestrolab/berengario",
        },
        additional_kwargs={"model": llm_model},
    )
    _llama_llm_cache[llm_model] = instance
    logger.info(f"Created shared LlamaOpenAI LLM (model={llm_model})")
    return instance


def get_openai_client() -> OpenAIClient:
    """Return the shared raw OpenAI client singleton.

    Used for direct chat completions (function calling, query optimization).
    Per-call timeouts are passed at call time, not construction time.
    """
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAIClient(
            api_key=settings.openrouter_api_key,
            base_url=settings.openrouter_api_base,
        )
        logger.info("Created shared raw OpenAI client")
    return _openai_client


def reset_caches() -> None:
    """Clear all cached clients. Intended for tests."""
    global _openai_client
    _embed_model_cache.clear()
    _llama_llm_cache.clear()
    _openai_client = None
