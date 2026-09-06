import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
from research import historical_trade_market_fetch as fetcher


class HistoricalTradeMarketFetchTests(unittest.TestCase):
    def test_universe_is_normalized_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "u.csv"
            pd.DataFrame([
                {"股票代码": "1", "股票名称": "甲"},
                {"股票代码": "000001", "股票名称": "甲"},
                {"股票代码": "600000", "股票名称": "乙"},
            ]).to_csv(path, index=False)
            out = fetcher.load_universe(path)
        self.assertEqual(out["股票代码"].tolist(), ["000001", "600000"])

    def test_batches_are_disjoint_and_complete(self):
        frame = pd.DataFrame({"股票代码": [f"{x:06d}" for x in range(23)], "股票名称": "x"})
        batches = [fetcher.batch_slice(frame, i) for i in range(fetcher.BATCH_COUNT)]
        codes = [code for batch in batches for code in batch["股票代码"]]
        self.assertEqual(sorted(codes), sorted(frame["股票代码"].tolist()))
        self.assertEqual(len(codes), len(set(codes)))

    def test_history_schema_is_stable(self):
        raw = pd.DataFrame({
            "日期": ["2026-01-02"], "开盘": [10], "收盘": [11],
            "最高": [12], "最低": [9], "成交量": [100], "成交额": [1000],
        })
        out = fetcher.normalize_history(raw, "000001", "甲")
        self.assertEqual(out.iloc[0]["股票代码"], "000001")
        self.assertEqual(out.iloc[0]["日期"], "2026-01-02")


if __name__ == "__main__":
    unittest.main()
