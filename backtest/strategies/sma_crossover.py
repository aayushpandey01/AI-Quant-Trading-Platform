"""Classic trend-following strategy: go long when a fast SMA crosses above
a slow SMA, go flat (or short) when it crosses back below."""
from __future__ import annotations

import pandas as pd

from backtest.strategies.base import BaseStrategy


class SMACrossoverStrategy(BaseStrategy):
    name = "sma_crossover"

    def __init__(self, fast_window: int = 20, slow_window: int = 50, allow_short: bool = False):
        if fast_window >= slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        super().__init__(fast_window=fast_window, slow_window=slow_window, allow_short=allow_short)
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.allow_short = allow_short

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        fast = df["close"].rolling(self.fast_window, min_periods=self.fast_window).mean()
        slow = df["close"].rolling(self.slow_window, min_periods=self.slow_window).mean()

        signal = pd.Series(0, index=df.index, dtype=int)
        long_mask = fast > slow
        signal[long_mask] = 1
        if self.allow_short:
            signal[~long_mask & fast.notna() & slow.notna()] = -1

        # No signal until both averages are defined
        signal[slow.isna()] = 0
        return signal
