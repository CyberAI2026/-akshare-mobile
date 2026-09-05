import importlib.util
import sys
import unittest
import tempfile
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pandas as pd

sys.modules.setdefault("akshare",MagicMock())
spec=importlib.util.spec_from_file_location("sector_membership",Path("research/market_sector_context_fetch.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SectorMembershipTests(unittest.TestCase):
    def test_normalize_constituents_filters_master_and_records_point_in_time(self):
        raw=pd.DataFrame({"代码":["000001","000002","600000"],"名称":["甲","乙","丙"]})
        captured=datetime(2026,9,3,19,15,tzinfo=ZoneInfo("Asia/Shanghai"))
        out=mod.normalize_constituents(raw,"概念","人工智能",{"000001","600000"},captured)
        self.assertEqual(set(out["股票代码"]),{"000001","600000"})
        self.assertTrue(out["抓取时间"].str.endswith("+0800").all())
        self.assertTrue(out["映射口径"].str.contains("不可用于倒推").all())

    def test_board_name_normalization(self):
        raw=pd.DataFrame({"板块名称":["人工智能"," 机器人 ","人工智能",None]})
        self.assertEqual(mod.normalize_board_names(raw),["人工智能","机器人"])

    def test_normalize_individual_industry(self):
        raw=pd.DataFrame({"item":["总市值","行业"],"value":["100亿","软件开发"]})
        captured=datetime(2026,9,3,19,15,tzinfo=ZoneInfo("Asia/Shanghai"))
        out=mod.normalize_individual_industry(raw,"000001","测试股",captured)
        self.assertEqual(out.iloc[0]["板块类型"],"行业")
        self.assertEqual(out.iloc[0]["板块名称"],"软件开发")
        self.assertEqual(out.iloc[0]["股票代码"],"000001")

    def test_formal_latest_only_updates_when_ready(self):
        self.assertEqual(mod.norm_code("SZ000001"),"000001")
        self.assertEqual(mod.norm_code(600000.0),"600000")

    def test_headerless_previous_cache_is_treated_as_missing(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"empty.csv"
            path.write_bytes(b"")
            out=mod.load_previous_mapping(path,{"000001"})
        self.assertTrue(out.empty)
        self.assertIn("股票代码",out.columns)

    def test_empty_output_keeps_csv_schema(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            master=pd.DataFrame({"股票代码":["000001"],"股票名称":["平安银行"]})
            mod.save_outputs(root,master,pd.DataFrame(),pd.DataFrame(),{"mapping_rows":0})
            loaded=pd.read_csv(root/"sector_membership.csv.gz",dtype={"股票代码":str})
        self.assertTrue(loaded.empty)
        self.assertIn("板块名称",loaded.columns)

    def test_weekend_skip_is_bypassed_for_cache_recovery(self):
        saturday=date(2026,9,5)
        empty=pd.DataFrame(columns=mod.MAPPING_COLUMNS)
        usable=pd.DataFrame([{"股票代码":"000001","板块类型":"行业","板块名称":"银行"}])
        self.assertFalse(mod.should_skip_non_trading_day(True,saturday,False))
        self.assertTrue(mod.should_skip_non_trading_day(True,saturday,True))
        self.assertFalse(mod.mapping_baseline_usable(empty,1))
        self.assertTrue(mod.mapping_baseline_usable(usable,1))

    def test_sina_fallback_maps_symbol_and_preserves_source(self):
        captured=datetime(2026,9,5,20,0,tzinfo=ZoneInfo("Asia/Shanghai"))
        listing=pd.DataFrame({"label":["gn_test"],"板块":["测试概念"]})
        detail=pd.DataFrame({"symbol":["sz000001","sh600000"],"name":["甲","乙"]})
        with unittest.mock.patch.object(mod.ak,"stock_sector_spot",return_value=listing), \
             unittest.mock.patch.object(mod.ak,"stock_sector_detail",return_value=detail):
            out,qa,count=mod.fetch_sina_type("概念","概念",{"000001"},captured,workers=1)
        self.assertEqual(count,1)
        self.assertEqual(out.iloc[0]["股票代码"],"000001")
        self.assertEqual(out.iloc[0]["板块名称"],"测试概念")
        self.assertEqual(out.iloc[0]["数据源"],"sina_sector_membership_via_akshare")
        self.assertEqual(qa[-1]["状态"],"成功")

    def test_shenwan_fallback_maps_first_level_industry(self):
        captured=datetime(2026,9,5,20,0,tzinfo=ZoneInfo("Asia/Shanghai"))
        listing=pd.DataFrame({"指数代码":["801010"],"指数名称":["农林牧渔"]})
        detail=pd.DataFrame({"证券代码":["000001","600000"],"证券名称":["甲","乙"]})
        with unittest.mock.patch.object(mod.ak,"index_realtime_sw",return_value=listing), \
             unittest.mock.patch.object(mod.ak,"index_component_sw",return_value=detail):
            out,qa,count=mod.fetch_sw_industries({"600000"},captured,workers=1)
        self.assertEqual(count,1)
        self.assertEqual(out.iloc[0]["股票代码"],"600000")
        self.assertEqual(out.iloc[0]["板块名称"],"农林牧渔")
        self.assertEqual(out.iloc[0]["数据源"],"shenwan_industry_membership_via_akshare")
        self.assertEqual(qa[-1]["状态"],"成功")


if __name__=="__main__":
    unittest.main()
