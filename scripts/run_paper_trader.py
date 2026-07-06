"""
Starts the paper (or live, depending on .env TRADING_MODE) trading loop.

Usage:
    python scripts/run_paper_trader.py --symbols RELIANCE,TCS --strategy sma_crossover
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backtest.strategies.momentum import MomentumStrategy
from backtest.strategies.rsi_meanreversion import RSIMeanReversionStrategy
from backtest.strategies.sma_crossover import SMACrossoverStrategy
from config.settings import settings
from data.data_store import DataStore
from data.kite_client import KiteClient
from execution.order_manager import OrderManager
from execution.paper_trader import PaperTrader
from execution.risk_manager import RiskManager

STRATEGIES = {
    "sma_crossover": lambda: SMACrossoverStrategy(),
    "rsi_mean_reversion": lambda: RSIMeanReversionStrategy(),
    "momentum": lambda: MomentumStrategy(),
}


def main():
    parser = argparse.ArgumentParser(description="Run the paper/live trading loop")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols, e.g. RELIANCE,TCS")
    parser.add_argument("--strategy", choices=list(STRATEGIES), default="sma_crossover")
    parser.add_argument("--poll-seconds", type=int, default=60)
    args = parser.parse_args()

    client = KiteClient()
    if not client.is_configured():
        print(
            "ERROR: Kite client not configured. This loop needs live prices, so it "
            "requires KITE_API_KEY + a valid access token (run scripts/login.py)."
        )
        sys.exit(1)

    store = DataStore()
    store.init_db()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    strategy = STRATEGIES[args.strategy]()
    risk = RiskManager()
    orders = OrderManager(store, client)

    print(f"Starting {settings.trading_mode.value.upper()} trading loop")
    print(f"Symbols: {symbols} | Strategy: {strategy.name} | Poll every {args.poll_seconds}s")
    print("Press Ctrl+C to stop.\n")

    trader = PaperTrader(
        symbols=symbols, strategy=strategy, store=store, kite_client=client,
        risk_manager=risk, order_manager=orders, poll_interval_seconds=args.poll_seconds,
    )
    trader.run_forever()


if __name__ == "__main__":
    main()
