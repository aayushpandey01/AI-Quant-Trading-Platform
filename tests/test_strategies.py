import pandas as pd
import pytest

from backtest.strategies.momentum import MomentumStrategy
from backtest.strategies.rsi_meanreversion import RSIMeanReversionStrategy
from backtest.strategies.sma_crossover import SMACrossoverStrategy


class TestSMACrossover:
    def test_rejects_invalid_windows(self):
        with pytest.raises(ValueError):
            SMACrossoverStrategy(fast_window=50, slow_window=20)

    def test_signal_shape_matches_input(self, sample_ohlcv):
        strat = SMACrossoverStrategy(fast_window=10, slow_window=30)
        signal = strat.generate_signals(sample_ohlcv)
        assert len(signal) == len(sample_ohlcv)
        assert signal.index.equals(sample_ohlcv.index)

    def test_signal_values_are_valid(self, sample_ohlcv):
        strat = SMACrossoverStrategy(fast_window=10, slow_window=30, allow_short=False)
        signal = strat.generate_signals(sample_ohlcv)
        assert set(signal.unique()).issubset({0, 1})

    def test_goes_long_on_strong_uptrend(self, trending_ohlcv):
        strat = SMACrossoverStrategy(fast_window=5, slow_window=20)
        signal = strat.generate_signals(trending_ohlcv)
        # after the warmup period, a strong monotonic uptrend should be long most of the time
        assert signal.iloc[40:].mean() > 0.8

    def test_no_signal_during_warmup(self, sample_ohlcv):
        strat = SMACrossoverStrategy(fast_window=10, slow_window=30)
        signal = strat.generate_signals(sample_ohlcv)
        assert (signal.iloc[:29] == 0).all()


class TestRSIMeanReversion:
    def test_signal_values_are_valid(self, sample_ohlcv):
        strat = RSIMeanReversionStrategy()
        signal = strat.generate_signals(sample_ohlcv)
        assert set(signal.unique()).issubset({0, 1})
        assert len(signal) == len(sample_ohlcv)

    def test_no_nan_in_output(self, sample_ohlcv):
        strat = RSIMeanReversionStrategy()
        signal = strat.generate_signals(sample_ohlcv)
        assert not signal.isna().any()


class TestMomentum:
    def test_signal_values_are_valid(self, sample_ohlcv):
        strat = MomentumStrategy(lookback=20)
        signal = strat.generate_signals(sample_ohlcv)
        assert set(signal.unique()).issubset({0, 1})

    def test_goes_long_on_uptrend(self, trending_ohlcv):
        strat = MomentumStrategy(lookback=20, threshold=0.0)
        signal = strat.generate_signals(trending_ohlcv)
        assert signal.iloc[40:].mean() > 0.9
