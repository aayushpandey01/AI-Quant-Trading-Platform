"""Standard quant performance metrics computed from an equity curve and/or trade log."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def returns_from_equity(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def cagr(equity: pd.Series, periods_per_year: int = TRADING_DAYS_PER_YEAR) -> float:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return 0.0
    n_periods = len(equity) - 1
    total_return = equity.iloc[-1] / equity.iloc[0]
    years = n_periods / periods_per_year
    if years <= 0:
        return 0.0
    return float(total_return ** (1 / years) - 1)


def sharpe_ratio(
    equity: pd.Series, risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    rets = returns_from_equity(equity)
    if rets.std() == 0 or len(rets) < 2:
        return 0.0
    excess = rets - (risk_free_rate / periods_per_year)
    return float(np.sqrt(periods_per_year) * excess.mean() / rets.std())


def sortino_ratio(
    equity: pd.Series, risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    rets = returns_from_equity(equity)
    downside = rets[rets < 0]
    if downside.std() == 0 or len(rets) < 2:
        return 0.0
    excess = rets - (risk_free_rate / periods_per_year)
    return float(np.sqrt(periods_per_year) * excess.mean() / downside.std())


def max_drawdown(equity: pd.Series) -> float:
    """Returns max drawdown as a negative fraction, e.g. -0.23 for a 23% drawdown."""
    if equity.empty:
        return 0.0
    running_max = equity.cummax()
    drawdown = (equity - running_max) / running_max
    return float(drawdown.min())


def win_rate(trade_pnls: pd.Series) -> float:
    closed = trade_pnls.dropna()
    if closed.empty:
        return 0.0
    return float((closed > 0).sum() / len(closed))


def profit_factor(trade_pnls: pd.Series) -> float:
    closed = trade_pnls.dropna()
    gains = closed[closed > 0].sum()
    losses = -closed[closed < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return float(gains / losses)


def summarize(equity: pd.Series, trade_pnls: pd.Series | None = None) -> dict:
    """One-stop summary dict, used by the backtest engine, CLI, and dashboard."""
    result = {
        "total_return_pct": round((equity.iloc[-1] / equity.iloc[0] - 1) * 100, 2) if len(equity) > 1 else 0.0,
        "cagr_pct": round(cagr(equity) * 100, 2),
        "sharpe_ratio": round(sharpe_ratio(equity), 3),
        "sortino_ratio": round(sortino_ratio(equity), 3),
        "max_drawdown_pct": round(max_drawdown(equity) * 100, 2),
        "final_equity": round(float(equity.iloc[-1]), 2) if len(equity) else 0.0,
    }
    if trade_pnls is not None and len(trade_pnls.dropna()) > 0:
        result["win_rate_pct"] = round(win_rate(trade_pnls) * 100, 2)
        result["profit_factor"] = round(profit_factor(trade_pnls), 3)
        result["num_trades"] = int(trade_pnls.dropna().shape[0])
    return result
