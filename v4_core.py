from __future__ import annotations

import io
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

import akshare as ak
import numpy as np
import pandas as pd
import requests

APP_VERSION = "V4"
STRATEGY_VERSION = "research_v0.4.1"

MODE_DAYS = {"25日粗筛": 25, "120日结构筛选": 120, "250日生命周期筛选": 250}


# ---------- 股票池输入 ----------
def _norm_code(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    s = str(value).strip()
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""
    return digits[-6:].zfill(6)


def _find_col(columns: Iterable[str], aliases: list[str]) -> str | None:
    cols = [str(c).strip() for c in columns]
    norm = {re.sub(r"[\s_\-]+", "", c).lower(): c for c in cols}
    for a in aliases:
        k = re.sub(r"[\s_\-]+", "", a).lower()
        if k in norm:
            return norm[k]
    for c in cols:
        nk = re.sub(r"[\s_\-]+", "", c).lower()
        if any(re.sub(r"[\s_\-]+", "", a).lower() in nk for a in aliases):
            return c
    return None


def pool_from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["股票代码", "股票名称"])
    code_col = _find_col(df.columns, ["股票代码", "证券代码", "代码", "stockcode", "code", "symbol"])
    name_col = _find_col(df.columns, ["股票名称", "证券名称", "证券简称", "名称", "name", "stockname"])
    if code_col is None:
        raise ValueError("没有识别到股票代码列。请至少包含“股票代码/证券代码/代码/code”之一。")
    out = pd.DataFrame()
    out["股票代码"] = df[code_col].map(_norm_code)
    out["股票名称"] = df[name_col].astype(str).str.strip() if name_col else ""
    out = out[out["股票代码"].str.fullmatch(r"\d{6}", na=False)].copy()
    out = out.drop_duplicates("股票代码", keep="first").reset_index(drop=True)
    return out


def pool_from_upload(file_name: str, data: bytes) -> pd.DataFrame:
    lower = file_name.lower()
    bio = io.BytesIO(data)
    if lower.endswith(".csv"):
        try:
            df = pd.read_csv(bio, dtype=str, encoding="utf-8-sig")
        except UnicodeDecodeError:
            bio.seek(0)
            df = pd.read_csv(bio, dtype=str, encoding="gb18030")
        return pool_from_dataframe(df)
    if lower.endswith((".xlsx", ".xls")):
        book = pd.ExcelFile(bio)
        best = None
        best_score = -1
        for sheet in book.sheet_names:
            tmp = pd.read_excel(book, sheet_name=sheet, dtype=str)
            score = 0
            if _find_col(tmp.columns, ["股票代码", "证券代码", "代码", "code", "symbol"]):
                score += 10
            if _find_col(tmp.columns, ["股票名称", "证券简称", "名称", "name"]):
                score += 2
            score += min(len(tmp), 1000) / 1000
            if score > best_score:
                best, best_score = tmp, score
        if best is None:
            raise ValueError("Excel 中没有可读取的工作表。")
        return pool_from_dataframe(best)
    raise ValueError("仅支持 .xlsx/.xls/.csv 股票池文件。")


def pool_from_text(text: str) -> pd.DataFrame:
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[,，\s]+", line, maxsplit=1)
        code = _norm_code(parts[0])
        name = parts[1].strip() if len(parts) > 1 else ""
        if re.fullmatch(r"\d{6}", code):
            rows.append((code, name))
    return pd.DataFrame(rows, columns=["股票代码", "股票名称"]).drop_duplicates("股票代码")


# ---------- 行情抓取 ----------
def market_prefix(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return "sh" + code
    if code.startswith(("0", "1", "2", "3")):
        return "sz" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    return code


def _date_range(days: int) -> tuple[str, str]:
    need = days + (5 if days == 120 else 0)
    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=max(120, int(need * 2.25) + 80))
    return start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")


def _std_em(df: pd.DataFrame) -> pd.DataFrame:
    ren = {"日期": "日期", "开盘": "开盘价", "最高": "最高价", "最低": "最低价", "收盘": "收盘价",
           "成交量": "成交量", "成交额": "成交额", "换手率": "换手率"}
    out = df[[c for c in ren if c in df.columns]].rename(columns=ren).copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
    return out


def _std_sina(df: pd.DataFrame) -> pd.DataFrame:
    ren = {"date": "日期", "open": "开盘价", "high": "最高价", "low": "最低价", "close": "收盘价",
           "volume": "成交量", "amount": "成交额", "turnover": "换手率"}
    out = df[[c for c in ren if c in df.columns]].rename(columns=ren).copy()
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
    if "换手率" not in out.columns:
        out["换手率"] = np.nan
    return out


def _fetch_hist_source(code: str, start: str, end: str, adjust: str, source: str) -> pd.DataFrame:
    if source == "sina":
        raw = ak.stock_zh_a_daily(symbol=market_prefix(code), start_date=start, end_date=end, adjust=adjust)
        return _std_sina(raw) if raw is not None and not raw.empty else pd.DataFrame()
    raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust=adjust)
    return _std_em(raw) if raw is not None and not raw.empty else pd.DataFrame()


def fetch_history(code: str, days: int, retries: int = 2, pause=(0.35, 0.9), include_raw: bool = True):
    start, end = _date_range(days)
    need = days + (5 if days == 120 else 0)
    errors = []
    qfq = pd.DataFrame(); qfq_source = ""
    # Streamlit Cloud 已验证新浪更稳定，因此 V4 优先新浪。
    for source in ("sina", "eastmoney"):
        for n in range(retries):
            try:
                time.sleep(random.uniform(*pause))
                qfq = _fetch_hist_source(code, start, end, "qfq", source)
                if qfq.empty:
                    raise RuntimeError("空数据")
                qfq = qfq.sort_values("日期").drop_duplicates("日期", keep="last").tail(need).reset_index(drop=True)
                if len(qfq) < min(10, need):
                    raise RuntimeError(f"交易日过少:{len(qfq)}")
                qfq_source = source
                break
            except Exception as e:
                errors.append(f"{source}/qfq/{n+1}:{type(e).__name__}:{e}")
        if not qfq.empty:
            break
    if qfq.empty:
        return pd.DataFrame(), {"source": "", "raw_source": "", "errors": errors, "raw_matched": 0}

    raw_source = ""; matched = 0
    if include_raw:
        raw = pd.DataFrame()
        for source in (qfq_source, "sina" if qfq_source != "sina" else "eastmoney"):
            for n in range(retries):
                try:
                    time.sleep(random.uniform(*pause))
                    raw = _fetch_hist_source(code, start, end, "", source)
                    if raw.empty:
                        raise RuntimeError("空数据")
                    raw = raw.sort_values("日期").drop_duplicates("日期", keep="last").tail(need).reset_index(drop=True)
                    raw_source = source
                    break
                except Exception as e:
                    errors.append(f"{source}/raw/{n+1}:{type(e).__name__}:{e}")
            if not raw.empty:
                break
        if not raw.empty:
            rr = raw[["日期", "开盘价", "最高价", "最低价", "收盘价"]].rename(columns={
                "开盘价": "未复权开盘价", "最高价": "未复权最高价", "最低价": "未复权最低价", "收盘价": "未复权收盘价"})
            qfq = qfq.merge(rr, on="日期", how="left")
            matched = int(qfq["未复权收盘价"].notna().sum())
            qfq["前复权比例系数"] = pd.to_numeric(qfq["收盘价"], errors="coerce") / pd.to_numeric(qfq["未复权收盘价"], errors="coerce").replace(0, np.nan)
    if days == 120 and "成交量" in qfq.columns:
        qfq["5日成交量比"] = pd.to_numeric(qfq["成交量"], errors="coerce") / pd.to_numeric(qfq["成交量"], errors="coerce").shift(1).rolling(5).mean()
        qfq = qfq.tail(120).reset_index(drop=True)
    else:
        qfq = qfq.tail(days).reset_index(drop=True)
    return qfq, {"source": qfq_source, "raw_source": raw_source, "errors": errors, "raw_matched": matched}


def fetch_pool_history(pool: pd.DataFrame, days: int, checkpoint=None, cache_dir: str | Path | None=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows, qa = [], []
    total = len(pool)
    cache_path = Path(cache_dir) if cache_dir else None
    if cache_path:
        cache_path.mkdir(parents=True, exist_ok=True)
    for i, row in pool.reset_index(drop=True).iterrows():
        code, input_name = row["股票代码"], str(row.get("股票名称", "") or "")
        cached = cache_path / f"{code}.csv" if cache_path else None
        if cached and cached.exists():
            try:
                df = pd.read_csv(cached, parse_dates=["日期"])
                meta = {"source": "cache", "raw_source": "cache", "errors": [], "raw_matched": int(df.get("未复权收盘价", pd.Series(dtype=float)).notna().sum())}
            except Exception:
                df, meta = fetch_history(code, days)
        else:
            df, meta = fetch_history(code, days)
        if cached and not df.empty and not cached.exists():
            df.to_csv(cached, index=False, encoding="utf-8-sig")
        if df.empty:
            qa.append({"股票代码": code, "股票名称": input_name, "状态": "失败", "交易日数": 0,
                       "前复权源": meta["source"], "未复权源": meta["raw_source"], "错误": " | ".join(meta["errors"][-5:])})
        else:
            x = df.copy(); x.insert(0, "股票名称", input_name); x.insert(0, "股票代码", code)
            all_rows.append(x)
            qa.append({"股票代码": code, "股票名称": input_name, "状态": "成功", "交易日数": len(df),
                       "前复权源": meta["source"], "未复权源": meta["raw_source"], "未复权匹配日": meta["raw_matched"],
                       "错误": " | ".join(meta["errors"][-3:])})
        if checkpoint:
            checkpoint(i + 1, total, code, qa[-1])
    data = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    return data, pd.DataFrame(qa)


# ---------- 研究筛选（可版本化，避免把规则写死在抓取层） ----------
def _series_metrics(g: pd.DataFrame) -> dict:
    g = g.sort_values("日期").copy()
    c = pd.to_numeric(g["收盘价"], errors="coerce")
    h = pd.to_numeric(g["最高价"], errors="coerce")
    l = pd.to_numeric(g["最低价"], errors="coerce")
    if c.dropna().empty:
        return {}
    last = float(c.iloc[-1])
    def ret(n):
        return float(last / c.iloc[-n-1] - 1) if len(c) > n and pd.notna(c.iloc[-n-1]) and c.iloc[-n-1] else np.nan
    ma20 = c.rolling(20).mean(); ma30 = c.rolling(30).mean(); ma60 = c.rolling(60).mean(); ma120 = c.rolling(120).mean()
    amp5 = float((h.tail(5).max() - l.tail(5).min()) / l.tail(5).min()) if len(g) >= 5 and l.tail(5).min() > 0 else np.nan
    hi20 = float(h.tail(min(20, len(h))).max()); hi250 = float(h.max()); lo250 = float(l.min())
    robust_upper = np.nan
    if len(g) >= 6:
        vals = sorted(pd.to_numeric(h.iloc[-6:-1], errors="coerce").dropna().tolist(), reverse=True)
        if len(vals) >= 2:
            robust_upper = vals[1]
    return {
        "最新收盘": last, "ret10": ret(10), "ret20": ret(20), "ret40": ret(40), "ret60": ret(60), "ret120": ret(120),
        "amp5": amp5, "距20日高点": last / hi20 - 1 if hi20 else np.nan,
        "距250日高点": last / hi250 - 1 if hi250 else np.nan,
        "250日位置": (last - lo250) / (hi250 - lo250) if hi250 > lo250 else np.nan,
        "MA20距离": last / ma20.iloc[-1] - 1 if len(ma20) and pd.notna(ma20.iloc[-1]) else np.nan,
        "MA30_5日斜率": ma30.iloc[-1] / ma30.iloc[-6] - 1 if len(ma30) >= 35 and pd.notna(ma30.iloc[-6]) else np.nan,
        "MA60_10日斜率": ma60.iloc[-1] / ma60.iloc[-11] - 1 if len(ma60) >= 70 and pd.notna(ma60.iloc[-11]) else np.nan,
        "MA120_20日斜率": ma120.iloc[-1] / ma120.iloc[-21] - 1 if len(ma120) >= 140 and pd.notna(ma120.iloc[-21]) else np.nan,
        "距稳健5日上沿": last / robust_upper - 1 if robust_upper and robust_upper > 0 else np.nan,
    }


def build_metrics(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    if data.empty:
        return pd.DataFrame()
    for code, g in data.groupby("股票代码", sort=True):
        m = _series_metrics(g)
        name = str(g["股票名称"].iloc[-1]) if "股票名称" in g else ""
        rows.append({"股票代码": code, "股票名称": name, **m})
    return pd.DataFrame(rows)


def _rank_and_audit(x: pd.DataFrame, score_col: str, max_n: int, eligible_col: str | None = None, stage: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回正式入选结果 + 全样本审计表。审计表保留每只股票为什么入选/未入选。"""
    z = x.copy()
    if z.empty:
        return z, z
    z["阶段排名"] = z[score_col].rank(method="first", ascending=False).astype("Int64")
    if eligible_col and eligible_col in z.columns:
        eligible = z[eligible_col].fillna(False).astype(bool)
    else:
        eligible = pd.Series(True, index=z.index)
    eligible_sorted = z[eligible].sort_values(score_col, ascending=False)
    selected_codes = set(eligible_sorted.head(max_n)["股票代码"].astype(str))
    z["本阶段入选"] = z["股票代码"].astype(str).isin(selected_codes)
    cap_note = f"；本阶段上限{max_n}只"
    def reason(r):
        if not bool(r.get(eligible_col, True)) if eligible_col else False:
            return f"未入选：未满足{stage}最低资格条件"
        if bool(r["本阶段入选"]):
            return f"入选：按{score_col}排序第{int(r['阶段排名'])}名{cap_note}"
        return f"未入选：满足基础条件，但排名第{int(r['阶段排名'])}名，超出{max_n}只上限"
    z["决策说明"] = z.apply(reason, axis=1)
    selected = z[z["本阶段入选"]].sort_values(score_col, ascending=False).reset_index(drop=True)
    audit = z.sort_values(["本阶段入选", score_col], ascending=[False, False]).reset_index(drop=True)
    return selected, audit


def stage1_rank(metrics: pd.DataFrame, max_n: int = 150, return_audit: bool = False):
    """25日：宽松粗筛。仅保留一个非常宽松的最低资格条件，其余以排序压缩样本。"""
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["ret20", "amp5", "距20日高点", "MA20距离"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    x["20日动量贡献"] = x["ret20"].clip(-0.2, 0.5).fillna(-0.2) * 35
    x["距20日高点贡献"] = (x["距20日高点"].clip(-0.3, 0).fillna(-0.3) + 0.3) * 25
    x["MA20位置贡献"] = x["MA20距离"].clip(-0.15, 0.3).fillna(-0.15) * 20
    x["短波动惩罚"] = (x["amp5"].fillna(0.5) - 0.18).clip(lower=0) * 25
    x["阶段1分"] = x["20日动量贡献"] + x["距20日高点贡献"] + x["MA20位置贡献"] - x["短波动惩罚"]
    # 只作为粗筛最低资格，不把尚未验证的细参数硬编码。
    x["阶段1通过"] = (x["最新收盘"] > 0) & (x["MA20距离"] > -0.08)
    x["阶段1风险提示"] = np.where(x["amp5"] > 0.18, "近5日波动偏大", "")
    selected, audit = _rank_and_audit(x, "阶段1分", max_n, "阶段1通过", "一级粗筛")
    return (selected, audit) if return_audit else selected


def stage2_rank(metrics: pd.DataFrame, max_n: int = 30, return_audit: bool = False):
    """120日：整理成熟+趋势仍活。当前版本以排序为主，不把研究中的弱证据做成硬淘汰线。"""
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["ret10", "ret40", "amp5", "MA20距离", "MA30_5日斜率", "距稳健5日上沿"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    near_upper = 1 - ((x["距稳健5日上沿"].fillna(-0.2) - 0.005).abs() / 0.08).clip(0, 1)
    mature = 1 - ((x["amp5"].fillna(0.4) - 0.12).abs() / 0.20).clip(0, 1)
    trend_alive = x["ret40"].clip(-0.25, 0.6).fillna(-0.25)
    x["稳健上沿贡献"] = near_upper * 30
    x["整理成熟贡献"] = mature * 15
    x["40日趋势贡献"] = trend_alive * 35
    x["MA30斜率贡献"] = x["MA30_5日斜率"].clip(-0.1, 0.15).fillna(-0.1) * 80
    x["阶段2分"] = x["稳健上沿贡献"] + x["整理成熟贡献"] + x["40日趋势贡献"] + x["MA30斜率贡献"]
    x["阶段2风险提示"] = np.select(
        [x["amp5"] > 0.18, x["ret40"] < 0, x["距稳健5日上沿"].abs() > 0.08],
        ["短波动偏大", "40日趋势偏弱", "距离短周期稳健上沿较远"], default="")
    selected, audit = _rank_and_audit(x, "阶段2分", max_n, None, "二级结构筛选")
    return (selected, audit) if return_audit else selected


def stage3_rank(metrics: pd.DataFrame, max_n: int = 10, return_audit: bool = False):
    """250日：生命周期。高位/长趋势优先，并显式展示过热与长期低位修复惩罚。"""
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["250日位置", "距250日高点", "ret40", "ret120", "MA60_10日斜率", "MA120_20日斜率"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")
    pos = x["250日位置"].clip(0, 1).fillna(0)
    near_hi = (1 + x["距250日高点"].clip(-1, 0).fillna(-1)).clip(0, 1)
    longtrend = x["ret120"].clip(-0.6, 1.2).fillna(-0.6)
    midtrend = x["ret40"].clip(-0.4, 0.8).fillna(-0.4)
    slope = x["MA120_20日斜率"].clip(-0.15, 0.20).fillna(-0.15)
    overheat = (x["ret40"].fillna(0) - 0.45).clip(lower=0)
    low_rebound = (0.45 - pos).clip(lower=0)
    x["250日位置贡献"] = pos * 35
    x["接近250日高点贡献"] = near_hi * 25
    x["120日趋势贡献"] = longtrend * 12
    x["40日趋势贡献"] = midtrend * 12
    x["MA120斜率贡献"] = slope * 60
    x["近期过热惩罚"] = overheat * 25
    x["长期低位反弹惩罚"] = low_rebound * 30
    x["阶段3分"] = x["250日位置贡献"] + x["接近250日高点贡献"] + x["120日趋势贡献"] + x["40日趋势贡献"] + x["MA120斜率贡献"] - x["近期过热惩罚"] - x["长期低位反弹惩罚"]
    x["生命周期标签"] = np.select(
        [pos < 0.45, x["ret40"] > 0.45, pos >= 0.75],
        ["长期低位修复", "近期加速偏大", "右上角/高位趋势"], default="中段/待确认")
    x["阶段3风险提示"] = np.select(
        [pos < 0.45, x["ret40"] > 0.45, x["ret120"] < 0],
        ["长期位置偏低，警惕下降趋势修复", "40日加速偏大，警惕趋势成熟", "120日趋势仍偏弱"], default="")
    selected, audit = _rank_and_audit(x, "阶段3分", max_n, None, "三级生命周期筛选")
    return (selected, audit) if return_audit else selected


# ---------- 14:45 实时 + 5分钟 ----------
def _std_spot(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    ren = {
        "代码":"股票代码", "名称":"股票名称", "最新价":"当前价", "今开":"今日开盘价", "最高":"今日最高价", "最低":"今日最低价",
        "成交量":"截至当前成交量", "成交额":"截至当前成交额", "换手率":"换手率", "量比":"实时量比", "涨跌幅":"当日涨跌幅", "昨收":"昨收",
        "最新":"当前价", "今开":"今日开盘价", "总手":"截至当前成交量", "金额":"截至当前成交额", "换手":"换手率", "涨幅":"当日涨跌幅"
    }
    out = df.rename(columns={k:v for k,v in ren.items() if k in df.columns}).copy()
    if "股票代码" in out:
        out["股票代码"] = out["股票代码"].map(_norm_code)
    return out


def fetch_spot_pool(pool: pd.DataFrame) -> tuple[pd.DataFrame, str, list[str]]:
    errors=[]
    sources = [("eastmoney", lambda: ak.stock_zh_a_spot_em()), ("sina", lambda: ak.stock_zh_a_spot())]
    spot = pd.DataFrame(); used=""
    for source, fn in sources:
        try:
            raw = fn(); tmp = _std_spot(raw)
            if tmp.empty or "股票代码" not in tmp:
                raise RuntimeError("实时接口字段异常/空")
            spot=tmp; used=source; break
        except Exception as e:
            errors.append(f"{source}:{type(e).__name__}:{e}")
    if spot.empty:
        return pd.DataFrame(), used, errors
    want=set(pool["股票代码"].astype(str))
    out=spot[spot["股票代码"].isin(want)].copy()
    out["日期"] = datetime.now().strftime("%Y-%m-%d")
    out["数据时间"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cols=["股票代码","股票名称","日期","数据时间","今日开盘价","当前价","今日最高价","今日最低价","截至当前成交量","截至当前成交额","换手率","实时量比","当日涨跌幅","昨收"]
    for c in cols:
        if c not in out: out[c]=np.nan
    return out[cols].sort_values("股票代码").reset_index(drop=True), used, errors


def _std_minute(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    ren={"day":"时间","open":"开盘价","high":"最高价","low":"最低价","close":"收盘价","volume":"成交量","amount":"成交额",
         "时间":"时间","开盘":"开盘价","最高":"最高价","最低":"最低价","收盘":"收盘价","成交量":"成交量","成交额":"成交额","换手率":"换手率"}
    out=df.rename(columns={k:v for k,v in ren.items() if k in df.columns}).copy()
    if "时间" in out: out["时间"]=pd.to_datetime(out["时间"], errors="coerce")
    return out


def fetch_5m(code: str) -> tuple[pd.DataFrame, str, list[str]]:
    errors=[]; today=datetime.now().date()
    try:
        raw=ak.stock_zh_a_minute(symbol=market_prefix(code), period="5", adjust="")
        x=_std_minute(raw)
        if not x.empty:
            x=x[x["时间"].dt.date==today]
            if not x.empty: return x.reset_index(drop=True), "sina", errors
    except Exception as e: errors.append(f"sina:{type(e).__name__}:{e}")
    try:
        start=f"{today:%Y-%m-%d} 09:30:00"; end=f"{today:%Y-%m-%d} 15:00:00"
        raw=ak.stock_zh_a_hist_min_em(symbol=code, start_date=start, end_date=end, period="5", adjust="")
        x=_std_minute(raw)
        if not x.empty: return x.reset_index(drop=True), "eastmoney", errors
    except Exception as e: errors.append(f"eastmoney:{type(e).__name__}:{e}")
    return pd.DataFrame(), "", errors


def fetch_realtime_package(pool: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    snap, source, errs = fetch_spot_pool(pool)
    mins=[]; qa=[]
    for _,r in pool.iterrows():
        code=r["股票代码"]; name=r.get("股票名称","")
        m,msrc,merr=fetch_5m(code)
        if not m.empty:
            m.insert(0,"股票名称",name); m.insert(0,"股票代码",code); mins.append(m)
        qa.append({"股票代码":code,"股票名称":name,"实时快照源":source,"5分钟源":msrc,"5分钟行数":len(m),"错误":" | ".join((errs+merr)[-5:])})
    minute=pd.concat(mins,ignore_index=True) if mins else pd.DataFrame()
    return snap, minute, pd.DataFrame(qa)


def confirmation_metrics(snapshot: pd.DataFrame, minute: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    for _,r in snapshot.iterrows():
        code=r["股票代码"]; name=r["股票名称"]
        m=minute[minute["股票代码"]==code].sort_values("时间") if not minute.empty else pd.DataFrame()
        current=pd.to_numeric(pd.Series([r.get("当前价")]),errors="coerce").iloc[0]
        pct=pd.to_numeric(pd.Series([r.get("当日涨跌幅")]),errors="coerce").iloc[0]
        qratio=pd.to_numeric(pd.Series([r.get("实时量比")]),errors="coerce").iloc[0]
        last30=np.nan; volacc=np.nan
        if len(m)>=2:
            close=pd.to_numeric(m["收盘价"],errors="coerce")
            last30=float(close.iloc[-1]/close.iloc[max(0,len(close)-7)]-1) if close.iloc[max(0,len(close)-7)] else np.nan
            vol=pd.to_numeric(m["成交量"],errors="coerce")
            if len(vol)>=6 and vol.iloc[:-3].tail(3).mean()>0:
                volacc=float(vol.tail(3).mean()/vol.iloc[:-3].tail(3).mean())
        score=(0 if pd.isna(pct) else max(-5,min(8,pct))*2.0)+(0 if pd.isna(last30) else max(-0.05,min(0.08,last30))*150)+(0 if pd.isna(qratio) else min(qratio,3)*3)+(0 if pd.isna(volacc) else min(volacc,3)*4)
        rows.append({"股票代码":code,"股票名称":name,"当前价":current,"当日涨跌幅":pct,"实时量比":qratio,"近约30分钟涨幅":last30,"尾盘量能加速比":volacc,"14:45确认分":score})
    return pd.DataFrame(rows).sort_values("14:45确认分",ascending=False).reset_index(drop=True)


# ---------- Excel ----------
def to_excel_bytes(sheets: dict[str,pd.DataFrame]) -> bytes:
    bio=io.BytesIO()
    with pd.ExcelWriter(bio,engine="openpyxl") as w:
        for name,df in sheets.items():
            (df if df is not None else pd.DataFrame()).to_excel(w,sheet_name=name[:31],index=False)
    return bio.getvalue()


# ---------- OpenAI 分析（可选） ----------
def openai_analyze(kind: str, payload: dict, model: str | None=None) -> str:
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        return "OPENAI_API_KEY 未配置；本次仅完成数据与机械排序。"
    from openai import OpenAI
    client=OpenAI(api_key=key)
    model=model or os.getenv("OPENAI_MODEL") or "gpt-5.6-terra"
    system=(
        "你是A股强势股二次启动研究系统的分析模块。目标是寻找已经证明强势、整理成熟后重新点火的候选，避免未整理完成和趋势尾端。"
        "必须把计算事实与判断分开；不能为了凑数而推荐；最终确认允许0到2只。"
        "已验证方向：中期趋势仍活、短周期波动降温、接近稳健4-5日上沿、适度重新加速有帮助；固定MA距离、固定量缩、固定距20日高点等不作为硬规则。"
        "交易受A股T+1约束，14:45确认重点看当天实时量价与5分钟结构。"
    )
    prompt=system+"\n任务类型:"+kind+"\n数据(JSON):\n"+json.dumps(payload,ensure_ascii=False,default=str)
    resp=client.responses.create(model=model,input=prompt)
    return resp.output_text


# ---------- GitHub 云端存储与任务触发 ----------
@dataclass
class GithubConfig:
    token: str
    repo: str
    branch: str="main"

    @property
    def api(self): return f"https://api.github.com/repos/{self.repo}"


def github_config_from_env() -> GithubConfig | None:
    token=os.getenv("GITHUB_PAT","").strip(); repo=os.getenv("GITHUB_REPO","").strip(); branch=os.getenv("GITHUB_BRANCH","main").strip()
    return GithubConfig(token,repo,branch) if token and repo else None


def gh_headers(cfg: GithubConfig):
    return {"Authorization":f"Bearer {cfg.token}","Accept":"application/vnd.github+json","X-GitHub-Api-Version":"2022-11-28"}


def gh_put_bytes(cfg: GithubConfig, path: str, content: bytes, message: str) -> str:
    import base64
    url=f"{cfg.api}/contents/{path}"
    old=requests.get(url,headers=gh_headers(cfg),params={"ref":cfg.branch},timeout=20)
    payload={"message":message,"content":base64.b64encode(content).decode(),"branch":cfg.branch}
    if old.status_code==200: payload["sha"]=old.json().get("sha")
    r=requests.put(url,headers=gh_headers(cfg),json=payload,timeout=30); r.raise_for_status()
    return r.json()["content"].get("download_url") or r.json()["content"].get("html_url")


def gh_dispatch(cfg: GithubConfig, workflow: str, inputs: dict | None=None):
    url=f"{cfg.api}/actions/workflows/{workflow}/dispatches"
    r=requests.post(url,headers=gh_headers(cfg),json={"ref":cfg.branch,"inputs":inputs or {}},timeout=20)
    if r.status_code not in (201,204):
        raise RuntimeError(f"GitHub Actions触发失败 {r.status_code}: {r.text[:300]}")


def gh_raw_url(cfg: GithubConfig, path: str) -> str:
    return f"https://raw.githubusercontent.com/{cfg.repo}/{cfg.branch}/{path}"


def gh_list_results(cfg: GithubConfig, path="v4_data") -> list[dict]:
    r=requests.get(f"{cfg.api}/contents/{path}",headers=gh_headers(cfg),params={"ref":cfg.branch},timeout=20)
    if r.status_code!=200: return []
    return r.json() if isinstance(r.json(),list) else []


def is_trade_day(d=None) -> bool:
    d=d or datetime.now().date()
    try:
        cal=ak.tool_trade_date_hist_sina()
        dates=set(pd.to_datetime(cal[cal.columns[0]],errors="coerce").dt.date.dropna())
        return d in dates
    except Exception:
        return d.weekday()<5
