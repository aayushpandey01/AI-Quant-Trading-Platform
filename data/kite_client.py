"""
Thin wrapper around Zerodha's Kite Connect SDK.

Design goals:
- The rest of the platform never touches `kiteconnect` directly, only this
  class. That keeps broker-specific quirks in one place and makes it
  possible to swap brokers later without touching backtest/execution code.
- Works in three modes:
    1. Fully configured (api key + secret + access token) -> real calls.
    2. Api key/secret present but no access token -> can run the login flow.
    3. Nothing configured -> raises a clear error when a network call is
       attempted, but the object can still be constructed (useful so the
       rest of the app, e.g. the dashboard, can boot without credentials
       and operate on historical/backtest data only).

Zerodha Kite Connect requires a paid API subscription (~Rs.2000/month) and a
daily login flow (access tokens expire every day at ~6am IST). See README.md
for the full setup walkthrough.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from config.logging_config import get_logger
from config.settings import settings

logger = get_logger(__name__)

try:
    from kiteconnect import KiteConnect
except ImportError:  # pragma: no cover
    KiteConnect = None  # type: ignore


class KiteClientError(Exception):
    """Raised when a Kite API call fails or credentials are missing."""


class KiteClient:
    """Wraps KiteConnect with sane defaults, logging, and error handling."""

    # Zerodha historical-data interval names
    VALID_INTERVALS = {
        "minute", "3minute", "5minute", "10minute", "15minute",
        "30minute", "60minute", "day",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        access_token: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or settings.kite_api_key
        self.api_secret = api_secret or settings.kite_api_secret
        self.access_token = access_token or settings.kite_access_token
        self._kite: Optional["KiteConnect"] = None

        if KiteConnect is None:
            logger.warning("kiteconnect package not installed - client is inert")
            return

        if not self.api_key:
            logger.warning("KITE_API_KEY not set - client is inert until configured")
            return

        self._kite = KiteConnect(api_key=self.api_key)
        if self.access_token:
            self._kite.set_access_token(self.access_token)

    # ------------------------------------------------------------------
    # Auth / login flow
    # ------------------------------------------------------------------
    def get_login_url(self) -> str:
        """Step 1 of daily login: send the user to this URL to authenticate."""
        self._require_client()
        return self._kite.login_url()

    def generate_session(self, request_token: str) -> str:
        """
        Step 2 of daily login: exchange the request_token (from the redirect
        URL after login) for an access_token. Call this once per trading day.
        Returns the access_token; caller is responsible for persisting it
        (e.g. writing it back to .env) for the rest of the session.
        """
        self._require_client()
        if not self.api_secret:
            raise KiteClientError("KITE_API_SECRET is required to generate a session")
        data = self._kite.generate_session(request_token, api_secret=self.api_secret)
        self.access_token = data["access_token"]
        self._kite.set_access_token(self.access_token)
        logger.info("Kite session established, access token acquired")
        return self.access_token

    def is_configured(self) -> bool:
        return self._kite is not None and bool(self.access_token)

    def _require_client(self) -> None:
        if self._kite is None:
            raise KiteClientError(
                "Kite client not configured - set KITE_API_KEY (and KITE_API_SECRET "
                "for login) in your .env file."
            )

    def _require_session(self) -> None:
        self._require_client()
        if not self.access_token:
            raise KiteClientError(
                "No access token set. Run the login flow (see README) to obtain one - "
                "Zerodha access tokens expire daily."
            )

    # ------------------------------------------------------------------
    # Instruments
    # ------------------------------------------------------------------
    def get_instruments(self, exchange: str = "NSE") -> list[dict[str, Any]]:
        """Full instrument list for an exchange (needed to map symbol -> token)."""
        self._require_session()
        try:
            return self._kite.instruments(exchange)
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch instruments: {exc}") from exc

    def get_instrument_token(self, symbol: str, exchange: str = "NSE") -> int:
        instruments = self.get_instruments(exchange)
        for inst in instruments:
            if inst["tradingsymbol"] == symbol:
                return int(inst["instrument_token"])
        raise KiteClientError(f"Symbol {symbol} not found on {exchange}")

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def get_historical_data(
        self,
        instrument_token: int,
        from_date: dt.date,
        to_date: dt.date,
        interval: str = "day",
    ) -> list[dict[str, Any]]:
        self._require_session()
        if interval not in self.VALID_INTERVALS:
            raise ValueError(f"interval must be one of {self.VALID_INTERVALS}")
        try:
            return self._kite.historical_data(
                instrument_token, from_date, to_date, interval
            )
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch historical data: {exc}") from exc

    def get_ltp(self, symbols: list[str]) -> dict[str, float]:
        """Last traded price for a list of 'EXCHANGE:SYMBOL' strings."""
        self._require_session()
        try:
            data = self._kite.ltp(symbols)
            return {k: v["last_price"] for k, v in data.items()}
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch LTP: {exc}") from exc

    def get_quote(self, symbols: list[str]) -> dict[str, Any]:
        self._require_session()
        try:
            return self._kite.quote(symbols)
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch quote: {exc}") from exc

    # ------------------------------------------------------------------
    # Orders (LIVE mode only - paper trading never calls these)
    # ------------------------------------------------------------------
    def place_order(
        self,
        symbol: str,
        transaction_type: str,  # "BUY" or "SELL"
        quantity: int,
        order_type: str = "MARKET",
        product: str = "CNC",  # CNC = delivery, MIS = intraday
        exchange: str = "NSE",
        price: Optional[float] = None,
        trigger_price: Optional[float] = None,
    ) -> str:
        self._require_session()
        try:
            order_id = self._kite.place_order(
                variety=self._kite.VARIETY_REGULAR,
                exchange=exchange,
                tradingsymbol=symbol,
                transaction_type=transaction_type,
                quantity=quantity,
                order_type=order_type,
                product=product,
                price=price,
                trigger_price=trigger_price,
            )
            logger.info(
                "LIVE order placed: %s %s x%d (order_id=%s)",
                transaction_type, symbol, quantity, order_id,
            )
            return order_id
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Order placement failed: {exc}") from exc

    def get_positions(self) -> dict[str, Any]:
        self._require_session()
        try:
            return self._kite.positions()
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch positions: {exc}") from exc

    def get_margins(self) -> dict[str, Any]:
        self._require_session()
        try:
            return self._kite.margins()
        except Exception as exc:  # noqa: BLE001
            raise KiteClientError(f"Failed to fetch margins: {exc}") from exc
