from __future__ import annotations

import argparse
import html
import hashlib
import json
import os
import re
import subprocess
import time
import concurrent.futures
from collections import Counter
from datetime import date, datetime, timedelta
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
    # 扩展发现面但不降低正文门槛；研股、方法论和综合页中只有同时通过
    # 当天发表时间、市场维度、板块/周期维度校验的文章才会入选。
    "https://www.tgb.cn/newIndex/1",
    "https://www.tgb.cn/newIndex/4",
    "https://www.tgb.cn/newIndex/5",
]
UA = "AStockResearch/1.0 (private research; low-frequency; contact via repository owner)"
TOPIC_API_URL = "https://www.tgb.cn/talk/getTalkByFlag"
TOPIC_SEQ = "21325"
TOPIC_DISCOVERY_PAGES = int(os.getenv("OPINION_TOPIC_DISCOVERY_PAGES", "6"))
ARTICLE_LIMIT = int(os.getenv("OPINION_ARTICLE_LIMIT", "30"))
MIN_ARTICLE_COUNT = int(os.getenv("OPINION_MIN_ARTICLES", "15"))
BATCH_SIZE = int(os.getenv("OPINION_BATCH_SIZE", "4"))
BATCH_WORKERS = int(os.getenv("OPINION_BATCH_WORKERS", "3"))
OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPINION_OPENAI_TIMEOUT_SECONDS", "240"))
OPENAI_MAX_RETRIES = int(os.getenv("OPINION_OPENAI_MAX_RETRIES", "1"))
MIN_TEXT = 600
THS_CONCEPT_LIMIT = int(os.getenv("OPINION_THS_CONCEPT_LIMIT", "10"))
MARKET_TERMS = ("市场", "大盘", "指数", "情绪", "成交额", "涨停", "跌停", "赚钱效应", "亏钱效应")
SECTOR_TERMS = ("板块", "题材", "主线", "周期", "轮动", "资金", "分歧", "退潮", "修复")
REVIEW_TERMS = ("复盘", "收盘", "市场", "情绪", "板块", "明日", "策略")
CRITICAL_QUALITY_FLAGS = ("单股为主", "缺少大盘", "缺少市场", "缺少板块")


def now_cn() -> datetime:
    return datetime.now(TZ)


def opinion_finalization(article_count: int, current: datetime | None = None) -> tuple[bool, str]:
    """Publish no earlier than 21:00; wait for 15 quality reviews until the 22:00 deadline."""
    current = current or now_cn()
    minutes = current.hour * 60 + current.minute
    if minutes < 21 * 60:
        return False, "before_21_release"
    if article_count >= MIN_ARTICLE_COUNT:
        return True, "quality_target_met"
    if minutes >= 22 * 60:
        return True, "deadline_partial"
    return False, "awaiting_more_quality_articles"


def source_date(current: datetime | None = None) -> date:
    current = current or now_cn()
    day = current.date() - timedelta(days=1) if current.hour < 6 else current.date()
    return day


def target_trade_date(current: datetime | None = None,
                      trade_dates: list[date] | None = None) -> date:
    """Attach weekend/holiday commentary to the next trading day, with audit dates."""
    day=source_date(current)
    if trade_dates is None:
        try:
            import akshare as ak
            calendar=ak.tool_trade_date_hist_sina()
            trade_dates=sorted(set(pd.to_datetime(
                calendar[calendar.columns[0]],errors="coerce"
            ).dt.date.dropna()))
        except Exception as exc:
            print("OPINION_TRADE_CALENDAR_FALLBACK",type(exc).__name__,str(exc)[:160],flush=True)
            trade_dates=[]
    if trade_dates:
        if day in trade_dates:
            return day
        future=[item for item in trade_dates if item>day]
        if future:
            return future[0]
    while day.weekday()>=5:
        day+=timedelta(days=1)
    return day


def wait_until_cn(env_name: str) -> None:
    not_before=os.getenv(env_name,"").strip()
    if not not_before:
        return
    try:
        hour,minute=(int(x) for x in not_before.split(":",1))
    except ValueError as exc:
        raise RuntimeError(f"{env_name}格式错误: {not_before}") from exc
    current=now_cn()
    target=current.replace(hour=hour,minute=minute,second=0,microsecond=0)
    if current<target:
        wait_seconds=int((target-current).total_seconds())
        print(f"{env_name}_WAIT seconds={wait_seconds} target_cn={target.isoformat()}",flush=True)
        time.sleep(wait_seconds)


def fetch_html(url: str) -> str:
    last_error=None
    for attempt in range(1,4):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
                timeout=25,
            )
            r.raise_for_status()
            return r.text
        except Exception as exc:
            last_error=exc
            print(f"OPINION_HTTP_RETRY attempt={attempt} url={url} error={type(exc).__name__}",flush=True)
            if attempt<3:
                time.sleep(attempt*2)
    raise last_error


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text or "")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def install_default_http_timeout(seconds: float = 15) -> None:
    """Bound AKShare/THS requests that do not pass their own timeout."""
    original=requests.sessions.Session.request
    if getattr(original,"_v5_opinion_timeout_wrapped",False):
        return
    def bounded(self,method,url,**kwargs):
        kwargs.setdefault("timeout",seconds)
        return original(self,method,url,**kwargs)
    bounded._v5_opinion_timeout_wrapped=True
    requests.sessions.Session.request=bounded


def normalize_concept_name(value: str) -> str:
    value=re.sub(r"[\s·•_—\-]+","",str(value or "").strip()).lower()
    return re.sub(r"(?:概念|板块)$","",value)


def compute_concept_index_metrics(frame: pd.DataFrame, name: str, code: str = "") -> dict | None:
    if frame is None or frame.empty or "日期" not in frame or "收盘价" not in frame:
        return None
    x=frame.copy()
    x["日期"]=pd.to_datetime(x["日期"],errors="coerce")
    x["收盘价"]=pd.to_numeric(x["收盘价"],errors="coerce")
    if "成交量" in x:
        x["成交量"]=pd.to_numeric(x["成交量"],errors="coerce")
    x=x.dropna(subset=["日期","收盘价"]).sort_values("日期").drop_duplicates("日期").tail(10)
    if len(x)<2:
        return None
    close=x["收盘价"]
    one_day=(close.iloc[-1]/close.iloc[-2]-1)*100
    five_day=(close.iloc[-1]/close.iloc[-6]-1)*100 if len(x)>=6 else None
    volume_ratio=None
    if "成交量" in x and len(x)>=6:
        baseline=x["成交量"].iloc[-6:-1].mean()
        if pd.notna(baseline) and baseline>0 and pd.notna(x["成交量"].iloc[-1]):
            volume_ratio=float(x["成交量"].iloc[-1]/baseline)
    if one_day>=1 and (five_day is None or five_day>0):
        state="上涨加强"
    elif one_day<=-1 and (five_day is None or five_day<0):
        state="退潮走弱"
    elif five_day is not None and five_day>=2:
        state="趋势偏强但当日分化"
    elif five_day is not None and five_day<=-2:
        state="趋势偏弱但当日修复/震荡"
    else:
        state="震荡分化"
    return {
        "concept":name,"ths_code":str(code or ""),
        "asof_date":x["日期"].iloc[-1].date().isoformat(),
        "one_day_pct":round(float(one_day),2),
        "five_day_pct":round(float(five_day),2) if five_day is not None else None,
        "volume_ratio_5d":round(volume_ratio,2) if volume_ratio is not None else None,
        "state":state,"source":"同花顺概念指数（AKShare）",
    }


def fetch_ths_concept_facts(sectors: list[dict], day: date, limit: int | None = None) -> dict:
    result={"status":"unavailable","asof_date":day.isoformat(),"items":[],
            "note":"客观指数数据与文章观点分开记录。"}
    wanted=[]
    for item in sectors or []:
        name=str(item.get("sector","")).strip()
        if name and name not in wanted:
            wanted.append(name)
    if not wanted:
        result["status"]="not_applicable"
        result["note"]="文章样本没有形成可匹配的概念板块。"
        return result
    try:
        install_default_http_timeout()
        import akshare as ak
        names=ak.stock_board_concept_name_ths()
        name_col=next((c for c in ["name","概念名称","板块名称","名称"] if c in names),None)
        code_col=next((c for c in ["code","概念代码","板块代码","代码"] if c in names),None)
        if name_col is None:
            raise RuntimeError(f"同花顺概念目录缺少名称列: {list(names.columns)}")
        catalog={}
        for _,row in names.iterrows():
            raw_name=str(row[name_col]).strip()
            key=normalize_concept_name(raw_name)
            if key and key not in catalog:
                catalog[key]=(raw_name,str(row[code_col]).strip() if code_col else "")
        matched=[]
        effective_limit=max(1,int(limit or THS_CONCEPT_LIMIT))
        for opinion_name in wanted:
            found=catalog.get(normalize_concept_name(opinion_name))
            if found and found not in matched:
                matched.append(found)
            if len(matched)>=effective_limit:
                break
        start=(day-timedelta(days=20)).strftime("%Y%m%d")
        end=day.strftime("%Y%m%d")
        def one(pair):
            name,code=pair
            try:
                raw=ak.stock_board_concept_index_ths(symbol=name,start_date=start,end_date=end)
                return compute_concept_index_metrics(raw,name,code),""
            except Exception as exc:
                return None,f"{name}:{type(exc).__name__}:{str(exc)[:120]}"
        errors=[]
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(5,max(1,len(matched)))) as executor:
            for item,error in executor.map(one,matched):
                if item:
                    result["items"].append(item)
                if error:
                    errors.append(error)
        result["status"]="ready" if result["items"] else "unavailable"
        result["matched_concepts"]=len(matched)
        result["failed_concepts"]=len(errors)
        if errors:
            result["errors"]=errors[:5]
        if result["items"]:
            result["asof_date"]=max(x["asof_date"] for x in result["items"])
    except Exception as exc:
        result["note"]=f"同花顺概念指数暂不可用: {type(exc).__name__}: {str(exc)[:160]}"
    return result


def render_source_links(sources: list[dict], limit: int = 30) -> str:
    links=[]
    for index,item in enumerate(sources[:limit],1):
        title=html.escape(str(item.get("title") or f"文章{index}"))
        url=html.escape(str(item.get("url") or ""),quote=True)
        if url.startswith("https://www.tgb.cn/") or url.startswith("https://m.tgb.cn/"):
            links.append(f'{index}. <a href="{url}">{title}</a>')
    return "<br>".join(links) or "本次没有合格文章链接"


def parse_published_at(text: str) -> datetime | None:
    """Parse the article's own publication timestamp; list-page dates are not proof."""
    patterns = [
        r"(?<!\d)(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?[T\s]+(\d{1,2}):(\d{2})(?!\d)",
        r"(?<!\d)(\d{2})-(\d{1,2})-(\d{1,2})\s+(\d{1,2}):(\d{2})(?!\d)",
    ]
    for pattern in patterns:
        match=re.search(pattern,text or "")
        if not match:
            continue
        year=int(match.group(1))
        if year<100:
            year+=2000
        try:
            return datetime(year,int(match.group(2)),int(match.group(3)),
                            int(match.group(4)),int(match.group(5)),tzinfo=TZ)
        except ValueError:
            continue
    return None


def review_quality_reasons(title: str, body: str) -> list[str]:
    reasons=[]
    if len(body)<MIN_TEXT:
        reasons.append(f"正文少于{MIN_TEXT}字")
    market_hits=sum(term in body for term in MARKET_TERMS)
    sector_hits=sum(term in body for term in SECTOR_TERMS)
    if not any(term in title for term in REVIEW_TERMS) and market_hits<2:
        reasons.append("缺少市场复盘主题")
    if market_hits<2:
        reasons.append("市场维度不足")
    if sector_hits<2:
        reasons.append("板块/周期维度不足")
    return reasons


def topic_api_post_date(value) -> date | None:
    """Normalize the topic feed's millisecond/second/printable publication time."""
    if value is None or value == "":
        return None
    try:
        numeric=float(value)
        if numeric>10_000_000_000:
            numeric/=1000
        return datetime.fromtimestamp(numeric,TZ).date()
    except (TypeError,ValueError,OverflowError,OSError):
        parsed=parse_published_at(str(value))
        return parsed.date() if parsed else None


def topic_api_candidates_from_payload(
    payload: dict, page_no: int, target_day: date | None = None
) -> list[dict]:
    """Convert current-day rows in the public #每日复盘 latest feed into candidates."""
    dto=(payload or {}).get("dto", {}) or {}
    rows=[]
    for item in dto.get("list", []) or []:
        # Filter by the feed timestamp before ranking. Otherwise old high-read posts can
        # crowd freshly published reviews out of ARTICLE_LIMIT.
        post_day=topic_api_post_date(item.get("postTime"))
        if target_day is not None and post_day is not None and post_day!=target_day:
            continue
        # Replies, short-form posts and video/news items do not expose a normal /a/ article body.
        if str(item.get("topicType", "")).upper() in {"R", "W", "VD", "CLS"}:
            continue
        topic_id=str(item.get("newTopicID") or item.get("newTopicIDNew") or "").strip()
        title=clean_text(str(item.get("subject") or ""))
        if not topic_id or len(title)<6:
            continue
        try:
            read_count=int(item.get("viewNum") or 0)
        except (TypeError,ValueError):
            read_count=0
        score=2
        score+=4 if any(k in title for k in REVIEW_TERMS) else 0
        score+=min(5,int(read_count>=100)+int(read_count>=500)+int(read_count>=1000)+int(read_count>=3000))
        rows.append({
            "url":urljoin("https://www.tgb.cn",f"/a/{topic_id}"),
            "title_hint":title,"read_count":read_count,"score":score,
            "post_date":post_day.isoformat() if post_day else "",
            "list_url":f"{TOPIC_API_URL}?flag=N&pageNo={page_no}&talkSeq={TOPIC_SEQ}",
        })
    return rows


def discover_topic_api_candidates() -> list[dict]:
    """Read multiple pages of the public latest feed, prioritizing current-day rows."""
    rows=[]
    for page_no in range(1,max(1,TOPIC_DISCOVERY_PAGES)+1):
        try:
            response=requests.get(
                TOPIC_API_URL,
                params={"flag":"N","pageNo":page_no,"talkSeq":TOPIC_SEQ},
                headers={"User-Agent":UA,"Accept-Language":"zh-CN,zh;q=0.9"},
                timeout=25,
            )
            response.raise_for_status()
            payload=response.json()
            dto=(payload or {}).get("dto", {}) or {}
            rows.extend(topic_api_candidates_from_payload(payload,page_no,source_date()))
            page_num=int(dto.get("pageNum") or page_no)
            if page_no>=page_num:
                break
        except Exception as exc:
            print(
                f"OPINION_TOPIC_API_FAILED page={page_no} error={type(exc).__name__}:{str(exc)[:160]}",
                flush=True,
            )
            break
    return rows


def discover_articles() -> list[dict]:
    seen: set[str] = set()
    rows: list[dict] = []
    target = source_date()
    date_tokens = {
        target.strftime("%m-%d"), target.strftime("%m.%d"),
        f"{target.month}-{target.day}", f"{target.month}.{target.day}",
        f"{target.month}月{target.day}日",
    }

    # Primary route: the topic's public latest-feed pages. Publication dates are
    # verified again on every article page, so older feed rows cannot enter the pool.
    for item in discover_topic_api_candidates():
        href=str(item.get("url") or "")
        if href and href not in seen:
            seen.add(href)
            rows.append(item)

    # Secondary routes: visible HTML lists. These remain useful if the JSON feed is
    # temporarily unavailable and also surface editorial/recommended review posts.
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
            relative_recent=bool(re.search(r"(?:刚刚|\\d+\\s*分钟前|\\d+\\s*小时前)",context))
            if not any(t in context or t in title for t in date_tokens) and not relative_recent:
                continue
            score = 0
            score += 4 if any(k in title for k in REVIEW_TERMS) else 0
            score += 2
            reads = re.search(r"(\d+)\s*阅读", context)
            read_count = int(reads.group(1)) if reads else 0
            score += min(5, int(read_count >= 100) + int(read_count >= 500) + int(read_count >= 1000) + int(read_count >= 3000))
            if score < 4:
                continue
            seen.add(href)
            rows.append({"url": href, "title_hint": title, "read_count": read_count, "score": score, "list_url": list_url})
    return sorted(rows, key=lambda x: (x["score"], x["read_count"]), reverse=True)[:ARTICLE_LIMIT]


def title_review_date_matches(title: str, target) -> bool:
    """标题明确标注旧复盘日期时拒绝；“明日策略9.4”不当作文章复盘日期。"""
    dates = []
    for match in re.finditer(r"(?:\d{4}年)?(\d{1,2})[月./-](\d{1,2})日?.{0,8}复盘", title):
        dates.append((int(match.group(1)), int(match.group(2))))
    for match in re.finditer(r"(?<!\d)(\d{2})(\d{2})复盘", title):
        dates.append((int(match.group(1)), int(match.group(2))))
    return not dates or (target.month, target.day) in dates


def extract_article(meta: dict) -> dict | None:
    html = fetch_html(meta["url"])
    soup = BeautifulSoup(html, "html.parser")
    publication_candidates=[]
    for selector in [
        'meta[property="article:published_time"]', 'meta[name="publishdate"]',
        'meta[name="pubdate"]', 'meta[name="date"]', 'time[datetime]',
    ]:
        for node in soup.select(selector):
            publication_candidates.append(str(node.get("content") or node.get("datetime") or ""))
    publication_candidates.append(clean_text(soup.get_text(" ",strip=True)))
    published_at=next((value for value in (parse_published_at(x) for x in publication_candidates) if value),None)
    if published_at is None or published_at.date()!=source_date():
        print("ARTICLE_PUBLICATION_DATE_REJECTED",published_at.isoformat() if published_at else "missing",meta["url"],flush=True)
        return None
    for tag in soup(["script", "style", "nav", "footer", "form", "noscript"]):
        tag.decompose()
    title_node = soup.select_one("h1") or soup.select_one("title")
    title = clean_text(title_node.get_text(" ", strip=True) if title_node else meta["title_hint"])
    if not title_review_date_matches(title, source_date()):
        print("ARTICLE_DATE_REJECTED", title[:120], meta["url"])
        return None
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
    quality_reasons=review_quality_reasons(title,text)
    if quality_reasons:
        print("ARTICLE_QUALITY_REJECTED", "|".join(quality_reasons), title[:100], flush=True)
        return None
    return {
        **meta,
        "title": title,
        "body": text,
        "body_chars": len(text),
        "body_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "published_at_cn": published_at.isoformat(),
        "quality_checks": ["当天发表时间已核验", f"正文不少于{MIN_TEXT}字", "覆盖市场维度", "覆盖板块/周期维度"],
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
        f"input_tokens={getattr(usage, 'input_tokens', None)} output_tokens={getattr(usage, 'output_tokens', None)}",
        flush=True,
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
        f"input_tokens={getattr(usage, 'input_tokens', None)} output_tokens={getattr(usage, 'output_tokens', None)}",
        flush=True,
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
        "published_at_cn": a.get("published_at_cn", ""),
        "quality_checks": a.get("quality_checks", []),
    } for a in articles]
    out = {
        "trade_date": day,
        "source_date": source_date().isoformat(),
        "generated_at_cn": now_cn().isoformat(),
        "method": "full-text transient mining; raw article bodies not persisted",
        "selection_standard": {
            "publication_date": "文章页面可核验的发表日期必须等于采集日",
            "minimum_articles_for_formal_consensus": MIN_ARTICLE_COUNT,
            "minimum_body_chars": MIN_TEXT,
            "topic_requirements": "必须同时覆盖市场以及板块/题材/周期维度",
            "exclusions": "排除旧文、无法核验发表时间、正文不完整、纯单股流水或缺少市场板块分析的帖子",
        },
        "sources": sources,
        "article_mining": mined,
        "daily_consensus": summary,
        "finalization": summary.get("finalization", {}),
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


def push_summary(summary: dict, source_day: str | None = None,
                 target_day: str | None = None,
                 sources: list[dict] | None = None) -> dict:
    if os.getenv("OPINION_SKIP_PUSH", "").strip().lower() in {"1", "true", "yes"}:
        print("OPINION_PUSHPLUS_SKIPPED context-only run")
        return {"accepted":False,"reason":"context-only run"}
    wait_until_cn("OPINION_PUSH_NOT_BEFORE_CN")
    token = os.getenv("PUSHPLUS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PUSHPLUS_TOKEN未配置，不能发送市场观点摘要")
    source_day=source_day or source_date().isoformat()
    target_day=target_day or target_trade_date().isoformat()
    market = summary.get("market_consensus", {}) or {}
    sectors = summary.get("sector_consensus", []) or []
    sector_groups = group_attention_sectors(sectors)
    stocks = summary.get("stock_attention", []) or []
    concept_facts=summary.get("ths_concept_index",{}) or {}
    def render(items):
        return "、".join(
            f"{x.get('sector', '')}（提及{x.get('mention_count', 0)}篇；{x.get('stance', '不明确')}）"
            for x in items
        ) or "无"
    lines = [
        f"<b>采集日：</b>{source_day}｜<b>适用交易日：</b>{target_day}",
        f"<b>文章样本：</b>{summary.get('article_count', 0)}篇／正式门槛{MIN_ARTICLE_COUNT}篇",
        f"<b>样本状态：</b>{summary.get('sample_status', '正式样本')}",
        f"<b>市场观点：</b>{market.get('stance', '—')}｜{'、'.join(market.get('phase', []) or [])}",
        f"<b>共识摘要：</b>{market.get('summary', '—')}",
        "<b>高关注·观点偏强/加强：</b>" + render(sector_groups["观点偏强或加强"]),
        "<b>高关注·活跃但分化：</b>" + render(sector_groups["活跃但分化"]),
        "<b>高关注·退潮/走弱：</b>" + render(sector_groups["退潮或走弱"]),
        "<b>高关注·状态不明确：</b>" + render(sector_groups["状态不明确"]),
        "<b>同花顺概念指数（客观行情）：</b>",
    ]
    fact_items=concept_facts.get("items",[]) or []
    if fact_items:
        for item in fact_items[:THS_CONCEPT_LIMIT]:
            five="—" if item.get("five_day_pct") is None else f"{item['five_day_pct']:+.2f}%"
            volume="—" if item.get("volume_ratio_5d") is None else f"{item['volume_ratio_5d']:.2f}倍"
            code=f"｜代码{html.escape(str(item.get('ths_code','')))}" if item.get("ths_code") else ""
            lines.append(
                f"• {html.escape(str(item.get('concept','')))}{code}｜1日{item.get('one_day_pct',0):+.2f}%｜5日{five}｜量比{volume}｜{html.escape(str(item.get('state','')))}"
            )
    else:
        lines.append("未取得与本次观点板块精确匹配且通过校验的同花顺概念指数。")
    lines.extend([
        "<b>观点热门个股：</b>" + "、".join(str(x.get("stock", "")) for x in stocks[:10]),
        "<small>“高关注”仅表示文章提及较多，不等于上涨或推荐；以上趋势标签来自公开文章观点，客观涨幅以盘后行情复盘为准。</small>",
        "<hr><b>本次纳入复盘的淘股吧文章：</b>",
        render_source_links(sources or []),
    ])
    r = requests.post(
        "https://www.pushplus.plus/send",
        json={"token": token, "title": "A股二次启动｜市场观点摘要", "content": "<br>".join(lines), "template": "html", "channel": "wechat"},
        timeout=20,
    )
    print("OPINION_PUSHPLUS", r.status_code, r.text[:300])
    r.raise_for_status()
    try:
        receipt = r.json()
    except Exception as exc:
        raise RuntimeError(f"PushPlus返回非JSON: {exc}") from exc
    if str(receipt.get("code", "")) != "200":
        raise RuntimeError(f"PushPlus业务回执失败: code={receipt.get('code')} msg={receipt.get('msg')}")
    return {
        "accepted":True,
        "short_code":str(receipt.get("data") or ""),
        "response_message":str(receipt.get("msg") or ""),
    }


def commit(message: str | None = None) -> None:
    subprocess.run(["git", "config", "user.name", "V5 Automation"], check=False)
    subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=False)
    subprocess.run(["git", "add", "v5_data/opinion"], check=True)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    if changed:
        subprocess.run(["git", "commit", "-m", message or f"Update 25-day market opinion database {target_trade_date().isoformat()}"], check=True)
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


def build_client(key: str) -> tuple[OpenAI, str]:
    model=os.getenv("OPINION_OPENAI_MODEL",os.getenv("OPENAI_MODEL","gpt-5.6-terra"))
    client=OpenAI(api_key=key,timeout=OPENAI_TIMEOUT_SECONDS,max_retries=OPENAI_MAX_RETRIES)
    return client,model


def public_article_metadata(article: dict) -> dict:
    return {
        "article_id":article["body_sha256"][:16],
        "title":article["title"],
        "url":article["url"],
        "read_count":article["read_count"],
        "body_chars":article["body_chars"],
        "body_sha256":article["body_sha256"],
        "published_at_cn":article.get("published_at_cn",""),
        "quality_checks":article.get("quality_checks",[]),
    }


def retain_ai_verified_quality(sources: list[dict], mined: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Apply the second quality gate after full-text AI extraction; never pad the count."""
    mined_by_id={str(item.get("article_id", "")):item for item in mined}
    kept_sources=[];kept_mined=[];rejected=[]
    for source in sources:
        article_id=str(source.get("article_id", ""))
        analysis=mined_by_id.get(article_id, {})
        flags=[str(x) for x in (analysis.get("quality_flags", []) or [])]
        critical=sorted({flag for flag in flags if any(term in flag for term in CRITICAL_QUALITY_FLAGS)})
        if critical:
            rejected.append({"article_id":article_id,"title":source.get("title", ""),"reasons":critical})
            continue
        kept_sources.append(source)
        kept_mined.append(analysis)
    return kept_sources,kept_mined,rejected


def fetch_selected_articles(selected: list[dict]) -> list[dict]:
    articles=[]
    for meta in selected:
        try:
            item=extract_article(meta)
            if item:
                articles.append(item)
        except Exception as exc:
            print("ARTICLE_FETCH_FAILED",meta["url"],type(exc).__name__,str(exc)[:200],flush=True)
        time.sleep(1.2)
    return articles


def run_discover_stage(stage_root: Path) -> None:
    """Discover once so parallel batch jobs do not simultaneously hammer the source site."""
    wait_until_cn("OPINION_COLLECT_NOT_BEFORE_CN")
    discovered=discover_articles()
    if not discovered:
        raise RuntimeError("没有发现当日淘股吧复盘文章")
    stage_root.mkdir(parents=True,exist_ok=True)
    payload={"source_date":source_date().isoformat(),"discovered":discovered}
    (stage_root/"discovery.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"OPINION_DISCOVERY_STAGE_OK source_date={payload['source_date']} discovered={len(discovered)}",flush=True)


def run_batch_stage(key: str, batch_index: int, batch_count: int, stage_root: Path) -> None:
    if batch_index<0 or batch_index>=batch_count:
        raise ValueError(f"batch-index必须在0到{batch_count-1}之间")
    discovery_path=stage_root/"discovery.json"
    if discovery_path.exists():
        discovery=json.loads(discovery_path.read_text(encoding="utf-8"))
        if str(discovery.get("source_date"))!=source_date().isoformat():
            raise RuntimeError("文章发现清单日期与当前源日期不一致")
        discovered=discovery.get("discovered",[]) or []
    else:
        wait_until_cn("OPINION_COLLECT_NOT_BEFORE_CN")
        discovered=discover_articles()
    staged_sources,_,_,_=load_staged_quality_pool(source_date().isoformat())
    staged_urls={str(item.get("url", "")) for item in staged_sources if item.get("url")}
    selected=[
        item for index,item in enumerate(discovered)
        if index%batch_count==batch_index and str(item.get("url", "")) not in staged_urls
    ]
    articles=fetch_selected_articles(selected)
    mined=[]
    if articles:
        client,model=build_client(key)
        result=analyze_batch(client,model,articles,batch_index+1)
        mined=result.get("articles",[]) or []
        expected={a["body_sha256"][:16] for a in articles}
        actual={str(x.get("article_id","")) for x in mined}
        if expected-actual:
            raise RuntimeError(f"批次缺失article_id: {sorted(expected-actual)}")
    stage_root.mkdir(parents=True,exist_ok=True)
    payload={
        "batch_index":batch_index,"batch_count":batch_count,
        "source_date":source_date().isoformat(),
        "trade_date":target_trade_date().isoformat(),
        "sources":[public_article_metadata(a) for a in articles],
        "article_mining":mined,
    }
    path=stage_root/f"batch_{batch_index}.json"
    path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"OPINION_BATCH_STAGE_OK batch={batch_index} selected={len(selected)} analyzed={len(articles)}",flush=True)


def load_batch_stages(stage_root: Path) -> tuple[list[dict],list[dict],str,str]:
    paths=sorted(stage_root.rglob("batch_*.json"))
    if not paths:
        raise RuntimeError(f"没有找到观点批次文件: {stage_root}")
    sources_by_id={};mined_by_id={};source_days=set();trade_days=set()
    for path in paths:
        data=json.loads(path.read_text(encoding="utf-8"))
        source_days.add(str(data.get("source_date","")))
        trade_days.add(str(data.get("trade_date","")))
        for item in data.get("sources",[]) or []:
            sources_by_id[str(item.get("article_id",""))]=item
        for item in data.get("article_mining",[]) or []:
            mined_by_id[str(item.get("article_id",""))]=item
    if len(source_days)!=1 or len(trade_days)!=1:
        raise RuntimeError(f"批次日期不一致: source={sorted(source_days)} trade={sorted(trade_days)}")
    sources=[x for key,x in sources_by_id.items() if key]
    mined=[mined_by_id[key] for key in sources_by_id if key in mined_by_id]
    missing=sorted(set(sources_by_id)-set(mined_by_id))
    if missing:
        raise RuntimeError(f"汇总前缺失article_id: {missing}")
    return sources,mined,next(iter(source_days)),next(iter(trade_days))


def staged_quality_path(source_day: str) -> Path:
    return ROOT/"staging"/f"{source_day}.json"


def load_staged_quality_pool(source_day: str) -> tuple[list[dict],list[dict],str,str]:
    path=staged_quality_path(source_day)
    if not path.exists():
        return [],[],source_day,""
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError,TypeError):
        return [],[],source_day,""
    if str(data.get("source_date", ""))!=source_day:
        return [],[],source_day,""
    return (
        data.get("sources",[]) or [],data.get("article_mining",[]) or [],
        source_day,str(data.get("trade_date", "")),
    )


def merge_staged_quality_pool(source_day: str, trade_day: str,
                              sources: list[dict], mined: list[dict]) -> tuple[list[dict],list[dict]]:
    old_sources,old_mined,_,old_trade_day=load_staged_quality_pool(source_day)
    sources_by_id={str(item.get("article_id", "")):item for item in old_sources if item.get("article_id")}
    mined_by_id={str(item.get("article_id", "")):item for item in old_mined if item.get("article_id")}
    for item in sources:
        article_id=str(item.get("article_id", ""))
        if article_id:
            sources_by_id[article_id]=item
    for item in mined:
        article_id=str(item.get("article_id", ""))
        if article_id:
            mined_by_id[article_id]=item
    common=sorted(set(sources_by_id)&set(mined_by_id))
    merged_sources=[sources_by_id[key] for key in common]
    merged_mined=[mined_by_id[key] for key in common]
    path=staged_quality_path(source_day)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({
        "source_date":source_day,"trade_date":trade_day or old_trade_day,
        "updated_at_cn":now_cn().isoformat(),
        "method":"incremental AI-verified quality pool; raw article bodies not persisted",
        "sources":merged_sources,"article_mining":merged_mined,
    },ensure_ascii=False,indent=2),encoding="utf-8")
    return merged_sources,merged_mined


def delivery_path(source_day: str) -> Path:
    return ROOT/"delivery"/f"{source_day}.json"


def summary_fingerprint(data: dict) -> str:
    payload=json.dumps(data.get("daily_consensus",{}),ensure_ascii=False,sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def deliver_data(data: dict) -> bool:
    source_day=str(data.get("source_date") or data.get("trade_date") or "")
    target_day=str(data.get("trade_date") or "")
    fingerprint=summary_fingerprint(data)
    receipt_path=delivery_path(source_day)
    if receipt_path.exists():
        old=json.loads(receipt_path.read_text(encoding="utf-8"))
        if old.get("summary_sha256")==fingerprint and old.get("status") in {"delivered","request_accepted"}:
            print(f"OPINION_DELIVERY_ALREADY_DONE source_date={source_day}",flush=True)
            return False
    request_receipt=push_summary(data.get("daily_consensus",{}),source_day,target_day,data.get("sources",[]) or [])
    if request_receipt.get("accepted"):
        receipt_path.parent.mkdir(parents=True,exist_ok=True)
        receipt_path.write_text(json.dumps({
            "status":"request_accepted","delivery_confirmation":"unverified",
            "source_date":source_day,"trade_date":target_day,
            "accepted_at_cn":now_cn().isoformat(),"summary_sha256":fingerprint,
            "article_count":len(data.get("sources",[]) or []),
            "pushplus_short_code":request_receipt.get("short_code",""),
            "pushplus_message":request_receipt.get("response_message",""),
        },ensure_ascii=False,indent=2),encoding="utf-8")
    return bool(request_receipt.get("accepted"))


def apply_sample_status(summary: dict, article_count: int) -> dict:
    """Keep full aggregation fields at the deadline while clearly labelling low confidence."""
    if article_count<MIN_ARTICLE_COUNT:
        summary["sample_status"]="样本不足，基于现有合格样本的非正式摘要"
        limitations=list(summary.get("limitations", []) or [])
        note=f"当天仅取得{article_count}篇合格复盘，低于{MIN_ARTICLE_COUNT}篇正式门槛；以下仍基于现有样本归纳，置信度应降低。"
        if note not in limitations:
            limitations.insert(0,note)
        summary["limitations"]=limitations
        market=summary.setdefault("market_consensus",{})
        market["confidence"]="低"
    else:
        summary["sample_status"]="正式样本"
    return summary


def current_summary_source_urls(source_day: str) -> set[str]:
    path=ROOT/"latest.json"
    if not path.exists():
        return set()
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if str(data.get("source_date") or "")!=source_day:
        return set()
    return {str(item.get("url") or "") for item in data.get("sources",[]) if item.get("url")}


def run_aggregate_stage(key: str, stage_root: Path) -> None:
    previous_urls=current_summary_source_urls(source_date().isoformat())
    sources,mined,source_day,trade_day=load_batch_stages(stage_root)
    sources,mined,rejected=retain_ai_verified_quality(sources,mined)
    if rejected:
        print(f"OPINION_AI_QUALITY_REJECTED count={len(rejected)}",flush=True)
    sources,mined=merge_staged_quality_pool(source_day,trade_day,sources,mined)
    if not sources:
        raise RuntimeError("所有文章均未通过正文规则与OpenAI二次质量复核")
    current_urls={str(item.get("url") or "") for item in sources if item.get("url")}
    if previous_urls and current_urls==previous_urls:
        print(
            f"OPINION_NO_NEW_QUALITY_ARTICLES source_date={source_day} articles={len(sources)} "
            "aggregate_skipped=true push_skipped=true",flush=True,
        )
        return
    should_finalize,finalization_reason=opinion_finalization(len(sources))
    if not should_finalize:
        print(
            f"OPINION_WAIT_FOR_MORE source_date={source_day} quality_articles={len(sources)} "
            f"minimum={MIN_ARTICLE_COUNT} reason={finalization_reason}", flush=True,
        )
        commit(f"Update market opinion quality pool {source_day}")
        return
    client,model=build_client(key)
    summary=aggregate(client,model,mined,sources)
    summary=apply_sample_status(summary,len(sources))
    if len(sources)<MIN_ARTICLE_COUNT:
        print(
            f"OPINION_SAMPLE_INSUFFICIENT_FULL_SUMMARY articles={len(sources)} "
            f"minimum={MIN_ARTICLE_COUNT}",flush=True,
        )
    summary["finalization"]={
        "reason":finalization_reason,
        "quality_article_count":len(sources),
        "minimum_quality_articles":MIN_ARTICLE_COUNT,
        "finalized_at_cn":now_cn().isoformat(),
        "ai_quality_rejected_count":len(rejected),
    }
    summary["ths_concept_index"]=fetch_ths_concept_facts(
        summary.get("sector_consensus",[]) or [],date.fromisoformat(source_day)
    )
    save_results(sources,mined,summary)
    if os.getenv("OPINION_PUSH_AFTER_AGGREGATE","").strip().lower() in {"1","true","yes"}:
        data=json.loads((ROOT/"latest.json").read_text(encoding="utf-8"))
        deliver_data(data)
    commit()
    print(f"OPINION_AGGREGATE_STAGE_OK source_date={source_day} trade_date={trade_day} articles={len(sources)}",flush=True)


def run_delivery_stage() -> None:
    path=ROOT/"latest.json"
    if not path.exists():
        print("OPINION_DELIVERY_NOT_READY reason=latest_missing",flush=True)
        raise RuntimeError("当日市场观点摘要尚未生成")
    data=json.loads(path.read_text(encoding="utf-8"))
    if str(data.get("source_date") or data.get("trade_date"))!=source_date().isoformat():
        print(f"OPINION_DELIVERY_NOT_READY reason=stale source_date={data.get('source_date')}",flush=True)
        raise RuntimeError(f"市场观点摘要仍是旧日期: {data.get('source_date')}")
    article_count=len(data.get("sources",[]) or [])
    reason=str((data.get("finalization",{}) or {}).get("reason", ""))
    if article_count<MIN_ARTICLE_COUNT and reason!="deadline_partial":
        raise RuntimeError("高质量文章尚未达到15篇且未到22:00兜底，不得提前发送低样本摘要")
    if deliver_data(data):
        commit(f"Record market opinion delivery {data.get('source_date')}")


def run_full_stage(key: str) -> None:
    wait_until_cn("OPINION_COLLECT_NOT_BEFORE_CN")
    discovered=discover_articles()
    articles=fetch_selected_articles(discovered)
    if not articles:
        raise RuntimeError("没有取得可分析的完整公开复盘正文")
    client,model=build_client(key)
    batches=[articles[i:i+BATCH_SIZE] for i in range(0,len(articles),BATCH_SIZE)]
    mined_by_batch={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1,min(BATCH_WORKERS,len(batches)))) as executor:
        futures={executor.submit(analyze_batch,client,model,batch,number):number
                 for number,batch in enumerate(batches,1)}
        for future in concurrent.futures.as_completed(futures):
            number=futures[future]
            result=future.result()
            mined_by_batch[number]=result.get("articles",[]) or []
    mined=[item for number in sorted(mined_by_batch) for item in mined_by_batch[number]]
    expected={a["body_sha256"][:16] for a in articles}
    actual={str(x.get("article_id","")) for x in mined}
    if expected-actual:
        raise RuntimeError(f"逐篇分析缺失article_id: {sorted(expected-actual)}")
    if len(articles)<MIN_ARTICLE_COUNT:
        summary={
            "market_consensus":{"stance":"样本不足","phase":[],"confidence":"低",
                                "summary":f"当天仅取得{len(articles)}篇合格复盘，低于{MIN_ARTICLE_COUNT}篇正式门槛，不形成正式市场共识。"},
            "market_disagreements":[],"sector_consensus":[],"stock_attention":[],
            "tomorrow_consensus_watch":[],
            "limitations":["当天合格样本不足；没有使用旧文章或低质量帖子补足数量。"],
            "article_count":len(articles),"source_platform":"淘股吧公开复盘",
            "sample_status":"样本不足，非正式摘要",
        }
    else:
        summary=aggregate(client,model,mined,articles)
        summary["sample_status"]="正式样本"
    summary["ths_concept_index"]=fetch_ths_concept_facts(
        summary.get("sector_consensus",[]) or [],source_date()
    )
    save_results(articles,mined,summary)
    deliver_data(json.loads((ROOT/"latest.json").read_text(encoding="utf-8")))
    commit()
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--stage",choices=["full","discover","batch","aggregate","push"],default="full")
    parser.add_argument("--batch-index",type=int,default=0)
    parser.add_argument("--batch-count",type=int,default=5)
    parser.add_argument("--stage-root",default="opinion_stage")
    args=parser.parse_args()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if args.stage not in {"push","discover"} and not key:
        raise RuntimeError("OPENAI_API_KEY未配置，不能执行正文观点挖掘")
    if args.stage=="discover":
        run_discover_stage(Path(args.stage_root))
    elif args.stage=="batch":
        run_batch_stage(key,args.batch_index,args.batch_count,Path(args.stage_root))
    elif args.stage=="aggregate":
        run_aggregate_stage(key,Path(args.stage_root))
    elif args.stage=="push":
        run_delivery_stage()
    else:
        run_full_stage(key)


if __name__ == "__main__":
    main()
