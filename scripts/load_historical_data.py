"""
Loads REAL historical data from Zerodha into the local database. Requires
a configured KITE_API_KEY + a valid KITE_ACCESS_TOKEN (run scripts/login.py
first if you haven't today - access tokens expire every day).

Usage:
    python scripts/load_historical_data.py --symbols RELIANCE,TCS --days 500
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.logging_config import get_logger
from data.data_store import DataStore
from data.historical_loader import fetch_and_store
from data.kite_client import KiteClient, KiteClientError

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Load real NSE historical data via Zerodha Kite Connect")
    parser.add_argument("--symbols", type=str, required=True, help="Comma-separated tradingsymbols, e.g. RELIANCE,TCS")
    parser.add_argument("--days", type=int, default=500)
    parser.add_argument("--interval", type=str, default="day", choices=[
        "minute", "3minute", "5minute", "10minute", "15minute", "30minute", "60minute", "day",
    ])
    parser.add_argument("--exchange", type=str, default="NSE")
    args = parser.parse_args()

    client = KiteClient()
    if not client.is_configured():
        print(
            "ERROR: Kite client is not fully configured. Set KITE_API_KEY in .env, then run "
            "'python scripts/login.py' to obtain today's access token."
        )
        sys.exit(1)

    store = DataStore()
    store.init_db()

    to_date = dt.date.today()
    from_date = to_date - dt.timedelta(days=args.days)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    for symbol in symbols:
        try:
            inserted = fetch_and_store(client, store, symbol, from_date, to_date, args.interval, args.exchange)
            print(f"{symbol}: {inserted} new candles loaded")
        except KiteClientError as exc:
            print(f"{symbol}: FAILED - {exc}")


if __name__ == "__main__":
    main()
