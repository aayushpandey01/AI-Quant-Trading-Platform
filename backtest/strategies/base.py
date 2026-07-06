"""
Strategy interface. Every strategy (rule-based or ML-based) implements
`generate_signals`, which turns an OHLCV DataFrame into a target-position
series. This is the one contract the backtest engine, paper trader, and
live executor all depend on - write a strategy once, run it anywhere.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseStrategy(ABC):
    """
    Subclass this and implement `generate_signals`.

    `generate_signals` must return a pandas Series, aligned with `df.index`,
    of target positions:
        1  -> be long
        0  -> be flat
       -1  -> be short (ignored by the risk manager if short-selling is
              disabled, which is the default for a cash equity account)

    Strategies should be stateless functions of the data passed in - do not
    reach out to global state - so the same class can run in backtest,
    paper, and live modes unmodified.
    """

    name: str = "base_strategy"

    def __init__(self, **params) -> None:
        self.params = params

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """df has columns: open, high, low, close, volume, indexed by timestamp."""
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{self.__class__.__name__} params={self.params}>"
