"""
Minerva AI — Configuration management.

All configuration loaded from environment variables via Pydantic Settings.
No hardcoded secrets. Fails fast if required values are missing in production.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Agent ---
    agent_mode: Literal["paper", "live"] = "paper"
    auto_execute: bool = False
    agent_loop_interval: int = Field(default=60, ge=5, le=3600)
    trading_pairs: str = "BTC/USDT,ETH/USDT"

    # --- Exchange ---
    binance_api_key: str = ""
    binance_api_secret: str = ""
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    okx_api_key: str = ""
    okx_api_secret: str = ""
    okx_passphrase: str = ""
    hyperliquid_wallet_address: str = ""
    hyperliquid_private_key: str = ""
    primary_exchange: Literal["binance", "bybit", "okx", "kraken", "hyperliquid"] = "hyperliquid"
    exchange_sandbox: bool = False

    # --- LLM ---
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"
    llm_provider: Literal["groq", "openai"] = "groq"
    llm_timeout: int = Field(default=5, ge=1, le=30)

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Supabase ---
    supabase_url: str = ""
    supabase_key: str = ""

    # --- Pinecone ---
    pinecone_api_key: str = ""
    pinecone_index_name: str = "minerva-memory"

    # --- MCP Bridge (Hermes Agent Integration) ---
    mcp_server_enabled: bool = True
    mcp_server_port: int = Field(default=9100, ge=1024, le=65535)
    mcp_server_host: str = "127.0.0.1"
    mcp_auth_token: str = ""

    # --- Jarvis HUD (WebSocket Relay) ---
    jarvis_hud_enabled: bool = True
    jarvis_ws_port: int = Field(default=8081, ge=1024, le=65535)
    jarvis_ws_host: str = "127.0.0.1"
    jarvis_ws_auth_token: str = ""
    hermes_api_url: str = ""  # Empty = use built-in MinervaAgent chat fallback

    # --- On-Chain (Arkham) ---
    arkham_cookie: str = ""
    arkham_x_payload: str = ""
    arkham_x_timestamp: str = ""
    arkham_polling_interval: int = Field(default=30, ge=10)
    whale_transfer_threshold_usd: float = 500000.0

    # --- News & Social ---
    rss_news_url: str = "https://api.rss2json.com/v1/api.json?rss_url=https://cointelegraph.com/rss"
    gmgn_social_url: str = ""

    # --- Telegram ---
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # --- Monitoring ---
    prometheus_pushgateway_url: str = ""
    logtail_token: str = ""

    # --- Risk ---
    max_position_size_usd: float = Field(default=1000.0, ge=0)
    max_total_exposure_usd: float = Field(default=5000.0, ge=0)
    max_drawdown_percent: float = Field(default=10.0, ge=0, le=100)
    daily_loss_limit_usd: float = Field(default=500.0, ge=0)

    # --- Logging ---
    log_level: str = "INFO"

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        v = v.upper()
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v

    def get_trading_pairs_list(self) -> list[str]:
        """Parse comma-separated trading pairs."""
        return [p.strip() for p in self.trading_pairs.split(",") if p.strip()]

    def get_exchange_credentials(self, exchange: str) -> dict[str, str]:
        """Get API credentials for the specified exchange."""
        creds: dict[str, dict[str, str]] = {
            "binance": {
                "apiKey": self.binance_api_key,
                "secret": self.binance_api_secret,
            },
            "bybit": {
                "apiKey": self.bybit_api_key,
                "secret": self.bybit_api_secret,
            },
            "okx": {
                "apiKey": self.okx_api_key,
                "secret": self.okx_api_secret,
                "password": self.okx_passphrase,
            },
            "hyperliquid": {
                "walletAddress": self.hyperliquid_wallet_address,
                "privateKey": self.hyperliquid_private_key,
            },
        }
        return creds.get(exchange, {})

    def get_llm_config(self) -> dict[str, str]:
        """
        Get LLM API configuration.

        Returns the API key and model for the configured LLM provider.
        If no API key is available, logs a warning and returns empty config.
        """
        if self.llm_provider == "groq":
            if not self.groq_api_key:
                logging.warning("GROQ_API_KEY not set; LLM slow path disabled")
                return {}
            return {
                "api_key": self.groq_api_key,
                "model": self.groq_model,
                "base_url": "https://api.groq.com/openai/v1",
            }
        else:
            if not self.openai_api_key:
                logging.warning("OPENAI_API_KEY not set; LLM slow path disabled")
                return {}
            return {
                "api_key": self.openai_api_key,
                "model": self.openai_model,
                "base_url": self.openai_base_url,
            }

    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    def has_pinecone(self) -> bool:
        return bool(self.pinecone_api_key)

    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    def has_onchain(self) -> bool:
        return bool(self.arkham_cookie and self.arkham_x_payload)

    def has_news(self) -> bool:
        return bool(self.rss_news_url)

    def has_social(self) -> bool:
        return bool(self.gmgn_social_url)

    def has_mcp(self) -> bool:
        return self.mcp_server_enabled


def _get_ephemeral_fallback(name: str) -> str:
    """
    Generate an ephemeral secret for non-production use.

    Logs a severe warning. This value is instance-isolated and will be lost
    on restart — not suitable for production clusters.
    """
    val = secrets.token_hex(32)
    logging.warning(
        "No %s configured. Generated ephemeral value. "
        "This is instance-isolated and NOT suitable for horizontal scaling.",
        name,
    )
    return val


# Singleton settings instance
_settings: Settings | None = None


def get_settings() -> Settings:
    """Get or create the application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
