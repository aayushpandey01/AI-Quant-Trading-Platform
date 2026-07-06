"""
Generates realistic-looking synthetic OHLCV data and loads it into the
local database. This lets you exercise the entire backtest engine and
dashboard WITHOUT a Zerodha API subscription - useful for development,
demos, and this being a college/portfolio project where you want something
runnable out of the box.

Once you have real Kite Connect credentials, use
`scripts/load_historical_data.py` instead to pull real NSE data.

Usage:
    python scripts/generate_sample_data.py
    python scripts/generate_sample_data.py --symbols RELIANCE,TCS,INFY --days 750
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger
from data.data_store import DataStore

logger = get_logger(__name__)

DEFAULT_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK"]
# rough starting prices so the synthetic series look plausible
BASE_PRICES = {"RELIANCE": 2900, "TCS": 3800, "INFY": 1600, "HDFCBANK": 1650}


def generate_gbm_series(
    start_price: float, n_days: int, mu: float = 0.10, sigma: float = 0.22, seed: int | None = None
) -> pd.DataFrame:
    """
    Geometric Brownian Motion daily closes, plus a simple model for
    open/high/low derived from the close-to-close move so candles look
    like real OHLC bars (not just flat close==open==high==low).
    """
    rng = np.random.default_rng(seed)
    dt_frac = 1 / 252
    daily_returns = rng.normal((mu - 0.5 * sigma**2) * dt_frac, sigma * np.sqrt(dt_frac), n_days)
    closes = start_price * np.exp(np.cumsum(daily_returns))

    opens = np.empty(n_days)
    opens[0] = start_price
    opens[1:] = closes[:-1] * (1 + rng.normal(0, 0.002, n_days - 1))

    intraday_range = np.abs(rng.normal(0.012, 0.006, n_days))
    highs = np.maximum(opens, closes) * (1 + intraday_range)
    lows = np.minimum(opens, closes) * (1 - intraday_range)
    volumes = rng.integers(500_000, 5_000_000, n_days)

    dates = pd.bdate_range(end=dt.date.today() - dt.timedelta(days=1), periods=n_days)
    return pd.DataFrame({
        "date": dates, "open": opens, "high": highs, "low": lows,
        "close": closes, "volume": volumes,
    })


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic OHLCV data for backtesting/dashboard demos")
    parser.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS))
    parser.add_argument("--days", type=int, default=500, help="Number of trading days of history to generate")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    store = DataStore()
    store.init_db()

    for i, symbol in enumerate(symbols):
        base_price = BASE_PRICES.get(symbol, 1000.0)
        df = generate_gbm_series(base_price, args.days, seed=args.seed + i)
        rows = df.to_dict("records")
        inserted = store.upsert_ohlcv(symbol, rows)
        logger.info("Generated %d synthetic candles for %s (%d new)", len(rows), symbol, inserted)

    print(f"\nDone. Loaded synthetic data for: {', '.join(symbols)}")
    print("Try it now:")
    print("  python scripts/run_backtest.py --symbol RELIANCE --strategy sma_crossover")
    print("  python main.py dashboard   (then open http://localhost:8000)")


if __name__ == "__main__":
    main()
