import json
import sys
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
sys.modules.setdefault("requests", MagicMock())
import v5_cli as cli


CN = ZoneInfo("Asia/Shanghai")


class TailStageTests(unittest.TestCase):
    def test_stage_windows_are_bounded(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 36, tzinfo=CN)):
            self.assertEqual(cli._enforce_tail_stage_window("precheck"), date(2026, 9, 7))
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 45, tzinfo=CN)):
            self.assertEqual(cli._enforce_tail_stage_window("finalize"), date(2026, 9, 7))

    def test_late_stage_fails_without_using_close_data(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 15, 1, tzinfo=CN)), \
             patch.object(cli, "pushplus_notify", return_value=True) as notify:
            with self.assertRaisesRegex(RuntimeError, "超过安全窗"):
                cli._enforce_tail_stage_window("finalize")
            notify.assert_called_once()

    def test_load_pool_enforces_target_date_and_trade_lock(self):
        with tempfile.TemporaryDirectory() as td:
            latest = Path(td)
            pd.DataFrame([
                {"股票代码": "600801", "股票名称": "华新建材"},
                {"股票代码": "603318", "股票名称": "水发燃气"},
            ]).to_csv(latest / "observation_pool.csv", index=False, encoding="utf-8-sig")
            (latest / "observation_pool_meta.json").write_text(json.dumps({
                "target_trade_date": "2026-09-07", "generated_trade_date": "2026-09-04"
            }), encoding="utf-8")
            with patch.object(cli, "LATEST", latest), \
                 patch.object(cli, "previous_trade_day", return_value=date(2026, 9, 4)), \
                 patch.object(cli, "refresh_stock_names", side_effect=lambda frame: frame), \
                 patch.object(cli, "exclude_active_trades", side_effect=lambda frame: (frame.iloc[[1]].copy(), {"600801"})):
                pool, meta = cli._load_tail_pool(date(2026, 9, 7))
            self.assertEqual(pool["股票代码"].tolist(), ["603318"])
            self.assertEqual(meta["target_trade_date"], "2026-09-07")

    def test_completed_tail_run_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            latest = Path(td)
            (latest / "last_tail_summary.json").write_text(json.dumps({
                "trade_date": "2026-09-07",
                "status": "completed",
                "pushplus_delivery_ok": True,
            }), encoding="utf-8")
            with patch.object(cli, "LATEST", latest):
                self.assertTrue(cli._tail_completed_for_date(date(2026, 9, 7)))
                self.assertFalse(cli._tail_completed_for_date(date(2026, 9, 8)))

    def test_precheck_persists_candidate_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pool = pd.DataFrame([{"股票代码": "603318", "股票名称": "水发燃气"}])
            empty = pd.DataFrame()
            with patch.object(cli, "ROOT", root), patch.object(cli, "LATEST", root / "latest"), \
                 patch.object(cli, "_enforce_tail_stage_window", return_value=date(2026, 9, 7)), \
                 patch.object(cli, "_load_tail_pool", return_value=(pool, {"target_trade_date": "2026-09-07"})), \
                 patch.object(cli, "wait_until_cn"), \
                 patch.object(cli, "fetch_realtime_package", return_value=(pool, empty, empty)), \
                 patch.object(cli, "fetch_candidate_decision_context", return_value=({}, empty)), \
                 patch.object(cli, "save_bytes"), patch.object(cli, "git_commit"), \
                 patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 41, tzinfo=CN)):
                cli.run_tail_precheck()
            marker = json.loads((root / "latest" / "tail_precheck_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["candidate_codes"], ["603318"])
            self.assertEqual(marker["status"], "precheck_completed")


if __name__ == "__main__":
    unittest.main()
