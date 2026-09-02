from __future__ import annotations

import concurrent.futures
import json
import random
import time
from pathlib import Path

import akshare as ak
import pandas as pd


INDEX_SYMBOLS = {
    "上证指数": "sh000001",
    "深证成指": "sz399001",
    "创业板指": "sz399006",
    "科创50": "sh000688",
    "北证50": "bj899050",
}


def retry(function, label: str, attempts: int = 4):
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            value = function()
            if value is None or (hasattr(value, "empty") and value.empty):
                raise RuntimeError("empty result")
            return value, errors
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{label}/{attempt}:{type(exc).__name__}:{exc}")
            if attempt < attempts:
                time.sleep((1.5 ** attempt) + random.uniform(0.2, 0.9))
    return pd.DataFrame(), errors


def fetch_index(name: str, symbol: str) -> tuple[pd.DataFrame, dict]:
    frame, errors = retry(
        lambda: ak.index_zh_a_hist(
            symbol=symbol,
            period="daily",
            start_date="20240101",
            end_date="20260902",
        ),
        f"index:{symbol}",
    )
    if frame.empty:
        return frame, {"对象": name, "代码": symbol, "状态": "failed", "错误": " | ".join(errors)}
    frame.insert(0, "指数代码", symbol)
    frame.insert(0, "指数名称", name)
    return frame, {"对象": name, "代码": symbol, "状态": "ok", "行数": len(frame), "错误": " | ".join(errors)}


def normalize_board_list(frame: pd.DataFrame) -> list[str]:
    for column in frame.columns:
        cleaned = str(column).strip()
        if cleaned in {"板块名称", "概念名称", "行业名称", "名称"}:
            return frame[column].dropna().astype(str).str.strip().drop_duplicates().tolist()
    raise RuntimeError(f"board name column not found: {list(frame.columns)}")


def normalize_constituents(frame: pd.DataFrame, board_type: str, board_name: str) -> pd.DataFrame:
    code_col = next(c for c in frame.columns if "代码" in str(c) or "code" in str(c).lower())
    name_col = next(c for c in frame.columns if "名称" in str(c) or "name" in str(c).lower())
    out = frame[[code_col, name_col]].copy()
    out.columns = ["股票代码", "股票名称"]
    out["股票代码"] = out["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    out["股票名称"] = out["股票名称"].astype(str).str.strip()
    out.insert(0, "板块名称", board_name)
    out.insert(0, "板块类型", board_type)
    return out.dropna(subset=["股票代码"]).drop_duplicates().reset_index(drop=True)


def main() -> None:
    root = Path("research_market_sector_context")
    root.mkdir(exist_ok=True)
    qa: list[dict] = []

    index_frames = []
    for name, symbol in INDEX_SYMBOLS.items():
        frame, audit = fetch_index(name, symbol)
        qa.append(audit)
        if not frame.empty:
            index_frames.append(frame)
    if index_frames:
        pd.concat(index_frames, ignore_index=True).to_csv(
            root / "market_indices.csv", index=False, encoding="utf-8-sig"
        )

    board_specs = [
        ("行业", ak.stock_board_industry_name_em, ak.stock_board_industry_cons_em),
        ("概念", ak.stock_board_concept_name_em, ak.stock_board_concept_cons_em),
    ]
    membership_frames = []
    for board_type, list_function, constituent_function in board_specs:
        board_frame, errors = retry(list_function, f"{board_type}:list")
        if board_frame.empty:
            qa.append({"对象": f"{board_type}板块列表", "状态": "failed", "错误": " | ".join(errors)})
            continue
        board_names = normalize_board_list(board_frame)
        qa.append({"对象": f"{board_type}板块列表", "状态": "ok", "行数": len(board_names), "错误": " | ".join(errors)})
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = {
                executor.submit(retry, lambda n=name: constituent_function(symbol=n), f"{board_type}:{name}", 3): name
                for name in board_names
            }
            for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
                board_name = futures[future]
                frame, board_errors = future.result()
                if frame.empty:
                    qa.append({"对象": f"{board_type}:{board_name}", "状态": "failed", "错误": " | ".join(board_errors)})
                else:
                    membership_frames.append(normalize_constituents(frame, board_type, board_name))
                if number % 50 == 0 or number == len(board_names):
                    print(f"{board_type} progress={number}/{len(board_names)}", flush=True)
    if membership_frames:
        membership = pd.concat(membership_frames, ignore_index=True).drop_duplicates()
        membership.to_csv(root / "current_sector_membership.csv", index=False, encoding="utf-8-sig")

    pd.DataFrame(qa).to_csv(root / "context_fetch_audit.csv", index=False, encoding="utf-8-sig")
    summary = {
        "index_rows": sum(len(frame) for frame in index_frames),
        "membership_rows": sum(len(frame) for frame in membership_frames),
        "warning": "sector membership is current-map retrospective and is not point-in-time classification",
    }
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if not index_frames:
        raise SystemExit("FAIL: all index sources unavailable")


if __name__ == "__main__":
    main()
