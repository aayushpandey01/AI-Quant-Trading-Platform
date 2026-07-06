"""
Risk management sits between "strategy says go long" and "an order is
actually placed". Nothing reaches the order manager without passing
through here first. This is the single most important safety net in a
live/paper trading system - keep it simple and easy to reason about.
"""
from __future__ import annotations

from dataclasses import dataclass

from config.logging_config import get_logger
from config.settings import settings

logger = get_logger(__name__)


@dataclass
class RiskCheckResult:
    approved: bool
    reason: str = ""
    approved_quantity: int = 0


class RiskManager:
    def __init__(
        self,
        max_position_pct: float | None = None,
        max_portfolio_exposure_pct: float | None = None,
        default_stop_loss_pct: float | None = None,
        default_take_profit_pct: float | None = None,
    ) -> None:
        self.max_position_pct = max_position_pct or settings.max_position_pct
        self.max_portfolio_exposure_pct = (
            max_portfolio_exposure_pct or settings.max_portfolio_exposure_pct
        )
        self.default_stop_loss_pct = default_stop_loss_pct or settings.default_stop_loss_pct
        self.default_take_profit_pct = default_take_profit_pct or settings.default_take_profit_pct

    def size_position(
        self, equity: float, price: float, requested_pct: float | None = None
    ) -> int:
        """How many shares to buy given equity, price, and a target % allocation."""
        pct = min(requested_pct or self.max_position_pct, self.max_position_pct)
        budget = equity * pct
        if price <= 0:
            return 0
        return max(int(budget // price), 0)

    def check_new_position(
        self,
        symbol: str,
        quantity: int,
        price: float,
        equity: float,
        current_exposure: float,
        cash: float,
    ) -> RiskCheckResult:
        """Run all pre-trade checks. Returns an approved (possibly reduced) quantity."""
        if quantity <= 0:
            return RiskCheckResult(False, "quantity must be positive")

        order_value = quantity * price
        if order_value > cash:
            affordable_qty = int(cash // price)
            if affordable_qty <= 0:
                return RiskCheckResult(False, f"insufficient cash for {symbol}")
            quantity = affordable_qty
            order_value = quantity * price
            logger.warning("Reduced %s order to %d shares due to cash limit", symbol, quantity)

        max_position_value = equity * self.max_position_pct
        if order_value > max_position_value:
            quantity = max(int(max_position_value // price), 0)
            order_value = quantity * price
            if quantity == 0:
                return RiskCheckResult(False, f"{symbol} order exceeds max position size")
            logger.warning(
                "Reduced %s order to %d shares due to max_position_pct=%.1f%%",
                symbol, quantity, self.max_position_pct * 100,
            )

        max_exposure_value = equity * self.max_portfolio_exposure_pct
        if current_exposure + order_value > max_exposure_value:
            remaining = max(max_exposure_value - current_exposure, 0)
            quantity = int(remaining // price)
            if quantity <= 0:
                return RiskCheckResult(
                    False, "portfolio exposure limit reached - no room for new positions"
                )
            logger.warning(
                "Reduced %s order to %d shares due to portfolio exposure cap", symbol, quantity
            )

        return RiskCheckResult(True, "ok", approved_quantity=quantity)

    def compute_stop_take(self, entry_price: float) -> tuple[float, float]:
        stop_loss = entry_price * (1 - self.default_stop_loss_pct)
        take_profit = entry_price * (1 + self.default_take_profit_pct)
        return round(stop_loss, 2), round(take_profit, 2)

    def should_exit_on_stop(self, current_price: float, stop_loss: float, take_profit: float) -> str | None:
        """Returns 'stop_loss', 'take_profit', or None."""
        if stop_loss and current_price <= stop_loss:
            return "stop_loss"
        if take_profit and current_price >= take_profit:
            return "take_profit"
        return None
