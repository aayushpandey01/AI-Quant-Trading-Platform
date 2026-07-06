"""
CLI to run a backtest and print a clean results summary.

Usage:
    python scripts/run_backtest.py --symbol RELIANCE --strategy sma_crossover
    python scripts/run_backtest.py --symbol TCS --strategy rsi_mean_reversion --capital 200000
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.engine import BacktestEngine
from backtest.strategies.momentum import MomentumStrategy
from backtest.strategies.rsi_meanreversion import RSIMeanReversionStrategy
from backtest.strategies.sma_crossover import SMACrossoverStrategy
from data.data_store import DataStore
from data.historical_loader import ohlcv_to_dataframe

STRATEGIES = {
    "sma_crossover": lambda: SMACrossoverStrategy(),
    "rsi_mean_reversion": lambda: RSIMeanReversionStrategy(),
    "momentum": lambda: MomentumStrategy(),
}


def main():
    parser = argparse.ArgumentParser(description="Run a backtest against locally stored OHLCV data")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--strategy", choices=list(STRATEGIES), default="sma_crossover")
    parser.add_argument("--capital", type=float, default=100_000.0)
    parser.add_argument("--position-size", type=float, default=0.10, help="Fraction of equity per position")
    args = parser.parse_args()

    store = DataStore()
    store.init_db()
    rows = store.get_ohlcv(args.symbol)
    if len(rows) < 30:
        print(f"Not enough data for {args.symbol} ({len(rows)} rows).")
        print("Run: python scripts/generate_sample_data.py   (for synthetic test data)")
        print("or:  python scripts/load_historical_data.py --symbols " + args.symbol)
        sys.exit(1)

    df = ohlcv_to_dataframe(rows)
    strategy = STRATEGIES[args.strategy]()
    engine = BacktestEngine(starting_capital=args.capital, position_size_pct=args.position_size)
    result = engine.run(strategy, df)

    print(f"\n{'=' * 50}")
    print(f"Backtest: {strategy.name} on {args.symbol}")
    print(f"Period:   {df.index[0].date()} -> {df.index[-1].date()}  ({len(df)} bars)")
    print(f"{'=' * 50}")
    for key, value in result.metrics.items():
        label = key.replace("_", " ").title()
        print(f"{label:<20}: {value}")
    print(f"{'=' * 50}\n")


if __name__ == "__main__":
    main()
