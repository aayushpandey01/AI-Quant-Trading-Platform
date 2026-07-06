"""
FastAPI backend for the dashboard. Serves both the REST API (equity curve,
positions, trades, on-demand backtests) and the static frontend.

Run with:
    uvicorn dashboard.backend:app --reload --port 8000
or:
    python main.py dashboard
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backtest.engine import BacktestEngine
from backtest.strategies.momentum import MomentumStrategy
from backtest.strategies.rsi_meanreversion import RSIMeanReversionStrategy
from backtest.strategies.sma_crossover import SMACrossoverStrategy
from config.logging_config import get_logger
from config.settings import settings
from data.data_store import DataStore
from data.historical_loader import ohlcv_to_dataframe

logger = get_logger(__name__)

app = FastAPI(title="AI Quant Trading Platform", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = DataStore()
store.init_db()

STRATEGY_REGISTRY = {
    "sma_crossover": SMACrossoverStrategy,
    "rsi_mean_reversion": RSIMeanReversionStrategy,
    "momentum": MomentumStrategy,
}


@app.get("/api/health")
def health():
    return {"status": "ok", "trading_mode": settings.trading_mode.value}


@app.get("/api/symbols")
def list_symbols():
    with store.session() as s:
        from data.data_store import OHLCV
        symbols = [row[0] for row in s.query(OHLCV.symbol).distinct().all()]
    return {"symbols": symbols}


@app.get("/api/equity-curve")
def equity_curve(mode: str = Query(default="paper")):
    rows = store.get_equity_curve(mode=mode)
    return {
        "mode": mode,
        "points": [
            {"timestamp": r.timestamp.isoformat(), "equity": r.equity, "cash": r.cash}
            for r in rows
        ],
    }


@app.get("/api/positions")
def positions():
    rows = store.get_positions()
    return {
        "positions": [
            {
                "symbol": p.symbol, "quantity": p.quantity, "avg_price": p.avg_price,
                "stop_loss": p.stop_loss, "take_profit": p.take_profit,
                "updated_at": p.updated_at.isoformat(),
            }
            for p in rows
        ]
    }


@app.get("/api/trades")
def trades(mode: Optional[str] = None):
    rows = store.get_trades(mode=mode)
    return {
        "trades": [
            {
                "id": t.id, "symbol": t.symbol, "side": t.side, "quantity": t.quantity,
                "price": t.price, "timestamp": t.timestamp.isoformat(), "mode": t.mode,
                "strategy": t.strategy, "pnl": t.pnl,
            }
            for t in rows
        ]
    }


@app.get("/api/backtest")
def run_backtest(
    symbol: str,
    strategy: str = Query(default="sma_crossover"),
    starting_capital: float = Query(default=100_000.0),
    position_size_pct: float = Query(default=0.10),
    fast_window: int = Query(default=20),
    slow_window: int = Query(default=50),
    rsi_period: int = Query(default=14),
    oversold: float = Query(default=30.0),
    overbought: float = Query(default=55.0),
    lookback: int = Query(default=20),
):
    if strategy not in STRATEGY_REGISTRY:
        raise HTTPException(400, f"Unknown strategy '{strategy}'. Choose from {list(STRATEGY_REGISTRY)}")

    rows = store.get_ohlcv(symbol)
    if len(rows) < 30:
        raise HTTPException(
            404,
            f"Not enough data for {symbol} ({len(rows)} rows). "
            "Load historical data first (see README / scripts/generate_sample_data.py).",
        )
    df = ohlcv_to_dataframe(rows)

    if strategy == "sma_crossover":
        strat = SMACrossoverStrategy(fast_window=fast_window, slow_window=slow_window)
    elif strategy == "rsi_mean_reversion":
        strat = RSIMeanReversionStrategy(period=rsi_period, oversold=oversold, overbought=overbought)
    else:
        strat = MomentumStrategy(lookback=lookback)

    engine = BacktestEngine(starting_capital=starting_capital, position_size_pct=position_size_pct)
    result = engine.run(strat, df)
    return result.to_dict()


# --- Static frontend (must be mounted last so /api routes take priority) ---
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
