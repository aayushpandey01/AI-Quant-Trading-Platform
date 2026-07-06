"""
Single entry point for the platform. Everything can also be run via the
individual scripts in scripts/, but this gives one command to remember.

Usage:
    python main.py dashboard [--port 8000] [--reload]
    python main.py generate-sample-data [--symbols RELIANCE,TCS] [--days 500]
    python main.py backtest --symbol RELIANCE --strategy sma_crossover
    python main.py trade --symbols RELIANCE,TCS --strategy sma_crossover
    python main.py login
    python main.py load-data --symbols RELIANCE,TCS --days 500

Any flags after the subcommand are passed straight through to the
underlying script, so `python main.py backtest -h` shows that script's
own help.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PASS_THROUGH_SCRIPTS = {
    "generate-sample-data": ROOT / "scripts" / "generate_sample_data.py",
    "backtest": ROOT / "scripts" / "run_backtest.py",
    "trade": ROOT / "scripts" / "run_paper_trader.py",
    "load-data": ROOT / "scripts" / "load_historical_data.py",
    "login": ROOT / "scripts" / "login.py",
}


def run_dashboard(rest: list[str]) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="main.py dashboard")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args(rest)

    import uvicorn
    from config.settings import settings

    uvicorn.run(
        "dashboard.backend:app",
        host=settings.dashboard_host,
        port=args.port or settings.dashboard_port,
        reload=args.reload,
    )
    return 0


def print_top_level_help() -> None:
    print(__doc__)
    print("Available commands:")
    print("  dashboard              Start the FastAPI + web dashboard")
    print("  generate-sample-data   Generate synthetic OHLCV data (no API key needed)")
    print("  backtest                Run a backtest against stored data")
    print("  trade                   Run the paper/live trading loop")
    print("  login                   Run the daily Zerodha login flow")
    print("  load-data               Load real historical data via Zerodha Kite Connect")


def main() -> int:
    argv = sys.argv[1:]
    if not argv or argv[0] in ("-h", "--help"):
        print_top_level_help()
        return 0

    command, rest = argv[0], argv[1:]

    if command == "dashboard":
        return run_dashboard(rest)

    if command in PASS_THROUGH_SCRIPTS:
        result = subprocess.run([sys.executable, str(PASS_THROUGH_SCRIPTS[command])] + rest)
        return result.returncode

    print(f"Unknown command: {command}\n")
    print_top_level_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
