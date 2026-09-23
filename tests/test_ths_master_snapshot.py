import io
import sys
import unittest
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
sys.modules.setdefault("requests", MagicMock())

from research.ths_master_snapshot import (
    master_code_text,
    prepare_snapshot,
    snapshot_gzip,
    snapshot_path,
)


class ThsMasterSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.master = pd.DataFrame({
            "股票代码": ["000001", "600000", "920298"],
            "股票名称": ["平安银行", "浦发银行", "腾信精密"],
        })

    def test_master_code_text_keeps_leading_zero_and_has_no_header(self):
        value = master_code_text(self.master).decode("utf-8")
        self.assertEqual(value, "000001\n600000\n920298\n")

    def test_fake_xls_preserves_ths_fields_and_reports_coverage(self):
        text = (
            "代码\t名称\t现价\t同花顺所属概念\t人气值\r\n"
            "000001\t平安银行\t12.30\t银行\t1000\r\n"
            "600000\t浦发银行\t10.20\t银行\t2000\r\n"
            "301150\t中一科技\t31.50\t锂电池\t3000\r\n"
        ).encode("gb18030")
        snapshot, report = prepare_snapshot(
            "Table.xls", text, self.master,
            uploaded_at=datetime(2026, 9, 23, 20, 30, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        self.assertIn("同花顺所属概念", snapshot.columns)
        self.assertIn("人气值", snapshot.columns)
        self.assertEqual(snapshot["股票代码"].tolist(), ["000001", "600000", "301150"])
        self.assertEqual(snapshot["主池匹配"].tolist(), ["是", "是", "否"])
        self.assertEqual(report["matched_rows"], 2)
        self.assertEqual(report["unmatched_codes"], ["301150"])
        self.assertEqual(report["missing_codes"], ["920298"])
        self.assertEqual(snapshot_path(report["snapshot_date"]), "v5_data/ths_snapshots/2026-09-23/ths_master_snapshot_20260923.csv.gz")
        self.assertTrue(snapshot_gzip(snapshot).startswith(b"\x1f\x8b"))

    def test_duplicate_codes_are_rejected(self):
        source = pd.DataFrame({"股票代码": ["000001", "000001"], "股票名称": ["平安银行", "平安银行"]})
        buf = io.BytesIO()
        source.to_excel(buf, index=False, engine="openpyxl")
        with self.assertRaisesRegex(ValueError, "代码重复"):
            prepare_snapshot("duplicate.xlsx", buf.getvalue(), self.master)


if __name__ == "__main__":
    unittest.main()
