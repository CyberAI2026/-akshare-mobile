from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

import numpy as np
import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
sys.modules.setdefault("requests", MagicMock())
from v5_core import build_metrics, fetch_pool_history_incremental, stage2_rank


def sample_history(contracting: bool = True, with_turnover: bool = True) -> pd.DataFrame:
    n = 80
    close = np.linspace(10.0, 13.0, n)
    close[-15:] = np.linspace(12.70, 13.00, 15)
    volume = np.full(n, 2000.0)
    volume[-15:-5] = 1800.0
    volume[-5:] = 900.0 if contracting else 2600.0
    turnover = np.full(n, np.nan)
    if with_turnover:
        turnover[-15:-5] = 4.0
        turnover[-5:] = 2.0 if contracting else 5.5
    return pd.DataFrame({
        "股票代码": ["000001"] * n,
        "股票名称": ["测试股份"] * n,
        "日期": pd.date_range("2026-05-01", periods=n, freq="B"),
        "收盘价": close,
        "最高价": close * 1.01,
        "最低价": close * 0.99,
        "成交量": volume,
        "换手率": turnover,
    })


class SecondStartEvidenceTests(unittest.TestCase):
    def test_metrics_expose_volume_turnover_and_consolidation(self):
        metrics = build_metrics(sample_history()).iloc[0]
        self.assertLess(metrics["成交量收敛比"], 1.0)
        self.assertLess(metrics["换手率收敛比"], 1.0)
        self.assertTrue(bool(metrics["流动性收敛证据"]))
        self.assertGreaterEqual(metrics["整理证据可用项"], 3)
        self.assertEqual(metrics["整理证据可用项"], 3)
        self.assertGreaterEqual(metrics["整理收敛支持项"], 2)
        self.assertIn(metrics["整理成熟度状态"], {"收敛较充分", "部分收敛/待确认"})

    def test_stage2_does_not_use_price_position_alone(self):
        history = sample_history(contracting=False)
        history.loc[history.index[-5:], "收盘价"] = [13.00, 12.15, 12.80, 12.20, 12.90]
        history.loc[history.index[-5:], "最高价"] = [13.10, 12.30, 12.95, 12.35, 13.00]
        history.loc[history.index[-5:], "最低价"] = [12.85, 12.00, 12.65, 12.05, 12.75]
        metrics = build_metrics(history)
        selected, audit = stage2_rank(metrics, min_n=1, max_n=1, return_audit=True)
        row = audit.iloc[0]
        self.assertFalse(bool(row["整理成熟"]))
        self.assertFalse(bool(row["阶段2通过"]))
        self.assertTrue(selected.empty)

    def test_missing_turnover_is_explicit_but_not_automatic_failure(self):
        metrics = build_metrics(sample_history(with_turnover=False))
        row = metrics.iloc[0]
        self.assertTrue(pd.isna(row["换手率收敛比"]))
        self.assertGreaterEqual(row["整理证据可用项"], 2)

    def test_volume_and_turnover_are_not_double_counted(self):
        metrics = build_metrics(sample_history()).iloc[0]
        # 振幅、流动性、短期止跌最多是三类独立证据；成交量和换手率不是两票。
        self.assertEqual(metrics["整理证据可用项"], 3)
        self.assertLessEqual(metrics["整理收敛支持项"], 3)

    def test_large_exception_backfill_uses_bounded_parallelism(self):
        pool = pd.DataFrame({
            "股票代码": [str(i).zfill(6) for i in range(30)],
            "股票名称": [f"测试{i}" for i in range(30)],
        })
        history = sample_history().drop(columns=["股票代码", "股票名称"])
        meta = {"source": "test", "raw_source": "test", "errors": [], "raw_matched": len(history), "cache_mode": "deep-backfill"}
        with tempfile.TemporaryDirectory() as tmp, \
             patch("v5_core.fetch_history_incremental", return_value=(history, meta)), \
             patch("v5_core.ThreadPoolExecutor") as executor_cls:
            executor_cls.return_value.__enter__.return_value.map.side_effect = lambda func, rows: list(map(func, rows))
            data, qa = fetch_pool_history_incremental(pool, 25, Path(tmp))
        executor_cls.assert_called_once_with(max_workers=4)
        self.assertEqual(len(qa), 30)
        self.assertEqual(qa["状态"].eq("成功").sum(), 30)
        self.assertEqual(data["股票代码"].nunique(), 30)


if __name__ == "__main__":
    unittest.main()
