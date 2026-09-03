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


class MarketReviewTests(unittest.TestCase):
    def test_official_counts_use_spot_and_public_limit_pools(self):
        spot=pd.DataFrame({
            "代码":["000001","000002","000003","000004","000005","000006"],
            "名称":["A","B","C","D","E","F"],
            "涨跌幅":[1.0,2.0,-1.0,-2.0,0.0,3.0],
            "成交额":[10,20,30,40,50,60],
        })
        legu=pd.DataFrame({"item":["上涨","下跌","平盘","涨停","跌停","停牌"],"value":[1,4,1,9,8,0]})
        up_pool=pd.DataFrame({"代码":["000001","000006"]})
        down_pool=pd.DataFrame({"代码":["000004"]})
        with patch.object(core,"fetch_index_history",return_value=(pd.DataFrame(),"",[])), \
             patch.object(core.ak,"stock_market_activity_legu",return_value=legu), \
             patch.object(core.ak,"stock_zt_pool_em",return_value=up_pool), \
             patch.object(core.ak,"stock_zt_pool_dtgc_em",return_value=down_pool), \
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
        self.assertTrue((qa["对象"]=="正式口径与乐咕差异").any())


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


if __name__ == "__main__":
    unittest.main()
