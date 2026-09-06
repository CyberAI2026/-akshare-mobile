from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def name_key(value) -> str:
    return str(value or "").strip().replace(" ", "").replace("-U", "").replace("A", "Ａ")


def load_trades(path: str | Path) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name="股票清仓主表", header=3)
    frame = frame[frame["账户"].notna()].copy()
    for col in ["建仓日期", "清仓日期"]:
        frame[col] = pd.to_datetime(frame[col], errors="coerce")
    for col in ["总盈亏", "盈亏比", "同期大盘", "跑赢大盘", "买入均价", "卖出均价", "持股天数", "交易费用"]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame.reset_index(drop=True)


def attach_codes(trades: pd.DataFrame, master_path: str | Path) -> pd.DataFrame:
    master = pd.read_csv(master_path, dtype={"股票代码": str})
    mapping = {name_key(name): str(code).zfill(6) for code, name in master[["股票代码", "股票名称"]].itertuples(index=False, name=None)}
    out = trades.copy()
    out["股票代码"] = out["证券名称"].map(lambda name: mapping.get(name_key(name)))
    out["名称匹配状态"] = np.where(out["股票代码"].notna(), "当前名称/规范别名匹配", "未匹配")
    # 原表“星和科技”没有对应A股简称，价格也不匹配星宸科技或同星科技；保持未核验。
    return out


def load_histories(root: str | Path) -> dict[str, pd.DataFrame]:
    histories = {}
    for path in Path(root).glob("**/[0-9][0-9][0-9][0-9][0-9][0-9].csv"):
        code = path.stem
        try:
            frame = pd.read_csv(path, dtype={"股票代码": str})
            frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
            frame = frame.dropna(subset=["日期"]).sort_values("日期").drop_duplicates("日期")
            if not frame.empty and code not in histories:
                histories[code] = frame.reset_index(drop=True)
        except Exception:
            continue
    return histories


def _return(values: pd.Series, start: int, end: int):
    if start < 0 or end < 0 or start >= len(values) or end >= len(values):
        return np.nan
    a, b = float(values.iloc[start]), float(values.iloc[end])
    return (b / a - 1) * 100 if a else np.nan


def enrich_one(row: pd.Series, history: pd.DataFrame | None) -> dict:
    base = row.to_dict()
    if history is None or history.empty or pd.isna(row["建仓日期"]) or pd.isna(row["清仓日期"]):
        return {**base, "外部行情状态": "未核验"}
    dates = history["日期"]
    entry_candidates = history.index[dates >= row["建仓日期"]]
    exit_candidates = history.index[dates <= row["清仓日期"]]
    if len(entry_candidates) == 0 or len(exit_candidates) == 0:
        return {**base, "外部行情状态": "日期范围不足"}
    entry = int(entry_candidates[0])
    exit_idx = int(exit_candidates[-1])
    if exit_idx < entry:
        return {**base, "外部行情状态": "日期顺序异常"}
    close = pd.to_numeric(history["收盘"], errors="coerce")
    high = pd.to_numeric(history["最高"], errors="coerce")
    low = pd.to_numeric(history["最低"], errors="coerce")
    volume = pd.to_numeric(history["成交量"], errors="coerce")
    buy = float(row["买入均价"])
    hold = history.iloc[entry:exit_idx + 1]
    hold_high = pd.to_numeric(hold["最高"], errors="coerce").max()
    hold_low = pd.to_numeric(hold["最低"], errors="coerce").min()
    pre20_high = high.iloc[max(0, entry - 20):entry].max()
    vol5 = volume.iloc[max(0, entry - 5):entry].mean()
    vol20 = volume.iloc[max(0, entry - 20):entry].mean()
    return {
        **base,
        "外部行情状态": "成功",
        "建仓前5日涨跌幅%": _return(close, entry - 6, entry - 1),
        "建仓前20日涨跌幅%": _return(close, entry - 21, entry - 1),
        "建仓前量比5/20": vol5 / vol20 if vol20 and not pd.isna(vol20) else np.nan,
        "建仓价距前20日高点%": (buy / pre20_high - 1) * 100 if pre20_high and not pd.isna(pre20_high) else np.nan,
        "持仓期最大浮盈估算%": (hold_high / buy - 1) * 100 if buy else np.nan,
        "持仓期最大浮亏估算%": (hold_low / buy - 1) * 100 if buy else np.nan,
        "清仓后5日涨跌幅%": _return(close, exit_idx, exit_idx + 5),
        "清仓后10日涨跌幅%": _return(close, exit_idx, exit_idx + 10),
    }


def holding_bucket(days) -> str:
    if pd.isna(days): return "未知"
    if days <= 2: return "1-2天"
    if days <= 5: return "3-5天"
    if days <= 10: return "6-10天"
    if days <= 20: return "11-20天"
    return "20天以上"


def grouped_summary(frame: pd.DataFrame, group: str) -> list[dict]:
    rows = []
    for key, data in frame.groupby(group, dropna=False):
        gains = data.loc[data["总盈亏"] > 0, "总盈亏"].sum()
        losses = abs(data.loc[data["总盈亏"] < 0, "总盈亏"].sum())
        rows.append({
            group: str(key), "交易数": len(data), "胜率": round(float((data["总盈亏"] > 0).mean()), 4),
            "总盈亏": round(float(data["总盈亏"].sum()), 2), "平均盈亏比": round(float(data["盈亏比"].mean()), 4),
            "盈亏因子": round(float(gains / losses), 4) if losses else None,
        })
    return rows


def outcome_diagnostics(frame: pd.DataFrame) -> dict:
    verified = frame[frame["外部行情状态"] == "成功"].copy()
    winners = verified[verified["总盈亏"] > 0]
    losers = verified[verified["总盈亏"] <= 0]

    def medians(data: pd.DataFrame) -> dict:
        columns = [
            "建仓前5日涨跌幅%", "建仓前20日涨跌幅%", "建仓前量比5/20",
            "建仓价距前20日高点%", "持仓期最大浮盈估算%", "持仓期最大浮亏估算%",
            "清仓后5日涨跌幅%", "清仓后10日涨跌幅%",
        ]
        return {
            column: round(float(data[column].median()), 4)
            for column in columns if column in data and data[column].notna().any()
        }

    loss_mfe = losers[losers["持仓期最大浮盈估算%"] >= 5]
    return {
        "verified_trade_count": len(verified),
        "winner_medians": medians(winners),
        "loser_medians": medians(losers),
        "losers_with_estimated_mfe_at_least_5pct": int(len(loss_mfe)),
        "their_total_final_pnl": round(float(loss_mfe["总盈亏"].sum()), 2),
        "losers_with_estimated_mae_at_most_minus_5pct": int(
            (losers["持仓期最大浮亏估算%"] <= -5).sum()
        ),
        "post_exit_5d_rebound_at_least_5pct": int((verified["清仓后5日涨跌幅%"] >= 5).sum()),
        "post_exit_5d_fall_at_most_minus_5pct": int((verified["清仓后5日涨跌幅%"] <= -5).sum()),
    }


def run(trades_path: str, master_path: str, history_root: str, output: str) -> None:
    trades = attach_codes(load_trades(trades_path), master_path)
    histories = load_histories(history_root)
    enriched = pd.DataFrame([enrich_one(row, histories.get(str(row.get("股票代码", "")))) for _, row in trades.iterrows()])
    enriched["持股周期"] = enriched["持股天数"].map(holding_bucket)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    enriched.to_csv(out / "trade_enriched.csv", index=False, encoding="utf-8-sig")
    gains = enriched.loc[enriched["总盈亏"] > 0, "总盈亏"].sum()
    losses = abs(enriched.loc[enriched["总盈亏"] < 0, "总盈亏"].sum())
    summary = {
        "trade_count": len(enriched),
        "external_history_success": int((enriched["外部行情状态"] == "成功").sum()),
        "external_history_unverified": int((enriched["外部行情状态"] != "成功").sum()),
        "total_pnl": round(float(enriched["总盈亏"].sum()), 2),
        "win_rate": round(float((enriched["总盈亏"] > 0).mean()), 4),
        "profit_factor": round(float(gains / losses), 4) if losses else None,
        "by_account": grouped_summary(enriched, "账户"),
        "by_holding_period": grouped_summary(enriched, "持股周期"),
        "outcome_diagnostics": outcome_diagnostics(enriched),
        "limitations": [
            "买入均价与建仓日期来自清仓汇总，不含逐笔加减仓路径，MFE/MAE为估算。",
            "当前阶段只使用公开日线和原表同期大盘字段；缺少可审计的历史板块、事件和资金面快照。",
            "未匹配名称和北交所行情不得参与外部行情结论。",
            "分组结果只描述这183笔交易，不构成持仓天数或阈值的因果结论，也不自动改变正式规则。",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", required=True)
    parser.add_argument("--master", required=True)
    parser.add_argument("--history-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    run(args.trades, args.master, args.history_root, args.output)


if __name__ == "__main__":
    main()
