import sys
import unittest
from unittest.mock import MagicMock

import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
from research import historical_trade_analysis as analysis


class HistoricalTradeAnalysisTests(unittest.TestCase):
    def test_name_key_normalizes_suffix_and_fullwidth_a(self):
        self.assertEqual(analysis.name_key("君实生物-U"), "君实生物")
        self.assertEqual(analysis.name_key("粤电力A"), "粤电力Ａ")

    def test_trade_window_metrics(self):
        history = pd.DataFrame({
            "日期": pd.date_range("2026-01-01", periods=35, freq="D"),
            "开盘": range(10, 45), "收盘": range(10, 45), "最高": range(11, 46),
            "最低": range(9, 44), "成交量": [100] * 35,
        })
        row = pd.Series({
            "建仓日期": pd.Timestamp("2026-01-22"), "清仓日期": pd.Timestamp("2026-01-25"),
            "买入均价": 31, "总盈亏": 1, "盈亏比": 1,
        })
        out = analysis.enrich_one(row, history)
        self.assertEqual(out["外部行情状态"], "成功")
        self.assertAlmostEqual(out["持仓期最大浮盈估算%"], (35 / 31 - 1) * 100)
        self.assertAlmostEqual(out["清仓后5日涨跌幅%"], (39 / 34 - 1) * 100)

    def test_holding_bucket(self):
        self.assertEqual(analysis.holding_bucket(2), "1-2天")
        self.assertEqual(analysis.holding_bucket(11), "11-20天")
        self.assertEqual(analysis.holding_bucket(30), "20天以上")

    def test_outcome_diagnostics_counts_only_verified_rows(self):
        frame = pd.DataFrame([
            {"外部行情状态": "成功", "总盈亏": -100, "持仓期最大浮盈估算%": 6,
             "持仓期最大浮亏估算%": -7, "清仓后5日涨跌幅%": 6},
            {"外部行情状态": "成功", "总盈亏": 50, "持仓期最大浮盈估算%": 8,
             "持仓期最大浮亏估算%": -2, "清仓后5日涨跌幅%": -6},
            {"外部行情状态": "未核验", "总盈亏": -200, "持仓期最大浮盈估算%": 9,
             "持仓期最大浮亏估算%": -9, "清仓后5日涨跌幅%": 9},
        ])
        result = analysis.outcome_diagnostics(frame)
        self.assertEqual(result["verified_trade_count"], 2)
        self.assertEqual(result["losers_with_estimated_mfe_at_least_5pct"], 1)
        self.assertEqual(result["losers_with_estimated_mae_at_most_minus_5pct"], 1)


if __name__ == "__main__":
    unittest.main()
