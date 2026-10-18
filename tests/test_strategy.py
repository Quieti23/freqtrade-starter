import importlib.util
from pathlib import Path
import unittest

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("starter_strategy", PROJECT / "strategies/StarterStrategy.py")
strategy_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(strategy_module)


class StrategyTests(unittest.TestCase):
    def test_indicator_and_signal_pipeline_with_synthetic_prices(self):
        strategy = strategy_module.StarterStrategy({})
        count = 500
        close = 100 + np.sin(np.arange(count) / 4) * 5
        frame = pd.DataFrame({
            "date": pd.date_range("2026-01-01", periods=count, freq="5min", tz="UTC"),
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": np.ones(count),
        })
        frame = strategy.populate_indicators(frame, {})
        frame = strategy.populate_entry_trend(frame, {})
        frame = strategy.populate_exit_trend(frame, {})
        self.assertGreater(frame["enter_long"].fillna(0).sum(), 0)
        self.assertGreater(frame["exit_long"].fillna(0).sum(), 0)
        self.assertFalse(strategy.can_short)
        self.assertTrue(frame.loc[60:, ["ema_fast", "ema_slow", "rsi"]].notna().all().all())
        frame["volume"] = 0
        frame["enter_long"] = 0
        frame["exit_long"] = 0
        frame = strategy.populate_entry_trend(frame, {})
        frame = strategy.populate_exit_trend(frame, {})
        self.assertEqual(frame["enter_long"].sum() + frame["exit_long"].sum(), 0)


if __name__ == "__main__":
    unittest.main()
