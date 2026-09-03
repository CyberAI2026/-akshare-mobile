import importlib.util
import sys
import unittest
from datetime import datetime
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

    def test_formal_latest_only_updates_when_ready(self):
        self.assertEqual(mod.norm_code("SZ000001"),"000001")
        self.assertEqual(mod.norm_code(600000.0),"600000")


if __name__=="__main__":
    unittest.main()
