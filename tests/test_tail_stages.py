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
    @staticmethod
    def _write_observation_source(folder: Path, generated: str, target: str,
                                  codes, generated_at: str = "2026-09-08T20:00:00+08:00"):
        folder.mkdir(parents=True, exist_ok=True)
        rows = codes if codes and isinstance(codes[0], dict) else [
            {"股票代码": code, "股票名称": f"测试{code}", "AI优先级": rank}
            for rank, code in enumerate(codes, start=1)
        ]
        pd.DataFrame(rows).to_csv(folder / "observation_pool.csv", index=False, encoding="utf-8-sig")
        (folder / "observation_pool_meta.json").write_text(json.dumps({
            "status": "valid", "generated_trade_date": generated,
            "target_trade_date": target, "generated_at_cn": generated_at,
            "observation_count": len(rows),
        }), encoding="utf-8")

    @staticmethod
    def _write_history(cache: Path, code: str, breakout: bool = False):
        dates = pd.date_range("2026-09-10", periods=8, freq="D")
        highs = [10.00, 10.10, 9.90, 10.00, 10.05, 10.00, 10.00, 10.00]
        closes = [9.80, 9.90, 9.85, 9.95, 9.90, 9.92, 9.95, 9.95]
        volumes = [100.0] * 8
        if breakout:
            highs[6], closes[6], volumes[6] = 10.40, 10.20, 200.0
            highs[7], closes[7], volumes[7] = 10.25, 10.15, 100.0
        pd.DataFrame({
            "日期": dates, "最高价": highs, "最低价": [9.70] * 8,
            "收盘价": closes, "成交量": volumes,
        }).to_csv(cache / f"{code}.csv", index=False)

    @staticmethod
    def _snapshot(code: str, price: float, high: float, low: float, volume: float):
        return pd.DataFrame([{
            "股票代码": code, "股票名称": "测试股", "当前价": price,
            "今日最高价": high, "今日最低价": low, "截至当前成交量": volume,
        }])

    @staticmethod
    def _write_high_hold_history(cache: Path, code: str):
        pd.DataFrame({
            "日期": pd.date_range("2026-09-10", periods=8, freq="D"),
            "最高价": [10.00, 10.10, 9.90, 10.00, 10.05, 10.30, 10.16, 10.17],
            "最低价": [9.70, 9.80, 9.75, 9.80, 9.85, 10.06, 10.08, 10.09],
            "收盘价": [9.80, 9.90, 9.85, 9.95, 9.90, 10.20, 10.13, 10.14],
            "成交量": [100.0, 100.0, 100.0, 100.0, 100.0, 200.0, 90.0, 80.0],
        }).to_csv(cache / f"{code}.csv", index=False)

    @staticmethod
    def _minutes(code: str, closes):
        return pd.DataFrame({
            "股票代码": [code] * len(closes),
            "时间": [f"14:{35 + i * 5:02d}" for i in range(len(closes))],
            "收盘价": closes,
        })

    def test_first_breakout_defaults_to_wait(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            self._write_history(cache, "000001")
            gate = cli.build_breakout_retest_gate(
                pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股"}]),
                self._snapshot("000001", 10.20, 10.25, 9.90, 100.0),
                self._minutes("000001", [10.10, 10.20]),
                {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念共振"}]},
                date(2026, 9, 21), cache,
            ).iloc[0]
        self.assertFalse(bool(gate["允许新开仓"]))
        self.assertEqual(gate["入场路径"], "WAIT")
        self.assertIn("首次突破一律WAIT", gate["入场门禁原因"])

    def test_strong_breakout_never_bypasses_retest(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            self._write_history(cache, "000001")
            gate = cli.build_breakout_retest_gate(
                pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股"}]),
                self._snapshot("000001", 10.20, 10.25, 9.90, 150.0),
                self._minutes("000001", [10.10, 10.20]),
                {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念共振"}]},
                date(2026, 9, 21), cache,
            ).iloc[0]
        self.assertFalse(bool(gate["允许新开仓"]))
        self.assertEqual(gate["入场路径"], "WAIT")
        self.assertIn("首次突破一律WAIT", gate["入场门禁原因"])

    def test_pullback_confirmation_passes(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            self._write_history(cache, "000001", breakout=True)
            gate = cli.build_breakout_retest_gate(
                pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股"}]),
                self._snapshot("000001", 10.12, 10.20, 10.00, 150.0),
                self._minutes("000001", [10.08, 10.12]),
                {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念分化"}]},
                date(2026, 9, 21), cache,
            ).iloc[0]
        self.assertTrue(bool(gate["允许新开仓"]))
        self.assertEqual(gate["入场路径"], "RETEST_CONFIRMED")
        self.assertLessEqual(gate["相对突破日成交量"], 0.8)

    def test_above_platform_tight_hold_passes(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            self._write_high_hold_history(cache, "000001")
            gate = cli.build_breakout_retest_gate(
                pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股"}]),
                self._snapshot("000001", 10.16, 10.18, 10.10, 100.0),
                self._minutes("000001", [10.14, 10.16]),
                {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念分化"}]},
                date(2026, 9, 21), cache,
            ).iloc[0]
        self.assertTrue(bool(gate["允许新开仓"]))
        self.assertEqual(gate["入场路径"], "ABOVE_PLATFORM_TIGHT_HOLD")
        self.assertLessEqual(gate["平台上方横盘振幅"], 0.06)

    def test_micro_platform_rebreak_passes(self):
        with tempfile.TemporaryDirectory() as td:
            cache = Path(td)
            self._write_high_hold_history(cache, "000001")
            gate = cli.build_breakout_retest_gate(
                pd.DataFrame([{"股票代码": "000001", "股票名称": "测试股"}]),
                self._snapshot("000001", 10.20, 10.22, 10.11, 110.0),
                self._minutes("000001", [10.18, 10.20]),
                {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念分化"}]},
                date(2026, 9, 21), cache,
            ).iloc[0]
        self.assertTrue(bool(gate["允许新开仓"]))
        self.assertEqual(gate["入场路径"], "MICRO_PLATFORM_REBREAK")
        self.assertGreaterEqual(gate["微平台再突破量比"], 1.05)
        self.assertLessEqual(gate["微平台再突破量比"], 1.80)

    def test_post_model_gate_downgrades_disallowed_trade(self):
        decisions = {"000001": {"decision": "TRADE", "position_pct_total_capital": 15,
                                  "buy_zone_low": 10.0, "buy_zone_high": 10.2, "risk": "原风险"}}
        gate = pd.DataFrame([{"股票代码": "000001", "允许新开仓": False,
                              "入场门禁原因": "首次突破默认WAIT"}])
        selected, downgraded = cli._apply_breakout_retest_post_gate(
            ["000001"], decisions, gate, "谨慎"
        )
        self.assertEqual(selected, [])
        self.assertEqual(downgraded, ["000001"])
        self.assertEqual(decisions["000001"]["decision"], "WAIT")
        self.assertEqual(decisions["000001"]["position_pct_total_capital"], 0)

    def test_dynamic_pool_range_uses_breadth_and_turnover(self):
        active = cli._after_close_pool_policy(
            pd.DataFrame([{"上涨比例": 0.70}]),
            pd.DataFrame([{"成交额较前一日变化率": 0.08}]),
        )
        weak = cli._after_close_pool_policy(
            pd.DataFrame([{"上涨比例": 0.58}]),
            pd.DataFrame([{"成交额较前一日变化率": 0.20}]),
        )
        self.assertEqual((active["minimum"], active["maximum"]), (5, 10))
        self.assertEqual((weak["minimum"], weak["maximum"]), (0, 5))

    def test_stage_windows_are_bounded(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 36, tzinfo=CN)):
            self.assertEqual(cli._enforce_tail_stage_window("precheck"), date(2026, 9, 7))
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 45, tzinfo=CN)):
            self.assertEqual(cli._enforce_tail_stage_window("finalize"), date(2026, 9, 7))

    def test_precheck_can_wait_from_bounded_early_dispatch(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", side_effect=[
                 datetime(2026, 9, 7, 14, 28, tzinfo=CN),
                 datetime(2026, 9, 7, 14, 32, tzinfo=CN),
             ]), \
             patch.object(cli, "wait_until_cn") as wait:
            self.assertEqual(cli._enforce_tail_stage_window("precheck"), date(2026, 9, 7))
            wait.assert_called_once_with(14, 32)

    def test_excessively_early_dispatch_still_fails(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 0, tzinfo=CN)), \
             patch.object(cli, "wait_until_cn") as wait:
            with self.assertRaisesRegex(RuntimeError, "过早启动"):
                cli._enforce_tail_stage_window("precheck")
            wait.assert_not_called()

    def test_late_stage_fails_without_using_close_data(self):
        with patch.object(cli, "is_trade_day", return_value=True), \
             patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 15, 1, tzinfo=CN)), \
             patch.object(cli, "pushplus_notify", return_value=True) as notify:
            with self.assertRaisesRegex(RuntimeError, "超过安全窗"):
                cli._enforce_tail_stage_window("finalize")
            notify.assert_not_called()

    def test_load_pool_enforces_target_date_and_trade_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            latest = root / "latest"
            latest.mkdir()
            pd.DataFrame([
                {"股票代码": "600801", "股票名称": "华新建材"},
                {"股票代码": "603318", "股票名称": "水发燃气"},
            ]).to_csv(latest / "observation_pool.csv", index=False, encoding="utf-8-sig")
            (latest / "observation_pool_meta.json").write_text(json.dumps({
                "target_trade_date": "2026-09-07", "generated_trade_date": "2026-09-04"
            }), encoding="utf-8")
            previous = {date(2026, 9, 7): date(2026, 9, 4),
                        date(2026, 9, 4): date(2026, 9, 3),
                        date(2026, 9, 3): date(2026, 9, 2)}
            with patch.object(cli, "ROOT", root), patch.object(cli, "LATEST", latest), \
                 patch.object(cli, "RECOMMENDATION_REGISTRY", root / "missing.csv"), \
                 patch.object(cli, "previous_trade_day", side_effect=lambda value: previous.get(value)), \
                 patch.object(cli, "refresh_stock_names", side_effect=lambda frame: frame), \
                 patch.object(cli, "exclude_active_trades", side_effect=lambda frame: (frame.iloc[[1]].copy(), {"600801"})):
                pool, meta = cli._load_tail_pool(date(2026, 9, 7))
            self.assertEqual(pool["股票代码"].tolist(), ["603318"])
            self.assertEqual(meta["target_trade_date"], "2026-09-07")

    def test_load_pool_rolls_three_trade_dates_deduplicates_and_caps(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "v5_data"
            latest = root / "latest"
            self._write_observation_source(
                latest, "2026-09-08", "2026-09-09", [f"00000{i}" for i in range(1, 5)]
            )
            self._write_observation_source(
                root / "runs" / "day2" / "ai", "2026-09-07", "2026-09-08",
                ["000004", "000005", "000006", "000007", "000008", "000009"],
                "2026-09-07T20:00:00+08:00",
            )
            self._write_observation_source(
                root / "runs" / "day2_old" / "ai", "2026-09-07", "2026-09-08",
                ["999999"], "2026-09-07T19:00:00+08:00",
            )
            self._write_observation_source(
                root / "runs" / "day3" / "ai", "2026-09-04", "2026-09-07",
                ["000009", "000010", "000011", "000012", "000013", "000014"],
                "2026-09-04T20:00:00+08:00",
            )
            previous = {date(2026, 9, 9): date(2026, 9, 8),
                        date(2026, 9, 8): date(2026, 9, 7),
                        date(2026, 9, 7): date(2026, 9, 4)}
            with patch.object(cli, "ROOT", root), patch.object(cli, "LATEST", latest), \
                 patch.object(cli, "RECOMMENDATION_REGISTRY", root / "missing.csv"), \
                 patch.object(cli, "previous_trade_day", side_effect=lambda value: previous.get(value)), \
                 patch.object(cli, "refresh_stock_names", side_effect=lambda frame: frame), \
                 patch.object(cli, "exclude_active_trades", side_effect=lambda frame: (frame, [])):
                pool, meta = cli._load_tail_pool(date(2026, 9, 9))
            self.assertEqual(len(pool), 10)
            self.assertTrue(set(["000001", "000002", "000003", "000004"]).issubset(set(pool["股票代码"])))
            repeated = pool[pool["股票代码"] == "000004"].iloc[0]
            self.assertEqual(repeated["滚动池来源次数"], 2)
            self.assertEqual(meta["rolling_union_count_before_exclusions"], 14)
            self.assertEqual(len(meta["rolling_trimmed_codes"]), 4)
            self.assertEqual(meta["rolling_source_dates"], ["2026-09-08", "2026-09-07", "2026-09-04"])
            self.assertNotIn("999999", set(pool["股票代码"]))

    def test_load_pool_excludes_active_and_sold_old_sources(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "v5_data"
            latest = root / "latest"
            registry = root / "feedback" / "recommendations.csv"
            self._write_observation_source(
                latest, "2026-09-08", "2026-09-09", ["600801", "603011", "000001", "600802"]
            )
            registry.parent.mkdir(parents=True)
            pd.DataFrame([
                {"股票代码": "600801", "决策": "TRADE", "真实交易状态": "已清仓",
                 "实际卖出日期": "2026-09-08", "数据状态": "实盘已卖出"},
                {"股票代码": "600802", "决策": "TRADE", "真实交易状态": "已清仓",
                 "实际卖出日期": "2026-09-07", "数据状态": "实盘已卖出"},
            ]).to_csv(registry, index=False)
            previous = {date(2026, 9, 9): date(2026, 9, 8),
                        date(2026, 9, 8): date(2026, 9, 7),
                        date(2026, 9, 7): date(2026, 9, 4)}
            def exclude_active(frame):
                return frame[frame["股票代码"] != "603011"].reset_index(drop=True), ["603011"]
            with patch.object(cli, "ROOT", root), patch.object(cli, "LATEST", latest), \
                 patch.object(cli, "RECOMMENDATION_REGISTRY", registry), \
                 patch.object(cli, "previous_trade_day", side_effect=lambda value: previous.get(value)), \
                 patch.object(cli, "refresh_stock_names", side_effect=lambda frame: frame), \
                 patch.object(cli, "exclude_active_trades", side_effect=exclude_active):
                pool, meta = cli._load_tail_pool(date(2026, 9, 9))
            self.assertEqual(pool["股票代码"].tolist(), ["000001", "600802"])
            self.assertEqual(meta["rolling_excluded_active_trade_codes"], ["603011"])
            self.assertEqual(meta["rolling_excluded_closed_trade_codes"], ["600801"])

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

    def test_completed_close_audit_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            latest=Path(td)
            (latest/"latest_close_audit.json").write_text(json.dumps({
                "trade_date":"2026-09-07","pushplus_delivery_ok":True,
            }),encoding="utf-8")
            with patch.object(cli,"LATEST",latest):
                self.assertTrue(cli._close_audit_completed_for_date(date(2026,9,7)))
                self.assertFalse(cli._close_audit_completed_for_date(date(2026,9,8)))

    def test_precheck_persists_candidate_identity(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pool = pd.DataFrame([{"股票代码": "603318", "股票名称": "水发燃气"}])
            empty = pd.DataFrame()
            order = []
            with patch.object(cli, "ROOT", root), patch.object(cli, "LATEST", root / "latest"), \
                 patch.object(cli, "_enforce_tail_stage_window", return_value=date(2026, 9, 7)), \
                 patch.object(cli, "_load_tail_pool", return_value=(pool, {"target_trade_date": "2026-09-07"})), \
                 patch.object(cli, "wait_until_cn", side_effect=lambda *_: order.append("wait-1440")), \
                 patch.object(cli, "fetch_realtime_package", side_effect=lambda *_: (order.append("realtime") or (pool, empty, empty))), \
                 patch.object(cli, "fetch_candidate_decision_context", side_effect=lambda *_: (order.append("context") or ({}, empty))), \
                 patch.object(cli, "save_bytes"), patch.object(cli, "git_commit"), \
                 patch.object(cli, "now_cn", return_value=datetime(2026, 9, 7, 14, 41, tzinfo=CN)):
                cli.run_tail_precheck()
            marker = json.loads((root / "latest" / "tail_precheck_meta.json").read_text(encoding="utf-8"))
            self.assertEqual(marker["candidate_codes"], ["603318"])
            self.assertEqual(marker["status"], "precheck_completed")
            self.assertEqual(order, ["context", "wait-1440", "realtime"])


if __name__ == "__main__":
    unittest.main()
