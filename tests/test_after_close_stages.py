from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

sys.modules.setdefault("akshare", MagicMock())
sys.modules.setdefault("requests", MagicMock())
from research import after_close_stages as stages


class AfterCloseStageTests(unittest.TestCase):
    def test_empty_csv_is_recoverable(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "empty.csv"
            path.write_text("", encoding="utf-8")
            self.assertTrue(stages._read_csv(path).empty)

    def test_stage_order_is_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / "run"
            run.mkdir()
            state = root / "state.json"
            state.write_text(json.dumps({"stage": "initialized", "folder": str(run)}), encoding="utf-8")
            with patch.object(stages, "STATE", state):
                with self.assertRaisesRegex(RuntimeError, "阶段顺序错误"):
                    stages._load_state("screen25_complete")

    def test_cache_summary_keeps_success_count(self):
        qa = pd.DataFrame([
            {"状态": "成功", "缓存模式": "incremental"},
            {"状态": "成功", "缓存模式": "cache/full"},
            {"状态": "失败", "缓存模式": "full-fetch-failed"},
        ])
        out = stages._qa_cache_summary(qa)
        self.assertEqual(out["总数"], 3)
        self.assertEqual(out["成功"], 2)
        self.assertEqual(out["命中或增量"], 2)

    def test_after_close_notifier_returns_delivery_receipt(self):
        summary = {"target_trade_date": "2026-09-07"}
        meta = {"market_assessment": {}}
        with patch.object(stages.cli, "pushplus_notify", return_value=True):
            self.assertTrue(stages.cli.notify_after_close_success(summary, pd.DataFrame(), meta))

    def test_ai_rerun_retries_delivery_without_repeating_openai(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / "run"
            latest = root / "latest"
            run.mkdir(); latest.mkdir()
            state_path = root / "state.json"
            state = {
                "stage": "completed", "status": "completed_push_failed",
                "folder": str(run), "stamp": "test", "target_trade_date": "2026-09-07",
            }
            state_path.write_text(json.dumps(state), encoding="utf-8")
            pd.DataFrame([{"股票代码": "000001", "股票名称": "平安银行"}]).to_csv(
                latest / "observation_pool.csv", index=False
            )
            (latest / "observation_pool_meta.json").write_text(
                json.dumps({"market_assessment": {}}), encoding="utf-8"
            )
            with patch.object(stages, "STATE", state_path), \
                 patch.object(stages.cli, "LATEST", latest), \
                 patch.object(stages.cli, "notify_after_close_success", return_value=True), \
                 patch.object(stages.cli, "git_commit"):
                stages.run_ai()
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "completed")
            self.assertTrue(saved["pushplus_delivery_ok"])


if __name__ == "__main__":
    unittest.main()
