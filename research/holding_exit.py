from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pandas as pd

from research.private_trade_ledger import build_positions, normalize_transactions


EXIT_COLUMNS = [
    "账户", "股票代码", "股票名称", "持仓数量", "可卖数量", "平均成本", "当前价",
    "最高收盘价", "最高浮盈%", "距高点回撤%", "结构止损参考", "结构破位确认",
    "回撤止盈已激活", "卖出建议", "建议卖出数量", "规则理由",
]

AFTER_CLOSE_COLUMNS = [
    "账户", "股票代码", "股票名称", "持仓数量", "平均成本", "数据日期", "最新收盘价",
    "最高收盘价", "最高浮盈%", "距高点回撤%", "原结构止损位", "当前结构止损位",
    "止损是否上调", "止盈激活价", "回撤止盈触发价", "盘后建议", "规则理由",
]


def active_position_cycles(transactions: pd.DataFrame, trade_date: date) -> pd.DataFrame:
    """Build active lots without persisting decrypted account data."""
    tx = normalize_transactions(transactions).sort_values(
        ["交易日期", "交易时间", "录入时间", "交易ID"], kind="stable"
    )
    positions = build_positions(tx)
    positions = positions[positions["持仓数量"] > 0].copy()
    if positions.empty:
        return positions.assign(持仓起始日期=pd.Series(dtype=str), 可卖数量=pd.Series(dtype=int))

    cycle_starts: dict[tuple[str, str], str] = {}
    sellable: dict[tuple[str, str], int] = {}
    balances: dict[tuple[str, str], int] = {}
    for _, row in tx.iterrows():
        key = (str(row["账户"]), str(row["股票代码"]))
        qty = int(row["成交数量"])
        before = balances.get(key, 0)
        if row["操作"] == "买入":
            if before == 0:
                cycle_starts[key] = str(row["交易日期"])
            balances[key] = before + qty
            if str(row["交易日期"]) < str(trade_date):
                sellable[key] = sellable.get(key, 0) + qty
        else:
            balances[key] = before - qty
            sellable[key] = max(0, sellable.get(key, 0) - qty)

    positions["持仓起始日期"] = [
        cycle_starts.get((str(r["账户"]), str(r["股票代码"])), "") for _, r in positions.iterrows()
    ]
    positions["可卖数量"] = [
        min(int(r["持仓数量"]), sellable.get((str(r["账户"]), str(r["股票代码"])), 0))
        for _, r in positions.iterrows()
    ]
    return positions


def saved_structure_stops(path: str | Path) -> dict[str, float]:
    source = Path(path)
    if not source.exists():
        return {}
    frame = pd.read_csv(source, dtype={"股票代码": str})
    if frame.empty or "结构止损位" not in frame:
        return {}
    frame["股票代码"] = frame["股票代码"].astype(str).str.zfill(6)
    frame["结构止损位"] = pd.to_numeric(frame["结构止损位"], errors="coerce")
    frame = frame.dropna(subset=["结构止损位"]).sort_values("推荐日期")
    return {str(r["股票代码"]): float(r["结构止损位"]) for _, r in frame.iterrows()}


def _partial_quantity(sellable: int) -> int:
    if sellable <= 0:
        return 0
    if sellable < 200:
        return sellable
    return max(100, int(math.floor((sellable * 0.5) / 100.0) * 100))


def evaluate_holding_exits(
    positions: pd.DataFrame,
    snapshot: pd.DataFrame,
    minute: pd.DataFrame,
    history_dir: str | Path,
    stops: dict[str, float],
) -> pd.DataFrame:
    """Deterministic layered exit: confirmed structure break first, trailing profit second."""
    if positions is None or positions.empty:
        return pd.DataFrame(columns=EXIT_COLUMNS)
    snap = snapshot.copy() if snapshot is not None else pd.DataFrame()
    if not snap.empty:
        snap["股票代码"] = snap["股票代码"].astype(str).str.zfill(6)
    mins = minute.copy() if minute is not None else pd.DataFrame()
    if not mins.empty:
        mins["股票代码"] = mins["股票代码"].astype(str).str.zfill(6)
    rows = []
    for _, pos in positions.iterrows():
        code = str(pos["股票代码"]).zfill(6)
        current_rows = snap[snap["股票代码"] == code] if not snap.empty else pd.DataFrame()
        current = pd.to_numeric(current_rows.get("当前价", pd.Series(dtype=float)), errors="coerce").dropna()
        current_price = float(current.iloc[-1]) if len(current) else float("nan")
        stock_minutes = mins[mins["股票代码"] == code].copy() if not mins.empty else pd.DataFrame()
        if not stock_minutes.empty and "时间" in stock_minutes:
            stock_minutes = stock_minutes.sort_values("时间")
        minute_closes = pd.to_numeric(stock_minutes.get("收盘价", pd.Series(dtype=float)), errors="coerce").dropna()

        history_path = Path(history_dir) / f"{code}.csv"
        hist = pd.read_csv(history_path) if history_path.exists() else pd.DataFrame()
        closes = pd.to_numeric(hist.get("收盘价", pd.Series(dtype=float)), errors="coerce")
        if not hist.empty and "日期" in hist:
            entered = pd.to_datetime(pos.get("持仓起始日期"), errors="coerce")
            dates = pd.to_datetime(hist["日期"], errors="coerce")
            closes_since_entry = closes[dates >= entered] if not pd.isna(entered) else closes
        else:
            closes_since_entry = closes
        high_candidates = [x for x in closes_since_entry.dropna().tolist() + minute_closes.tolist() if x > 0]
        if math.isfinite(current_price) and current_price > 0:
            high_candidates.append(current_price)
        high_close = max(high_candidates) if high_candidates else float("nan")
        cost = float(pos["平均成本"])
        max_gain = (high_close / cost - 1) if cost > 0 and math.isfinite(high_close) else float("nan")
        drawdown = (high_close - current_price) / high_close if high_close > 0 and math.isfinite(current_price) else float("nan")

        saved_stop = float(stops.get(code, 0) or 0)
        ma10 = float(closes.dropna().tail(10).mean()) if len(closes.dropna()) >= 5 else 0.0
        # Before a trade has earned 5%, preserve the original entry invalidation level.
        # Once it has, trail structural support upward to the completed-day MA10.
        structural_stop = max(saved_stop, ma10 if math.isfinite(max_gain) and max_gain >= 0.05 else 0.0)
        last_two = minute_closes.tail(2)
        data_complete = bool(
            math.isfinite(current_price) and current_price > 0 and structural_stop > 0 and len(last_two) == 2
        )
        structure_broken = bool(
            structural_stop > 0 and len(last_two) == 2 and
            (last_two < structural_stop).all() and math.isfinite(current_price) and current_price < structural_stop
        )
        trailing_active = bool(math.isfinite(max_gain) and max_gain >= 0.08)
        pullback_hit = bool(trailing_active and math.isfinite(drawdown) and drawdown >= 0.05)
        sellable = int(pos.get("可卖数量", 0) or 0)
        if not data_complete:
            action, qty, reason = "DATA_ERROR", 0, "实时价、两根5分钟收盘或结构止损缺失，禁止把缺失结果解释为继续持有"
        elif sellable <= 0:
            action, qty, reason = "HOLD_T1", 0, "当日新增持仓不可卖；仅提示结构风险"
        elif structure_broken:
            action, qty, reason = "EXIT_ALL", sellable, "连续两根5分钟收盘低于结构止损，结构破位优先全部退出"
        elif pullback_hit:
            action, qty, reason = "REDUCE_50", _partial_quantity(sellable), "最高浮盈达到8%后，从最高收盘价回撤达到5%，先减仓一半锁利"
        else:
            action, qty, reason = "HOLD", 0, "未确认结构破位，且盈利回撤止盈条件未同时满足"
        rows.append({
            "账户": pos["账户"], "股票代码": code, "股票名称": pos["股票名称"],
            "持仓数量": int(pos["持仓数量"]), "可卖数量": sellable, "平均成本": round(cost, 4),
            "当前价": round(current_price, 4) if math.isfinite(current_price) else None,
            "最高收盘价": round(high_close, 4) if math.isfinite(high_close) else None,
            "最高浮盈%": round(max_gain * 100, 2) if math.isfinite(max_gain) else None,
            "距高点回撤%": round(drawdown * 100, 2) if math.isfinite(drawdown) else None,
            "结构止损参考": round(structural_stop, 4) if structural_stop > 0 else None,
            "结构破位确认": structure_broken, "回撤止盈已激活": trailing_active,
            "卖出建议": action, "建议卖出数量": qty, "规则理由": reason,
        })
    return pd.DataFrame(rows, columns=EXIT_COLUMNS)


def evaluate_after_close_holdings(
    positions: pd.DataFrame,
    history_dir: str | Path,
    stops: dict[str, float],
) -> pd.DataFrame:
    """Review every actual open holding from completed daily bars without lowering its stop."""
    if positions is None or positions.empty:
        return pd.DataFrame(columns=AFTER_CLOSE_COLUMNS)
    rows = []
    for _, pos in positions.iterrows():
        code = str(pos["股票代码"]).zfill(6)
        history_path = Path(history_dir) / f"{code}.csv"
        hist = pd.read_csv(history_path) if history_path.exists() else pd.DataFrame()
        if not hist.empty and "日期" in hist and "收盘价" in hist:
            hist = hist.copy()
            hist["日期"] = pd.to_datetime(hist["日期"], errors="coerce")
            hist["收盘价"] = pd.to_numeric(hist["收盘价"], errors="coerce")
            entered = pd.to_datetime(pos.get("持仓起始日期"), errors="coerce")
            hist = hist.dropna(subset=["日期", "收盘价"]).sort_values("日期")
            if not pd.isna(entered):
                hist = hist[hist["日期"] >= entered]
        cost = float(pos.get("平均成本", 0) or 0)
        saved_stop = float(stops.get(code, 0) or 0)
        if hist.empty or cost <= 0 or saved_stop <= 0:
            rows.append({
                "账户": pos.get("账户", ""), "股票代码": code, "股票名称": pos.get("股票名称", ""),
                "持仓数量": int(pos.get("持仓数量", 0) or 0), "平均成本": round(cost, 4) if cost > 0 else None,
                "原结构止损位": round(saved_stop, 4) if saved_stop > 0 else None,
                "盘后建议": "DATA_ERROR", "规则理由": "完整日线、持仓成本或原结构止损缺失，禁止默认继续持有",
            })
            continue
        closes = hist["收盘价"]
        rolling_ma10 = closes.rolling(10, min_periods=5).mean()
        running_high = closes.cummax()
        gain_reached = running_high / cost - 1 >= 0.05
        raised_candidates = rolling_ma10[gain_reached].dropna()
        current_stop = max(saved_stop, float(raised_candidates.max()) if len(raised_candidates) else 0.0)
        latest = float(closes.iloc[-1])
        high_close = float(running_high.iloc[-1])
        max_gain = high_close / cost - 1
        drawdown = (high_close - latest) / high_close if high_close > 0 else float("nan")
        trailing_active = max_gain >= 0.08
        take_profit_activation = cost * 1.08
        trailing_trigger = high_close * 0.95 if trailing_active else None
        if latest < current_stop:
            action = "EXIT_NEXT_SESSION"
            reason = "收盘价已低于当前结构止损，若仍有持仓，下一交易时段优先退出并由14:45规则继续确认"
        elif trailing_trigger is not None and latest <= trailing_trigger:
            action = "REDUCE_NEXT_SESSION"
            reason = "最高浮盈已达8%且收盘回撤达到5%，下一交易时段优先减仓并继续执行盘中规则"
        else:
            action = "HOLD"
            reason = "收盘结构仍有效；继续持有并使用更新后的结构止损和回撤止盈参考"
        rows.append({
            "账户": pos.get("账户", ""), "股票代码": code, "股票名称": pos.get("股票名称", ""),
            "持仓数量": int(pos.get("持仓数量", 0) or 0), "平均成本": round(cost, 4),
            "数据日期": hist.iloc[-1]["日期"].date().isoformat(), "最新收盘价": round(latest, 4),
            "最高收盘价": round(high_close, 4), "最高浮盈%": round(max_gain * 100, 2),
            "距高点回撤%": round(drawdown * 100, 2), "原结构止损位": round(saved_stop, 4),
            "当前结构止损位": round(current_stop, 4), "止损是否上调": current_stop > saved_stop + 1e-9,
            "止盈激活价": round(take_profit_activation, 4),
            "回撤止盈触发价": round(trailing_trigger, 4) if trailing_trigger is not None else None,
            "盘后建议": action, "规则理由": reason,
        })
    return pd.DataFrame(rows, columns=AFTER_CLOSE_COLUMNS)
