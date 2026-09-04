from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock

sys.modules.setdefault("bs4", MagicMock())
sys.modules.setdefault("openai", MagicMock())

from datetime import date

from research.market_opinion_mining import group_attention_sectors, title_review_date_matches


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


if __name__ == "__main__":
    unittest.main()
