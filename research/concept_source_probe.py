from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import akshare as ak
import pandas as pd
import requests


OUT = Path("concept_source_probe")


def record(name: str, fn) -> dict:
    try:
        value = fn()
        if isinstance(value, pd.DataFrame):
            return {
                "source": name,
                "status": "success" if not value.empty else "empty",
                "rows": len(value),
                "columns": [str(x) for x in value.columns],
                "sample": value.head(3).astype(str).to_dict("records"),
            }
        return {"source": name, "status": "success", "type": type(value).__name__}
    except Exception as exc:
        return {"source": name, "status": "failure", "error": f"{type(exc).__name__}: {str(exc)[:500]}"}


def ths_first_board_table() -> pd.DataFrame:
    boards = ak.stock_board_concept_name_ths()
    if boards is None or boards.empty:
        return pd.DataFrame()
    code_col = "code" if "code" in boards else boards.columns[-1]
    code = str(boards.iloc[0][code_col])
    url = f"https://q.10jqka.com.cn/gn/detail/code/{code}/"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    response.raise_for_status()
    tables = pd.read_html(StringIO(response.text))
    candidates = [x for x in tables if any("代码" in str(c) for c in x.columns)]
    return candidates[0] if candidates else pd.DataFrame()


def main() -> None:
    available = sorted(name for name in dir(ak) if "concept" in name.lower() or "board_cons" in name.lower())
    results = [
        record("sina_concept_list", lambda: ak.stock_sector_spot(indicator="概念")),
        record("eastmoney_concept_list", ak.stock_board_concept_name_em),
        record("ths_concept_list", ak.stock_board_concept_name_ths),
        record("ths_first_board_html_table", ths_first_board_table),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"available_functions": available, "results": results}
    (OUT / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
