from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("Asia/Shanghai")
VERSION = "stock-sector-attribution-v0.1.0"


def norm_code(value) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(x for x in raw if x.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _board_col(frame: pd.DataFrame):
    for col in ["板块名称", "行业", "名称", "概念名称", "行业名称"]:
        if col in frame:
            return col
    return None


def load_sector_strength(path: Path) -> dict[str, dict]:
    """把十张板块事实表转为板块强度证据；排名只在同表内归一化。"""
    if not path.exists():
        return {}
    out: dict[str, dict] = {}
    sheets = pd.read_excel(path, sheet_name=None)
    for sheet, frame in sheets.items():
        if frame is None or frame.empty or "质量" in sheet:
            continue
        board_col = _board_col(frame)
        if not board_col:
            continue
        score_col = None
        direction = False
        for candidate in ["净额", "行业-涨跌幅", "阶段涨跌幅", "涨跌幅"]:
            if candidate in frame:
                score_col = candidate
                direction = candidate == "净额"
                break
        if not score_col:
            continue
        x = frame[[board_col, score_col]].copy()
        x[score_col] = pd.to_numeric(x[score_col], errors="coerce")
        x = x.dropna().sort_values(score_col, ascending=False)
        n = max(1, len(x))
        for rank, (_, row) in enumerate(x.iterrows(), 1):
            board = str(row[board_col]).strip()
            if not board:
                continue
            normalized = max(0.0, 1.0 - (rank - 1) / n)
            item = out.setdefault(board, {"事实强度分": 0.0, "事实证据": []})
            item["事实强度分"] += normalized
            item["事实证据"].append(f"{sheet}第{rank}/{n}（{score_col}={row[score_col]}）")
    if out:
        maximum = max(x["事实强度分"] for x in out.values()) or 1.0
        for item in out.values():
            item["事实强度分"] = round(item["事实强度分"] / maximum * 70, 4)
            item["事实证据"] = item["事实证据"][:4]
    return out


def load_opinion_mentions(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return json.dumps(data.get("daily_consensus", {}), ensure_ascii=False)
    except Exception:
        return ""


def build_attribution(membership: pd.DataFrame, master: pd.DataFrame,
                      strength: dict[str, dict], opinion_text: str,
                      snapshot_date: str) -> pd.DataFrame:
    x = membership.copy()
    x["股票代码"] = x["股票代码"].map(norm_code)
    master = master.copy()
    master["股票代码"] = master["股票代码"].map(norm_code)
    wanted = [c for c in ["股票代码", "最近提交日期", "首次进入日期"] if c in master]
    x = x.merge(master[wanted].drop_duplicates("股票代码"), on="股票代码", how="left")
    rows = []
    for _, row in x.iterrows():
        board = str(row.get("板块名称", "")).strip()
        fact = strength.get(board, {})
        fact_score = float(fact.get("事实强度分", 0.0))
        opinion_hit = bool(board and board in opinion_text)
        type_prior = 8.0 if str(row.get("板块类型")) == "概念" else 5.0
        score = fact_score + (20.0 if opinion_hit else 0.0) + type_prior
        evidence = list(fact.get("事实证据", []))
        if opinion_hit:
            evidence.append("当日正文观点共识提及该板块")
        if not evidence:
            evidence.append("仅确认板块成分关系，暂缺同日板块异动证据")
        strength_date = str(row.get("最近提交日期", "") or "")[:10]
        point_in_time = strength_date == snapshot_date
        rows.append({
            "快照日期": snapshot_date, "强势观察日期": strength_date,
            "股票代码": row.get("股票代码"), "股票名称": row.get("股票名称", ""),
            "板块类型": row.get("板块类型", ""), "板块名称": board,
            "归因得分": round(score, 4), "事实强度分": fact_score,
            "观点提及": opinion_hit, "归因证据": "；".join(evidence),
            "时点一致": point_in_time,
            "归因口径": "板块成分×同日板块行情/资金排名×正文观点共识；属于可审计关联归因，不声称确定因果",
            "时点限制": "" if point_in_time else "现有成分快照与强势观察日不同，不得倒推为历史确定归因",
            "版本": VERSION,
        })
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    result = result.sort_values(["股票代码", "归因得分", "板块类型"], ascending=[True, False, True])
    result["主导板块候选"] = False
    first = result.groupby("股票代码", sort=False).head(1).index
    result.loc[first, "主导板块候选"] = True
    return result.reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--membership", default="v5_data/context/sector_membership/latest.csv.gz")
    parser.add_argument("--master", default="v5_data/master/master_registry.csv")
    parser.add_argument("--sector-facts", default="v5_data/latest/sector_fund_flow.xlsx")
    parser.add_argument("--opinion", default="v5_data/opinion/latest.json")
    parser.add_argument("--output-root", default="v5_data/stock_sector_attribution")
    args = parser.parse_args()

    membership_path = Path(args.membership)
    if not membership_path.exists():
        working = membership_path.with_name("working.csv.gz")
        if working.exists():
            membership_path = working
        else:
            raise FileNotFoundError(f"板块成分映射不存在: {membership_path}")
    membership = pd.read_csv(membership_path, dtype={"股票代码": str})
    master = pd.read_csv(args.master, dtype={"股票代码": str})
    snapshot_date = str(membership.get("快照日期", pd.Series([datetime.now(TZ).date()])).iloc[0])[:10]
    strength = load_sector_strength(Path(args.sector_facts))
    opinion_text = load_opinion_mentions(Path(args.opinion))
    result = build_attribution(membership, master, strength, opinion_text, snapshot_date)

    root = Path(args.output_root)
    root.mkdir(parents=True, exist_ok=True)
    result.to_csv(root / "latest.csv", index=False, encoding="utf-8-sig")
    history = root / "history"
    history.mkdir(parents=True, exist_ok=True)
    result.to_csv(history / f"{snapshot_date}.csv.gz", index=False, encoding="utf-8-sig", compression="gzip")
    summary = {
        "status": "completed", "snapshot_date": snapshot_date,
        "rows": len(result), "stocks": int(result["股票代码"].nunique()) if not result.empty else 0,
        "multi_concept_stocks": int((result[result["板块类型"] == "概念"].groupby("股票代码").size() > 1).sum()) if not result.empty else 0,
        "fact_board_count": len(strength), "version": VERSION,
        "causality_warning": "主导板块是可审计关联归因，不是已证明的因果关系；历史回看仅使用当日保存的成分快照。",
    }
    (root / "latest_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
