"""Shared LLM utilities with fallback model support."""

import logging
import time
from typing import Optional

from openai import OpenAI as OpenAIClient
from openai.types.chat import ChatCompletion

from src.config import settings

logger = logging.getLogger(__name__)

# --- Model failure alert throttling ---
MODEL_ALERT_THROTTLE_SECONDS = 3600  # 1 hour
_last_alert_time: float = 0.0

# Patterns that indicate a model/server error (used for fallback + alerts)
MODEL_ERROR_INDICATORS = [
    "400",
    "500",
    "502",
    "503",
    "504",
    "429",
    "timeout",
    "overloaded",
]


def is_model_error(error_str: str) -> bool:
    """Check if an error string looks like a model/server failure."""
    return any(ind in error_str for ind in MODEL_ERROR_INDICATORS)


def send_model_failure_alert(error: str, model: str, context: str = "") -> None:
    """Send an alert email to platform admins about a model failure.

    Throttled to at most once per MODEL_ALERT_THROTTLE_SECONDS.

    Args:
        error: The error message/string.
        model: The model name that failed.
        context: Additional context (e.g. "email query from user@x.com").
    """
    global _last_alert_time

    now = time.time()
    if now - _last_alert_time < MODEL_ALERT_THROTTLE_SECONDS:
        logger.debug("Model failure alert suppressed (throttled)")
        return

    admin_emails = settings.get_platform_admin_emails()
    if not admin_emails:
        logger.warning("Model failure detected but no platform admin emails configured")
        return

    try:
        from src.email.email_sender import EmailSender

        sender = EmailSender()
        subject = f"[Berengario] LLM model failure: {model}"
        body_text = (
            f"A model failure was detected.\n\n"
            f"Model: {model}\n"
            f"Error: {error[:500]}\n"
            f"Context: {context or 'N/A'}\n"
            f"Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n\n"
            f"The system attempted to use the fallback model. "
            f"Please check your LLM provider configuration."
        )
        body_html = (
            f"<h3>LLM Model Failure Alert</h3>"
            f"<p><strong>Model:</strong> {model}</p>"
            f"<p><strong>Error:</strong> <code>{error[:500]}</code></p>"
            f"<p><strong>Context:</strong> {context or 'N/A'}</p>"
            f"<p><strong>Time:</strong> {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}</p>"
            f"<p>The system attempted to use the fallback model. "
            f"Please check your LLM provider configuration.</p>"
        )

        for admin_email in admin_emails:
            sender.send_reply(
                to_address=admin_email,
                subject=subject,
                body_text=body_text,
                body_html=body_html,
            )

        _last_alert_time = now
        logger.info(
            "Sent model failure alert to %d admin(s) for model %s",
            len(admin_emails),
            model,
        )
    except Exception as exc:
        logger.warning("Failed to send model failure alert: %s", exc)


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
        if not is_model_error(error_str):
            raise

        logger.warning(
            f"Primary model {model} failed ({error_str[:100]}), "
            f"falling back to {fallback_model}"
        )
        send_model_failure_alert(error_str, model)
        return client.chat.completions.create(model=fallback_model, **kwargs)
