"""
Minerva AI — Structured logging.

JSON-formatted structured logging via structlog.
Sensitive data (API keys, tokens, secrets) is never logged.
"""

from __future__ import annotations

import logging
import sys

import structlog


# Fields that must never appear in log output
_SENSITIVE_FIELDS = frozenset({
    "api_key", "api_secret", "secret", "password", "token",
    "passphrase", "apiKey", "apiSecret", "authorization",
    "binance_api_key", "binance_api_secret",
    "bybit_api_key", "bybit_api_secret",
    "okx_api_key", "okx_api_secret", "okx_passphrase",
    "groq_api_key", "openai_api_key",
    "supabase_key", "pinecone_api_key",
    "telegram_bot_token", "redis_url",
})


def _redact_sensitive(
    _logger: object, _method_name: str, event_dict: dict
) -> dict:
    """Structlog processor that redacts sensitive fields."""
    for key in list(event_dict.keys()):
        if key.lower() in _SENSITIVE_FIELDS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def setup_logging(level: str = "INFO") -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            _redact_sensitive,
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a named structured logger.

    Args:
        name: Logger name, typically __name__ of the calling module.

    Returns:
        Configured structlog BoundLogger instance.
    """
    return structlog.get_logger(name)
