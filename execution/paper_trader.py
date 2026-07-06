"""
The trading loop that runs during market hours: pull latest prices, feed
them + recent history into a strategy, size and risk-check the resulting
signal, and execute through the OrderManager. Works in paper or live mode
depending on settings.trading_mode - the loop itself doesn't know or care.
"""
from __future__ import annotations

import datetime as dt
import time

import pandas as pd

from backtest.strategies.base import BaseStrategy
from config.logging_config import get_logger
from config.settings import settings
from data.data_store import DataStore
from data.historical_loader import ohlcv_to_dataframe
from data.kite_client import KiteClient
from execution.order_manager import OrderManager
from execution.risk_manager import RiskManager

logger = get_logger(__name__)

NSE_OPEN = dt.time(9, 15)
NSE_CLOSE = dt.time(15, 30)


class PaperTrader:
    def __init__(
        self,
        symbols: list[str],
        strategy: BaseStrategy,
        store: DataStore,
        kite_client: KiteClient,
        risk_manager: RiskManager | None = None,
        order_manager: OrderManager | None = None,
        poll_interval_seconds: int = 60,
        exchange: str = "NSE",
    ) -> None:
        self.symbols = symbols
        self.strategy = strategy
        self.store = store
        self.kite = kite_client
        self.risk = risk_manager or RiskManager()
        self.orders = order_manager or OrderManager(store, kite_client)
        self.poll_interval_seconds = poll_interval_seconds
        self.exchange = exchange
        self._cash = settings.starting_capital

    @staticmethod
    def is_market_open(now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now()
        if now.weekday() >= 5:  # Sat/Sun
            return False
        return NSE_OPEN <= now.time() <= NSE_CLOSE

    def current_equity(self) -> float:
        equity = self._cash
        for pos in self.store.get_positions():
            try:
                ltp = self.kite.get_ltp([f"{self.exchange}:{pos.symbol}"])
                price = ltp.get(f"{self.exchange}:{pos.symbol}", pos.avg_price)
            except Exception:  # noqa: BLE001
                price = pos.avg_price
            equity += pos.quantity * price
        return equity

    def process_symbol(self, symbol: str) -> None:
        rows = self.store.get_ohlcv(symbol)
        if len(rows) < 30:
            logger.warning("Not enough history for %s (%d rows) - skipping", symbol, len(rows))
            return

        df = ohlcv_to_dataframe(rows)
        try:
            ltp_data = self.kite.get_ltp([f"{self.exchange}:{symbol}"])
            latest_price = ltp_data[f"{self.exchange}:{symbol}"]
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not fetch LTP for %s: %s", symbol, exc)
            return

        # Append the live tick as today's provisional bar so the strategy sees it
        today = pd.Timestamp(dt.date.today())
        df.loc[today] = {
            "open": latest_price, "high": latest_price,
            "low": latest_price, "close": latest_price, "volume": 0,
        }

        signal = self.strategy.generate_signals(df)
        target_position = int(signal.iloc[-1])

        existing = next((p for p in self.store.get_positions() if p.symbol == symbol), None)
        held_qty = existing.quantity if existing else 0

        equity = self.current_equity()
        exposure = sum(
            p.quantity * latest_price for p in self.store.get_positions() if p.symbol != symbol
        )

        if target_position == 1 and held_qty == 0:
            qty = self.risk.size_position(equity, latest_price)
            check = self.risk.check_new_position(symbol, qty, latest_price, equity, exposure, self._cash)
            if check.approved and check.approved_quantity > 0:
                result = self.orders.buy(symbol, check.approved_quantity, latest_price, self.strategy.name)
                self._cash -= (result["fill_price"] * check.approved_quantity + result["commission"])
                stop_loss, take_profit = self.risk.compute_stop_take(result["fill_price"])
                self.store.upsert_position(symbol, check.approved_quantity, result["fill_price"], stop_loss, take_profit)
            else:
                logger.info("Risk manager rejected BUY for %s: %s", symbol, check.reason)

        elif target_position <= 0 and held_qty > 0:
            result = self.orders.sell(symbol, held_qty, latest_price, self.strategy.name)
            self._cash += (result["fill_price"] * held_qty - result["commission"])

        elif existing and existing.stop_loss:
            exit_reason = self.risk.should_exit_on_stop(latest_price, existing.stop_loss, existing.take_profit)
            if exit_reason:
                logger.info("%s triggered for %s at %.2f", exit_reason, symbol, latest_price)
                result = self.orders.sell(symbol, held_qty, latest_price, self.strategy.name)
                self._cash += (result["fill_price"] * held_qty - result["commission"])

    def run_once(self) -> None:
        for symbol in self.symbols:
            try:
                self.process_symbol(symbol)
            except Exception:  # noqa: BLE001
                logger.exception("Error processing %s", symbol)
        self.store.record_equity(self.current_equity(), self._cash, mode=settings.trading_mode.value)

    def run_forever(self) -> None:
        logger.info(
            "Starting %s trading loop for %s, poll every %ds",
            settings.trading_mode.value, self.symbols, self.poll_interval_seconds,
        )
        try:
            while True:
                if self.is_market_open():
                    self.run_once()
                else:
                    logger.debug("Market closed, sleeping")
                time.sleep(self.poll_interval_seconds)
        except KeyboardInterrupt:
            logger.info("Trading loop stopped by user")
