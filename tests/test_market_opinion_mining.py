from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules.setdefault("bs4", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("requests", MagicMock())

from datetime import date, datetime
from zoneinfo import ZoneInfo

from research.market_opinion_mining import (
    apply_sample_status,
    compute_concept_index_metrics,
    group_attention_sectors,
    parse_published_at,
    render_source_links,
    review_quality_reasons,
    opinion_finalization,
    retain_ai_verified_quality,
    source_date,
    target_trade_date,
    title_review_date_matches,
    topic_api_candidates_from_payload,
    topic_api_post_date,
)
from research import market_opinion_mining as opinion


class OpinionSectorGroupingTests(unittest.TestCase):
    def test_opinion_waits_until_fifteen_or_22_deadline(self):
        cn=ZoneInfo("Asia/Shanghai")
        self.assertEqual(opinion_finalization(15,datetime(2026,9,8,20,55,tzinfo=cn)),(False,"before_21_release"))
        self.assertEqual(opinion_finalization(15,datetime(2026,9,8,21,0,tzinfo=cn)),(True,"quality_target_met"))
        self.assertEqual(opinion_finalization(12,datetime(2026,9,8,21,30,tzinfo=cn)),(False,"awaiting_more_quality_articles"))
        self.assertEqual(opinion_finalization(12,datetime(2026,9,8,22,0,tzinfo=cn)),(True,"deadline_partial"))

    def test_ai_quality_gate_rejects_single_stock_or_missing_dimensions(self):
        sources=[{"article_id":"a","title":"综合复盘"},{"article_id":"b","title":"个人持仓"}]
        mined=[
            {"article_id":"a","quality_flags":["广告"]},
            {"article_id":"b","quality_flags":["单股为主","缺少板块"]},
        ]
        kept,analyses,rejected=retain_ai_verified_quality(sources,mined)
        self.assertEqual([x["article_id"] for x in kept],["a"])
        self.assertEqual([x["article_id"] for x in analyses],["a"])
        self.assertEqual(rejected[0]["article_id"],"b")

    def test_fetch_html_retries_transient_timeout(self):
        response=MagicMock(text="ok")
        response.raise_for_status.return_value=None
        with patch.object(opinion.requests,"get",side_effect=[TimeoutError("temporary"),response]) as get, \
             patch.object(opinion.time,"sleep"):
            self.assertEqual(opinion.fetch_html("https://www.tgb.cn/test"),"ok")
        self.assertEqual(get.call_count,2)

    def test_discovery_stage_is_saved_once_for_parallel_batches(self):
        discovered=[{"url":"https://www.tgb.cn/a/1","title_hint":"复盘文章","read_count":1,"score":6,"list_url":"x"}]
        with tempfile.TemporaryDirectory() as td, \
             patch.object(opinion,"wait_until_cn"), \
             patch.object(opinion,"discover_articles",return_value=discovered) as discover, \
             patch.object(opinion,"source_date",return_value=date(2026,9,7)):
            opinion.run_discover_stage(Path(td))
            saved=opinion.json.loads((Path(td)/"discovery.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["source_date"],"2026-09-07")
        self.assertEqual(saved["discovered"],discovered)
        discover.assert_called_once()

    def test_quality_pool_accumulates_and_deduplicates_between_runs(self):
        with tempfile.TemporaryDirectory() as td, patch.object(opinion,"ROOT",Path(td)), \
             patch.object(opinion,"now_cn",return_value=datetime(2026,9,8,21,10,tzinfo=ZoneInfo("Asia/Shanghai"))):
            first_sources=[{"article_id":"a","title":"A","url":"https://www.tgb.cn/a/1"}]
            first_mined=[{"article_id":"a","quality_flags":[]}]
            sources,mined=opinion.merge_staged_quality_pool("2026-09-08","2026-09-09",first_sources,first_mined)
            self.assertEqual([x["article_id"] for x in sources],["a"])
            second_sources=[first_sources[0],{"article_id":"b","title":"B","url":"https://www.tgb.cn/a/2"}]
            second_mined=[first_mined[0],{"article_id":"b","quality_flags":[]}]
            sources,mined=opinion.merge_staged_quality_pool("2026-09-08","2026-09-09",second_sources,second_mined)
            self.assertEqual([x["article_id"] for x in sources],["a","b"])
            saved=opinion.json.loads((Path(td)/"staging"/"2026-09-08.json").read_text(encoding="utf-8"))
            self.assertEqual(len(saved["sources"]),2)
            self.assertNotIn("body",saved)

    def test_pushplus_acceptance_keeps_shortcode_without_claiming_delivery(self):
        response=MagicMock(status_code=200,text='{"code":200}')
        response.json.return_value={"code":200,"msg":"执行成功","data":"short-code-1"}
        with patch.dict(opinion.os.environ,{"PUSHPLUS_TOKEN":"token"},clear=False), \
             patch.object(opinion.requests,"post",return_value=response):
            receipt=opinion.push_summary({"article_count":0},"2026-09-06","2026-09-07",[])
        self.assertTrue(receipt["accepted"])
        self.assertEqual(receipt["short_code"],"short-code-1")

    def test_attention_and_trend_are_separate(self):
        sectors = [
            {"sector": "机器人", "mention_count": 8, "stance": "加强"},
            {"sector": "农业", "mention_count": 10, "stance": "退潮"},
            {"sector": "液冷", "mention_count": 6, "stance": "活跃"},
            {"sector": "未知", "mention_count": 2, "stance": "不明确"},
        ]
        groups = group_attention_sectors(sectors)
        self.assertEqual(groups["退潮或走弱"][0]["sector"], "农业")
        self.assertEqual(groups["观点偏强或加强"][0]["sector"], "机器人")
        self.assertEqual(groups["活跃但分化"][0]["sector"], "液冷")
        self.assertEqual(groups["状态不明确"][0]["sector"], "未知")

    def test_explicit_old_review_date_is_rejected_but_tomorrow_strategy_is_allowed(self):
        target = date(2026, 9, 3)
        self.assertFalse(title_review_date_matches("2026年9月2日 市场复盘与明日策略", target))
        self.assertFalse(title_review_date_matches("0902复盘丨指数承压", target))
        self.assertTrue(title_review_date_matches("9月3日主题复盘", target))
        self.assertTrue(title_review_date_matches("退潮期空仓！附9.4明日市场核心策略", target))

    def test_weekend_articles_target_next_trading_day(self):
        current=datetime(2026,9,5,20,30,tzinfo=ZoneInfo("Asia/Shanghai"))
        calendar=[date(2026,9,4),date(2026,9,7)]
        self.assertEqual(source_date(current),date(2026,9,5))
        self.assertEqual(target_trade_date(current,calendar),date(2026,9,7))

    def test_publication_timestamp_must_be_parsed_from_article_page(self):
        parsed=parse_published_at("淘股吧原创 2026-09-06 20:48 | 浏览100")
        self.assertEqual(parsed.date(),date(2026,9,6))
        self.assertEqual(parsed.hour,20)
        compact=parse_published_at("26-09-06 21:03 300次浏览")
        self.assertEqual(compact.date(),date(2026,9,6))
        iso=parse_published_at("2026-09-06T21:03:22+08:00")
        self.assertEqual(iso.date(),date(2026,9,6))

    def test_quality_requires_market_and_sector_dimensions(self):
        good=("市场指数成交额与赚钱效应发生变化，情绪进入分歧。"
              "板块题材围绕主线轮动，资金从高位退潮方向转向低位修复。"*30)
        self.assertEqual(review_quality_reasons("9月6日市场复盘",good),[])
        single_stock=("某股票今日买入，记录个人成交和持仓。"*80)
        reasons=review_quality_reasons("个人实盘",single_stock)
        self.assertIn("市场维度不足",reasons)
        self.assertIn("板块/周期维度不足",reasons)

    def test_ths_concept_metrics_separate_daily_and_five_day_state(self):
        import pandas as pd
        frame=pd.DataFrame({
            "日期":pd.date_range("2026-09-01",periods=6,freq="D"),
            "收盘价":[100,101,102,103,104,106],
            "成交量":[100,100,100,100,100,150],
        })
        out=compute_concept_index_metrics(frame,"机器人","885000")
        self.assertEqual(out["asof_date"],"2026-09-06")
        self.assertAlmostEqual(out["five_day_pct"],6.0,places=2)
        self.assertEqual(out["volume_ratio_5d"],1.5)
        self.assertEqual(out["state"],"上涨加强")

    def test_article_links_only_render_tgb_sources_and_escape_html(self):
        rendered=render_source_links([
            {"title":"复盘 <一>","url":"https://www.tgb.cn/a/abc"},
            {"title":"外站", "url":"https://example.com/a"},
        ])
        self.assertIn("https://www.tgb.cn/a/abc",rendered)
        self.assertIn("复盘 &lt;一&gt;",rendered)
        self.assertNotIn("example.com",rendered)


    def test_topic_api_pages_expand_latest_review_discovery(self):
        payload={"dto":{"list":[
            {"topicType":"T","newTopicID":"abc123","subject":"9.8市场复盘与板块轮动","viewNum":"888"},
            {"topicType":"W","newTopicID":"short1","subject":"短说说不是文章","viewNum":99},
            {"topicType":"T","newTopicID":"def456","subject":"收盘情绪及明日策略","viewNum":12},
        ]}}
        rows=topic_api_candidates_from_payload(payload,2)
        self.assertEqual([x["url"] for x in rows],[
            "https://www.tgb.cn/a/abc123","https://www.tgb.cn/a/def456",
        ])
        self.assertTrue(all("pageNo=2" in x["list_url"] for x in rows))

    def test_topic_api_current_day_precedes_old_high_read_posts(self):
        cn=ZoneInfo("Asia/Shanghai")
        current_ms=int(datetime(2026,9,8,21,7,tzinfo=cn).timestamp()*1000)
        old_ms=int(datetime(2026,9,7,23,0,tzinfo=cn).timestamp()*1000)
        payload={"dto":{"list":[
            {"topicType":"T","newTopicID":"fresh","subject":"9月8日市场复盘与板块轮动","viewNum":"3","postTime":current_ms},
            {"topicType":"T","newTopicID":"old","subject":"高阅读历史市场复盘","viewNum":"99999","postTime":old_ms},
        ]}}
        rows=topic_api_candidates_from_payload(payload,1,date(2026,9,8))
        self.assertEqual([x["url"] for x in rows],["https://www.tgb.cn/a/fresh"])
        self.assertEqual(topic_api_post_date(current_ms),date(2026,9,8))

    def test_partial_sample_keeps_full_consensus_fields(self):
        summary={
            "market_consensus":{"stance":"谨慎","phase":["分歧"],"summary":"现有样本形成的摘要","confidence":"中"},
            "market_disagreements":["农业持续性存在分歧"],
            "sector_consensus":[{"sector":"农业","mention_count":4,"stance":"加强"}],
            "stock_attention":[{"stock":"亚盛集团","mention_count":3}],
            "tomorrow_consensus_watch":["观察农业分化"],
            "limitations":[],
        }
        out=apply_sample_status(summary,7)
        self.assertEqual(out["market_consensus"]["summary"],"现有样本形成的摘要")
        self.assertEqual(out["market_consensus"]["confidence"],"低")
        self.assertTrue(out["sector_consensus"])
        self.assertTrue(out["stock_attention"])
        self.assertIn("基于现有合格样本",out["sample_status"])


if __name__ == "__main__":
    unittest.main()
