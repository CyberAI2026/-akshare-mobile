from __future__ import annotations

import hashlib
import io
import math
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken


CN_TZ = ZoneInfo("Asia/Shanghai")
TRANSACTION_COLUMNS = [
    "交易ID",
    "交易日期",
    "交易时间",
    "账户",
    "操作",
    "股票代码",
    "股票名称",
    "成交价格",
    "成交数量",
    "成交金额",
    "手续费",
    "备注",
    "录入时间",
]


def empty_transactions() -> pd.DataFrame:
    return pd.DataFrame(columns=TRANSACTION_COLUMNS)


def generate_encryption_key() -> str:
    """生成一次性配置用密钥；调用方负责安全保存，不写日志或文件。"""
    return Fernet.generate_key().decode("utf-8")


def normalize_code(value) -> str:
    raw = str(value or "").strip()
    if raw.endswith(".0"):
        raw = raw[:-2]
    digits = "".join(ch for ch in raw if ch.isdigit())
    code = digits[-6:].zfill(6) if digits else ""
    if len(code) != 6:
        raise ValueError(f"股票代码无效：{value}")
    return code


def normalize_side(value) -> str:
    side = str(value or "").strip().upper()
    mapping = {"买入": "买入", "BUY": "买入", "B": "买入", "卖出": "卖出", "SELL": "卖出", "S": "卖出"}
    if side not in mapping:
        raise ValueError(f"操作必须是买入或卖出：{value}")
    return mapping[side]


def _date_text(value) -> str:
    if value is None or pd.isna(value):
        raise ValueError("交易日期不能为空")
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            raise ValueError("交易日期不能为空")
        return stamp.date().isoformat()
    except Exception as exc:
        raise ValueError(f"交易日期无效：{value}") from exc


def _time_text(value) -> str:
    raw = str(value or "").strip()
    if not raw or raw.lower() == "nan":
        return "15:00:00"
    try:
        return pd.Timestamp(f"2000-01-01 {raw}").strftime("%H:%M:%S")
    except Exception as exc:
        raise ValueError(f"交易时间无效：{value}") from exc


def _transaction_id(row: dict) -> str:
    identity = "|".join(
        str(row.get(name, ""))
        for name in ["交易日期", "交易时间", "账户", "操作", "股票代码", "成交价格", "成交数量", "手续费", "备注"]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _text(value, default: str = "") -> str:
    if value is None or pd.isna(value):
        return default
    cleaned = str(value).strip()
    return default if cleaned.lower() in {"", "nan", "none", "nat"} else cleaned


def normalize_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return empty_transactions()
    aliases = {
        "日期": "交易日期", "时间": "交易时间", "账号": "账户", "账户名称": "账户",
        "方向": "操作", "买卖": "操作", "代码": "股票代码", "证券代码": "股票代码",
        "名称": "股票名称", "证券名称": "股票名称", "价格": "成交价格", "成交价": "成交价格",
        "数量": "成交数量", "股数": "成交数量", "金额": "成交金额", "费用": "手续费",
    }
    source = frame.rename(columns={c: aliases.get(str(c).strip(), str(c).strip()) for c in frame.columns}).copy()
    required = ["交易日期", "操作", "股票代码", "成交价格", "成交数量"]
    missing = [c for c in required if c not in source.columns]
    if missing:
        raise ValueError("缺少必填列：" + "、".join(missing))

    entered_at = datetime.now(CN_TZ).isoformat(timespec="seconds")
    rows = []
    for _, raw in source.iterrows():
        price = float(raw.get("成交价格"))
        qty_float = float(raw.get("成交数量"))
        if not math.isfinite(price) or price <= 0:
            raise ValueError("成交价格必须大于0")
        if not math.isfinite(qty_float) or qty_float <= 0 or not qty_float.is_integer():
            raise ValueError("成交数量必须是正整数")
        qty = int(qty_float)
        fee = float(raw.get("手续费", 0) or 0)
        if pd.isna(fee):
            fee = 0.0
        if not math.isfinite(fee) or fee < 0:
            raise ValueError("手续费不能为负数")
        amount = round(price * qty, 2)
        supplied = raw.get("成交金额", None)
        if supplied is not None and str(supplied).strip() not in {"", "nan", "None"}:
            if abs(float(supplied) - amount) > 0.02:
                raise ValueError(f"成交金额与价格×数量不一致：{supplied} != {amount}")
        row = {
            "交易日期": _date_text(raw.get("交易日期")),
            "交易时间": _time_text(raw.get("交易时间", "")),
            "账户": _text(raw.get("账户", "默认账户"), "默认账户"),
            "操作": normalize_side(raw.get("操作")),
            "股票代码": normalize_code(raw.get("股票代码")),
            "股票名称": _text(raw.get("股票名称", "")),
            "成交价格": round(price, 4),
            "成交数量": qty,
            "成交金额": amount,
            "手续费": round(fee, 2),
            "备注": _text(raw.get("备注", "")),
            "录入时间": _text(raw.get("录入时间", ""), entered_at),
        }
        existing_id = _text(raw.get("交易ID", ""))
        row["交易ID"] = existing_id or _transaction_id(row)
        rows.append(row)
    return pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)


def _sort_transactions(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    return frame.sort_values(["交易日期", "交易时间", "录入时间", "交易ID"], kind="stable").reset_index(drop=True)


def append_transactions(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    old = normalize_transactions(existing)
    new = normalize_transactions(incoming)
    parts = [part for part in (old, new) if not part.empty]
    combined = pd.concat(parts, ignore_index=True).drop_duplicates("交易ID", keep="first") if parts else empty_transactions()
    combined = _sort_transactions(combined)
    balances: dict[tuple[str, str], int] = {}
    for _, row in combined.iterrows():
        key = (str(row["账户"]), str(row["股票代码"]))
        current = balances.get(key, 0)
        qty = int(row["成交数量"])
        if row["操作"] == "买入":
            balances[key] = current + qty
        else:
            if qty > current:
                raise ValueError(f"{key[0]} 的 {key[1]} 卖出{qty}股，超过此前持仓{current}股")
            balances[key] = current - qty
    return combined


def build_positions(transactions: pd.DataFrame) -> pd.DataFrame:
    tx = _sort_transactions(normalize_transactions(transactions))
    columns = ["账户", "股票代码", "股票名称", "持仓数量", "平均成本", "累计买入金额", "累计卖出金额", "已实现盈亏", "最近交易日期", "状态"]
    if tx.empty:
        return pd.DataFrame(columns=columns)
    states: dict[tuple[str, str], dict] = {}
    for _, row in tx.iterrows():
        key = (row["账户"], row["股票代码"])
        state = states.setdefault(key, {"qty": 0, "avg": 0.0, "buy": 0.0, "sell": 0.0, "realized": 0.0, "name": "", "date": ""})
        qty = int(row["成交数量"])
        amount = float(row["成交金额"])
        fee = float(row["手续费"])
        if row["股票名称"]:
            state["name"] = row["股票名称"]
        if row["操作"] == "买入":
            new_qty = state["qty"] + qty
            state["avg"] = ((state["qty"] * state["avg"]) + amount + fee) / new_qty
            state["qty"] = new_qty
            state["buy"] += amount
        else:
            if qty > state["qty"]:
                raise ValueError(f"{key[0]} 的 {key[1]} 卖出数量超过持仓")
            state["realized"] += amount - fee - state["avg"] * qty
            state["qty"] -= qty
            state["sell"] += amount
            if state["qty"] == 0:
                state["avg"] = 0.0
        state["date"] = row["交易日期"]
    rows = []
    for (account, code), state in states.items():
        rows.append({
            "账户": account, "股票代码": code, "股票名称": state["name"],
            "持仓数量": state["qty"], "平均成本": round(state["avg"], 4),
            "累计买入金额": round(state["buy"], 2), "累计卖出金额": round(state["sell"], 2),
            "已实现盈亏": round(state["realized"], 2), "最近交易日期": state["date"],
            "状态": "持仓中" if state["qty"] > 0 else "已清仓",
        })
    return pd.DataFrame(rows, columns=columns).sort_values(["状态", "账户", "股票代码"], ascending=[False, True, True]).reset_index(drop=True)


def active_position_codes(transactions: pd.DataFrame) -> set[str]:
    positions = build_positions(transactions)
    if positions.empty:
        return set()
    return set(positions.loc[positions["持仓数量"] > 0, "股票代码"].astype(str))


def _fernet(key: str | bytes) -> Fernet:
    raw = key.encode("utf-8") if isinstance(key, str) else key
    try:
        return Fernet(raw)
    except Exception as exc:
        raise ValueError("TRADING_DATA_KEY格式无效，必须是Fernet密钥") from exc


def encrypt_transactions(transactions: pd.DataFrame, key: str | bytes) -> bytes:
    normalized = normalize_transactions(transactions)
    payload = normalized.to_csv(index=False).encode("utf-8-sig")
    return _fernet(key).encrypt(payload)


def decrypt_transactions(blob: bytes, key: str | bytes) -> pd.DataFrame:
    if not blob:
        return empty_transactions()
    try:
        payload = _fernet(key).decrypt(blob)
    except InvalidToken as exc:
        raise ValueError("交易数据密钥错误或加密文件已损坏") from exc
    try:
        frame = pd.read_csv(io.BytesIO(payload), dtype={"股票代码": str, "交易ID": str})
    except Exception as exc:
        raise ValueError("交易台账解密成功但内容无法读取") from exc
    return normalize_transactions(frame)


def load_encrypted_transactions(path: str | Path, key: str | bytes) -> pd.DataFrame:
    ledger = Path(path)
    return decrypt_transactions(ledger.read_bytes(), key) if ledger.exists() else empty_transactions()
