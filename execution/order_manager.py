"""
Unified order manager. Same interface for paper and live trading, so a
strategy/loop written against this class doesn't care which mode it's
running in - only the .env TRADING_MODE setting changes behavior.

Paper mode: fills are simulated instantly at the given price (optionally
with slippage), positions and trades are written to the local DataStore.

Live mode: orders are routed through KiteClient to Zerodha. Positions are
still mirrored into the local DataStore for the dashboard, but the broker
is the source of truth for live mode.
"""
from __future__ import annotations

from config.logging_config import get_logger
from config.settings import TradingMode, settings
from data.data_store import DataStore
from data.kite_client import KiteClient

logger = get_logger(__name__)


class OrderManager:
    def __init__(
        self,
        store: DataStore,
        kite_client: KiteClient | None = None,
        mode: TradingMode | None = None,
        slippage_pct: float = 0.0005,
        commission_pct: float = 0.0003,
    ) -> None:
        self.store = store
        self.kite = kite_client
        self.mode = mode or settings.trading_mode
        self.slippage_pct = slippage_pct
        self.commission_pct = commission_pct

    # ------------------------------------------------------------------
    def buy(self, symbol: str, quantity: int, price: float, strategy: str | None = None) -> dict:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        if self.mode == TradingMode.LIVE:
            if self.kite is None:
                raise RuntimeError("LIVE mode requires a configured KiteClient")
            order_id = self.kite.place_order(symbol, "BUY", quantity)
            fill_price = price  # actual fill price would be polled from order history
        else:
            order_id = f"PAPER-{symbol}-{quantity}-BUY"
            fill_price = price * (1 + self.slippage_pct)

        commission = fill_price * quantity * self.commission_pct
        trade = self.store.record_trade(
            symbol=symbol, side="BUY", quantity=quantity, price=fill_price,
            mode=self.mode.value, strategy=strategy, order_id=order_id,
        )

        existing = self._get_position(symbol)
        if existing:
            total_qty = existing.quantity + quantity
            new_avg = ((existing.avg_price * existing.quantity) + (fill_price * quantity)) / total_qty
        else:
            total_qty = quantity
            new_avg = fill_price
        self.store.upsert_position(symbol, total_qty, new_avg)

        logger.info("BUY filled: %s x%d @ %.2f (mode=%s)", symbol, quantity, fill_price, self.mode.value)
        return {"order_id": order_id, "fill_price": fill_price, "commission": commission, "trade_id": trade.id}

    def sell(self, symbol: str, quantity: int, price: float, strategy: str | None = None) -> dict:
        if quantity <= 0:
            raise ValueError("quantity must be positive")

        existing = self._get_position(symbol)
        if not existing or existing.quantity < quantity:
            raise ValueError(f"Cannot sell {quantity} of {symbol}: insufficient position")

        if self.mode == TradingMode.LIVE:
            if self.kite is None:
                raise RuntimeError("LIVE mode requires a configured KiteClient")
            order_id = self.kite.place_order(symbol, "SELL", quantity)
            fill_price = price
        else:
            order_id = f"PAPER-{symbol}-{quantity}-SELL"
            fill_price = price * (1 - self.slippage_pct)

        commission = fill_price * quantity * self.commission_pct
        pnl = (fill_price - existing.avg_price) * quantity - commission

        trade = self.store.record_trade(
            symbol=symbol, side="SELL", quantity=quantity, price=fill_price,
            mode=self.mode.value, strategy=strategy, order_id=order_id, pnl=pnl,
        )

        remaining_qty = existing.quantity - quantity
        self.store.upsert_position(symbol, remaining_qty, existing.avg_price if remaining_qty > 0 else 0.0)

        logger.info(
            "SELL filled: %s x%d @ %.2f | pnl=%.2f (mode=%s)",
            symbol, quantity, fill_price, pnl, self.mode.value,
        )
        return {"order_id": order_id, "fill_price": fill_price, "commission": commission, "pnl": pnl, "trade_id": trade.id}

    def _get_position(self, symbol: str):
        for pos in self.store.get_positions():
            if pos.symbol == symbol:
                return pos
        return None
