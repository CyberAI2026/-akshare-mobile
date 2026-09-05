from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from research import recommendation_feedback as rf
from research.stock_sector_attribution import build_attribution, load_membership, load_opinion_mentions


class RecommendationFeedbackTests(unittest.TestCase):
    def test_horizons_and_stop_touch_exclude_recommendation_day(self):
        dates = pd.bdate_range("2026-09-01", periods=11)
        bars = pd.DataFrame({
            "日期": dates, "收盘": [10, 10.2, 10.4, 10.1, 10.5, 11, 11.1, 11.2, 11.3, 11.4, 12],
            "最低": [8.0, 9.8, 9.4, 9.7, 9.9, 10.2, 10.4, 10.6, 10.8, 11, 11.2],
        })
        row = pd.Series({"推荐日期": "2026-09-01", "结构止损位": 9.5})
        out = rf.evaluate_record(row, bars, dates[-1].date())
        self.assertEqual(out["推荐日收盘价"], 10)
        self.assertAlmostEqual(out["D+3涨跌幅%"], 1.0)
        self.assertTrue(out["3日内触碰止损"])
        self.assertEqual(out["首次触碰止损日期"], "2026-09-03")
        self.assertAlmostEqual(out["D+10涨跌幅%"], 20.0)

    def test_saved_anchor_is_not_downgraded_when_same_day_bar_is_temporarily_missing(self):
        row=pd.Series({"推荐日期":"2026-09-04","推荐日收盘价":24.8,"结构止损位":23.82})
        bars=pd.DataFrame({"日期":[pd.Timestamp("2026-09-03")],"收盘":[24.0],"最低":[23.5]})
        out=rf.evaluate_record(row,bars,pd.Timestamp("2026-09-04").date())
        self.assertIn("跟踪中",out["数据状态"])
        summary=rf.build_daily_summary(pd.DataFrame([{"数据状态":out["数据状态"]}]),pd.Timestamp("2026-09-04").date())
        self.assertEqual(summary["tracking"],1)

    def test_register_is_idempotent_and_anchor_is_pending(self):
        decisions = pd.DataFrame([{
            "股票代码": "000001", "股票名称": "平安银行", "decision": "TRADE",
            "结构止损参考": 9.0, "买入区间下沿": 10.0, "买入区间上沿": 10.2,
            "建议仓位占总资金%": 5,
        }])
        meta = {"trade_date": "2026-09-03", "generated_at_cn": "2026-09-03T14:45:00+08:00",
                "selected_codes": ["000001"], "model": "test"}
        snap = pd.DataFrame([{"股票代码": "000001", "最新价": 10.1}])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(rf, "ROOT", root), patch.object(rf, "REGISTRY", root / "recommendations.csv"):
                rf.register_tail_recommendations(decisions, meta, snap, {})
                result = rf.register_tail_recommendations(decisions, meta, snap, {})
                saved = pd.read_csv(root / "recommendations.csv", dtype={"股票代码": str})
                self.assertEqual(result["registry_count"], 1)
                self.assertTrue(pd.isna(saved.iloc[0]["推荐日收盘价"]))
                self.assertEqual(saved.iloc[0]["推荐时参考价"], 10.1)

    def test_reference_price_accepts_current_price_column(self):
        snap = pd.DataFrame([{"股票代码": "600801", "当前价": 24.7}])
        self.assertEqual(rf._reference_price(snap, "600801"), 24.7)

    def test_update_all_allows_blank_date_in_numeric_inferred_column(self):
        bars = pd.DataFrame({"日期": [pd.Timestamp("2026-09-04")], "收盘": [24.8], "最低": [23.82]})
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            registry = root / "recommendations.csv"
            pd.DataFrame([{"推荐ID":"x","推荐日期":"2026-09-04","股票代码":"600801",
                           "结构止损位":23.82,"首次触碰止损日期":None}]).to_csv(registry,index=False)
            with patch.object(rf,"ROOT",root), patch.object(rf,"REGISTRY",registry), \
                 patch.object(rf,"LATEST_DAILY",root/"latest_daily.json"), \
                 patch.object(rf,"LATEST_WEEKLY",root/"latest_weekly.json"), \
                 patch.object(rf,"fetch_bars",return_value=bars), \
                 patch.object(rf,"_recover_reference_from_tail",return_value=24.7), \
                 patch.object(rf.time,"sleep"):
                rf.update_all(pd.Timestamp("2026-09-04").date(),notify=False)
            saved=pd.read_csv(registry)
            self.assertEqual(saved.iloc[0]["数据状态"],"跟踪中")
            self.assertEqual(saved.iloc[0]["推荐时参考价"],24.7)


class AttributionTests(unittest.TestCase):
    def test_missing_or_null_opinion_is_empty_text(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(load_opinion_mentions(root / "missing.json"), "")
            path = root / "opinion.json"
            path.write_text('{"daily_consensus": null}', encoding="utf-8")
            self.assertEqual(load_opinion_mentions(path), "{}")

    def test_headerless_membership_is_safe_skip(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"empty.csv.gz"
            pd.DataFrame().to_csv(path,index=False,compression="gzip")
            out=load_membership(path)
        self.assertTrue(out.empty)

    def test_multiple_concepts_and_primary_candidate(self):
        membership = pd.DataFrame([
            {"股票代码": "1", "股票名称": "甲", "板块类型": "概念", "板块名称": "机器人"},
            {"股票代码": "1", "股票名称": "甲", "板块类型": "概念", "板块名称": "人工智能"},
            {"股票代码": "1", "股票名称": "甲", "板块类型": "行业", "板块名称": "机械"},
        ])
        master = pd.DataFrame([{"股票代码": "1", "最近提交日期": "2026-09-03"}])
        strength = {"机器人": {"事实强度分": 70, "事实证据": ["5日涨幅第1"]}}
        out = build_attribution(membership, master, strength, "机器人活跃", "2026-09-03")
        self.assertEqual(len(out), 3)
        primary = out[out["主导板块候选"]].iloc[0]
        self.assertEqual(primary["板块名称"], "机器人")
        self.assertTrue(primary["时点一致"])


if __name__ == "__main__":
    unittest.main()
