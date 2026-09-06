from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("bs4", MagicMock())
sys.modules.setdefault("openai", MagicMock())
sys.modules.setdefault("requests", MagicMock())

from datetime import date, datetime
from zoneinfo import ZoneInfo

from research.market_opinion_mining import (
    group_attention_sectors,
    parse_published_at,
    review_quality_reasons,
    source_date,
    target_trade_date,
    title_review_date_matches,
)


class OpinionSectorGroupingTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
