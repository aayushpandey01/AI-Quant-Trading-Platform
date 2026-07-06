import numpy as np
import pandas as pd

from backtest import metrics


class TestMetrics:
    def test_cagr_flat_equity_is_zero(self):
        equity = pd.Series([100_000] * 252)
        assert metrics.cagr(equity) == pytest_approx(0.0)

    def test_cagr_doubling_in_a_year(self):
        equity = pd.Series(np.linspace(100_000, 200_000, 253))
        result = metrics.cagr(equity)
        assert 0.9 < result < 1.1  # ~100% return in a year

    def test_max_drawdown_no_drawdown(self):
        equity = pd.Series([100, 110, 120, 130])
        assert metrics.max_drawdown(equity) == 0.0

    def test_max_drawdown_detects_dip(self):
        equity = pd.Series([100, 120, 90, 130])
        dd = metrics.max_drawdown(equity)
        assert dd == pytest_approx((90 - 120) / 120)

    def test_sharpe_zero_when_no_variance(self):
        equity = pd.Series([100_000] * 100)
        assert metrics.sharpe_ratio(equity) == 0.0

    def test_win_rate(self):
        pnls = pd.Series([10, -5, 20, -1, None])
        assert metrics.win_rate(pnls) == 0.5

    def test_profit_factor(self):
        pnls = pd.Series([10, 10, -5])
        assert metrics.profit_factor(pnls) == pytest_approx(20 / 5)

    def test_profit_factor_no_losses(self):
        pnls = pd.Series([10, 10])
        assert metrics.profit_factor(pnls) == float("inf")

    def test_summarize_returns_expected_keys(self):
        equity = pd.Series(np.linspace(100_000, 110_000, 100))
        pnls = pd.Series([500, -200, 300])
        summary = metrics.summarize(equity, pnls)
        for key in ["total_return_pct", "cagr_pct", "sharpe_ratio", "sortino_ratio", "max_drawdown_pct", "win_rate_pct", "profit_factor", "num_trades"]:
            assert key in summary


def pytest_approx(value, tol=1e-6):
    from pytest import approx
    return approx(value, abs=tol)
