"""Time-series momentum: go long when trailing N-period return is positive
and above a threshold, go flat otherwise. Simple but a solid baseline for
comparing more complex strategies against."""
from __future__ import annotations

import pandas as pd

from backtest.strategies.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    name = "momentum"

    def __init__(self, lookback: int = 20, threshold: float = 0.0):
        super().__init__(lookback=lookback, threshold=threshold)
        self.lookback = lookback
        self.threshold = threshold

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        returns = df["close"].pct_change(self.lookback)
        signal = pd.Series(0, index=df.index, dtype=int)
        signal[returns > self.threshold] = 1
        signal[returns.isna()] = 0
        return signal
