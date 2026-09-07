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

    def test_120d_shards_are_disjoint_and_complete(self):
        frame = pd.DataFrame({"股票代码": [f"{i:06d}" for i in range(203)]})
        parts = [stages._shard_frame(frame, i, 4) for i in range(4)]
        combined = pd.concat(parts, ignore_index=True)
        self.assertEqual(len(combined), len(frame))
        self.assertEqual(set(combined["股票代码"]), set(frame["股票代码"]))
        self.assertEqual(sum(len(part) for part in parts), len(frame))
        self.assertLessEqual(max(len(part) for part in parts), 51)

    def test_25d_refresh_prioritizes_today_and_avoids_refreshing_entire_master(self):
        active = pd.DataFrame({
            "股票代码": ["000001", "000002", "000003", "000004", "000005"],
            "股票名称": ["A", "B", "C", "D", "E"],
        })
        daily = pd.DataFrame({"股票代码": ["000002", "000003"]})
        manifest = pd.DataFrame([
            {"股票代码": "000001", "缓存行数": 25, "日期已最新": True, "最后交易日": "2026-09-07"},
            {"股票代码": "000002", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-04"},
            {"股票代码": "000003", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-03"},
            {"股票代码": "000004", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-02"},
            {"股票代码": "000005", "缓存行数": 25, "日期已最新": True, "最后交易日": "2026-09-07"},
        ])
        planned = stages._plan_25d_cache_refresh(active, daily, manifest, minimum_ready=3)
        self.assertEqual(set(planned["股票代码"]), {"000002", "000003"})

    def test_25d_refresh_adds_recent_old_names_only_when_capacity_needs_them(self):
        active = pd.DataFrame({
            "股票代码": ["000001", "000002", "000003", "000004"],
            "股票名称": ["A", "B", "C", "D"],
        })
        daily = pd.DataFrame({"股票代码": ["000002"]})
        manifest = pd.DataFrame([
            {"股票代码": "000001", "缓存行数": 25, "日期已最新": True, "最后交易日": "2026-09-07"},
            {"股票代码": "000002", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-01"},
            {"股票代码": "000003", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-04"},
            {"股票代码": "000004", "缓存行数": 25, "日期已最新": False, "最后交易日": "2026-09-02"},
        ])
        planned = stages._plan_25d_cache_refresh(active, daily, manifest, minimum_ready=3)
        self.assertEqual(set(planned["股票代码"]), {"000002", "000003"})

    def test_after_close_notifier_returns_delivery_receipt(self):
        summary = {"target_trade_date": "2026-09-07"}
        meta = {"market_assessment": {}}
        with patch.object(stages.cli, "pushplus_notify", return_value=True):
            self.assertTrue(stages.cli.notify_after_close_success(summary, pd.DataFrame(), meta))

    def test_stage2_gate_evidence_is_attached_to_ai_research_pack(self):
        research = pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股份"}])
        audit = pd.DataFrame([{
            "股票代码": "000001", "阶段2通过": True, "整理成熟": True,
            "流动性收敛": True, "短期下行停止": True,
        }])
        out = stages._attach_stage2_evidence(research, audit).iloc[0]
        self.assertTrue(bool(out["阶段2通过"]))
        self.assertTrue(bool(out["整理成熟"]))
        self.assertTrue(bool(out["流动性收敛"]))

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

    def test_ai_failed_state_is_allowed_to_resume_from_saved_inputs(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            run = root / "run"
            latest = root / "latest"
            (run / "250d").mkdir(parents=True)
            latest.mkdir()
            state_path = root / "state.json"
            state_path.write_text(json.dumps({
                "stage": "ai_failed", "status": "completed_ai_failed",
                "folder": str(run), "generated_trade_date": "2026-09-07",
                "engine": "test", "stamp": "test",
            }), encoding="utf-8")
            pd.DataFrame([{"股票代码": "000001", "股票名称": "平安银行"}]).to_csv(
                run / "250d" / "research_pack_30_40.csv", index=False
            )
            empty_sheets = {"五大指数180日": pd.DataFrame(), "市场宽度当日": pd.DataFrame(),
                            "市场宽度历史180": pd.DataFrame(), "市场滚动上下文": pd.DataFrame()}
            with pd.ExcelWriter(run / "market_review.xlsx") as writer:
                for name, frame in empty_sheets.items():
                    frame.to_excel(writer, sheet_name=name, index=False)
            with pd.ExcelWriter(run / "sector_fund_flow.xlsx") as writer:
                pd.DataFrame().to_excel(writer, sheet_name="板块质量校验", index=False)
            with patch.object(stages, "STATE", state_path), \
                 patch.object(stages.cli, "LATEST", latest), \
                 patch.object(stages.cli, "run_openai_after_close", side_effect=RuntimeError("stop-after-gate")), \
                 patch.object(stages.cli, "git_commit"), \
                 patch.object(stages.cli, "notify_failure"):
                with self.assertRaisesRegex(RuntimeError, "stop-after-gate"):
                    stages.run_ai()
            saved = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(saved["stage"], "ai_failed")


if __name__ == "__main__":
    unittest.main()
