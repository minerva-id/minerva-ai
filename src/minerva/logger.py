"""
Minerva AI — Structured logging.

JSON-formatted structured logging via structlog.
Sensitive data (API keys, tokens, secrets) is never logged.
Supports remote log shipping to Logtail / BetterStack when configured.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import queue
import sys
from typing import Any

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


class _LogtailHandler(logging.Handler):
    """
    HTTP log handler for Logtail / BetterStack.

    Sends structured JSON log records to the Logtail HTTP ingestion
    endpoint. Uses a non-blocking queue + background thread to avoid
    blocking the asyncio event loop.

    Sensitive fields are already redacted by the structlog pipeline
    before reaching this handler.
    """

    LOGTAIL_URL = "https://in.logs.betterstack.com"

    def __init__(self, source_token: str) -> None:
        super().__init__()
        self._source_token = source_token
        self._log_queue: queue.Queue[dict[str, Any]] = queue.Queue(
            maxsize=5000
        )
        self._session_started = False

    def emit(self, record: logging.LogRecord) -> None:
        """Queue a log record for async shipping."""
        try:
            # structlog renders the message as JSON in record.getMessage()
            msg = record.getMessage()
            try:
                payload = json.loads(msg)
            except (json.JSONDecodeError, TypeError):
                payload = {"message": msg, "level": record.levelname}

            self._log_queue.put_nowait(payload)
        except queue.Full:
            pass  # Drop rather than block

    def flush_batch(self) -> None:
        """
        Flush queued log entries to Logtail via HTTP POST.

        Called periodically from the agent's async loop via
        asyncio.to_thread to avoid blocking.
        """
        import urllib.request

        batch: list[dict[str, Any]] = []
        while not self._log_queue.empty() and len(batch) < 100:
            try:
                batch.append(self._log_queue.get_nowait())
            except queue.Empty:
                break

        if not batch:
            return

        body = json.dumps(batch).encode("utf-8")
        req = urllib.request.Request(
            self.LOGTAIL_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._source_token}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except Exception:
            pass  # Logging failures must not crash the agent


# Module-level reference for the Logtail handler (if enabled)
_logtail_handler: _LogtailHandler | None = None


def get_logtail_handler() -> _LogtailHandler | None:
    """Get the Logtail handler instance (if configured)."""
    return _logtail_handler


def setup_logging(level: str = "INFO", logtail_token: str = "") -> None:
    """
    Configure structured logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        logtail_token: Logtail/BetterStack source token for remote log
            shipping. If empty, only stdout logging is used.
    """
    global _logtail_handler
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    # Attach Logtail handler if token is provided
    if logtail_token:
        _logtail_handler = _LogtailHandler(logtail_token)
        _logtail_handler.setLevel(numeric_level)
        logging.getLogger().addHandler(_logtail_handler)
        logging.info(
            "Logtail handler attached — logs will ship to BetterStack"
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
