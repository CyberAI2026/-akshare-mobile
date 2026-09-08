import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from research.holding_exit import active_position_cycles, evaluate_holding_exits


def transactions(today_buy=False):
    day = "2026-09-08" if today_buy else "2026-09-04"
    return pd.DataFrame([{
        "交易日期": day, "交易时间": "14:48:00", "账户": "默认账户", "操作": "买入",
        "股票代码": "600801", "股票名称": "华新建材", "成交价格": 24.8,
        "成交数量": 2100, "手续费": 0, "备注": "",
    }])


class HoldingExitTests(unittest.TestCase):
    def test_active_cycle_and_t1_sellable(self):
        old = active_position_cycles(transactions(), date(2026, 9, 8))
        today = active_position_cycles(transactions(True), date(2026, 9, 8))
        self.assertEqual(int(old.iloc[0]["可卖数量"]), 2100)
        self.assertEqual(int(today.iloc[0]["可卖数量"]), 0)

    def test_structure_break_has_priority(self):
        with tempfile.TemporaryDirectory() as td:
            pd.DataFrame({"日期": pd.date_range("2026-08-25", periods=10), "收盘价": [24.0] * 10}).to_csv(Path(td) / "600801.csv", index=False)
            pos = active_position_cycles(transactions(), date(2026, 9, 8))
            snap = pd.DataFrame([{"股票代码": "600801", "当前价": 23.7}])
            minute = pd.DataFrame([{"股票代码": "600801", "时间": "14:35", "收盘价": 23.75}, {"股票代码": "600801", "时间": "14:40", "收盘价": 23.7}])
            out = evaluate_holding_exits(pos, snap, minute, td, {"600801": 23.82})
            self.assertEqual(out.iloc[0]["卖出建议"], "EXIT_ALL")
            self.assertEqual(int(out.iloc[0]["建议卖出数量"]), 2100)

    def test_five_percent_pullback_only_after_eight_percent_gain(self):
        with tempfile.TemporaryDirectory() as td:
            prices = [24.8, 25.0, 26.0, 27.0, 25.6]
            pd.DataFrame({"日期": pd.date_range("2026-09-04", periods=5), "收盘价": prices}).to_csv(Path(td) / "600801.csv", index=False)
            pos = active_position_cycles(transactions(), date(2026, 9, 8))
            snap = pd.DataFrame([{"股票代码": "600801", "当前价": 25.6}])
            minute = pd.DataFrame([{"股票代码": "600801", "时间": "14:35", "收盘价": 25.7}, {"股票代码": "600801", "时间": "14:40", "收盘价": 25.6}])
            out = evaluate_holding_exits(pos, snap, minute, td, {"600801": 23.82})
            self.assertEqual(out.iloc[0]["卖出建议"], "REDUCE_50")
            self.assertEqual(int(out.iloc[0]["建议卖出数量"]), 1000)


if __name__ == "__main__":
    unittest.main()
