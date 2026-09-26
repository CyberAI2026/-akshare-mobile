from __future__ import annotations

import hashlib
import re
from datetime import date

import pandas as pd

from v5_core import _norm_code


def daily_batch_identity(pool: pd.DataFrame, business_day: date | str) -> str:
    """同一业务日的同一组股票生成确定性批次标识，用于拦截重复点击。"""
    if pool is None or pool.empty or "股票代码" not in pool.columns:
        raise ValueError("每日强势股批次为空或缺少股票代码列。")
    codes=sorted({
        code for code in pool["股票代码"].map(_norm_code)
        if re.fullmatch(r"\d{6}",code)
    })
    if not codes:
        raise ValueError("每日强势股批次没有可识别的六位代码。")
    day=date.fromisoformat(str(business_day)) if not isinstance(business_day,date) else business_day
    fingerprint=hashlib.sha256("\n".join(codes).encode("ascii")).hexdigest()[:16]
    return f"{day:%Y%m%d}_{fingerprint}"
