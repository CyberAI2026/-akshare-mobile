from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from bs4 import BeautifulSoup
from openai import OpenAI

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path("v5_data/opinion")
LIST_URLS = [
    "https://www.tgb.cn/talk/talkSeq/21325",
    "https://www.tgb.cn/newIndex/2",
]
UA = "AStockResearch/1.0 (private research; low-frequency; contact via repository owner)"
ARTICLE_LIMIT = int(os.getenv("OPINION_ARTICLE_LIMIT", "20"))
BATCH_SIZE = int(os.getenv("OPINION_BATCH_SIZE", "4"))
MIN_TEXT = 500


def now_cn() -> datetime:
    return datetime.now(TZ)


def target_trade_date():
    current = now_cn()
    day = current.date() - timedelta(days=1) if current.hour < 6 else current.date()
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def fetch_html(url: str) -> str:
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=25,
    )
    r.raise_for_status()
    return r.text


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def discover_articles() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    target = target_trade_date()
    date_tokens = {
        target.strftime("%m-%d"), target.strftime("%m.%d"),
        f"{target.month}-{target.day}", f"{target.month}.{target.day}",
        f"{target.month}月{target.day}日",
    }
    for list_url in LIST_URLS:
        html = fetch_html(list_url)
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href*="/a/"]'):
            href = urljoin(list_url, a.get("href", ""))
            title = clean_text(a.get_text(" ", strip=True))
            if not href or href in seen or len(title) < 6:
                continue
            node = a
            contexts = [title]
            for _ in range(4):
                node = node.parent if node else None
                if node:
                    contexts.append(clean_text(node.get_text(" ", strip=True)))
            context = min((x for x in contexts if any(t in x for t in date_tokens)), key=len, default=contexts[-1])
            # 必须能在标题或邻近列表项中确认目标交易日，避免把旧文章混入当日共识。
            if not any(t in context or t in title for t in date_tokens):
                continue
            score = 0
            score += 4 if any(k in title for k in ["复盘", "收盘", "市场", "情绪", "板块", "明日"]) else 0
            score += 2
            reads = re.search(r"(\d+)\s*阅读", context)
            read_count = int(reads.group(1)) if reads else 0
            score += min(5, int(read_count >= 100) + int(read_count >= 500) + int(read_count >= 1000) + int(read_count >= 3000))
            if score < 4:
                continue
            seen.add(href)
            rows.append({"url": href, "title_hint": title, "read_count": read_count, "score": score, "list_url": list_url})
    return sorted(rows, key=lambda x: (x["score"], x["read_count"]), reverse=True)[:ARTICLE_LIMIT]


def extract_article(meta: dict) -> dict | None:
    html = fetch_html(meta["url"])
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "form", "noscript"]):
        tag.decompose()
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = clean_text(title_node.get_text(" ", strip=True) if title_node else meta["title_hint"])
    candidates = []
    selectors = [
        "article", ".article-content", ".article_content", ".content", ".topic-content",
        ".p_coten", ".body-content", "[class*=article]", "[class*=content]",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            text = clean_text(node.get_text("\n", strip=True))
            if len(text) >= MIN_TEXT:
                candidates.append(text)
    if not candidates:
        text = clean_text(soup.get_text("\n", strip=True))
    else:
        text = max(candidates, key=len)
    # 去除明显站点尾部；正文仍完整进入本次临时分析，不写入磁盘。
    for marker in ["加入淘股吧", "关于我们", "意见反馈"]:
        pos = text.find(marker)
        if pos > MIN_TEXT:
            text = text[:pos]
    text = clean_text(text)
    if len(text) < MIN_TEXT:
        return None
    return {
        **meta,
        "title": title,
        "body": text,
        "body_chars": len(text),
        "body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回JSON对象")
    return json.loads(text[start:end + 1])


def analyze_batch(client: OpenAI, model: str, articles: list[dict], batch_no: int) -> dict:
    payload = [{
        "article_id": a["body_sha256"][:16],
        "title": a["title"],
        "url": a["url"],
        "read_count": a["read_count"],
        # 正文完整用于本次分析；不把正文写入任何结果文件。
        "full_text": a["body"],
    } for a in articles]
    prompt = """你是A股收盘复盘文本挖掘器。完整阅读输入的每篇公开文章正文，只抽取作者明确表达的观点，不把观点当事实，不提供买卖建议。
输出一个合法JSON对象：
{
 "articles":[{
  "article_id":"","market_stance":"偏多/中性/谨慎/偏空/不明确",
  "market_phase":["启动/发酵/高潮/分歧/修复/退潮/冰点/混沌"],
  "market_summary":"不超过80字的忠实转述",
  "sectors":[{"name":"","stance":"加强/活跃/分化/退潮/不明确","evidence":"不超过50字"}],
  "stocks":[{"name":"","sector":"","role":"龙头/核心/跟随/高关注/风险/不明确"}],
  "tomorrow_watch":["不超过3项"],
  "numeric_claims":["文中可核验的市场数字"],
  "quality_flags":["广告/单股为主/缺少大盘/缺少板块/明显情绪化/无"]
 }]
}
必须覆盖全部article_id。禁止输出输入中不存在的行情、板块和股票。"""
    resp = client.responses.create(
        model=model,
        input=prompt + "\n输入JSON：\n" + json.dumps(payload, ensure_ascii=False),
        max_output_tokens=10000,
    )
    usage = getattr(resp, "usage", None)
    print(
        "OPINION_OPENAI_CALL_OK "
        f"batch={batch_no} response_id={getattr(resp, 'id', None)} model={getattr(resp, 'model', model)} "
        f"input_tokens={getattr(usage, 'input_tokens', None)} output_tokens={getattr(usage, 'output_tokens', None)}"
    )
    return parse_json(resp.output_text)


def aggregate(client: OpenAI, model: str, mined: list[dict], source_rows: list[dict]) -> dict:
    prompt = """你是A股市场观点数据库的聚合器。以下是多篇完整正文经过逐篇抽取得到的观点。
生成合法JSON对象：
{
 "market_consensus":{"stance":"","phase":[],"summary":"","confidence":"低/中/高"},
 "market_disagreements":[""],
 "sector_consensus":[{"sector":"","mention_count":0,"consensus":"","stance":"加强/活跃/分化/退潮/不明确","representative_stocks":[]}],
 "stock_attention":[{"stock":"","mention_count":0,"sectors":[],"roles":[]}],
 "tomorrow_consensus_watch":[""],
 "limitations":[""]
}
共识必须由多篇文章支持；少数意见列入分歧。不要把作者观点写成客观事实，不给出买卖建议。"""
    resp = client.responses.create(
        model=model,
        input=prompt + "\n逐篇抽取JSON：\n" + json.dumps(mined, ensure_ascii=False),
        max_output_tokens=6000,
    )
    usage = getattr(resp, "usage", None)
    print(
        "OPINION_OPENAI_AGGREGATE_OK "
        f"response_id={getattr(resp, 'id', None)} model={getattr(resp, 'model', model)} "
        f"input_tokens={getattr(usage, 'input_tokens', None)} output_tokens={getattr(usage, 'output_tokens', None)}"
    )
    result = parse_json(resp.output_text)
    result["article_count"] = len(source_rows)
    result["source_platform"] = "淘股吧公开复盘"
    return result


def group_attention_sectors(sectors: list[dict], limit: int = 10) -> dict[str, list[dict]]:
    """关注度由提及次数决定，趋势状态单独分组；热度绝不等同于上涨。"""
    ranked = sorted(
        [x for x in sectors if str(x.get("sector", "")).strip()],
        key=lambda x: int(x.get("mention_count", 0) or 0),
        reverse=True,
    )[:limit]
    groups = {"观点偏强或加强": [], "活跃但分化": [], "退潮或走弱": [], "状态不明确": []}
    for item in ranked:
        stance = str(item.get("stance", "") or "不明确")
        if any(k in stance for k in ["退潮", "走弱", "弱化", "冰点", "下跌"]):
            key = "退潮或走弱"
        elif any(k in stance for k in ["加强", "强势", "上涨", "修复", "发酵", "高潮"]):
            key = "观点偏强或加强"
        elif any(k in stance for k in ["活跃", "分化", "分歧"]):
            key = "活跃但分化"
        else:
            key = "状态不明确"
        groups[key].append(item)
    return groups


def save_results(articles: list[dict], mined: list[dict], summary: dict) -> None:
    day = target_trade_date().isoformat()
    daily = ROOT / "daily"
    daily.mkdir(parents=True, exist_ok=True)
    # 只保存元数据、哈希和本系统生成的结构化观点；不保存正文。
    sources = [{
        "article_id": a["body_sha256"][:16],
        "title": a["title"],
        "url": a["url"],
        "read_count": a["read_count"],
        "body_chars": a["body_chars"],
        "body_sha256": a["body_sha256"],
    } for a in articles]
    out = {
        "trade_date": day,
        "generated_at_cn": now_cn().isoformat(),
        "method": "full-text transient mining; raw article bodies not persisted",
        "sources": sources,
        "article_mining": mined,
        "daily_consensus": summary,
    }
    (daily / f"{day}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    (ROOT / "latest.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    index_path = ROOT / "opinion_25d.csv"
    sector_groups = group_attention_sectors(summary.get("sector_consensus", []) or [])
    row = {
        "日期": day,
        "文章数": len(articles),
        "市场倾向": summary.get("market_consensus", {}).get("stance", ""),
        "市场阶段": "|".join(summary.get("market_consensus", {}).get("phase", []) or []),
        "摘要": summary.get("market_consensus", {}).get("summary", ""),
        "高关注偏强板块": "|".join(str(x.get("sector", "")) for x in sector_groups["观点偏强或加强"]),
        "高关注分化板块": "|".join(str(x.get("sector", "")) for x in sector_groups["活跃但分化"]),
        "高关注退潮板块": "|".join(str(x.get("sector", "")) for x in sector_groups["退潮或走弱"]),
        "高关注状态不明板块": "|".join(str(x.get("sector", "")) for x in sector_groups["状态不明确"]),
        "热门个股": "|".join(str(x.get("stock", "")) for x in (summary.get("stock_attention", []) or [])[:10]),
    }
    old = pd.read_csv(index_path, dtype=str, encoding="utf-8-sig") if index_path.exists() else pd.DataFrame()
    frame = pd.concat([old[old.get("日期", pd.Series(dtype=str)).astype(str) != day], pd.DataFrame([row])], ignore_index=True)
    frame = frame.sort_values("日期").tail(25)
    frame.to_csv(index_path, index=False, encoding="utf-8-sig")


def push_summary(summary: dict) -> None:
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if not token:
        return
    market = summary.get("market_consensus", {}) or {}
    sectors = summary.get("sector_consensus", []) or []
    sector_groups = group_attention_sectors(sectors)
    stocks = summary.get("stock_attention", []) or []
    def render(items):
        return "、".join(
            f"{x.get('sector', '')}（提及{x.get('mention_count', 0)}篇；{x.get('stance', '不明确')}）"
            for x in items
        ) or "无"
    lines = [
        f"<b>文章样本：</b>{summary.get('article_count', 0)}篇公开复盘全文",
        f"<b>市场观点：</b>{market.get('stance', '—')}｜{'、'.join(market.get('phase', []) or [])}",
        f"<b>共识摘要：</b>{market.get('summary', '—')}",
        "<b>高关注·观点偏强/加强：</b>" + render(sector_groups["观点偏强或加强"]),
        "<b>高关注·活跃但分化：</b>" + render(sector_groups["活跃但分化"]),
        "<b>高关注·退潮/走弱：</b>" + render(sector_groups["退潮或走弱"]),
        "<b>高关注·状态不明确：</b>" + render(sector_groups["状态不明确"]),
        "<b>观点热门个股：</b>" + "、".join(str(x.get("stock", "")) for x in stocks[:10]),
        "<small>“高关注”仅表示文章提及较多，不等于上涨或推荐；以上趋势标签来自公开文章观点，客观涨幅以盘后行情复盘为准。</small>",
    ]
    r = requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": "A股二次启动｜市场观点摘要", "content": "<br>".join(lines), "template": "html", "channel": "wechat"},
        timeout=20,
    )
    print("OPINION_PUSHPLUS", r.status_code, r.text[:300])
    r.raise_for_status()


def commit() -> None:
    subprocess.run(["git", "config", "user.name", "V5 Automation"], check=False)
    subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "v5_data/opinion"], check=True)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    if changed:
        subprocess.run(["git", "commit", "-m", f"Update 25-day market opinion database {target_trade_date().isoformat()}"], check=True)
        # 研究期间主分支可能有并行维护提交；先变基再推送，避免非快进导致数据产物只留在artifact。
        for attempt in range(1, 4):
            pull = subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False)
            if pull.returncode != 0:
                subprocess.run(["git", "rebase", "--abort"], check=False)
                raise RuntimeError("观点数据库保存前rebase失败")
            push = subprocess.run(["git", "push", "origin", "HEAD:main"], check=False)
            if push.returncode == 0:
                return
            print(f"OPINION_GIT_PUSH_RETRY attempt={attempt}")
            time.sleep(attempt * 2)
        raise RuntimeError("观点数据库连续3次推送失败")


def main() -> None:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("OPENAI_API_KEY未配置，不能执行正文观点挖掘")
    model = os.getenv("OPINION_OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-5.6-terra"))
    discovered = discover_articles()
    articles = []
    for meta in discovered:
        try:
            item = extract_article(meta)
            if item:
                articles.append(item)
        except Exception as exc:
            print("ARTICLE_FETCH_FAILED", meta["url"], type(exc).__name__, str(exc)[:200])
        time.sleep(1.2)
    if not articles:
        raise RuntimeError("没有取得可分析的完整公开复盘正文")
    client = OpenAI(api_key=key)
    mined = []
    for i in range(0, len(articles), BATCH_SIZE):
        result = analyze_batch(client, model, articles[i:i + BATCH_SIZE], i // BATCH_SIZE + 1)
        mined.extend(result.get("articles", []) or [])
    expected = {a["body_sha256"][:16] for a in articles}
    actual = {str(x.get("article_id", "")) for x in mined}
    if expected - actual:
        raise RuntimeError(f"逐篇分析缺失article_id: {sorted(expected - actual)}")
    summary = aggregate(client, model, mined, articles)
    save_results(articles, mined, summary)
    push_summary(summary)
    commit()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
