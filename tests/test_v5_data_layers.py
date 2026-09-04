import unittest
import sys
from unittest.mock import MagicMock
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pandas as pd

sys.modules.setdefault("akshare",MagicMock())
sys.modules.setdefault("requests",MagicMock())
import v5_core as core
import v5_cli as cli


class MarketReviewTests(unittest.TestCase):
    def test_official_counts_use_spot_and_public_limit_pools(self):
        spot=pd.DataFrame({
            "代码":["000001","000002","000003","000004","000005","000006"],
            "名称":["A","B","C","D","E","F"],
            "涨跌幅":[1.0,2.0,-1.0,-2.0,0.0,3.0],
            "成交额":[10,20,30,40,50,60],
        })
        legu=pd.DataFrame({"item":["上涨","下跌","平盘","涨停","跌停","停牌"],"value":[1,4,1,9,8,0]})
        up_pool=pd.DataFrame({"代码":["000001","000006"],"连板数":[2,3]})
        down_pool=pd.DataFrame({"代码":["000004"]})
        broken_pool=pd.DataFrame({"代码":["000002"],"涨跌幅":[4.0]})
        previous_pool=pd.DataFrame({"代码":["000003","000005"],"涨跌幅":[2.0,-1.0]})
        strong_pool=pd.DataFrame({"代码":["000001","000003","000006"]})
        with patch.object(core,"fetch_index_history",return_value=(pd.DataFrame(),"",[])), \
             patch.object(core.ak,"stock_market_activity_legu",return_value=legu), \
             patch.object(core.ak,"stock_zt_pool_em",return_value=up_pool), \
             patch.object(core.ak,"stock_zt_pool_dtgc_em",return_value=down_pool), \
             patch.object(core.ak,"stock_zt_pool_zbgc_em",return_value=broken_pool), \
             patch.object(core.ak,"stock_zt_pool_previous_em",return_value=previous_pool), \
             patch.object(core.ak,"stock_zt_pool_strong_em",return_value=strong_pool), \
             patch.object(core.ak,"stock_zh_a_spot_em",side_effect=RuntimeError("blocked")), \
             patch.object(core.ak,"stock_zh_a_spot",return_value=spot):
            _,breadth,qa=core.fetch_market_review(5)
        r=breadth.iloc[0]
        self.assertEqual((r["上涨家数"],r["下跌家数"],r["平盘家数"]),(3,2,1))
        self.assertEqual((r["涨停家数"],r["跌停家数"]),(2,1))
        self.assertEqual(r["股票数"],6)
        self.assertFalse(r["市场宽度是否降级"])
        self.assertFalse(r["涨跌停是否降级"])
        self.assertEqual(r["涨停股池代码"],"000001|000006")
        self.assertEqual((r["炸板家数"],r["触板家数"]),(1,3))
        self.assertAlmostEqual(r["封板成功率"],2/3)
        self.assertEqual(r["最高连板数"],3)
        self.assertAlmostEqual(r["昨日涨停平均溢价"],0.5)
        self.assertAlmostEqual(r["昨日涨停红盘率"],0.5)
        self.assertTrue(r["市场情绪影子层可用"])
        self.assertEqual(r["炸板股池代码"],"000002")
        self.assertTrue((qa["对象"]=="正式口径与乐咕差异").any())

        payload=cli._market_payload(pd.DataFrame(),breadth)
        self.assertNotIn("炸板家数",payload["市场宽度当日"][0])
        components=cli._market_sentiment_components(breadth)
        self.assertEqual(set(components["成分类型"]),{"涨停","跌停","炸板","昨日涨停","强势股"})


class SectorFlowTests(unittest.TestCase):
    @staticmethod
    def _table(names):
        n=len(names)
        return pd.DataFrame({
            "序号":range(1,n+1),"行业":names,"行业指数":[100+i for i in range(n)],
            "阶段涨跌幅":[f"{i+1}%" for i in range(n)],
            "流入资金":[10+i for i in range(n)],"流出资金":[5+i for i in range(n)],
            "净额":[5 for _ in range(n)],"公司家数":[10 for _ in range(n)],
        })

    def test_sector_flow_deduplicates_and_records_cross_period_warning(self):
        concept_now=self._table(["AI视频","AI视频","军工"])
        concept_now=concept_now.rename(columns={"阶段涨跌幅":"行业-涨跌幅"})
        industry_now=self._table(["军工装备","教育"]).rename(columns={"阶段涨跌幅":"行业-涨跌幅"})

        def concept(symbol):
            return concept_now if symbol=="即时" else self._table(["AI视频","军工","自由贸易港"])

        def industry(symbol):
            return industry_now if symbol=="即时" else self._table(["军工装备","教育"])

        with patch.object(core.ak,"stock_fund_flow_concept",side_effect=concept), \
             patch.object(core.ak,"stock_fund_flow_industry",side_effect=industry):
            tables,qa=core.fetch_public_sector_flow(datetime(2026,9,2,15,30))
        self.assertEqual(len(tables),10)
        self.assertEqual(len(tables["concept_now"]),2)
        self.assertEqual(tables["concept_now"]["行业"].nunique(),2)
        self.assertEqual(tables["concept_now"].iloc[0]["资金单位"],"亿元")
        self.assertTrue((qa["测试"]=="concept_now").any())
        self.assertTrue(qa["错误"].str.contains("自由贸易港",na=False).any())
        self.assertEqual(tables["concept_now"].iloc[0]["业务时区"],"Asia/Shanghai")
        self.assertTrue(str(tables["concept_now"].iloc[0]["抓取时间"]).endswith("+0800"))

    def test_high_attention_sector_crosses_opinion_with_market_fact(self):
        concept_now = pd.DataFrame({
            "行业": ["机器人", "液冷", "农业", "低位题材"],
            "板块类型": ["概念"] * 4,
            "行业-涨跌幅": [4.0, 2.0, 1.0, -1.0],
            "净额": [5.0, 2.0, -1.0, -2.0],
        })
        opinion = {"daily_consensus": {"sector_consensus": [
            {"sector": "农业", "mention_count": 10, "stance": "退潮"},
            {"sector": "机器人", "mention_count": 8, "stance": "加强"},
            {"sector": "液冷", "mention_count": 6, "stance": "分化"},
            {"sector": "不存在", "mention_count": 4, "stance": "活跃"},
        ]}}
        out = cli._attention_sector_market_groups({"concept_now": concept_now}, opinion)
        self.assertEqual(out["groups"]["高关注且观点退潮"][0]["板块"], "农业")
        self.assertEqual(out["groups"]["高关注且涨幅靠前"][0]["板块"], "机器人")
        self.assertEqual(out["groups"]["高关注但活跃分化"][0]["板块"], "液冷")
        self.assertEqual(out["groups"]["高关注但行情未核验"][0]["板块"], "不存在")

    def test_sector_flow_converts_aware_utc_to_china_business_date(self):
        table=self._table(["军工"])
        now_table=table.rename(columns={"阶段涨跌幅":"行业-涨跌幅"})
        def source(symbol):
            return now_table if symbol=="即时" else table
        with patch.object(core.ak,"stock_fund_flow_concept",side_effect=source), \
             patch.object(core.ak,"stock_fund_flow_industry",side_effect=source), \
             patch.object(core,"is_trade_day",return_value=True):
            tables,_=core.fetch_public_sector_flow(datetime(2026,9,3,8,0,tzinfo=ZoneInfo("UTC")))
        row=tables["concept_now"].iloc[0]
        self.assertEqual(row["交易日期"],"2026-09-03")
        self.assertEqual(row["抓取时间"],"2026-09-03 16:00:00+0800")

    def test_complete_industry_family_remains_partially_usable_when_concepts_fail(self):
        tables={f"industry_{p}":self._table(["水泥","教育"]) for p in ["now","3d","5d","10d","20d"]}
        qa=pd.DataFrame([
            *[{"测试":f"concept_{p}","状态":"失败"} for p in ["now","3d","5d","10d","20d"]],
            *[{"测试":f"industry_{p}","状态":"成功"} for p in ["now","3d","5d","10d","20d"]],
        ])
        usable,validation=cli._sector_readiness(tables,qa)
        self.assertTrue(validation["ai_enabled"])
        self.assertEqual(validation["status"],"部分可用")
        self.assertEqual(validation["industry_table_count"],5)
        self.assertEqual(validation["concept_table_count"],0)
        self.assertEqual(len(usable),5)


class NotificationTests(unittest.TestCase):
    def test_pushplus_retries_then_succeeds(self):
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'{"code":200}'
        with patch.dict(cli.os.environ,{"PUSHPLUS_TOKEN":"test-token"}), \
             patch.object(cli.urllib.request,"urlopen",side_effect=[RuntimeError("temporary"),response]) as mocked, \
             patch.object(cli.time,"sleep") as sleeper:
            ok=cli.pushplus_notify("title","body",attempts=3)
        self.assertTrue(ok)
        self.assertEqual(mocked.call_count,2)
        sleeper.assert_called_once_with(2)


if __name__ == "__main__":
    unittest.main()
