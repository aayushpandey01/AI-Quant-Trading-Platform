import pandas as pd
import pytest

from backtest.engine import BacktestEngine
from backtest.strategies.base import BaseStrategy
from backtest.strategies.sma_crossover import SMACrossoverStrategy


class AlwaysLongStrategy(BaseStrategy):
    name = "always_long"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(1, index=df.index)


class AlwaysFlatStrategy(BaseStrategy):
    name = "always_flat"

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(0, index=df.index)


class TestBacktestEngine:
    def test_raises_on_empty_dataframe(self):
        engine = BacktestEngine()
        with pytest.raises(ValueError):
            engine.run(AlwaysLongStrategy(), pd.DataFrame())

    def test_raises_on_missing_columns(self, sample_ohlcv):
        engine = BacktestEngine()
        bad_df = sample_ohlcv.drop(columns=["close"])
        with pytest.raises(ValueError):
            engine.run(AlwaysLongStrategy(), bad_df)

    def test_flat_strategy_never_trades(self, sample_ohlcv):
        engine = BacktestEngine(starting_capital=100_000)
        result = engine.run(AlwaysFlatStrategy(), sample_ohlcv)
        assert len(result.trades) == 0
        # equity should equal starting capital throughout (no positions ever taken)
        assert (result.equity_curve == 100_000).all()

    def test_always_long_on_uptrend_is_profitable(self, trending_ohlcv):
        engine = BacktestEngine(starting_capital=100_000, commission_pct=0.0001, slippage_pct=0.0001)
        result = engine.run(AlwaysLongStrategy(), trending_ohlcv)
        assert result.equity_curve.iloc[-1] > 100_000
        assert result.metrics["total_return_pct"] > 0

    def test_no_lookahead_bias(self, sample_ohlcv):
        """The signal computed on the FULL series for day t must not affect
        the trade executed on day t (it should only affect day t+1)."""
        engine = BacktestEngine()
        strat = SMACrossoverStrategy(fast_window=5, slow_window=15)
        result_full = engine.run(strat, sample_ohlcv)

        # Truncate the data by 30 bars and rerun - the equity curve up to the
        # truncation point (minus the last couple of bars, where trailing
        # window effects differ) should be identical, proving future data
        # wasn't used to make earlier decisions.
        truncated = sample_ohlcv.iloc[:-30]
        result_truncated = engine.run(strat, truncated)

        common_len = len(truncated) - 5
        pd.testing.assert_series_equal(
            result_full.equity_curve.iloc[:common_len],
            result_truncated.equity_curve.iloc[:common_len],
            check_names=False,
        )

    def test_position_sizing_respects_pct(self, trending_ohlcv):
        engine = BacktestEngine(starting_capital=100_000, position_size_pct=0.10)
        result = engine.run(AlwaysLongStrategy(), trending_ohlcv)
        first_buy = result.trades[0]
        assert first_buy.side == "BUY"
        position_value = first_buy.quantity * first_buy.price
        assert position_value <= 100_000 * 0.10 * 1.01  # small tolerance for slippage rounding

    def test_metrics_are_computed(self, sample_ohlcv):
        engine = BacktestEngine()
        result = engine.run(SMACrossoverStrategy(fast_window=10, slow_window=30), sample_ohlcv)
        for key in ["total_return_pct", "cagr_pct", "sharpe_ratio", "max_drawdown_pct", "final_equity"]:
            assert key in result.metrics

    def test_to_dict_is_json_serializable(self, sample_ohlcv):
        import json
        engine = BacktestEngine()
        result = engine.run(SMACrossoverStrategy(fast_window=10, slow_window=30), sample_ohlcv)
        json.dumps(result.to_dict())  # should not raise
