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
    compute_concept_index_metrics,
    group_attention_sectors,
    parse_published_at,
    render_source_links,
    review_quality_reasons,
    source_date,
    target_trade_date,
    title_review_date_matches,
)
from research import market_opinion_mining as opinion


class OpinionSectorGroupingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
