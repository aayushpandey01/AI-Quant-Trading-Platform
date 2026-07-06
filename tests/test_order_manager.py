import pytest

from config.settings import TradingMode
from data.data_store import DataStore
from execution.order_manager import OrderManager


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = DataStore(database_url=f"sqlite:///{db_path}")
    s.init_db()
    return s


@pytest.fixture
def order_manager(store):
    return OrderManager(store, kite_client=None, mode=TradingMode.PAPER)


class TestPaperBuy:
    def test_buy_creates_trade_and_position(self, order_manager, store):
        result = order_manager.buy("TCS", 10, 3500.0, strategy="test_strategy")
        assert result["order_id"].startswith("PAPER-")
        positions = store.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10

    def test_buy_applies_slippage(self, order_manager):
        result = order_manager.buy("TCS", 10, 100.0)
        assert result["fill_price"] > 100.0  # buys fill slightly above quoted price

    def test_rejects_zero_quantity(self, order_manager):
        with pytest.raises(ValueError):
            order_manager.buy("TCS", 0, 100.0)

    def test_averaging_into_existing_position(self, order_manager, store):
        order_manager.buy("TCS", 10, 100.0)
        order_manager.buy("TCS", 10, 200.0)
        positions = store.get_positions()
        assert positions[0].quantity == 20
        # average price should be between 100 and 200
        assert 100 < positions[0].avg_price < 200


class TestPaperSell:
    def test_sell_without_position_raises(self, order_manager):
        with pytest.raises(ValueError):
            order_manager.sell("TCS", 10, 100.0)

    def test_sell_reduces_position(self, order_manager, store):
        order_manager.buy("TCS", 10, 100.0)
        order_manager.sell("TCS", 5, 110.0)
        positions = store.get_positions()
        assert positions[0].quantity == 5

    def test_sell_full_position_removes_it(self, order_manager, store):
        order_manager.buy("TCS", 10, 100.0)
        order_manager.sell("TCS", 10, 110.0)
        assert len(store.get_positions()) == 0

    def test_sell_computes_pnl(self, order_manager):
        order_manager.buy("TCS", 10, 100.0)
        result = order_manager.sell("TCS", 10, 120.0)
        assert result["pnl"] > 0  # sold higher than bought
