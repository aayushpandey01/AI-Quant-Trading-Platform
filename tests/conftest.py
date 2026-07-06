import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Deterministic synthetic OHLCV data for reproducible tests."""
    rng = np.random.default_rng(7)
    n = 300
    dates = pd.bdate_range("2023-01-02", periods=n)
    returns = rng.normal(0.0006, 0.015, n)
    closes = 1000 * np.exp(np.cumsum(returns))
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.005
    lows = np.minimum(opens, closes) * 0.995
    volumes = rng.integers(100_000, 1_000_000, n)

    df = pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
    return df


@pytest.fixture
def trending_ohlcv() -> pd.DataFrame:
    """A strongly upward-trending series - useful for sanity-checking that
    trend-following strategies actually go long and make money on it."""
    n = 200
    dates = pd.bdate_range("2023-01-02", periods=n)
    closes = np.linspace(100, 250, n) + np.sin(np.linspace(0, 15, n)) * 2
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * 1.003
    lows = np.minimum(opens, closes) * 0.997
    volumes = np.full(n, 500_000)
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=dates,
    )
