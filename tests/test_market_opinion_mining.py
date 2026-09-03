from __future__ import annotations

import unittest

from research.market_opinion_mining import group_attention_sectors


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


if __name__ == "__main__":
    unittest.main()
