from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from urllib.parse import urljoin

import akshare as ak
import pandas as pd
import requests
from bs4 import BeautifulSoup
from py_mini_racer import py_mini_racer
from akshare.stock_feature.stock_board_concept_ths import _get_file_content_ths


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


def ths_first_board_pagination() -> pd.DataFrame:
    boards = ak.stock_board_concept_name_ths()
    code = str(boards.iloc[0]["code"])
    url = f"https://q.10jqka.com.cn/gn/detail/code/{code}/"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    links = []
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "/page/" in href or "page=" in href:
            links.append({"text": anchor.get_text(strip=True), "url": urljoin(url, href)})
    return pd.DataFrame(links).drop_duplicates() if links else pd.DataFrame()


def ths_large_board_page2() -> pd.DataFrame:
    boards = ak.stock_board_concept_name_ths()
    named = boards[boards["name"].astype(str).str.contains("融资融券", na=False)]
    row = named.iloc[0] if not named.empty else boards.iloc[0]
    code = str(row["code"])
    js = py_mini_racer.MiniRacer()
    js.eval(_get_file_content_ths("ths.js"))
    v_code = js.call("v")
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://q.10jqka.com.cn/"})
    session.cookies.set("v", v_code, domain=".10jqka.com.cn")
    first_url = f"https://q.10jqka.com.cn/gn/detail/code/{code}/"
    first = session.get(first_url, timeout=15)
    candidates = [
        f"https://q.10jqka.com.cn/gn/detail/field/264648/order/desc/page/2/ajax/1/code/{code}/",
        f"http://q.10jqka.com.cn/gn/detail/field/264648/order/desc/page/2/ajax/1/code/{code}/",
        f"https://q.10jqka.com.cn/gn/detail/field/199112/order/desc/page/2/ajax/1/code/{code}/",
    ]
    rows = [{"variant": "first", "status": first.status_code, "chars": len(first.text), "tables": len(pd.read_html(StringIO(first.text))) if first.ok else 0}]
    for url in candidates:
        response = session.get(url, timeout=15)
        table_count = 0
        code_rows = 0
        if response.ok:
            tables = pd.read_html(StringIO(response.text))
            table_count = len(tables)
            code_rows = sum(len(x) for x in tables if any("代码" in str(c) for c in x.columns))
        rows.append({"variant": url, "status": response.status_code, "chars": len(response.text), "tables": table_count, "code_rows": code_rows})
    return pd.DataFrame(rows)


def main() -> None:
    available = sorted(name for name in dir(ak) if "concept" in name.lower() or "board_cons" in name.lower())
    results = [
        record("sina_concept_list", lambda: ak.stock_sector_spot(indicator="概念")),
        record("eastmoney_concept_list", ak.stock_board_concept_name_em),
        record("ths_concept_list", ak.stock_board_concept_name_ths),
        record("ths_first_board_html_table", ths_first_board_table),
        record("ths_first_board_pagination", ths_first_board_pagination),
        record("ths_large_board_page2", ths_large_board_page2),
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {"available_functions": available, "results": results}
    (OUT / "result.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
