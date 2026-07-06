import datetime as dt

import pytest

from data.data_store import DataStore


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = DataStore(database_url=f"sqlite:///{db_path}")
    s.init_db()
    return s


class TestOHLCV:
    def test_upsert_and_retrieve(self, store):
        rows = [
            {"date": dt.datetime(2024, 1, 1), "open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000},
            {"date": dt.datetime(2024, 1, 2), "open": 102, "high": 108, "low": 101, "close": 106, "volume": 1200},
        ]
        inserted = store.upsert_ohlcv("TEST", rows)
        assert inserted == 2
        fetched = store.get_ohlcv("TEST")
        assert len(fetched) == 2
        assert fetched[0].close == 102

    def test_upsert_is_idempotent(self, store):
        rows = [{"date": dt.datetime(2024, 1, 1), "open": 100, "high": 105, "low": 99, "close": 102, "volume": 1000}]
        store.upsert_ohlcv("TEST", rows)
        second_insert = store.upsert_ohlcv("TEST", rows)
        assert second_insert == 0
        assert len(store.get_ohlcv("TEST")) == 1


class TestTrades:
    def test_record_and_retrieve_trade(self, store):
        trade = store.record_trade("TCS", "BUY", 10, 3500.0, mode="paper")
        assert trade.id is not None
        trades = store.get_trades(mode="paper")
        assert len(trades) == 1
        assert trades[0].symbol == "TCS"

    def test_filter_trades_by_mode(self, store):
        store.record_trade("TCS", "BUY", 10, 3500.0, mode="paper")
        store.record_trade("TCS", "BUY", 5, 3500.0, mode="backtest")
        assert len(store.get_trades(mode="paper")) == 1
        assert len(store.get_trades(mode="backtest")) == 1
        assert len(store.get_trades()) == 2


class TestPositions:
    def test_upsert_position(self, store):
        store.upsert_position("TCS", 10, 3500.0, stop_loss=3400, take_profit=3700)
        positions = store.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10

    def test_closing_position_removes_from_active_list(self, store):
        store.upsert_position("TCS", 10, 3500.0)
        store.close_position("TCS")
        assert len(store.get_positions()) == 0


class TestEquityCurve:
    def test_record_and_retrieve_equity(self, store):
        store.record_equity(105_000, 20_000, mode="paper")
        store.record_equity(107_000, 18_000, mode="paper")
        curve = store.get_equity_curve(mode="paper")
        assert len(curve) == 2
        assert curve[-1].equity == 107_000
