from __future__ import annotations

import gzip
import re
from datetime import datetime

import pandas as pd

from v5_core import CN_TZ, _find_col, _norm_code, _read_delimited_stock_file, _read_excel_best_sheet


CODE_ALIASES = ["股票代码", "证券代码", "代码", "stockcode", "code", "symbol"]


def _read_full_upload(file_name: str, data: bytes) -> pd.DataFrame:
    """使用现有可靠解析器读取表格，但保留同花顺全部原始字段。"""
    if not data:
        raise ValueError("上传文件为空。")
    lower = (file_name or "").lower()
    is_xlsx_zip = data[:4] == b"PK\x03\x04"
    is_ole_xls = data[:8] == bytes.fromhex("D0CF11E0A1B11AE1")
    try:
        if is_xlsx_zip or lower.endswith(".xlsx"):
            return _read_excel_best_sheet(data, engine="openpyxl")
        if is_ole_xls:
            return _read_excel_best_sheet(data, engine="xlrd")
        if lower.endswith(".xls"):
            try:
                return _read_excel_best_sheet(data, engine="xlrd")
            except Exception:
                return _read_delimited_stock_file(data)
        return _read_delimited_stock_file(data)
    except Exception as exc:
        raise ValueError(
            f"无法识别同花顺补充数据文件 {file_name!r}：{exc}"
        ) from exc


def master_code_text(master: pd.DataFrame) -> bytes:
    """生成可直接粘贴到同花顺的六位代码文本。"""
    if master is None or master.empty or "股票代码" not in master.columns:
        raise ValueError("云端主池为空或缺少股票代码列。")
    codes = master["股票代码"].map(_norm_code)
    invalid = ~codes.str.fullmatch(r"\d{6}", na=False)
    if invalid.any():
        raise ValueError(f"云端主池包含 {int(invalid.sum())} 条无效代码，请先修复主池。")
    codes = codes.drop_duplicates()
    return ("\n".join(codes.tolist()) + "\n").encode("utf-8")


def _clean_columns(frame: pd.DataFrame) -> pd.DataFrame:
    cleaned = frame.copy()
    cleaned.columns = [str(column).strip() for column in cleaned.columns]
    blank_columns = [
        column for column in cleaned.columns
        if not column or re.fullmatch(r"Unnamed:\s*\d+", column, flags=re.IGNORECASE)
    ]
    if blank_columns:
        cleaned = cleaned.drop(columns=blank_columns)
    return cleaned


def prepare_snapshot(
    file_name: str,
    data: bytes,
    master: pd.DataFrame,
    uploaded_at: datetime | None = None,
) -> tuple[pd.DataFrame, dict]:
    """保留同花顺全部字段，但只将代码唯一匹配到当前主池。"""
    raw = _clean_columns(_read_full_upload(file_name, data))
    code_column = _find_col(raw.columns, CODE_ALIASES)
    if code_column is None:
        raise ValueError("同花顺补充数据必须包含股票代码列。")

    snapshot = raw.copy()
    normalized_codes = snapshot[code_column].map(_norm_code)
    invalid = ~normalized_codes.str.fullmatch(r"\d{6}", na=False)
    if invalid.any():
        raise ValueError(f"文件中有 {int(invalid.sum())} 行无法识别六位股票代码。")
    snapshot[code_column] = normalized_codes
    if code_column != "股票代码":
        if "股票代码" in snapshot.columns:
            snapshot = snapshot.drop(columns=["股票代码"])
        snapshot = snapshot.rename(columns={code_column: "股票代码"})

    duplicate_count = int(snapshot["股票代码"].duplicated(keep=False).sum())
    if duplicate_count:
        raise ValueError(f"文件中有 {duplicate_count} 行股票代码重复，请在同花顺中去重后重新导出。")

    master_codes = master["股票代码"].map(_norm_code).drop_duplicates()
    master_set = set(master_codes)
    uploaded_set = set(snapshot["股票代码"])
    matched = snapshot["股票代码"].isin(master_set)
    unmatched_codes = snapshot.loc[~matched, "股票代码"].tolist()
    missing_codes = [code for code in master_codes if code not in uploaded_set]

    now = uploaded_at or datetime.now(CN_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=CN_TZ)
    else:
        now = now.astimezone(CN_TZ)
    snapshot.insert(0, "快照日期", now.strftime("%Y-%m-%d"))
    snapshot.insert(1, "上传时间", now.isoformat(timespec="seconds"))
    snapshot.insert(2, "主池匹配", matched.map({True: "是", False: "否"}))

    report = {
        "uploaded_rows": len(snapshot),
        "matched_rows": int(matched.sum()),
        "unmatched_rows": len(unmatched_codes),
        "missing_master_rows": len(missing_codes),
        "master_rows": len(master_codes),
        "field_count": len(snapshot.columns) - 3,
        "unmatched_codes": unmatched_codes,
        "missing_codes": missing_codes,
        "snapshot_date": now.strftime("%Y-%m-%d"),
        "uploaded_at": now.isoformat(timespec="seconds"),
    }
    return snapshot, report


def snapshot_gzip(snapshot: pd.DataFrame) -> bytes:
    csv_bytes = snapshot.to_csv(index=False).encode("utf-8-sig")
    return gzip.compress(csv_bytes, compresslevel=9, mtime=0)


def snapshot_path(snapshot_date: str) -> str:
    compact = snapshot_date.replace("-", "")
    return f"v5_data/ths_snapshots/{snapshot_date}/ths_master_snapshot_{compact}.csv.gz"
