"""
Fetches historical OHLCV data from Zerodha and persists it via DataStore.
Kite's API caps historical requests to ~60 days per call for minute data
(2000 days for daily), so this chunks requests automatically.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

from config.logging_config import get_logger
from data.data_store import DataStore, OHLCV
from data.kite_client import KiteClient

logger = get_logger(__name__)

# Zerodha's documented per-request limits by interval (days)
_CHUNK_DAYS = {
    "minute": 60, "3minute": 100, "5minute": 100, "10minute": 100,
    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000,
}


def _date_chunks(start: dt.date, end: dt.date, chunk_days: int):
    cur = start
    while cur < end:
        chunk_end = min(cur + dt.timedelta(days=chunk_days), end)
        yield cur, chunk_end
        cur = chunk_end + dt.timedelta(days=1)


def fetch_and_store(
    client: KiteClient,
    store: DataStore,
    symbol: str,
    from_date: dt.date,
    to_date: dt.date,
    interval: str = "day",
    exchange: str = "NSE",
) -> int:
    """Fetch historical candles for `symbol` and persist new ones. Returns rows inserted."""
    token = client.get_instrument_token(symbol, exchange)
    chunk_days = _CHUNK_DAYS.get(interval, 60)

    total_inserted = 0
    for start, end in _date_chunks(from_date, to_date, chunk_days):
        candles = client.get_historical_data(token, start, end, interval)
        total_inserted += store.upsert_ohlcv(symbol, candles)
        logger.info("Fetched %d candles for %s [%s -> %s]", len(candles), symbol, start, end)

    return total_inserted


def ohlcv_to_dataframe(rows: list[OHLCV]) -> pd.DataFrame:
    """Convert DataStore OHLCV rows into a pandas DataFrame indexed by timestamp."""
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame([{
        "timestamp": r.timestamp, "open": r.open, "high": r.high,
        "low": r.low, "close": r.close, "volume": r.volume,
    } for r in rows])
    df = df.set_index("timestamp").sort_index()
    return df
