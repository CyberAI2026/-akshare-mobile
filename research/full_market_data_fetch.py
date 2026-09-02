from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import time
from pathlib import Path

import akshare as ak
import pandas as pd


EXPECTED_COLUMNS = [
    "日期", "股票代码", "开盘", "收盘", "最高", "最低",
    "成交量", "成交额", "振幅", "涨跌幅", "涨跌额", "换手率",
]


def fetch_symbol(code: str, start: str, end: str, output_dir: Path, retries: int) -> dict:
    target = output_dir / f"{code}.csv.gz"
    errors: list[str] = []
    for attempt in range(1, retries + 1):
        try:
            frame = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start,
                end_date=end,
                adjust="qfq",
            )
            if frame is None or frame.empty:
                raise RuntimeError("empty history")
            missing = [column for column in EXPECTED_COLUMNS if column not in frame.columns]
            if missing:
                raise RuntimeError(f"missing columns: {missing}")
            frame = frame[EXPECTED_COLUMNS].copy()
            frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
            frame = frame.dropna(subset=["日期"]).sort_values("日期").drop_duplicates("日期")
            frame.to_csv(target, index=False, encoding="utf-8-sig", compression="gzip")
            return {
                "股票代码": code,
                "状态": "ok",
                "行数": len(frame),
                "首日": frame["日期"].min().date().isoformat(),
                "末日": frame["日期"].max().date().isoformat(),
                "错误": " | ".join(errors),
            }
        except Exception as exc:  # noqa: BLE001 - provider errors must be audited
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < retries:
                time.sleep((1.4 ** attempt) + random.uniform(0.2, 0.8))
    return {
        "股票代码": code,
        "状态": "failed",
        "行数": 0,
        "首日": "",
        "末日": "",
        "错误": " | ".join(errors),
    }


def fetch_name_tables(output_dir: Path) -> pd.DataFrame:
    master = ak.stock_info_a_code_name().copy()
    master.columns = [str(column).strip() for column in master.columns]
    code_col = next(column for column in master.columns if "code" in column.lower() or "代码" in column)
    name_col = next(column for column in master.columns if "name" in column.lower() or "名称" in column)
    master = master[[code_col, name_col]].rename(columns={code_col: "股票代码", name_col: "股票名称"})
    master["股票代码"] = master["股票代码"].astype(str).str.extract(r"(\d{6})", expand=False)
    master["股票名称"] = master["股票名称"].astype(str).str.strip()
    master = master.dropna().drop_duplicates("股票代码").sort_values("股票代码").reset_index(drop=True)
    master.to_csv(output_dir / "a_share_code_name.csv", index=False, encoding="utf-8-sig")

    try:
        changes = ak.stock_info_change_name(symbol="all")
        if changes is not None and not changes.empty:
            changes.to_csv(output_dir / "a_share_name_changes.csv", index=False, encoding="utf-8-sig")
    except Exception as exc:  # noqa: BLE001
        (output_dir / "name_changes_error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
    return master


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public full-market A-share daily data")
    parser.add_argument("--start", default="20240101")
    parser.add_argument("--end", required=True)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--output", default="research_public_market_data")
    args = parser.parse_args()

    root = Path(args.output)
    daily_dir = root / "daily_qfq"
    daily_dir.mkdir(parents=True, exist_ok=True)
    master = fetch_name_tables(root)
    codes = master["股票代码"].tolist()

    rows: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(fetch_symbol, code, args.start, args.end, daily_dir, args.retries): code
            for code in codes
        }
        for number, future in enumerate(concurrent.futures.as_completed(futures), 1):
            row = future.result()
            rows.append(row)
            if number % 100 == 0 or number == len(codes):
                ok = sum(item["状态"] == "ok" for item in rows)
                print(f"progress={number}/{len(codes)} ok={ok} failed={number-ok}", flush=True)

    audit = pd.DataFrame(rows).sort_values("股票代码").reset_index(drop=True)
    audit.to_csv(root / "fetch_audit.csv", index=False, encoding="utf-8-sig")
    summary = {
        "start": args.start,
        "end": args.end,
        "listed_symbols": len(codes),
        "success_symbols": int((audit["状态"] == "ok").sum()),
        "failed_symbols": int((audit["状态"] != "ok").sum()),
        "rows": int(audit["行数"].sum()),
        "adjust": "qfq",
        "scope": "public full-market data; no private trade list",
    }
    (root / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if summary["success_symbols"] < max(1000, int(summary["listed_symbols"] * 0.80)):
        raise SystemExit("FAIL: full-market history coverage below 80%")


if __name__ == "__main__":
    main()
