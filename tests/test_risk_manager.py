import pytest

from execution.risk_manager import RiskManager


class TestRiskManager:
    def test_size_position_basic(self):
        rm = RiskManager(max_position_pct=0.10)
        qty = rm.size_position(equity=100_000, price=100)
        assert qty == 100  # 10% of 100k = 10k / 100 = 100 shares

    def test_size_position_zero_price_is_safe(self):
        rm = RiskManager()
        assert rm.size_position(equity=100_000, price=0) == 0

    def test_rejects_negative_quantity(self):
        rm = RiskManager()
        result = rm.check_new_position("TCS", -5, 100, 100_000, 0, 100_000)
        assert result.approved is False

    def test_reduces_quantity_when_exceeding_cash(self):
        rm = RiskManager(max_position_pct=1.0)
        result = rm.check_new_position("TCS", 1000, 100, 100_000, 0, cash=5_000)
        assert result.approved is True
        assert result.approved_quantity == 50  # 5000 cash / 100 price

    def test_reduces_quantity_when_exceeding_max_position_pct(self):
        rm = RiskManager(max_position_pct=0.05)
        result = rm.check_new_position("TCS", 1000, 100, equity=100_000, current_exposure=0, cash=200_000)
        assert result.approved is True
        assert result.approved_quantity == 50  # 5% of 100k = 5000 / 100

    def test_rejects_when_exposure_cap_reached(self):
        rm = RiskManager(max_position_pct=1.0, max_portfolio_exposure_pct=0.5)
        result = rm.check_new_position(
            "TCS", 100, 100, equity=100_000, current_exposure=50_000, cash=100_000
        )
        assert result.approved is False

    def test_stop_take_profit_computation(self):
        rm = RiskManager(default_stop_loss_pct=0.02, default_take_profit_pct=0.05)
        stop, take = rm.compute_stop_take(entry_price=100)
        assert stop == 98.0
        assert take == 105.0

    def test_should_exit_on_stop_loss(self):
        rm = RiskManager()
        assert rm.should_exit_on_stop(95, stop_loss=98, take_profit=110) == "stop_loss"

    def test_should_exit_on_take_profit(self):
        rm = RiskManager()
        assert rm.should_exit_on_stop(112, stop_loss=98, take_profit=110) == "take_profit"

    def test_no_exit_within_bounds(self):
        rm = RiskManager()
        assert rm.should_exit_on_stop(102, stop_loss=98, take_profit=110) is None
