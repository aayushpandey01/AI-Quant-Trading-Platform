"""
Event-driven-ish backtest engine (vectorized signal generation, bar-by-bar
execution loop for realistic cash/position accounting).

Key design decisions, stated explicitly so results can be trusted:
- No lookahead bias: a strategy sees data up to and including bar t's close
  to produce a signal, but that signal is only *executed* at bar t+1's open.
  This mirrors reality - you can't trade on a close you haven't seen yet.
- Commission and slippage are charged on every fill, in percent terms.
- Position sizing is a fixed percent of *current* equity (not initial
  capital), so it compounds like real trading.
- Long-only by default (matches a cash equity/ETF account); short signals
  from a strategy are treated as "flat" unless `allow_short=True`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from backtest import metrics
from backtest.strategies.base import BaseStrategy
from config.logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class Trade:
    timestamp: pd.Timestamp
    side: str          # BUY / SELL
    quantity: int
    price: float
    commission: float
    pnl: float | None = None  # set on closing (SELL) trades


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    trades: list[Trade] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def trade_pnls(self) -> pd.Series:
        pnls = [t.pnl for t in self.trades if t.pnl is not None]
        return pd.Series(pnls, dtype=float)

    def to_dict(self) -> dict:
        return {
            "metrics": self.metrics,
            "equity_curve": [
                {"timestamp": ts.isoformat(), "equity": float(v)}
                for ts, v in self.equity_curve.items()
            ],
            "trades": [
                {
                    "timestamp": t.timestamp.isoformat(), "side": t.side,
                    "quantity": t.quantity, "price": round(t.price, 2),
                    "commission": round(t.commission, 2),
                    "pnl": round(t.pnl, 2) if t.pnl is not None else None,
                }
                for t in self.trades
            ],
        }


class BacktestEngine:
    def __init__(
        self,
        starting_capital: float = 100_000.0,
        commission_pct: float = 0.0003,   # ~ Zerodha delivery brokerage + STT/charges, approximate
        slippage_pct: float = 0.0005,
        position_size_pct: float = 0.10,  # % of equity risked per position
        allow_short: bool = False,
    ) -> None:
        self.starting_capital = starting_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct
        self.position_size_pct = position_size_pct
        self.allow_short = allow_short

    def run(self, strategy: BaseStrategy, df: pd.DataFrame) -> BacktestResult:
        if df.empty:
            raise ValueError("Cannot backtest on an empty DataFrame")
        required_cols = {"open", "high", "low", "close"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame missing required columns: {missing}")

        raw_signal = strategy.generate_signals(df)
        if not self.allow_short:
            raw_signal = raw_signal.clip(lower=0)

        # Execute on the NEXT bar's open, relative to the signal formed at
        # bar t's close - this is what prevents lookahead bias.
        exec_signal = raw_signal.shift(1).fillna(0).astype(int)

        cash = self.starting_capital
        shares = 0
        avg_entry_price = 0.0
        equity_curve = []
        trades: list[Trade] = []

        for i, (ts, row) in enumerate(df.iterrows()):
            target_position = exec_signal.iloc[i]  # 1 = long, 0 = flat (or -1 if shorting allowed)
            exec_price = row["open"]

            # --- Flat/short -> Long ---
            if target_position == 1 and shares <= 0:
                if shares < 0:  # cover short first
                    cover_price = exec_price * (1 + self.slippage_pct)
                    cost = -shares * cover_price
                    commission = cost * self.commission_pct
                    pnl = (avg_entry_price - cover_price) * (-shares) - commission
                    cash -= (cost + commission)
                    trades.append(Trade(ts, "BUY", -shares, cover_price, commission, pnl))
                    shares = 0

                equity_now = cash
                fill_price = exec_price * (1 + self.slippage_pct)
                budget = equity_now * self.position_size_pct
                qty = int(budget // fill_price)
                if qty > 0:
                    cost = qty * fill_price
                    commission = cost * self.commission_pct
                    cash -= (cost + commission)
                    shares = qty
                    avg_entry_price = fill_price
                    trades.append(Trade(ts, "BUY", qty, fill_price, commission, None))

            # --- Long -> Flat/short ---
            elif target_position <= 0 and shares > 0:
                fill_price = exec_price * (1 - self.slippage_pct)
                proceeds = shares * fill_price
                commission = proceeds * self.commission_pct
                pnl = (fill_price - avg_entry_price) * shares - commission
                cash += (proceeds - commission)
                trades.append(Trade(ts, "SELL", shares, fill_price, commission, pnl))
                shares = 0
                avg_entry_price = 0.0

                if target_position == -1 and self.allow_short:
                    fill_price_short = exec_price * (1 - self.slippage_pct)
                    budget = cash * self.position_size_pct
                    qty = int(budget // fill_price_short)
                    if qty > 0:
                        proceeds = qty * fill_price_short
                        commission = proceeds * self.commission_pct
                        cash += (proceeds - commission)
                        shares = -qty
                        avg_entry_price = fill_price_short
                        trades.append(Trade(ts, "SELL", qty, fill_price_short, commission, None))

            mark_price = row["close"]
            equity = cash + shares * mark_price
            equity_curve.append((ts, equity))

        equity_series = pd.Series(
            [e for _, e in equity_curve],
            index=[t for t, _ in equity_curve],
            name="equity",
        )

        result = BacktestResult(equity_curve=equity_series, trades=trades)
        pnl_series = result.trade_pnls()
        result.metrics = metrics.summarize(equity_series, pnl_series if len(pnl_series) else None)
        logger.info(
            "Backtest complete: %s | final_equity=%.2f | trades=%d",
            strategy.name, equity_series.iloc[-1] if len(equity_series) else 0, len(trades),
        )
        return result
