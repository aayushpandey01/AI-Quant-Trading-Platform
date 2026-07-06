"""
Centralized configuration for the whole platform.

All modules should import `settings` from here rather than reading
environment variables directly. This keeps configuration in one place
and makes the rest of the codebase testable (settings can be
monkey-patched or overridden in tests).
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Zerodha Kite Connect ---
    kite_api_key: str = ""
    kite_api_secret: str = ""
    kite_access_token: str = ""

    # --- Trading mode ---
    trading_mode: TradingMode = TradingMode.PAPER

    # --- Database ---
    database_url: str = f"sqlite:///{BASE_DIR / 'quant_platform.db'}"

    # --- Risk management ---
    max_position_pct: float = 0.10          # max % of capital in a single position
    max_portfolio_exposure_pct: float = 0.60  # max % of capital deployed at once
    default_stop_loss_pct: float = 0.02
    default_take_profit_pct: float = 0.05
    starting_capital: float = 100_000.0

    # --- Dashboard ---
    dashboard_host: str = "0.0.0.0"
    dashboard_port: int = 8000

    # --- Logging ---
    log_level: str = "INFO"

    @property
    def is_live(self) -> bool:
        return self.trading_mode == TradingMode.LIVE


settings = Settings()
