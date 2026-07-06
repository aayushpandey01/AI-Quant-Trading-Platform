"""
Persistence layer. Uses SQLAlchemy so the same code works against SQLite
(default, zero-setup) or Postgres (set DATABASE_URL to a postgres:// URL
for a heavier personal/production setup) without changes.

Tables:
    ohlcv           - historical + incrementally updated candle data
    trades          - every simulated or live fill
    positions       - current open positions (paper or live)
    equity_curve    - snapshot of portfolio value over time, for the dashboard
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import (
    Column, DateTime, Float, Integer, String, UniqueConstraint, create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.logging_config import get_logger
from config.settings import settings

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class OHLCV(Base):
    __tablename__ = "ohlcv"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0.0)

    __table_args__ = (UniqueConstraint("symbol", "timestamp", name="uq_symbol_ts"),)


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, index=True)
    side = Column(String, nullable=False)          # BUY / SELL
    quantity = Column(Integer, nullable=False)
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, nullable=False, default=dt.datetime.utcnow)
    mode = Column(String, nullable=False, default="paper")  # paper / live / backtest
    strategy = Column(String, nullable=True)
    order_id = Column(String, nullable=True)
    pnl = Column(Float, nullable=True)              # realized PnL, set on closing trades


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False, unique=True, index=True)
    quantity = Column(Integer, nullable=False, default=0)
    avg_price = Column(Float, nullable=False, default=0.0)
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)


class EquitySnapshot(Base):
    __tablename__ = "equity_curve"
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, default=dt.datetime.utcnow, index=True)
    equity = Column(Float, nullable=False)
    cash = Column(Float, nullable=False)
    mode = Column(String, nullable=False, default="paper")


class DataStore:
    """Owns the DB engine/session factory and exposes typed helper methods."""

    def __init__(self, database_url: Optional[str] = None) -> None:
        self.database_url = database_url or settings.database_url
        connect_args = {"check_same_thread": False} if "sqlite" in self.database_url else {}
        self.engine = create_engine(self.database_url, connect_args=connect_args)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine)
        logger.info("Database tables created/verified at %s", self.database_url)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.SessionLocal()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------
    def upsert_ohlcv(self, symbol: str, rows: list[dict]) -> int:
        """Insert candles, skipping ones that already exist (symbol+timestamp unique)."""
        if not rows:
            return 0
        inserted = 0
        with self.session() as s:
            existing = {
                ts for (ts,) in s.query(OHLCV.timestamp).filter(OHLCV.symbol == symbol)
            }
            for row in rows:
                ts = row["date"] if "date" in row else row["timestamp"]
                if hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()
                if isinstance(ts, dt.datetime) and ts.tzinfo is not None:
                    ts = ts.replace(tzinfo=None)
                if ts in existing:
                    continue
                s.add(OHLCV(
                    symbol=symbol, timestamp=ts,
                    open=float(row["open"]), high=float(row["high"]),
                    low=float(row["low"]), close=float(row["close"]),
                    volume=float(row.get("volume", 0.0)),
                ))
                inserted += 1
        logger.info("Upserted %d new candles for %s", inserted, symbol)
        return inserted

    def get_ohlcv(
        self, symbol: str, start: Optional[dt.datetime] = None,
        end: Optional[dt.datetime] = None,
    ) -> list[OHLCV]:
        with self.session() as s:
            q = s.query(OHLCV).filter(OHLCV.symbol == symbol)
            if start:
                q = q.filter(OHLCV.timestamp >= start)
            if end:
                q = q.filter(OHLCV.timestamp <= end)
            return q.order_by(OHLCV.timestamp.asc()).all()

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------
    def record_trade(
        self, symbol: str, side: str, quantity: int, price: float,
        mode: str = "paper", strategy: Optional[str] = None,
        order_id: Optional[str] = None, pnl: Optional[float] = None,
        timestamp: Optional[dt.datetime] = None,
    ) -> Trade:
        with self.session() as s:
            trade = Trade(
                symbol=symbol, side=side, quantity=quantity, price=price,
                mode=mode, strategy=strategy, order_id=order_id, pnl=pnl,
                timestamp=timestamp or dt.datetime.utcnow(),
            )
            s.add(trade)
            s.flush()
            s.refresh(trade)
            return trade

    def get_trades(self, mode: Optional[str] = None) -> list[Trade]:
        with self.session() as s:
            q = s.query(Trade)
            if mode:
                q = q.filter(Trade.mode == mode)
            return q.order_by(Trade.timestamp.asc()).all()

    # ------------------------------------------------------------------
    # Positions
    # ------------------------------------------------------------------
    def upsert_position(
        self, symbol: str, quantity: int, avg_price: float,
        stop_loss: Optional[float] = None, take_profit: Optional[float] = None,
    ) -> None:
        with self.session() as s:
            pos = s.query(Position).filter(Position.symbol == symbol).first()
            if pos is None:
                pos = Position(symbol=symbol)
                s.add(pos)
            pos.quantity = quantity
            pos.avg_price = avg_price
            pos.stop_loss = stop_loss
            pos.take_profit = take_profit
            pos.updated_at = dt.datetime.utcnow()

    def get_positions(self) -> list[Position]:
        with self.session() as s:
            return s.query(Position).filter(Position.quantity != 0).all()

    def close_position(self, symbol: str) -> None:
        with self.session() as s:
            pos = s.query(Position).filter(Position.symbol == symbol).first()
            if pos:
                pos.quantity = 0
                pos.updated_at = dt.datetime.utcnow()

    # ------------------------------------------------------------------
    # Equity curve
    # ------------------------------------------------------------------
    def record_equity(self, equity: float, cash: float, mode: str = "paper") -> None:
        with self.session() as s:
            s.add(EquitySnapshot(equity=equity, cash=cash, mode=mode))

    def get_equity_curve(self, mode: Optional[str] = None) -> list[EquitySnapshot]:
        with self.session() as s:
            q = s.query(EquitySnapshot)
            if mode:
                q = q.filter(EquitySnapshot.mode == mode)
            return q.order_by(EquitySnapshot.timestamp.asc()).all()
