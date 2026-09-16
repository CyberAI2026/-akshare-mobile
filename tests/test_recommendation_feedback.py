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

    def test_normalized_cache_schema_matures_third_trading_day(self):
        bars = pd.DataFrame({
            "日期": pd.to_datetime(["2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09"]),
            "收盘价": [24.8, 24.44, 25.01, 25.10],
            "最低价": [23.82, 24.40, 24.32, 24.82],
        })
        row = pd.Series({"推荐日期": "2026-09-04", "推荐日收盘价": 24.8, "结构止损位": 23.82})
        out = rf.evaluate_record(row, bars, pd.Timestamp("2026-09-09").date())
        self.assertEqual(out["D+3日期"], "2026-09-09")
        self.assertEqual(out["D+3收盘价"], 25.10)
        self.assertAlmostEqual(out["D+3涨跌幅%"], 1.2097)
        self.assertFalse(out["3日内触碰止损"])

    def test_accepted_delivery_key_is_not_sent_twice(self):
        with tempfile.TemporaryDirectory() as td:
            receipts = Path(td) / "receipts.json"
            receipts.write_text('{"receipts":[{"delivery_key":"correction-v1","status":"request_accepted"}]}', encoding="utf-8")
            with patch.object(rf, "DELIVERY_RECEIPTS", receipts), \
                 patch.object(rf.urllib.request, "urlopen") as urlopen:
                result = rf.pushplus("title", "body", delivery_key="correction-v1")
            self.assertEqual(result["status"], "request_accepted")
            urlopen.assert_not_called()

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
                 patch.object(rf,"TRADE_LEDGER",root/"missing-trades.enc"), \
                 patch.object(rf,"fetch_bars",return_value=bars), \
                 patch.object(rf,"_recover_reference_from_tail",return_value=24.7), \
                 patch.object(rf.time,"sleep"):
                rf.update_all(pd.Timestamp("2026-09-04").date(),notify=False)
            saved=pd.read_csv(registry)
            self.assertEqual(saved.iloc[0]["数据状态"],"跟踪中")
            self.assertEqual(saved.iloc[0]["推荐时参考价"],24.7)

    def test_real_full_exit_stops_horizon_tracking_and_uses_actual_loss(self):
        records = pd.DataFrame([{
            "推荐ID": "2026-09-04_600801", "推荐日期": "2026-09-04", "股票代码": "600801",
            "股票名称": "华新建材", "决策": "TRADE", "数据状态": "跟踪中",
            "D+3日期": "2026-09-09", "D+3涨跌幅%": 1.2097,
        }])
        trades = pd.DataFrame([
            {"交易日期":"2026-09-04","交易时间":"14:48:00","账户":"默认账户","操作":"买入",
             "股票代码":"600801","股票名称":"华新建材","成交价格":24.8,"成交数量":2100,"手续费":5},
            {"交易日期":"2026-09-16","交易时间":"13:05:00","账户":"默认账户","操作":"卖出",
             "股票代码":"600801","股票名称":"华新建材","成交价格":23.5,"成交数量":2100,"手续费":5},
        ])
        linked = rf.apply_actual_trade_outcomes(records, trades)
        row = linked.iloc[0]
        self.assertEqual(row["数据状态"], "实盘已卖出")
        self.assertEqual(row["实际结果"], "亏损卖出")
        self.assertLess(float(row["实际收益率%"]), 0)
        daily = rf.build_daily_summary(linked, pd.Timestamp("2026-09-09").date())
        self.assertEqual(daily["actual_closed"], 1)
        self.assertEqual(daily["due_cohorts"]["D+3"], [])
        weekly = rf.build_weekly_summary(linked, pd.Timestamp("2026-09-16").date())
        actual = weekly["真实交易结果"]
        self.assertEqual(actual["已完成实盘数"], 1)
        self.assertEqual(actual["亏损卖出数"], 1)
        self.assertEqual(actual["胜率%"], 0.0)
        self.assertIsNone(actual["盈亏比"])

    def test_open_real_position_remains_eligible_for_horizon_tracking(self):
        records = pd.DataFrame([{
            "推荐ID":"x", "推荐日期":"2026-09-04", "股票代码":"600801",
            "股票名称":"华新建材", "决策":"TRADE", "数据状态":"跟踪中",
            "D+3日期":"2026-09-09", "D+3涨跌幅%":1.2,
        }])
        trades = pd.DataFrame([{
            "交易日期":"2026-09-04","交易时间":"14:48:00","账户":"默认账户","操作":"买入",
            "股票代码":"600801","股票名称":"华新建材","成交价格":24.8,"成交数量":2100,"手续费":0,
        }])
        linked = rf.apply_actual_trade_outcomes(records, trades)
        self.assertEqual(linked.iloc[0]["真实交易状态"], "持仓中")
        daily = rf.build_daily_summary(linked, pd.Timestamp("2026-09-09").date())
        self.assertEqual(len(daily["due_cohorts"]["D+3"]), 1)

    def test_same_recommendation_aggregates_real_cycles_across_accounts(self):
        records = pd.DataFrame([{
            "推荐ID":"x", "推荐日期":"2026-09-04", "股票代码":"600801",
            "股票名称":"华新建材", "决策":"TRADE", "数据状态":"跟踪中",
        }])
        trades = pd.DataFrame([
            {"交易日期":"2026-09-04","账户":"A","操作":"买入","股票代码":"600801","股票名称":"华新建材","成交价格":10,"成交数量":100},
            {"交易日期":"2026-09-04","账户":"B","操作":"买入","股票代码":"600801","股票名称":"华新建材","成交价格":10,"成交数量":100},
            {"交易日期":"2026-09-16","账户":"A","操作":"卖出","股票代码":"600801","股票名称":"华新建材","成交价格":11,"成交数量":100},
            {"交易日期":"2026-09-16","账户":"B","操作":"卖出","股票代码":"600801","股票名称":"华新建材","成交价格":9,"成交数量":100},
        ])
        linked = rf.apply_actual_trade_outcomes(records, trades)
        self.assertEqual(linked.iloc[0]["真实交易状态"], "已清仓")
        self.assertEqual(linked.iloc[0]["实际结果"], "平本卖出")
        self.assertEqual(float(linked.iloc[0]["实际收益率%"]), 0.0)


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
