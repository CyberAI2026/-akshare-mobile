from __future__ import annotations

import io
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import akshare as ak
import numpy as np
import pandas as pd
import requests

APP_VERSION = "V5.3-auditable-market-sector-layer"
STRATEGY_VERSION = "research_v0.5-evidence-aligned+pool-v0.3+market-v0.3+sector-v0.1+ai-v0.2"
CN_TZ = ZoneInfo("Asia/Shanghai")


def now_cn() -> datetime:
    return datetime.now(CN_TZ)


def _as_cn_time(value: datetime | None = None) -> datetime:
    """统一业务时钟为北京时间；无时区时间按北京时间解释以兼容旧调用。"""
    if value is None:
        return now_cn()
    if value.tzinfo is None:
        return value.replace(tzinfo=CN_TZ)
    return value.astimezone(CN_TZ)


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
    # 比较时清理空格/下划线/连字符，但返回 DataFrame 中“真实原始列名”。
    # 这对“    名称”这类行情软件导出表头尤其重要。
    original = list(columns)
    pairs = [(c, str(c).strip()) for c in original]
    norm = {re.sub(r"[\s_\-]+", "", cleaned).lower(): c for c, cleaned in pairs}
    for a in aliases:
        k = re.sub(r"[\s_\-]+", "", a).lower()
        if k in norm:
            return norm[k]
    alias_norm = [re.sub(r"[\s_\-]+", "", a).lower() for a in aliases]
    for c, cleaned in pairs:
        nk = re.sub(r"[\s_\-]+", "", cleaned).lower()
        if any(a in nk for a in alias_norm):
            return c
    return None


def _resolve_codes_by_name(names: pd.Series) -> pd.DataFrame:
    """为只有股票名称的行情软件导出表补全A股代码；歧义或缺失时拒绝静默猜测。"""
    requested = names.astype(str).str.strip()
    requested = requested[requested.ne("") & requested.ne("nan")].drop_duplicates()
    sources = [
        ("stock_info_a_code_name", lambda: ak.stock_info_a_code_name()),
        ("stock_zh_a_spot_em", lambda: ak.stock_zh_a_spot_em()),
    ]
    errors = []
    tables = []

    # 每日手工上传优先使用仓库内的代码—名称快照，避免交易所/行情接口
    # 临时不可达时，只有名称的通达信/同花顺导出文件无法提交。
    local_candidates = [
        Path("v5_data/reference/a_share_code_name_master.csv"),
        Path(__file__).resolve().parent / "v5_data/reference/a_share_code_name_master.csv",
    ]
    for local_path in local_candidates:
        if not local_path.exists():
            continue
        try:
            raw = pd.read_csv(local_path, dtype=str, encoding="utf-8-sig")
            code_col = _find_col(raw.columns, ["股票代码", "证券代码", "代码", "code", "symbol"])
            name_col = _find_col(raw.columns, ["股票名称", "证券名称", "证券简称", "名称", "name"])
            if code_col is None or name_col is None:
                raise RuntimeError(f"本地代码表字段异常: {list(raw.columns)}")
            x = pd.DataFrame({
                "股票代码": raw[code_col].map(_norm_code),
                "股票名称": raw[name_col].astype(str).str.strip(),
            })
            x = x[x["股票代码"].str.fullmatch(r"\d{6}", na=False) & x["股票名称"].ne("")]
            if not x.empty:
                tables.append(x)
                break
        except Exception as e:
            errors.append(f"local_code_name:{type(e).__name__}:{e}")
    for source, fetcher in sources:
        try:
            raw = fetcher()
            if raw is None or raw.empty:
                raise RuntimeError("空数据")
            code_col = _find_col(raw.columns, ["股票代码", "证券代码", "代码", "code", "symbol"])
            name_col = _find_col(raw.columns, ["股票名称", "证券名称", "证券简称", "名称", "name"])
            if code_col is None or name_col is None:
                raise RuntimeError(f"字段异常: {list(raw.columns)}")
            x = pd.DataFrame({
                "股票代码": raw[code_col].map(_norm_code),
                "股票名称": raw[name_col].astype(str).str.strip(),
            })
            x = x[x["股票代码"].str.fullmatch(r"\d{6}", na=False) & x["股票名称"].ne("")]
            tables.append(x)
        except Exception as e:
            errors.append(f"{source}:{type(e).__name__}:{e}")
    if not tables:
        raise ValueError("文件只有股票名称，但在线代码—名称表获取失败：" + " | ".join(errors))

    master = pd.concat(tables, ignore_index=True).drop_duplicates()
    ambiguous = set(master.loc[master["股票名称"].duplicated(keep=False), "股票名称"])
    master = master[~master["股票名称"].isin(ambiguous)].drop_duplicates("股票名称")
    code_map = master.set_index("股票名称")["股票代码"]
    missing = [name for name in requested if name not in code_map.index]
    if missing:
        shown = "、".join(missing[:12])
        more = f"等共{len(missing)}只" if len(missing) > 12 else ""
        raise ValueError(f"仅有名称的文件中有股票无法唯一匹配代码：{shown}{more}。请补充代码后重试。")
    return pd.DataFrame({
        "股票代码": [code_map[name] for name in requested],
        "股票名称": list(requested),
    }).reset_index(drop=True)


def pool_from_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["股票代码", "股票名称"])
    code_col = _find_col(df.columns, ["股票代码", "证券代码", "代码", "stockcode", "code", "symbol"])
    name_col = _find_col(df.columns, ["股票名称", "证券名称", "证券简称", "名称", "name", "stockname"])
    if code_col is None:
        if name_col is None:
            raise ValueError("没有识别到股票代码或股票名称列。")
        return _resolve_codes_by_name(df[name_col])
    out = pd.DataFrame()
    out["股票代码"] = df[code_col].map(_norm_code)
    out["股票名称"] = df[name_col].astype(str).str.strip() if name_col else ""
    out = out[out["股票代码"].str.fullmatch(r"\d{6}", na=False)].copy()
    out = out.drop_duplicates("股票代码", keep="first").reset_index(drop=True)
    return out


def _read_delimited_stock_file(data: bytes) -> pd.DataFrame:
    """读取 CSV/TSV/文本导出的“伪 .xls”。不少行情软件把制表符文本保存成 .xls 扩展名。"""
    last_err = None
    # 部分行情软件会把 UTF-16LE 制表符文本命名为 .xls，且文件末尾可能带单个
    # 残缺字节。先严格解码；仅对能由 BOM/NUL 分布确认的 UTF-16 文本允许
    # 忽略最后一个残缺字节，避免把真正的二进制 Excel 静默当成文本。
    looks_utf16_le = data.startswith(b"\xff\xfe") or (
        len(data) >= 8 and data[1:8:2].count(0) >= 3
    )
    looks_utf16_be = data.startswith(b"\xfe\xff") or (
        len(data) >= 8 and data[0:8:2].count(0) >= 3
    )
    encodings = ["utf-8-sig", "gb18030", "gbk"]
    if looks_utf16_le:
        encodings.extend(["utf-16", "utf-16-le"])
    elif looks_utf16_be:
        encodings.extend(["utf-16", "utf-16-be"])
    else:
        encodings.append("utf-16")

    for enc in encodings:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError as e:
            last_err = e
            if enc.startswith("utf-16") and (looks_utf16_le or looks_utf16_be):
                try:
                    usable = data[:-1] if len(data) % 2 else data
                    text = usable.decode(enc, errors="strict")
                except Exception as retry_error:
                    last_err = retry_error
                    continue
            else:
                continue
        except Exception as e:
            last_err = e
            continue
        # 部分行情软件导出的“xls”其实是仅使用 CR 的制表符文本；统一换行后再交给 pandas。
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # 优先制表符；再让 pandas 自动嗅探常见分隔符。
        for sep in ("\t", None, ",", ";", "|"):
            try:
                kwargs = dict(dtype=str)
                if sep is None:
                    tmp = pd.read_csv(io.StringIO(text), sep=None, engine="python", **kwargs)
                else:
                    tmp = pd.read_csv(io.StringIO(text), sep=sep, engine="python", **kwargs)
                if tmp is not None and len(tmp.columns) >= 1 and len(tmp) >= 1:
                    # 名单可能只有“名称”列；代码可由本地代码—名称快照补全。
                    has_code = _find_col(tmp.columns, ["股票代码", "证券代码", "代码", "stockcode", "code", "symbol"])
                    has_name = _find_col(tmp.columns, ["股票名称", "证券名称", "证券简称", "名称", "name", "stockname"])
                    if has_code or has_name:
                        return tmp
            except Exception as e:
                last_err = e
    raise ValueError(f"无法按文本/CSV/TSV格式读取文件：{last_err}")


def _read_excel_best_sheet(data: bytes, engine: str | None = None) -> pd.DataFrame:
    bio = io.BytesIO(data)
    book = pd.ExcelFile(bio, engine=engine)
    best = None
    best_score = -1
    for sheet in book.sheet_names:
        tmp = pd.read_excel(book, sheet_name=sheet, dtype=str)
        score = 0
        if _find_col(tmp.columns, ["股票代码", "证券代码", "代码", "stockcode", "code", "symbol"]):
            score += 10
        if _find_col(tmp.columns, ["股票名称", "证券名称", "证券简称", "股票简称", "名称", "name", "stockname"]):
            score += 2
        score += min(len(tmp), 1000) / 1000
        if score > best_score:
            best, best_score = tmp, score
    if best is None:
        raise ValueError("Excel 中没有可读取的工作表。")
    return best


def pool_from_upload(file_name: str, data: bytes) -> pd.DataFrame:
    lower = (file_name or "").lower()
    if not data:
        raise ValueError("上传文件为空。")

    # 不只相信扩展名，先根据文件签名识别真实格式。
    is_xlsx_zip = data[:4] == b"PK\x03\x04"
    is_ole_xls = data[:8] == bytes.fromhex("D0CF11E0A1B11AE1")

    try:
        if is_xlsx_zip:
            return pool_from_dataframe(_read_excel_best_sheet(data, engine="openpyxl"))
        if is_ole_xls:
            return pool_from_dataframe(_read_excel_best_sheet(data, engine="xlrd"))

        if lower.endswith(".xlsx"):
            return pool_from_dataframe(_read_excel_best_sheet(data, engine="openpyxl"))
        if lower.endswith(".xls"):
            # 真 .xls 用 xlrd；若其实是行情软件导出的制表符文本，则自动回退到文本读取。
            try:
                return pool_from_dataframe(_read_excel_best_sheet(data, engine="xlrd"))
            except Exception:
                return pool_from_dataframe(_read_delimited_stock_file(data))
        if lower.endswith((".csv", ".txt", ".tsv")):
            return pool_from_dataframe(_read_delimited_stock_file(data))

        # 未知扩展名也尝试文本嗅探，提升兼容性。
        return pool_from_dataframe(_read_delimited_stock_file(data))
    except Exception as e:
        raise ValueError(
            f"无法识别股票池文件 {file_name!r}。支持标准 XLSX、标准 XLS，以及行情软件导出的制表符/CSV文本。详细错误：{e}"
        ) from e


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
    end_dt = now_cn()
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
    lo5 = float(l.tail(min(5, len(l))).min()) if len(l) else np.nan
    lo10 = float(l.tail(min(10, len(l))).min()) if len(l) else np.nan
    return {
        "最新收盘": last, "ret1": ret(1), "ret10": ret(10), "ret20": ret(20), "ret40": ret(40), "ret60": ret(60), "ret120": ret(120),
        "amp5": amp5, "距20日高点": last / hi20 - 1 if hi20 else np.nan,
        "距250日高点": last / hi250 - 1 if hi250 else np.nan,
        "250日位置": (last - lo250) / (hi250 - lo250) if hi250 > lo250 else np.nan,
        "MA20距离": last / ma20.iloc[-1] - 1 if len(ma20) and pd.notna(ma20.iloc[-1]) else np.nan,
        "MA30_5日斜率": ma30.iloc[-1] / ma30.iloc[-6] - 1 if len(ma30) >= 35 and pd.notna(ma30.iloc[-6]) else np.nan,
        "MA60_10日斜率": ma60.iloc[-1] / ma60.iloc[-11] - 1 if len(ma60) >= 70 and pd.notna(ma60.iloc[-11]) else np.nan,
        "MA120_20日斜率": ma120.iloc[-1] / ma120.iloc[-21] - 1 if len(ma120) >= 140 and pd.notna(ma120.iloc[-21]) else np.nan,
        "距稳健5日上沿": last / robust_upper - 1 if robust_upper and robust_upper > 0 else np.nan,
        "近5日低点": lo5, "近10日低点": lo10,
        "距近5日低点": last / lo5 - 1 if pd.notna(lo5) and lo5 > 0 else np.nan,
        "距近10日低点": last / lo10 - 1 if pd.notna(lo10) and lo10 > 0 else np.nan,
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


def _rank_and_audit(x: pd.DataFrame, score_col: str, min_n: int, max_n: int, eligible_col: str | None = None, stage: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """软容量筛选：不是死卡一个数字。

    先保证最低研究容量 min_n；如果 min_n 边界出现同分，则把同分组一起纳入，
    但最多到 max_n。若合格样本本来少于 min_n，则不为凑数降低资格线。
    """
    z = x.copy()
    if z.empty:
        return z, z
    if eligible_col and eligible_col in z.columns:
        eligible = z[eligible_col].fillna(False).astype(bool)
    else:
        eligible = pd.Series(True, index=z.index)
    # 主排序只使用既有研究分；代码只用于完全同分时保证结果可复现，不代表策略证据。
    eligible_sorted = z[eligible].sort_values([score_col, "股票代码"], ascending=[False, True]).copy()
    if eligible_sorted.empty:
        selected_codes=set(); cutoff=np.nan; selected_n=0
    elif len(eligible_sorted) <= min_n:
        selected_n=len(eligible_sorted); cutoff=eligible_sorted[score_col].min()
        selected_codes=set(eligible_sorted["股票代码"].astype(str))
    else:
        cutoff=eligible_sorted.iloc[min_n-1][score_col]
        natural_n=int((eligible_sorted[score_col] >= cutoff).sum())
        selected_n=min(max_n, max(min_n, natural_n))
        selected_codes=set(eligible_sorted.head(selected_n)["股票代码"].astype(str))
    z["阶段排名"] = z[score_col].rank(method="min", ascending=False).astype("Int64")
    z["本阶段入选"] = z["股票代码"].astype(str).isin(selected_codes)
    z["阶段软容量下限"] = min_n
    z["阶段软容量上限"] = max_n
    z["实际入选数"] = selected_n
    z["边界分数"] = cutoff
    def reason(r):
        if eligible_col and not bool(r.get(eligible_col, False)):
            return f"未入选：未满足{stage}最低资格条件"
        if bool(r["本阶段入选"]):
            return f"入选：{score_col}={r.get(score_col)}；软容量{min_n}-{max_n}只，本次实际{selected_n}只"
        return f"未入选：满足基础条件，但位于本次软容量边界之外（{min_n}-{max_n}只）"
    z["决策说明"] = z.apply(reason, axis=1)
    selected = z[z["本阶段入选"]].sort_values([score_col, "股票代码"], ascending=[False, True]).reset_index(drop=True)
    audit = z.sort_values(["本阶段入选", score_col, "股票代码"], ascending=[False, False, True]).reset_index(drop=True)
    return selected, audit

def stage1_rank(metrics: pd.DataFrame, min_n: int = 150, max_n: int = 200, return_audit: bool = False):
    """25日一级：宽松粗筛，只做方向性压缩，不把弱证据写成硬门槛。

    研究约束：
    - 不使用“距20日高点越近越好”作为核心得分；
    - 不使用精确MA20距离作为资格线；
    - 5日振幅只用于识别仍然极端的短波动，不假设某个固定振幅最优；
    - 本层不是买点判断，只把明显弱/乱的状态排到后面。
    """
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["ret10", "ret20", "amp5", "MA20距离", "距稳健5日上沿"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")

    x["20日方向证据"] = (x["ret20"] >= 0).astype(int) * 2
    x["MA20上方证据"] = (x["MA20距离"] >= 0).astype(int) * 2
    x["短波动非极端证据"] = (x["amp5"] <= 0.18).astype(int)
    x["10日不过热证据"] = (x["ret10"] <= 0.20).astype(int)
    x["10日非急跌证据"] = (x["ret10"] >= -0.12).astype(int)
    # 仅作为很宽的结构辅助，不使用20日最高点距离做核心排序。
    x["短沿附近辅助"] = x["距稳健5日上沿"].between(-0.10, 0.06, inclusive="both").astype(int)
    x["阶段1分"] = x[["20日方向证据", "MA20上方证据", "短波动非极端证据", "10日不过热证据", "10日非急跌证据", "短沿附近辅助"]].sum(axis=1)
    x["阶段1通过"] = x["最新收盘"].notna() & (x["最新收盘"] > 0)
    x["阶段1风险提示"] = np.select(
        [x["amp5"] > 0.18, x["ret10"] > 0.20, x["ret20"] < 0],
        ["近5日波动仍偏大", "近10日速度偏快", "20日方向仍偏弱"], default="")
    x["阶段1规则说明"] = "宽松粗筛：方向/非极端波动/不过热；不以精确MA距离或距20日高点为硬规则"
    selected, audit = _rank_and_audit(x, "阶段1分", min_n, max_n, "阶段1通过", "一级粗筛")
    return (selected, audit) if return_audit else selected


def stage2_rank(metrics: pd.DataFrame, min_n: int = 30, max_n: int = 40, return_audit: bool = False):
    """120日二级：核心研究层——整理成熟 + 中期趋势仍活 + 接近稳健5日上沿。

    强证据用于资格/主排序；信号日2%-6%重新加速仅作中等证据加分，绝不作为稳定胜率承诺。
    """
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["ret1", "ret10", "ret40", "amp5", "MA20距离", "MA30_5日斜率", "距稳健5日上沿"]:
        x[c] = pd.to_numeric(x[c], errors="coerce")

    x["整理成熟"] = (x["amp5"] <= 0.18) & (x["ret10"] <= 0.20)
    x["中期趋势仍活"] = x["ret40"] >= 0
    x["均线趋势辅助"] = (x["MA20距离"] > 0) & (x["MA30_5日斜率"] > 0)
    x["稳健上沿核心区"] = x["距稳健5日上沿"].between(-0.02, 0.03, inclusive="both")
    x["稳健上沿宽区"] = x["距稳健5日上沿"].between(-0.05, 0.05, inclusive="both")
    x["适度重新加速"] = x["ret1"].between(0.02, 0.06, inclusive="both")

    x["整理成熟贡献"] = x["整理成熟"].astype(int) * 3
    x["40日趋势贡献"] = x["中期趋势仍活"].astype(int) * 3
    x["均线趋势辅助贡献"] = x["均线趋势辅助"].astype(int)
    x["稳健上沿贡献"] = np.select([x["稳健上沿核心区"], x["稳健上沿宽区"]], [4, 2], default=0)
    x["重新加速辅助贡献"] = x["适度重新加速"].astype(int)  # 中等证据，权重低于结构证据
    x["阶段2分"] = x[["整理成熟贡献", "40日趋势贡献", "均线趋势辅助贡献", "稳健上沿贡献", "重新加速辅助贡献"]].sum(axis=1)

    # 只把反复验证较强的“成熟+趋势仍活”作为最低资格；上沿距离和重新加速用于排序，不做绝对门槛。
    x["阶段2通过"] = x["整理成熟"] & x["中期趋势仍活"]
    x["阶段2风险提示"] = np.select(
        [x["amp5"] > 0.18, x["ret10"] > 0.20, x["ret40"] < 0, x["距稳健5日上沿"].abs() > 0.08],
        ["短波动仍偏大", "10日速度仍偏快，整理可能未完成", "40日趋势偏弱", "距离短周期稳健上沿较远"], default="")
    x["阶段2规则说明"] = "核心：整理成熟+40日趋势仍活+稳健5日上沿；2%-6%单日加速仅为中等证据"
    selected, audit = _rank_and_audit(x, "阶段2分", min_n, max_n, "阶段2通过", "二级结构筛选")
    return (selected, audit) if return_audit else selected


def stage3_rank(metrics: pd.DataFrame, max_n: int = 10, return_audit: bool = False):
    """250日三级：生命周期否决/修正层，而不是“越靠250日最高点越好”。

    主要任务：识别长期下降趋势修复，避免把修复反弹误判成右上角二次启动；
    40日累计涨幅过大只做风险提示，不因累计涨幅单独判定趋势末端。
    若传入阶段2分，则保留二级结构排序作为三级的连续性证据。
    """
    x = metrics.copy()
    if x.empty:
        return (x, x) if return_audit else x
    for c in ["250日位置", "距250日高点", "ret40", "ret120", "MA60_10日斜率", "MA120_20日斜率", "阶段2分"]:
        if c not in x.columns:
            x[c] = np.nan
        x[c] = pd.to_numeric(x[c], errors="coerce")

    pos = x["250日位置"]
    long_ok = (x["ret120"] >= 0) & (x["MA120_20日斜率"] >= 0)
    clear_down_rebound = (pos < 0.45) & (x["ret120"] < 0) & (x["MA120_20日斜率"] < 0)
    right_upper = (pos >= 0.65) & long_ok
    mid_up = long_ok & ~right_upper

    x["长期趋势证据"] = long_ok.astype(int) * 3
    x["右上角位置证据"] = right_upper.astype(int) * 2
    x["40日仍活证据"] = (x["ret40"] >= 0).astype(int)
    x["长期下降修复惩罚"] = clear_down_rebound.astype(int) * 6

    # 保留二级排序连续性；不让250日层用一套任意权重彻底洗牌。
    if x["阶段2分"].notna().any():
        pct = x["阶段2分"].rank(method="average", pct=True)
        x["二级结构延续贡献"] = pct * 3
    else:
        x["二级结构延续贡献"] = 0.0

    x["阶段3分"] = x["长期趋势证据"] + x["右上角位置证据"] + x["40日仍活证据"] + x["二级结构延续贡献"] - x["长期下降修复惩罚"]
    x["生命周期标签"] = np.select(
        [clear_down_rebound, right_upper, mid_up],
        ["长期下降趋势修复", "右上角/高位趋势", "中期上升趋势延续"], default="中段/待确认")
    x["阶段3通过"] = ~clear_down_rebound
    x["阶段3风险提示"] = np.select(
        [clear_down_rebound, x["ret40"] > 0.50, x["ret120"] < 0],
        ["长期下降趋势中的修复/反弹，降级", "40日加速较大：仅作趋势成熟风险提示，不单独判尾端", "120日趋势偏弱"], default="")
    x["阶段3规则说明"] = "生命周期否决/修正：重点排除长期下降修复；不把接近250日高点或累计涨幅本身当成越高越好"
    selected, audit = _rank_and_audit(x, "阶段3分", max_n, max_n, "阶段3通过", "三级生命周期筛选")
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
    captured_at = _as_cn_time()
    out["日期"] = captured_at.strftime("%Y-%m-%d")
    out["数据时间"] = captured_at.strftime("%Y-%m-%d %H:%M:%S%z")
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
    errors=[]; today=now_cn().date()
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


def fetch_candidate_decision_context(pool: pd.DataFrame, news_limit: int = 6) -> tuple[dict[str,pd.DataFrame], pd.DataFrame]:
    """为少量尾盘候选补充基本资料、近10日资金流与最新事件标题；失败项显式进入QA。"""
    profiles=[]; flows=[]; news_rows=[]; qa=[]
    for _, row in pool.iterrows():
        code=str(row["股票代码"]).zfill(6); name=str(row.get("股票名称","") or "")
        try:
            info=ak.stock_individual_info_em(symbol=code, timeout=15)
            item=_find_col(info.columns,["item","项目","指标"])
            value=_find_col(info.columns,["value","值","内容"])
            if info.empty or item is None or value is None:
                raise RuntimeError("个股资料为空或字段异常")
            for _, r in info.iterrows():
                profiles.append({"股票代码":code,"股票名称":name,"资料项":str(r[item]),"资料值":r[value],
                                 "数据时间":now_cn().isoformat(),"数据源":"东方财富个股资料/AKShare"})
            qa.append({"股票代码":code,"股票名称":name,"数据层":"基本面/行业资料","状态":"成功","行数":len(info),"错误":""})
        except Exception as exc:
            qa.append({"股票代码":code,"股票名称":name,"数据层":"基本面/行业资料","状态":"失败","行数":0,"错误":f"{type(exc).__name__}:{exc}"})
        try:
            market="sh" if code.startswith(("5","6","9")) else "sz"
            ff=ak.stock_individual_fund_flow(stock=code, market=market)
            if ff is None or ff.empty:
                raise RuntimeError("个股资金流为空")
            date_col=_find_col(ff.columns,["日期","date"])
            if date_col is not None:
                ff[date_col]=pd.to_datetime(ff[date_col],errors="coerce")
                ff=ff.sort_values(date_col).tail(10)
            else:
                ff=ff.tail(10)
            ff.insert(0,"股票名称",name); ff.insert(0,"股票代码",code)
            ff["数据源"]="东方财富个股资金流/AKShare"
            flows.append(ff)
            qa.append({"股票代码":code,"股票名称":name,"数据层":"近10日资金流","状态":"成功","行数":len(ff),"错误":""})
        except Exception as exc:
            qa.append({"股票代码":code,"股票名称":name,"数据层":"近10日资金流","状态":"失败","行数":0,"错误":f"{type(exc).__name__}:{exc}"})
        try:
            nw=ak.stock_news_em(symbol=code)
            if nw is None or nw.empty:
                raise RuntimeError("个股新闻为空")
            title_col=_find_col(nw.columns,["新闻标题","标题"])
            time_col=_find_col(nw.columns,["发布时间","时间","日期"])
            source_col=_find_col(nw.columns,["文章来源","来源"])
            url_col=_find_col(nw.columns,["新闻链接","链接","url"])
            if title_col is None:
                raise RuntimeError("新闻标题字段缺失")
            if time_col is not None:
                nw[time_col]=pd.to_datetime(nw[time_col],errors="coerce")
                nw=nw.sort_values(time_col,ascending=False)
            for _, r in nw.head(max(1,news_limit)).iterrows():
                news_rows.append({"股票代码":code,"股票名称":name,"发布时间":r.get(time_col,"") if time_col else "",
                                  "新闻标题":str(r.get(title_col,"")),"来源":str(r.get(source_col,"")) if source_col else "",
                                  "链接":str(r.get(url_col,"")) if url_col else "","数据源":"东方财富个股新闻/AKShare"})
            qa.append({"股票代码":code,"股票名称":name,"数据层":"事件标题","状态":"成功","行数":min(len(nw),max(1,news_limit)),"错误":""})
        except Exception as exc:
            qa.append({"股票代码":code,"股票名称":name,"数据层":"事件标题","状态":"失败","行数":0,"错误":f"{type(exc).__name__}:{exc}"})
    tables={
        "候选基本资料":pd.DataFrame(profiles),
        "候选近10日资金流":pd.concat(flows,ignore_index=True) if flows else pd.DataFrame(),
        "候选最新事件标题":pd.DataFrame(news_rows),
    }
    return tables,pd.DataFrame(qa)


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


# ---------- OpenAI 分析 ----------
def openai_analyze(kind: str, payload: dict, model: str | None=None) -> str:
    """调用 Responses API。API 不继承聊天上下文，因此研究边界必须显式写入提示词。"""
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY 未配置；V5.1不会伪造AI观察池。")
    from openai import OpenAI
    client=OpenAI(api_key=key)
    model=model or os.getenv("OPENAI_MODEL") or "gpt-5.6-terra"
    common=(
        "你是A股强势股二次启动研究系统的研究层。只分析输入数据，不使用外部行情，不臆造缺失字段。"
        "研究目标：已知强势股在整理成熟后寻找真正的二次启动点，避免整理未完成时过早介入，也避免趋势成熟/尾端追高。"
        "证据层级：较强证据包括短周期波动已降温、10日速度不过热、中期趋势仍活、靠近稳健4-5日上沿；"
        "中等证据包括适度重新加速与避免极端结构风险；弱或已否定规则不得升级成硬条件，包括固定MA距离、固定量缩比、"
        "固定距20日高点、固定等待天数、固定市场宽度阈值、累计涨幅直接代表趋势年龄。"
        "市场环境只作为风险与仓位上下文，不得使用未经验证的固定阈值一票否决。"
        "必须区分计算事实和研究判断；允许空结果，禁止为了凑数而选股。"
    )
    if "盘后" in kind or "观察池" in kind:
        task=(
            "当前任务是盘后30只研究池筛选到次日0-10只观察池，不是最终买入推荐。"
            "必须优先排除明显长期下降趋势修复、趋势尾端/近期加速极端、结构尚未成熟者；"
            "同时允许仍需次日14:40-14:45验证的候选进入观察池。"
        )
    elif "尾盘" in kind or "14:45" in kind:
        task=(
            "当前任务是次日14:45尾盘确认，最多0-5只；受A股T+1约束。"
            "结构止损距离不是保证最大亏损，隔夜跳空可能造成更大损失。"
        )
    else:
        task="按任务数据完成研究，不扩展到输入之外。"
    output_rule=(
        "只输出一个合法JSON对象，不要Markdown代码围栏，不要JSON前后解释文字。严格遵守任务数据中给定的输出格式。"
    )
    prompt=common+task+output_rule+"\n任务类型:"+kind+"\n数据(JSON):\n"+json.dumps(payload,ensure_ascii=False,default=str,allow_nan=False)
    requested_at = now_cn().isoformat()
    resp=client.responses.create(model=model,input=prompt,max_output_tokens=12000)
    text=(resp.output_text or "").strip()
    if not text:
        raise RuntimeError("OpenAI 返回空文本。")
    usage = getattr(resp, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None
    # 只保存调用凭证与用量，不保存提示词、第三方正文或密钥。
    audit_dir = Path("v5_data/openai_audit")
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit_record = {
        "status": "succeeded",
        "kind": kind,
        "requested_at_cn": requested_at,
        "completed_at_cn": now_cn().isoformat(),
        "response_id": getattr(resp, "id", None),
        "model": getattr(resp, "model", model),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    }
    with (audit_dir / "calls.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(audit_record, ensure_ascii=False) + "\n")
    (audit_dir / "latest.json").write_text(
        json.dumps(audit_record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        "OPENAI_API_CALL_OK "
        f"requested_at={requested_at} response_id={getattr(resp, 'id', None)} "
        f"model={getattr(resp, 'model', model)} "
        f"input_tokens={input_tokens} output_tokens={output_tokens} total_tokens={total_tokens}"
    )
    return text


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

# ---------- V5: 证券类型隔离 / 云端主池 / 全局缓存 / 市场环境 ----------
INDEX_NAMES = {
    "上证指数", "深证成指", "创业板指", "科创50", "北证50",
    "上证综指", "深证成份指数", "创业板指数", "科创50指数", "北证50指数",
}
INDEX_SYMBOLS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    "北证50": "bj899050",
}


def is_index_record(code: str, name: str = "") -> bool:
    """只用于把明确的指数记录从个股池隔离。

    000001/000688 与股票代码有歧义，因此不能仅靠代码排除，必须结合名称；
    399xxx/899050 则可明确视为指数代码域。
    """
    code = _norm_code(code)
    nm = str(name or "").strip().replace(" ", "")
    if code.startswith("399") or code == "899050":
        return True
    if nm in {x.replace(" ", "") for x in INDEX_NAMES}:
        return True
    if "指数" in nm:
        return True
    if nm in {"科创50", "北证50"}:
        return True
    return False


def split_stock_and_indices(pool: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回(个股池, 被隔离的指数/非个股记录)。"""
    if pool is None or pool.empty:
        empty = pd.DataFrame(columns=["股票代码", "股票名称"])
        return empty.copy(), empty.copy()
    x = pool[["股票代码", "股票名称"]].copy()
    x["股票代码"] = x["股票代码"].map(_norm_code)
    x["股票名称"] = x["股票名称"].fillna("").astype(str).str.strip()
    mask = x.apply(lambda r: is_index_record(r["股票代码"], r["股票名称"]), axis=1)
    idx = x[mask].drop_duplicates("股票代码", keep="first").reset_index(drop=True)
    stocks = x[~mask].copy()
    # A股个股代码域：沪市5/6/9、深市0/1/2/3、北交4/8；399等指数已隔离。
    stocks = stocks[stocks["股票代码"].str.match(r"^[0-9]{6}$", na=False)].copy()
    stocks = stocks.drop_duplicates("股票代码", keep="first").reset_index(drop=True)
    return stocks, idx


def _cache_read(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        x = pd.read_csv(path, parse_dates=["日期"], dtype={"股票代码": str})
        if "日期" in x:
            x["日期"] = pd.to_datetime(x["日期"], errors="coerce")
        return x.sort_values("日期").drop_duplicates("日期", keep="last").reset_index(drop=True)
    except Exception:
        return pd.DataFrame()


def seed_global_cache_from_old_runs(root: str | Path, global_cache: str | Path) -> dict:
    """首次升级时复用V4历史缓存：同一股票选行数最多的旧缓存，避免重新全量抓取。"""
    root = Path(root); dst = Path(global_cache); dst.mkdir(parents=True, exist_ok=True)
    best: dict[str, tuple[int, Path]] = {}
    if not root.exists():
        return {"seeded": 0, "scanned": 0}
    scanned = 0
    for p in root.glob("runs/*/*d/cache/*.csv"):
        scanned += 1
        code = p.stem
        try:
            # 只读日期列会更快；失败再忽略。
            n = max(0, sum(1 for _ in p.open("r", encoding="utf-8-sig", errors="ignore")) - 1)
        except Exception:
            continue
        if code not in best or n > best[code][0]:
            best[code] = (n, p)
    seeded = 0
    import shutil
    for code, (_, src) in best.items():
        target = dst / f"{code}.csv"
        if not target.exists():
            shutil.copy2(src, target); seeded += 1
            continue
        try:
            cur_n = max(0, sum(1 for _ in target.open("r", encoding="utf-8-sig", errors="ignore")) - 1)
        except Exception:
            cur_n = 0
        if cur_n < best[code][0]:
            shutil.copy2(src, target); seeded += 1
    return {"seeded": seeded, "scanned": scanned, "available": len(best)}


def fetch_history_incremental(code: str, days: int, cache_file: str | Path, stale_days: int = 8):
    """全局缓存优先。缓存长度足够时只补最近一小段，不再每日重抓120/250日。

    如果缓存长度不足，仍调用原有fetch_history获取完整所需长度；这样新股/首次晋级股票可自动补齐。
    """
    cache_file = Path(cache_file); cache_file.parent.mkdir(parents=True, exist_ok=True)
    need = days + (5 if days == 120 else 0)
    cached = _cache_read(cache_file)
    errors = []
    source = "global-cache"
    raw_source = "global-cache"

    enough = len(cached) >= need
    latest = cached["日期"].max().date() if (not cached.empty and "日期" in cached and cached["日期"].notna().any()) else None
    today = datetime.now().date()
    fresh = bool(latest and (today - latest).days <= stale_days)

    if enough and fresh:
        out = cached.copy()
    elif enough and latest:
        # 增量补最近一段，覆盖若干旧交易日以吸收复权因子变化。
        start = (latest - timedelta(days=12)).strftime("%Y%m%d")
        end = datetime.now().strftime("%Y%m%d")
        inc = pd.DataFrame(); used = ""
        for src in ("sina", "eastmoney"):
            try:
                inc = _fetch_hist_source(code, start, end, "qfq", src)
                if inc is None or inc.empty:
                    raise RuntimeError("空数据")
                used = src; break
            except Exception as e:
                errors.append(f"incremental/{src}:{type(e).__name__}:{e}")
        if inc is not None and not inc.empty:
            # 增量行情若缺真实成交额/换手率，保留接口返回；不自行用前复权价格伪造。
            out = pd.concat([cached, inc], ignore_index=True, sort=False)
            out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
            out = out.sort_values("日期").drop_duplicates("日期", keep="last").tail(max(280, need + 20)).reset_index(drop=True)
            source = f"global-cache+{used}"
            raw_source = "global-cache"
        else:
            out = cached.copy()
            source = "global-cache(stale-fetch-failed)"
    else:
        full, meta = fetch_history(code, max(days, 250 if days >= 250 else days))
        if full is None or full.empty:
            return pd.DataFrame(), {"source": meta.get("source", ""), "raw_source": meta.get("raw_source", ""), "errors": meta.get("errors", []), "raw_matched": meta.get("raw_matched", 0), "cache_mode": "full-fetch-failed"}
        out = full.copy(); source = meta.get("source", ""); raw_source = meta.get("raw_source", ""); errors.extend(meta.get("errors", []))

    if out is None or out.empty:
        return pd.DataFrame(), {"source": source, "raw_source": raw_source, "errors": errors, "raw_matched": 0, "cache_mode": "empty"}
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce")
    out = out.sort_values("日期").drop_duplicates("日期", keep="last").tail(max(280, need + 20)).reset_index(drop=True)
    out.to_csv(cache_file, index=False, encoding="utf-8-sig")

    view = out.tail(need).copy()
    if days == 120 and "成交量" in view.columns:
        vol = pd.to_numeric(view["成交量"], errors="coerce")
        view["5日成交量比"] = vol / vol.shift(1).rolling(5).mean()
        view = view.tail(120).reset_index(drop=True)
    else:
        view = view.tail(days).reset_index(drop=True)
    raw_matched = int(view.get("未复权收盘价", pd.Series(dtype=float)).notna().sum()) if not view.empty else 0
    return view, {"source": source, "raw_source": raw_source, "errors": errors, "raw_matched": raw_matched, "cache_mode": "incremental" if "+" in source else "cache/full"}


def fetch_pool_history_incremental(pool: pd.DataFrame, days: int, global_cache_dir: str | Path, checkpoint=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows, qa = [], []
    cache_dir = Path(global_cache_dir); cache_dir.mkdir(parents=True, exist_ok=True)
    total = len(pool)
    for i, row in pool.reset_index(drop=True).iterrows():
        code = _norm_code(row["股票代码"]); name = str(row.get("股票名称", "") or "")
        df, meta = fetch_history_incremental(code, days, cache_dir / f"{code}.csv")
        if df.empty:
            q = {"股票代码": code, "股票名称": name, "状态": "失败", "交易日数": 0, "前复权源": meta.get("source", ""), "未复权源": meta.get("raw_source", ""), "缓存模式": meta.get("cache_mode", ""), "错误": " | ".join(meta.get("errors", [])[-5:])}
        else:
            x = df.copy(); x.insert(0, "股票名称", name); x.insert(0, "股票代码", code); all_rows.append(x)
            q = {"股票代码": code, "股票名称": name, "状态": "成功", "交易日数": len(df), "前复权源": meta.get("source", ""), "未复权源": meta.get("raw_source", ""), "缓存模式": meta.get("cache_mode", ""), "未复权匹配日": meta.get("raw_matched", 0), "错误": " | ".join(meta.get("errors", [])[-3:])}
        qa.append(q)
        if checkpoint:
            checkpoint(i + 1, total, code, q)
    data = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    return data, pd.DataFrame(qa)


def load_master_pool(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["股票代码", "股票名称", "首次进入日期", "最近提交日期", "提交次数", "当前状态", "淘汰日期", "淘汰原因"])
    x = pd.read_csv(p, dtype={"股票代码": str})
    x["股票代码"] = x["股票代码"].map(_norm_code)
    return x


def merge_master_pool(master: pd.DataFrame, daily: pd.DataFrame, asof=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """把每日30~40只提交与云端主池合并。用户无需判断是否重复。

    已被淘汰的股票若再次被用户提交，会自动重新激活。
    """
    asof = pd.Timestamp(asof or datetime.now().date()).strftime("%Y-%m-%d")
    stocks, excluded = split_stock_and_indices(daily)
    m = master.copy() if master is not None else pd.DataFrame()
    if m.empty:
        m = pd.DataFrame(columns=["股票代码", "股票名称", "首次进入日期", "最近提交日期", "提交次数", "当前状态", "淘汰日期", "淘汰原因"])
    for c in ["股票代码", "股票名称", "首次进入日期", "最近提交日期", "提交次数", "当前状态", "淘汰日期", "淘汰原因"]:
        if c not in m: m[c] = ""
    # pandas 3 对把字符串写入全空且被推断为 float64 的列改为硬错误。
    # 主池状态/日期/说明列在任何赋值前统一为字符串对象，兼容历史 CSV 空列。
    for c in ["股票代码", "股票名称", "首次进入日期", "最近提交日期", "当前状态", "淘汰日期", "淘汰原因"]:
        m[c] = m[c].fillna("").astype("object")
    m["股票代码"] = m["股票代码"].map(_norm_code)
    m = m.drop_duplicates("股票代码", keep="last").set_index("股票代码", drop=False)
    changes=[]
    for _, r in stocks.iterrows():
        code, name = r["股票代码"], str(r.get("股票名称", "") or "")
        if code in m.index:
            old_status = str(m.at[code, "当前状态"] or "")
            m.at[code, "股票名称"] = name or m.at[code, "股票名称"]
            m.at[code, "最近提交日期"] = asof
            try: cnt = int(float(m.at[code, "提交次数"] or 0)) + 1
            except Exception: cnt = 1
            m.at[code, "提交次数"] = cnt
            m.at[code, "当前状态"] = "活跃"
            m.at[code, "淘汰日期"] = ""; m.at[code, "淘汰原因"] = ""
            changes.append({"股票代码":code,"股票名称":name,"变动":"重新激活" if old_status=="已淘汰" else "已有/再次提交"})
        else:
            m.loc[code] = {"股票代码": code, "股票名称": name, "首次进入日期": asof, "最近提交日期": asof, "提交次数": 1, "当前状态": "活跃", "淘汰日期": "", "淘汰原因": ""}
            changes.append({"股票代码":code,"股票名称":name,"变动":"新增"})
    out = m.reset_index(drop=True).sort_values("股票代码").reset_index(drop=True)
    if not excluded.empty:
        for _,r in excluded.iterrows():
            changes.append({"股票代码":r["股票代码"],"股票名称":r["股票名称"],"变动":"隔离为指数/非个股"})
    return out, pd.DataFrame(changes)


def maintain_master_pool(master: pd.DataFrame, metrics120: pd.DataFrame | None, asof=None, inactive_calendar_days: int = 45) -> tuple[pd.DataFrame, pd.DataFrame]:
    """保守、可逆的主池维护v0.1。

    自动淘汰不是交易规则，也不用于证明胜率。只有“较久未被用户再次提交 + 120日结构同时明显转弱”才淘汰。
    若以后用户再次提交，该股票会自动重新激活，因此删除是可逆的。
    """
    if master is None or master.empty:
        return master, pd.DataFrame()
    asof_ts = pd.Timestamp(asof or datetime.now().date())
    x = master.copy()
    # CSV/Excel round-trips may infer all-empty text columns such as 淘汰日期/淘汰原因 as float64 (NaN).
    # Force registry text fields to object before assigning date/reason strings, otherwise pandas>=2.2
    # can raise: TypeError: Invalid value 'YYYY-MM-DD' for dtype 'float64'.
    for c in ["股票代码", "股票名称", "首次进入日期", "最近提交日期", "当前状态", "淘汰日期", "淘汰原因"]:
        if c not in x.columns:
            x[c] = ""
        x[c] = x[c].astype("object")
        x[c] = x[c].where(pd.notna(x[c]), "")
    met = metrics120.copy() if metrics120 is not None else pd.DataFrame()
    if not met.empty:
        keepcols=[c for c in ["股票代码","ret20","ret40","ret120","MA20距离","MA30_5日斜率","amp5","ret10"] if c in met.columns]
        x=x.merge(met[keepcols],on="股票代码",how="left")
    for c in ["ret20","ret40","ret120","MA20距离","MA30_5日斜率","amp5","ret10"]:
        if c not in x: x[c]=np.nan
        x[c]=pd.to_numeric(x[c],errors="coerce")
    last_seen=pd.to_datetime(x["最近提交日期"],errors="coerce")
    age=(asof_ts-last_seen).dt.days
    weak=(x["ret40"]<0)&(x["MA20距离"]<0)&(x["MA30_5日斜率"]<=0)
    very_weak=(x["ret120"]<0)&(x["ret40"]<0)&(x["MA30_5日斜率"]<0)
    short_weak=(x["ret20"]<0)&(x["ret10"]<0)&(x["MA20距离"]<0)
    auto_drop=((age>=inactive_calendar_days)&(weak|very_weak)) | ((age>=60)&short_weak)&(x["当前状态"].astype(str)!="已淘汰")
    cooling=(age>=15)&~auto_drop&(x["当前状态"].astype(str)!="已淘汰")
    active=(age<15)&(x["当前状态"].astype(str)!="已淘汰")
    x.loc[active,"当前状态"]="活跃"
    x.loc[cooling,"当前状态"]="冷却观察"
    x.loc[auto_drop,"当前状态"]="已淘汰"
    x.loc[auto_drop,"淘汰日期"]=asof_ts.strftime("%Y-%m-%d")
    x.loc[auto_drop,"淘汰原因"]="维护v0.1：较久未再次提交，且120日/40日趋势证据同步转弱；若后续重新强势并再次提交可自动恢复"
    audit_cols=["股票代码","股票名称","当前状态","最近提交日期","ret20","ret40","ret120","MA20距离","MA30_5日斜率","淘汰日期","淘汰原因"]
    audit=x[audit_cols].copy()
    base_cols=["股票代码","股票名称","首次进入日期","最近提交日期","提交次数","当前状态","淘汰日期","淘汰原因"]
    return x[base_cols].sort_values("股票代码").reset_index(drop=True), audit.sort_values(["当前状态","股票代码"]).reset_index(drop=True)


def fetch_index_history(symbol: str, days: int = 120) -> tuple[pd.DataFrame, str, list[str]]:
    errors=[]
    # 新浪指数日线通常最简洁；若接口/代码不支持则回退东财指数历史。
    try:
        raw=ak.stock_zh_index_daily(symbol=symbol)
        if raw is not None and not raw.empty:
            ren={"date":"日期","open":"开盘价","high":"最高价","low":"最低价","close":"收盘价","volume":"成交量","amount":"成交额"}
            x=raw.rename(columns={k:v for k,v in ren.items() if k in raw.columns}).copy()
            x["日期"]=pd.to_datetime(x["日期"],errors="coerce")
            return x.sort_values("日期").tail(days).reset_index(drop=True),"sina",errors
    except Exception as e: errors.append(f"sina-index:{type(e).__name__}:{e}")
    try:
        code=symbol[2:] if len(symbol)>6 else symbol
        raw=ak.index_zh_a_hist(symbol=code,period="daily",start_date=(datetime.now()-timedelta(days=400)).strftime("%Y%m%d"),end_date=datetime.now().strftime("%Y%m%d"))
        ren={"日期":"日期","开盘":"开盘价","最高":"最高价","最低":"最低价","收盘":"收盘价","成交量":"成交量","成交额":"成交额"}
        x=raw.rename(columns={k:v for k,v in ren.items() if k in raw.columns}).copy(); x["日期"]=pd.to_datetime(x["日期"],errors="coerce")
        return x.sort_values("日期").tail(days).reset_index(drop=True),"eastmoney",errors
    except Exception as e: errors.append(f"em-index:{type(e).__name__}:{e}")
    return pd.DataFrame(),"",errors


def _price_limit_rule(code: str, name: str = "") -> tuple[float, str]:
    """按代码板块 + ST 名称给出常规日涨跌幅限制。

    仅用于市场生态统计；IPO/恢复上市等无涨跌幅限制日不强行归入涨停。
    """
    code=_norm_code(code); name=str(name or "").upper().replace(" ", "")
    if "ST" in name:
        return 5.0, "ST/*ST 5%"
    if code.startswith(("300","301")):
        return 20.0, "创业板20%"
    if code.startswith(("688","689")):
        return 20.0, "科创板20%"
    if code.startswith(("4","8","920")):
        return 30.0, "北交所30%"
    return 10.0, "沪深主板10%"


def _limit_flags(code: str, name: str, pct) -> tuple[bool,bool,str]:
    try: p=float(pct)
    except Exception: return False,False,"未知"
    limit,board=_price_limit_rule(code,name)
    # 用规则幅度-0.2个百分点作为识别门槛，同时限制上界，避免把新股无涨跌幅限制的大涨误算成涨停。
    near=max(0.1, limit-0.2)
    up=(p >= near) and (p <= limit+0.8)
    down=(p <= -near) and (p >= -(limit+0.8))
    return bool(up),bool(down),board


def _public_market_activity_legu() -> tuple[dict, str]:
    """直接读取公开市场赚钱效应统计，不用逐股涨跌幅推算涨停/跌停。"""
    raw = ak.stock_market_activity_legu()
    if raw is None or raw.empty:
        raise RuntimeError("乐咕市场赚钱效应为空")
    cols = list(raw.columns)
    if "item" in cols and "value" in cols:
        items = raw[["item","value"]].copy()
    elif len(cols) >= 2:
        items = raw.iloc[:, :2].copy()
        items.columns = ["item","value"]
    else:
        raise RuntimeError(f"乐咕返回字段异常: {cols}")
    d = {}
    for _, r in items.iterrows():
        k = str(r["item"]).strip()
        v = r["value"]
        d[k] = v
    required = ["上涨","下跌","涨停","跌停"]
    miss = [k for k in required if k not in d]
    if miss:
        raise RuntimeError(f"乐咕缺少字段: {miss}")
    return d, "legulegu_public_market_activity"


def _to_count(v):
    try:
        if pd.isna(v): return np.nan
        s=str(v).replace(",","").replace("%","").strip()
        return int(round(float(s)))
    except Exception:
        return np.nan


def _count_spot_breadth(spot: pd.DataFrame) -> dict:
    """按逐股快照的涨跌幅符号统计市场宽度，不推算涨跌停。"""
    if spot is None or spot.empty or "当日涨跌幅" not in spot:
        return {}
    pct = pd.to_numeric(spot["当日涨跌幅"], errors="coerce")
    valid = pct.notna()
    if not valid.any():
        return {}
    return {
        "股票数": int(valid.sum()),
        "上涨": int((pct[valid] > 0).sum()),
        "下跌": int((pct[valid] < 0).sum()),
        "平盘": int((pct[valid] == 0).sum()),
    }


def _pool_codes(pool: pd.DataFrame) -> str:
    if pool is None or pool.empty:
        return ""
    code_col = _find_col(pool.columns, ["代码", "股票代码", "证券代码"])
    if code_col is None:
        return ""
    codes = pool[code_col].map(_norm_code)
    return "|".join(sorted(set(c for c in codes if c)))


def _pool_numeric(pool: pd.DataFrame, aliases: list[str]) -> pd.Series:
    if pool is None or pool.empty:
        return pd.Series(dtype=float)
    col=_find_col(pool.columns,aliases)
    if col is None:
        return pd.Series(dtype=float)
    return pd.to_numeric(pool[col].astype(str).str.replace("%","",regex=False).str.replace(",","",regex=False),errors="coerce").dropna()


def fetch_market_review(days: int = 180) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """市场数据层。

    规则：
    1) 上涨/下跌/平盘由覆盖完整的逐股快照按涨跌幅正负直接计数；
    2) 涨停/跌停直接读取东方财富公开涨跌停池，不用涨跌幅阈值推算；
    3) 乐咕市场活跃度仅用于独立交叉核验，不再覆盖正式口径；
    4) 正式源失败时允许降级，但必须在 QA 和数据源字段中明确标记。
    """
    idx_rows=[]; qa=[]
    for name,symbol in INDEX_SYMBOLS.items():
        d,src,errs=fetch_index_history(symbol,days)
        if not d.empty:
            d.insert(0,"指数名称",name); d.insert(0,"指数代码",symbol); idx_rows.append(d)
        qa.append({"对象":name,"代码":symbol,"状态":"成功" if not d.empty else "失败","数据源":src,"交易日数":len(d),"错误":" | ".join(errs[-4:])})
    indices=pd.concat(idx_rows,ignore_index=True) if idx_rows else pd.DataFrame()

    # A. 乐咕公开市场统计：只做交叉核验
    activity={}
    activity_src=""
    try:
        activity, activity_src = _public_market_activity_legu()
        qa.append({"对象":"市场统计交叉核验（非正式口径）","代码":"","状态":"成功","数据源":activity_src,"交易日数":1,"错误":""})
    except Exception as e:
        qa.append({"对象":"市场统计交叉核验（非正式口径）","代码":"","状态":"失败","数据源":"legulegu","交易日数":0,"错误":f"{type(e).__name__}:{e}"})

    # B. 东方财富公开池：涨停/跌停为正式计数；炸板、昨日涨停、强势股为第一阶段影子情绪层。
    captured_at=_as_cn_time()
    today=captured_at.strftime("%Y%m%d")
    limit_pools={}
    for label, fn in [
        ("公开涨停股池", lambda: ak.stock_zt_pool_em(date=today)),
        ("公开跌停股池", lambda: ak.stock_zt_pool_dtgc_em(date=today)),
        ("公开炸板股池", lambda: ak.stock_zt_pool_zbgc_em(date=today)),
        ("昨日涨停股池", lambda: ak.stock_zt_pool_previous_em(date=today)),
        ("公开强势股池", lambda: ak.stock_zt_pool_strong_em(date=today)),
    ]:
        try:
            p=fn()
            if p is None:
                raise RuntimeError("公开股池返回None")
            limit_pools[label]=p.copy()
            qa.append({"对象":label,"代码":"","状态":"成功","数据源":"eastmoney_public_pool","交易日数":len(p),"错误":""})
        except Exception as e:
            qa.append({"对象":label,"代码":"","状态":"失败","数据源":"eastmoney_public_pool","交易日数":0,"错误":f"{type(e).__name__}:{e}"})

    # C. 全市场快照：正式上涨/下跌/平盘口径，同时补充成交额和涨跌幅分布
    spot=pd.DataFrame(); spot_src=""; spot_candidates=[]
    for src,fn in [("eastmoney",lambda: ak.stock_zh_a_spot_em()),("sina",lambda: ak.stock_zh_a_spot())]:
        try:
            raw=fn(); candidate=_std_spot(raw)
            if candidate.empty: raise RuntimeError("空快照")
            valid_pct=int(pd.to_numeric(candidate.get("当日涨跌幅",pd.Series(dtype=float)),errors="coerce").notna().sum())
            if valid_pct==0: raise RuntimeError("快照缺少有效涨跌幅")
            spot_candidates.append((valid_pct,len(candidate),src,candidate))
            qa.append({"对象":"全市场逐股快照候选","代码":"","状态":"成功","数据源":src,"交易日数":len(candidate),"错误":f"有效涨跌幅={valid_pct}"})
        except Exception as e:
            qa.append({"对象":"全市场逐股快照候选","代码":"","状态":"失败","数据源":src,"交易日数":0,"错误":f"{type(e).__name__}:{e}"})
    if spot_candidates:
        _,_,spot_src,spot=max(spot_candidates,key=lambda x:(x[0],x[1]))
        qa.append({"对象":"全市场逐股快照正式源","代码":"","状态":"成功","数据源":spot_src,"交易日数":len(spot),"错误":"按有效涨跌幅覆盖数择优"})

    pct=pd.to_numeric(spot.get("当日涨跌幅",pd.Series(dtype=float)),errors="coerce") if not spot.empty else pd.Series(dtype=float)
    amt=pd.to_numeric(spot.get("截至当前成交额",pd.Series(dtype=float)),errors="coerce") if not spot.empty else pd.Series(dtype=float)

    spot_counts=_count_spot_breadth(spot)
    # 快照不可用时才降级到乐咕，并明确标记，避免把降级值伪装成正式快照口径。
    degraded_breadth=not bool(spot_counts)
    ups=spot_counts.get("上涨", _to_count(activity.get("上涨")))
    downs=spot_counts.get("下跌", _to_count(activity.get("下跌")))
    flats=spot_counts.get("平盘", _to_count(activity.get("平盘")))
    up_pool=limit_pools.get("公开涨停股池", pd.DataFrame())
    down_pool=limit_pools.get("公开跌停股池", pd.DataFrame())
    up_pool_ok="公开涨停股池" in limit_pools
    down_pool_ok="公开跌停股池" in limit_pools
    degraded_limits=not (up_pool_ok and down_pool_ok)
    up_limit=int(len(up_pool)) if up_pool_ok else _to_count(activity.get("涨停"))
    down_limit=int(len(down_pool)) if down_pool_ok else _to_count(activity.get("跌停"))
    broken_pool=limit_pools.get("公开炸板股池",pd.DataFrame())
    previous_pool=limit_pools.get("昨日涨停股池",pd.DataFrame())
    strong_pool=limit_pools.get("公开强势股池",pd.DataFrame())
    broken_count=int(len(broken_pool)) if "公开炸板股池" in limit_pools else np.nan
    touched_count=(up_limit+broken_count) if pd.notna(up_limit) and pd.notna(broken_count) else np.nan
    seal_success_rate=(up_limit/touched_count) if pd.notna(touched_count) and touched_count else np.nan
    streaks=_pool_numeric(up_pool,["连板数","连续涨停天数","几天几板"])
    highest_streak=int(streaks.max()) if not streaks.empty else np.nan
    previous_pct=_pool_numeric(previous_pool,["涨跌幅","当日涨跌幅","涨幅"])
    previous_premium_mean=float(previous_pct.mean()) if not previous_pct.empty else np.nan
    previous_positive_rate=float((previous_pct>0).mean()) if not previous_pct.empty else np.nan
    broken_pct=_pool_numeric(broken_pool,["涨跌幅","当日涨跌幅","涨幅"])
    broken_close_mean=float(broken_pct.mean()) if not broken_pct.empty else np.nan
    sentiment_shadow_ready=all(k in limit_pools for k in ["公开炸板股池","昨日涨停股池","公开强势股池"])
    suspended=_to_count(activity.get("停牌"))
    stat_date=str(activity.get("统计日期","")).strip()
    counts=[x for x in [ups,downs,flats] if pd.notna(x)]
    valid=spot_counts.get("股票数", int(sum(counts)) if len(counts)==3 else np.nan)
    breadth_source=(spot_src or "legulegu_fallback") + "+" + ("eastmoney_public_pool" if not degraded_limits else "legulegu_limit_fallback")

    if activity:
        diffs=[]
        for label,formal_key,legu_key in [("上涨",ups,"上涨"),("下跌",downs,"下跌"),("平盘",flats,"平盘"),("涨停",up_limit,"涨停"),("跌停",down_limit,"跌停")]:
            other=_to_count(activity.get(legu_key))
            if pd.notna(formal_key) and pd.notna(other) and int(formal_key)!=int(other):
                diffs.append(f"{label}:正式{int(formal_key)}/乐咕{int(other)}")
        qa.append({"对象":"正式口径与乐咕差异","代码":"","状态":"警告" if diffs else "一致","数据源":breadth_source,"交易日数":1,"错误":" | ".join(diffs)})

    row={
        "日期":captured_at.strftime("%Y-%m-%d"),
        "数据时间":captured_at.strftime("%Y-%m-%d %H:%M:%S%z"),
        "业务时区":"Asia/Shanghai",
        "数据源":breadth_source,
        "快照数据源":spot_src,
        "股票数":valid,
        "上涨家数":ups,"下跌家数":downs,"平盘家数":flats,"停牌家数":suspended,
        "上涨比例":(ups/valid if pd.notna(ups) and valid else np.nan),
        "下跌比例":(downs/valid if pd.notna(downs) and valid else np.nan),
        "净上涨家数":(ups-downs if pd.notna(ups) and pd.notna(downs) else np.nan),
        "涨停家数":up_limit,"跌停家数":down_limit,
        "炸板家数":broken_count,"触板家数":touched_count,"封板成功率":seal_success_rate,
        "最高连板数":highest_streak,"昨日涨停家数":int(len(previous_pool)) if "昨日涨停股池" in limit_pools else np.nan,
        "昨日涨停平均溢价":previous_premium_mean,"昨日涨停红盘率":previous_positive_rate,
        "炸板股平均收盘涨幅":broken_close_mean,"强势股池家数":int(len(strong_pool)) if "公开强势股池" in limit_pools else np.nan,
        "市场情绪影子层可用":sentiment_shadow_ready,
        "涨停股池代码":_pool_codes(up_pool),"跌停股池代码":_pool_codes(down_pool),
        "炸板股池代码":_pool_codes(broken_pool),"昨日涨停股池代码":_pool_codes(previous_pool),
        "强势股池代码":_pool_codes(strong_pool),
        "市场宽度是否降级":degraded_breadth,"涨跌停是否降级":degraded_limits,
        "真实涨停家数":_to_count(activity.get("真实涨停")),
        "真实跌停家数":_to_count(activity.get("真实跌停")),
        "ST涨停家数":_to_count(activity.get("st st*涨停", activity.get("ST ST*涨停"))),
        "ST跌停家数":_to_count(activity.get("st st*跌停", activity.get("ST ST*跌停"))),
        "乐咕统计时间":stat_date,
        "乐咕上涨家数":_to_count(activity.get("上涨")),"乐咕下跌家数":_to_count(activity.get("下跌")),
        "乐咕平盘家数":_to_count(activity.get("平盘")),"乐咕涨停家数":_to_count(activity.get("涨停")),"乐咕跌停家数":_to_count(activity.get("跌停")),
        "涨5%以上家数":int((pct>=5).sum()) if not pct.empty else np.nan,
        "跌5%以上家数":int((pct<=-5).sum()) if not pct.empty else np.nan,
        "全市场成交额":float(amt.sum()) if not amt.empty and amt.notna().any() else np.nan,
        "说明":"上涨/下跌/平盘由逐股快照计数；涨停/跌停读取东方财富公开池；炸板、封板率、昨日涨停溢价、连板高度为影子情绪层，仅记录和QA，暂不改变推荐。乐咕只做交叉核验。"
    }
    # 旧字段保留兼容，但不再叫“近似”：数值直接等于公开统计；若公开源失败则为空。
    row["涨停近似家数"]=row["涨停家数"]
    row["跌停近似家数"]=row["跌停家数"]
    breadth=pd.DataFrame([row])
    return indices,breadth,pd.DataFrame(qa)


SECTOR_PERIODS = {
    "now": "即时",
    "3d": "3日排行",
    "5d": "5日排行",
    "10d": "10日排行",
    "20d": "20日排行",
}


def _normalize_sector_flow(raw: pd.DataFrame, sector_type: str, period: str,
                           fetched_at: datetime, trade_date) -> tuple[pd.DataFrame, list[str]]:
    """标准化同花顺公开板块资金数据，并返回质量警告。"""
    if raw is None or raw.empty:
        return pd.DataFrame(), ["空数据"]
    x=raw.copy()
    warnings=[]
    name_col=_find_col(x.columns,["行业","板块名称","概念名称"])
    if name_col is None:
        return pd.DataFrame(), [f"缺少板块名称字段: {list(x.columns)}"]
    if name_col != "行业":
        x=x.rename(columns={name_col:"行业"})
    x["行业"]=x["行业"].astype(str).str.strip()
    x=x[x["行业"].ne("") & x["行业"].ne("nan")].copy()
    duplicate_names=x.loc[x["行业"].duplicated(keep=False),"行业"].drop_duplicates().tolist()
    if duplicate_names:
        warnings.append("重复板块已去重:"+"|".join(duplicate_names))
        x=x.drop_duplicates("行业",keep="first").copy()
    for c in ["行业指数","行业-涨跌幅","阶段涨跌幅","流入资金","流出资金","净额","公司家数","领涨股-涨跌幅","当前价"]:
        if c in x:
            x[c]=pd.to_numeric(x[c].astype(str).str.replace("%","",regex=False).str.replace("亿","",regex=False).str.replace("万","",regex=False),errors="coerce")
    if all(c in x for c in ["流入资金","流出资金","净额"]):
        bad=((x["流入资金"]-x["流出资金"]-x["净额"]).abs()>0.021).sum()
        if bad:
            warnings.append(f"资金净额算术不一致:{int(bad)}行")
    x.insert(0,"周期",period)
    x.insert(0,"板块类型",sector_type)
    x.insert(0,"抓取时间",fetched_at.strftime("%Y-%m-%d %H:%M:%S%z"))
    x.insert(0,"业务时区","Asia/Shanghai")
    x.insert(0,"交易日期",str(trade_date))
    x["资金单位"]="亿元"
    x["数据源"]="同花顺公开板块资金/AKShare"
    x["数据源URL"]="https://data.10jqka.com.cn/funds/gnzjl/" if sector_type=="概念" else "https://data.10jqka.com.cn/funds/hyzjl/"
    return x.reset_index(drop=True), warnings


def fetch_public_sector_flow(fetched_at: datetime | None = None) -> tuple[dict[str,pd.DataFrame], pd.DataFrame]:
    """获取同花顺概念/行业即时及多周期资金数据，作为增强层而非个股结构替代。"""
    fetched_at=_as_cn_time(fetched_at)
    trade_date=fetched_at.date()
    try:
        for _ in range(10):
            if is_trade_day(trade_date): break
            trade_date-=timedelta(days=1)
    except Exception:
        pass
    tables={}; qa=[]
    for sector_type,fn in [
        ("概念",ak.stock_fund_flow_concept),
        ("行业",ak.stock_fund_flow_industry),
    ]:
        for period,symbol in SECTOR_PERIODS.items():
            key=("concept" if sector_type=="概念" else "industry")+"_"+period
            try:
                raw=fn(symbol=symbol)
                x,warnings=_normalize_sector_flow(raw,sector_type,period,fetched_at,trade_date)
                if x.empty:
                    raise RuntimeError("标准化后为空; "+" | ".join(warnings))
                tables[key]=x
                qa.append({"测试":key,"状态":"警告" if warnings else "成功","行数":len(x),"重复数":max(0,len(raw)-len(x)),"数据源":"同花顺公开板块资金/AKShare","交易日期":str(trade_date),"错误":" | ".join(warnings)})
            except Exception as e:
                qa.append({"测试":key,"状态":"失败","行数":0,"重复数":0,"数据源":"同花顺公开板块资金/AKShare","交易日期":str(trade_date),"错误":f"{type(e).__name__}: {e}"})
    for prefix in ["concept","industry"]:
        now=tables.get(prefix+"_now")
        if now is None or now.empty:
            continue
        now_names=set(now["行业"])
        for period in ["3d","5d","10d","20d"]:
            other=tables.get(prefix+"_"+period)
            if other is None or other.empty:
                continue
            other_names=set(other["行业"])
            missing=sorted(other_names-now_names)
            extra=sorted(now_names-other_names)
            if missing or extra:
                qa.append({"测试":f"{prefix}_now_vs_{period}","状态":"警告","行数":len(now_names),"重复数":0,"数据源":"cross_period_qa","交易日期":str(trade_date),"错误":f"即时缺少:{'|'.join(missing)}; 即时独有:{'|'.join(extra)}"})
    return tables,pd.DataFrame(qa)
