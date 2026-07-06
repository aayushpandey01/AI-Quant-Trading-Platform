"""Mean-reversion strategy: buy when RSI dips into oversold territory,
exit when it climbs back to/above the midline (or into overbought)."""
from __future__ import annotations

import pandas as pd

from backtest.strategies.base import BaseStrategy


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-12)
    return 100 - (100 / (1 + rs))


class RSIMeanReversionStrategy(BaseStrategy):
    name = "rsi_mean_reversion"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 55):
        super().__init__(period=period, oversold=oversold, overbought=overbought)
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        rsi = _rsi(df["close"], self.period)

        position = 0
        values = [0] * len(df)
        rsi_vals = rsi.to_numpy()
        for i in range(len(df)):
            r = rsi_vals[i]
            if pd.isna(r):
                values[i] = 0
                continue
            if position == 0 and r < self.oversold:
                position = 1
            elif position == 1 and r >= self.overbought:
                position = 0
            values[i] = position
        return pd.Series(values, index=df.index, dtype=int)
