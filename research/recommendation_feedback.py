from __future__ import annotations

import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path("v5_data/feedback")
REGISTRY = ROOT / "recommendations.csv"
LATEST_DAILY = ROOT / "latest_daily.json"
LATEST_WEEKLY = ROOT / "latest_weekly.json"

BASE_COLUMNS = [
    "推荐ID", "推荐日期", "推荐时间", "股票代码", "股票名称", "决策", "推荐时参考价",
    "推荐日收盘价", "结构止损位", "买入区间下沿", "买入区间上沿", "建议仓位占总资金%",
    "主导板块归因", "全部概念", "板块归因证据", "来源观察池日期", "OpenAI模型",
    "D+3日期", "D+3收盘价", "D+3涨跌幅%", "D+5日期", "D+5收盘价", "D+5涨跌幅%",
    "D+10日期", "D+10收盘价", "D+10涨跌幅%", "3日内触碰止损", "5日内触碰止损",
    "首次触碰止损日期", "最后更新日期", "数据状态",
]


def now_cn() -> datetime:
    return datetime.now(TZ)


def norm_code(value) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(x for x in raw if x.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _number(value):
    try:
        x = float(value)
        return None if pd.isna(x) else x
    except Exception:
        return None


def _load_attribution() -> dict:
    path = Path("v5_data/stock_sector_attribution/latest.csv")
    if not path.exists():
        return {}
    try:
        frame = pd.read_csv(path, dtype={"股票代码": str})
    except Exception:
        return {}
    out = {}
    for code, group in frame.groupby(frame["股票代码"].map(norm_code)):
        ranked = group.sort_values("归因得分", ascending=False)
        primary = ranked.iloc[0] if not ranked.empty else {}
        concepts = ranked.loc[ranked.get("板块类型", "") == "概念", "板块名称"].astype(str).tolist()
        out[code] = {
            "primary": str(primary.get("板块名称", "") or ""),
            "concepts": "|".join(dict.fromkeys(concepts)),
            "evidence": str(primary.get("归因证据", "") or ""),
        }
    return out


def _reference_price(snap45: pd.DataFrame, code: str):
    if snap45 is None or snap45.empty:
        return None
    x = snap45.copy()
    if "股票代码" not in x:
        return None
    x["股票代码"] = x["股票代码"].map(norm_code)
    rows = x[x["股票代码"] == code]
    if rows.empty:
        return None
    for col in ["当前价", "最新价", "现价", "价格", "收盘", "收盘价"]:
        if col in rows:
            value = _number(rows.iloc[-1][col])
            if value is not None:
                return value
    return None


def _recover_reference_from_tail(row: pd.Series):
    """Recover a missed 14:45 reference from the immutable tail workbook, never from close price."""
    trade_date = str(row.get("推荐日期", ""))[:10]
    code = norm_code(row.get("股票代码"))
    folder = Path("v5_data/tail") / trade_date
    for path in sorted(folder.glob("1445_confirmation_*.xlsx"), reverse=True):
        try:
            snap = pd.read_excel(path, sheet_name="14点45实时快照", dtype={"股票代码": str})
            value = _reference_price(snap, code)
            if value is not None:
                return value
        except Exception:
            continue
    return None


def register_tail_recommendations(final_decisions: pd.DataFrame, final_meta: dict,
                                  snap45: pd.DataFrame | None = None,
                                  obs_meta: dict | None = None) -> dict:
    """登记OpenAI最终TRADE标的。推荐日正式收盘价由收盘后更新任务回填。"""
    ROOT.mkdir(parents=True, exist_ok=True)
    selected = {norm_code(x) for x in final_meta.get("selected_codes", []) if norm_code(x)}
    trades = final_decisions.copy() if final_decisions is not None else pd.DataFrame()
    if not trades.empty:
        trades["股票代码"] = trades["股票代码"].map(norm_code)
        trades = trades[(trades["股票代码"].isin(selected)) & (trades["decision"].astype(str).str.upper() == "TRADE")]
    old = pd.read_csv(REGISTRY, dtype={"股票代码": str}) if REGISTRY.exists() else pd.DataFrame(columns=BASE_COLUMNS)
    attribution = _load_attribution()
    trade_date = str(final_meta.get("trade_date") or now_cn().date())
    rows = []
    for _, r in trades.iterrows():
        code = norm_code(r.get("股票代码"))
        attr = attribution.get(code, {})
        rows.append({
            "推荐ID": f"{trade_date}_{code}", "推荐日期": trade_date,
            "推荐时间": final_meta.get("generated_at_cn", now_cn().isoformat()),
            "股票代码": code, "股票名称": r.get("股票名称", ""), "决策": "TRADE",
            "推荐时参考价": _reference_price(snap45, code), "推荐日收盘价": None,
            "结构止损位": _number(r.get("结构止损参考")),
            "买入区间下沿": _number(r.get("买入区间下沿")),
            "买入区间上沿": _number(r.get("买入区间上沿")),
            "建议仓位占总资金%": _number(r.get("建议仓位占总资金%")),
            "主导板块归因": attr.get("primary", ""), "全部概念": attr.get("concepts", ""),
            "板块归因证据": attr.get("evidence", ""),
            "来源观察池日期": (obs_meta or {}).get("generated_trade_date", ""),
            "OpenAI模型": final_meta.get("model", ""), "数据状态": "等待推荐日正式收盘",
        })
    if rows:
        incoming = pd.DataFrame(rows)
        combined = incoming if old.empty else pd.concat([old, incoming], ignore_index=True, sort=False)
        combined = combined.drop_duplicates("推荐ID", keep="last")
    else:
        combined = old
    for col in BASE_COLUMNS:
        if col not in combined:
            combined[col] = None
    combined[BASE_COLUMNS].to_csv(REGISTRY, index=False, encoding="utf-8-sig")
    return {"registered": len(rows), "selected_codes": sorted(selected), "registry_count": len(combined)}


def fetch_bars(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak

    cache = Path("v5_data/cache/history") / f"{code}.csv"
    cached = pd.DataFrame()
    if cache.exists():
        try:
            cached = pd.read_csv(cache)
            cached["日期"] = pd.to_datetime(cached["日期"], errors="coerce").dt.date
        except Exception:
            cached = pd.DataFrame()
    start = pd.to_datetime(start_date).date()
    end = pd.to_datetime(end_date).date()
    if not cached.empty and cached["日期"].min() <= start and cached["日期"].max() >= end:
        return cached
    try:
        raw = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=start.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"), adjust="",
        )
    except Exception:
        if not cached.empty:
            return cached
        raise
    if raw is None or raw.empty:
        return cached
    raw["日期"] = pd.to_datetime(raw["日期"], errors="coerce").dt.date
    return raw.sort_values("日期").drop_duplicates("日期")


def evaluate_record(row: pd.Series, bars: pd.DataFrame, asof=None) -> dict:
    out = {}
    if bars is None or bars.empty:
        return {"数据状态": "行情缺失"}
    rec_date = pd.to_datetime(row["推荐日期"]).date()
    x = bars.copy()
    x["日期"] = pd.to_datetime(x["日期"], errors="coerce").dt.date
    x = x[x["日期"] >= rec_date].sort_values("日期").drop_duplicates("日期")
    if asof is not None:
        x = x[x["日期"] <= asof]
    if x.empty or x.iloc[0]["日期"] != rec_date:
        return {"数据状态": "等待推荐日正式收盘"}
    anchor = _number(x.iloc[0].get("收盘"))
    if not anchor:
        return {"数据状态": "推荐日收盘缺失"}
    out["推荐日收盘价"] = anchor
    future = x.iloc[1:].reset_index(drop=True)
    for horizon in (3, 5, 10):
        if len(future) >= horizon:
            target = future.iloc[horizon - 1]
            close = _number(target.get("收盘"))
            out[f"D+{horizon}日期"] = str(target["日期"])
            out[f"D+{horizon}收盘价"] = close
            out[f"D+{horizon}涨跌幅%"] = round((close / anchor - 1) * 100, 4) if close else None
    stop = _number(row.get("结构止损位"))
    first_touch = ""
    if stop:
        for horizon in (3, 5):
            window = future.head(horizon)
            mature = len(window) >= horizon
            lows = pd.to_numeric(window.get("最低"), errors="coerce") if "最低" in window else pd.Series(dtype=float)
            touched = bool((lows <= stop).any()) if not lows.empty else False
            out[f"{horizon}日内触碰止损"] = touched if mature else None
            if touched and not first_touch:
                first_touch = str(window.loc[lows <= stop, "日期"].iloc[0])
    out["首次触碰止损日期"] = first_touch
    out["最后更新日期"] = str(asof or now_cn().date())
    out["数据状态"] = "D+10完成" if out.get("D+10日期") else "跟踪中"
    return out


def _metric(records: pd.DataFrame, horizon: int) -> dict:
    col = f"D+{horizon}涨跌幅%"
    s = pd.to_numeric(records.get(col), errors="coerce").dropna()
    wins = s[s > 0]
    losses = s[s < 0]
    avg_win = float(wins.mean()) if len(wins) else None
    avg_loss = float(losses.mean()) if len(losses) else None
    ratio = avg_win / abs(avg_loss) if avg_win is not None and avg_loss not in (None, 0) else None
    return {
        "样本数": int(len(s)), "胜率%": round(float((s > 0).mean() * 100), 2) if len(s) else None,
        "平均收益%": round(float(s.mean()), 4) if len(s) else None,
        "中位收益%": round(float(s.median()), 4) if len(s) else None,
        "平均盈利%": round(avg_win, 4) if avg_win is not None else None,
        "平均亏损%": round(avg_loss, 4) if avg_loss is not None else None,
        "盈亏比": round(ratio, 4) if ratio is not None else None,
    }


def build_daily_summary(records: pd.DataFrame, asof) -> dict:
    due = {}
    for horizon in (3, 5, 10):
        col = f"D+{horizon}日期"
        if col in records:
            due[f"D+{horizon}"] = records[records[col].astype(str) == str(asof)][
                ["推荐日期", "股票代码", "股票名称", col, f"D+{horizon}涨跌幅%"]
            ].fillna("").to_dict("records")
        else:
            due[f"D+{horizon}"] = []
    return {
        "asof": str(asof), "total_recommendations": int(len(records)),
        "tracking": int((records.get("数据状态", "") == "跟踪中").sum()),
        "completed_d10": int(records.get("D+10日期", pd.Series(dtype=object)).notna().sum()),
        "due_cohorts": due,
        "method": "推荐日正式收盘价为锚；D+N按后续第N个交易日收盘；止损触碰按推荐后交易日最低价<=结构止损位。",
    }


def build_weekly_summary(records: pd.DataFrame, asof) -> dict:
    summary = {
        "asof": str(asof), "generated_at_cn": now_cn().isoformat(),
        "D+3": _metric(records, 3), "D+5": _metric(records, 5), "D+10": _metric(records, 10),
    }
    for horizon in (3, 5):
        col = f"{horizon}日内触碰止损"
        s = records.get(col, pd.Series(dtype=object)).dropna()
        if len(s):
            normalized = s.map(lambda x: str(x).lower() in {"true", "1", "yes"})
            summary[f"{horizon}日止损触发率%"] = round(float(normalized.mean() * 100), 2)
            summary[f"{horizon}日止损样本数"] = int(len(s))
        else:
            summary[f"{horizon}日止损触发率%"] = None
            summary[f"{horizon}日止损样本数"] = 0
    summary["使用限制"] = "仅评估历史推荐，不构成收益承诺；小样本不得直接升级为正式策略规则。"
    return summary


def pushplus(title: str, content: str):
    token = (os.getenv("PUSHPLUS_TOKEN") or "").strip()
    if not token:
        print("PushPlus skipped: token missing")
        return
    body = json.dumps({"token": token, "title": title, "content": content, "template": "html", "channel": "wechat"}, ensure_ascii=False).encode()
    req = urllib.request.Request("https://www.pushplus.plus/send", data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        print("PushPlus feedback receipt:", resp.read().decode(errors="replace")[:300])


def update_all(asof=None, notify=True) -> dict:
    asof = asof or now_cn().date()
    if not REGISTRY.exists():
        ROOT.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(columns=BASE_COLUMNS).to_csv(REGISTRY, index=False, encoding="utf-8-sig")
    # Tracking columns intentionally mix numbers, booleans, dates and blanks.
    # Object dtype prevents pandas from rejecting a later date/blank assignment into an all-NaN column.
    records = pd.read_csv(REGISTRY, dtype={"股票代码": str}).astype(object)
    for idx, row in records.iterrows():
        code = norm_code(row.get("股票代码"))
        start = str(row.get("推荐日期"))
        if _number(row.get("推荐时参考价")) is None:
            recovered = _recover_reference_from_tail(row)
            if recovered is not None:
                records.at[idx, "推荐时参考价"] = recovered
        try:
            bars = fetch_bars(code, start, str(asof))
            updates = evaluate_record(row, bars, asof)
            for key, value in updates.items():
                records.at[idx, key] = value
        except Exception as exc:
            if _number(row.get("推荐日收盘价")) is not None:
                records.at[idx, "数据状态"] = f"跟踪中（本次行情更新失败:{type(exc).__name__}）"
            else:
                records.at[idx, "数据状态"] = f"更新失败:{type(exc).__name__}:{exc}"
        time.sleep(0.12)
    for col in BASE_COLUMNS:
        if col not in records:
            records[col] = None
    records[BASE_COLUMNS].to_csv(REGISTRY, index=False, encoding="utf-8-sig")
    daily = build_daily_summary(records, asof)
    weekly = build_weekly_summary(records, asof)
    ROOT.mkdir(parents=True, exist_ok=True)
    LATEST_DAILY.write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    daily_dir = ROOT / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    (daily_dir / f"{asof}.json").write_text(json.dumps(daily, ensure_ascii=False, indent=2), encoding="utf-8")
    LATEST_WEEKLY.write_text(json.dumps(weekly, ensure_ascii=False, indent=2), encoding="utf-8")
    if pd.Timestamp(asof).weekday() == 4:
        weekly_dir = ROOT / "weekly"
        weekly_dir.mkdir(parents=True, exist_ok=True)
        iso = pd.Timestamp(asof).isocalendar()
        (weekly_dir / f"{iso.year}-W{iso.week:02d}.json").write_text(json.dumps(weekly, ensure_ascii=False, indent=2), encoding="utf-8")
    if notify:
        rows = [f"<b>推荐跟踪：</b>累计{len(records)}只"]
        for h in (3, 5, 10):
            m = weekly[f"D+{h}"]
            rows.append(f"<b>D+{h}：</b>样本{m['样本数']}｜胜率{m['胜率%']}%｜均值{m['平均收益%']}%｜盈亏比{m['盈亏比']}")
            for item in daily["due_cohorts"][f"D+{h}"]:
                rows.append(f"{item['股票代码']} {item['股票名称']}：{item[f'D+{h}涨跌幅%']}%")
        rows.append(f"<b>止损触发：</b>3日{weekly['3日止损触发率%']}%｜5日{weekly['5日止损触发率%']}%")
        pushplus("A股二次启动｜推荐跟踪反馈", "<br>".join(rows))
    return {"daily": daily, "weekly": weekly}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["update"])
    parser.add_argument("--asof", default="")
    parser.add_argument("--no-notify", action="store_true")
    args = parser.parse_args()
    asof = pd.to_datetime(args.asof).date() if args.asof else now_cn().date()
    result = update_all(asof, not args.no_notify)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
