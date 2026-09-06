from __future__ import annotations

import argparse
import json
import signal
import time
from contextlib import contextmanager
from pathlib import Path

import akshare as ak
import pandas as pd


START_DATE = "20250801"
END_DATE = "20260904"
SINA_START_DATE = "2025-08-01"
SINA_END_DATE = "2026-09-04"
BATCH_COUNT = 9


@contextmanager
def alarm_timeout(seconds: int):
    def handler(_signum, _frame):
        raise TimeoutError(f"upstream call exceeded {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def load_universe(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"股票代码": str})
    required = {"股票代码", "股票名称"}
    if not required.issubset(frame.columns):
        raise ValueError("研究清单必须包含股票代码和股票名称")
    out = frame[["股票代码", "股票名称"]].copy()
    out["股票代码"] = out["股票代码"].astype(str).str.extract(r"(\d{1,6})", expand=False).str.zfill(6)
    if out["股票代码"].isna().any():
        raise ValueError("研究清单含无效股票代码")
    return out.drop_duplicates("股票代码").sort_values("股票代码").reset_index(drop=True)


def batch_slice(frame: pd.DataFrame, index: int, count: int = BATCH_COUNT) -> pd.DataFrame:
    if index < 0 or index >= count:
        raise ValueError(f"batch index must be 0..{count - 1}")
    return frame.iloc[index::count].reset_index(drop=True)


def normalize_history(frame: pd.DataFrame, code: str, name: str) -> pd.DataFrame:
    aliases = {
        "日期": "日期", "date": "日期", "开盘": "开盘", "open": "开盘",
        "收盘": "收盘", "close": "收盘", "最高": "最高", "high": "最高",
        "最低": "最低", "low": "最低", "成交量": "成交量", "volume": "成交量",
        "成交额": "成交额", "amount": "成交额", "振幅": "振幅", "涨跌幅": "涨跌幅",
        "涨跌额": "涨跌额", "换手率": "换手率",
    }
    out = frame.rename(columns={c: aliases.get(str(c), str(c)) for c in frame.columns}).copy()
    required = ["日期", "开盘", "收盘", "最高", "最低", "成交量"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError("行情缺少字段: " + ",".join(missing))
    keep = [c for c in [*required, "成交额", "振幅", "涨跌幅", "涨跌额", "换手率"] if c in out.columns]
    out = out[keep]
    out.insert(0, "股票名称", name)
    out.insert(0, "股票代码", code)
    out["日期"] = pd.to_datetime(out["日期"], errors="coerce").dt.strftime("%Y-%m-%d")
    return out.dropna(subset=["日期"]).drop_duplicates("日期").sort_values("日期").reset_index(drop=True)


def sina_symbol(code: str) -> str | None:
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("0", "3")):
        return "sz" + code
    return None


def fetch_one(code: str, name: str) -> tuple[pd.DataFrame, str]:
    errors = []
    sources = [("eastmoney", lambda: ak.stock_zh_a_hist(
        symbol=code, period="daily", start_date=START_DATE,
        end_date=END_DATE, adjust="qfq",
    ))]
    symbol = sina_symbol(code)
    if symbol:
        sources.append(("sina", lambda: ak.stock_zh_a_daily(
            symbol=symbol, start_date=SINA_START_DATE,
            end_date=SINA_END_DATE, adjust="qfq",
        )))
    for source, fetch in sources:
        try:
            with alarm_timeout(15):
                raw = fetch()
            out = normalize_history(raw, code, name)
            if out.empty:
                raise RuntimeError("empty history")
            return out, f"success source={source}"
        except Exception as exc:
            errors.append(f"{source} {type(exc).__name__}: {exc}")
            time.sleep(1)
    return pd.DataFrame(), " | ".join(errors)


def run(universe_path: str | Path, batch_index: int, output: str | Path) -> None:
    universe = load_universe(universe_path)
    selected = batch_slice(universe, batch_index)
    out_dir = Path(output) / f"batch_{batch_index}"
    out_dir.mkdir(parents=True, exist_ok=True)
    qa = []
    for pos, row in selected.iterrows():
        code, name = row["股票代码"], row["股票名称"]
        history, message = fetch_one(code, name)
        status = "成功" if not history.empty else "失败"
        if not history.empty:
            history.to_csv(out_dir / f"{code}.csv", index=False, encoding="utf-8-sig")
        qa.append({"股票代码": code, "股票名称": name, "状态": status, "行数": len(history), "说明": message})
        print(f"batch={batch_index} progress={pos + 1}/{len(selected)} code={code} status={status}", flush=True)
    qa_frame = pd.DataFrame(qa)
    qa_frame.to_csv(out_dir / "qa.csv", index=False, encoding="utf-8-sig")
    summary = {
        "batch_index": batch_index, "batch_count": BATCH_COUNT, "requested": len(selected),
        "success": int((qa_frame["状态"] == "成功").sum()) if not qa_frame.empty else 0,
        "failed": int((qa_frame["状态"] != "成功").sum()) if not qa_frame.empty else 0,
        "start_date": START_DATE, "end_date": END_DATE,
        "privacy": "仅股票代码、名称和公开行情；不含账户或成交信息",
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--batch-index", required=True, type=int)
    parser.add_argument("--output", default="historical_market_artifact")
    args = parser.parse_args()
    run(args.universe, args.batch_index, args.output)


if __name__ == "__main__":
    main()
