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
        structure_broken = bool(
            structural_stop > 0 and len(last_two) == 2 and
            (last_two < structural_stop).all() and math.isfinite(current_price) and current_price < structural_stop
        )
        trailing_active = bool(math.isfinite(max_gain) and max_gain >= 0.08)
        pullback_hit = bool(trailing_active and math.isfinite(drawdown) and drawdown >= 0.05)
        sellable = int(pos.get("可卖数量", 0) or 0)
        if sellable <= 0:
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
