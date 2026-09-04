from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from v5_core import (
    STRATEGY_VERSION,
    build_metrics,
    confirmation_metrics,
    fetch_market_review,
    fetch_candidate_decision_context,
    fetch_public_sector_flow,
    fetch_pool_history_incremental,
    fetch_realtime_package,
    is_trade_day,
    load_master_pool,
    maintain_master_pool,
    merge_master_pool,
    openai_analyze,
    pool_from_dataframe,
    seed_global_cache_from_old_runs,
    split_stock_and_indices,
    stage1_rank,
    stage2_rank,
    stage3_rank,
    to_excel_bytes,
)

TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path("v5_data")
OLD_ROOT = Path("v4_data")
CACHE = ROOT / "cache" / "history"
REGISTRY = ROOT / "master" / "master_registry.csv"
CURRENT_MASTER = ROOT / "master" / "current_master_pool.csv"
ELIMINATED = ROOT / "master" / "eliminated_archive.csv"
LATEST = ROOT / "latest"
MARKET_HISTORY = ROOT / "market" / "market_breadth_history.csv"


def now_cn() -> datetime:
    return datetime.now(TZ)


def save_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def save_df(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def save_json(path: Path, obj: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, default=str, indent=2), encoding="utf-8")


def load_market_opinion_context(trade_date) -> dict:
    """读取同交易日的正文挖掘衍生观点；不读取或保存第三方原文。"""
    path = Path("v5_data/opinion/latest.json")
    if not path.exists():
        return {"status": "unavailable", "reason": "当日正文观点挖掘尚未完成"}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("trade_date", "")) != str(trade_date):
            return {"status": "stale", "source_trade_date": data.get("trade_date"), "reason": "观点日期与行情日期不一致"}
        return {
            "status": "available",
            "trade_date": data.get("trade_date"),
            "article_count": len(data.get("sources", []) or []),
            "daily_consensus": data.get("daily_consensus", {}),
        }
    except Exception as exc:
        return {"status": "invalid", "reason": f"{type(exc).__name__}: {exc}"}


def pushplus_notify(title: str, content: str, template: str = "html", attempts: int = 3) -> bool:
    """通过 PushPlus 推送到普通微信；短暂故障自动重试，研究结果始终保存在GitHub。"""
    token = (os.getenv("PUSHPLUS_TOKEN") or "").strip()
    if not token:
        print("PushPlus skipped: PUSHPLUS_TOKEN not configured")
        return False
    payload = json.dumps({
        "token": token,
        "title": str(title)[:100],
        "content": str(content),
        "template": template,
        "channel": "wechat",
    }, ensure_ascii=False).encode("utf-8")
    last_error = ""
    for attempt in range(1, max(1, attempts) + 1):
        req = urllib.request.Request(
            "https://www.pushplus.plus/send",
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "AStock-V5.3"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            try:
                response_obj = json.loads(body)
                response_code = str(response_obj.get("code", ""))
                response_msg = str(response_obj.get("msg", ""))[:200]
                response_data = str(response_obj.get("data", ""))[:200]
                ok = response_code == "200"
                print(
                    f"PushPlus receipt attempt={attempt} code={response_code} "
                    f"msg={response_msg!r} data={response_data!r}"
                )
            except Exception:
                response_obj = {}
                ok = "200" in body
                print(f"PushPlus non-JSON receipt attempt={attempt}: {body[:300]}")
            if ok:
                print(f"PushPlus success on attempt {attempt}")
                return True
            last_error = f"unexpected response: {body[:300]}"
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
        print(f"PushPlus attempt {attempt} failed: {last_error}")
        if attempt < attempts:
            time.sleep(2 if attempt == 1 else 5)
    print(f"PushPlus exhausted retries: {last_error}")
    return False


def _fmt_pct(x):
    try:
        return f"{float(x):.1f}%"
    except Exception:
        return "—"


def notify_after_close_success(summary: dict, obs: pd.DataFrame, obs_meta: dict):
    ma = obs_meta.get("market_assessment", {}) or {}
    lines = [
        f"<b>目标交易日：</b>{summary.get('target_trade_date','—')}",
        f"<b>主池：</b>{summary.get('master_count','—')}只 → 一级 {summary.get('stage1','—')}只 → 研究池 {summary.get('stage2_research_pool','—')}只",
        f"<b>本次主池变动：</b>新增 {summary.get('daily_new_count',0)}｜重新激活 {summary.get('daily_reactivated_count',0)}｜新淘汰 {summary.get('daily_eliminated_count',0)}｜冷却 {summary.get('cooling_count',0)}",
        f"<b>缓存：</b>{summary.get('cache_summary',{})}",
        f"<b>OpenAI观察池：</b>{summary.get('observation_pool_count',0)}只",
        f"<b>市场风险：</b>{ma.get('risk_level','—')}｜{ma.get('next_day_aggressiveness','—')}",
    ]
    if ma.get("summary"):
        lines.append(f"<b>市场判断：</b>{ma.get('summary')}")
    feedback_path = Path("v5_data/feedback/latest_daily.json")
    if feedback_path.exists():
        try:
            fb = json.loads(feedback_path.read_text(encoding="utf-8"))
            if str(fb.get("asof", "")) == str(summary.get("generated_trade_date", summary.get("completed_cn", "")))[0:10]:
                lines.append(f"<b>推荐跟踪：</b>累计{fb.get('total_recommendations', 0)}只｜D+10完成{fb.get('completed_d10', 0)}只")
                for horizon, cohort in (fb.get("due_cohorts", {}) or {}).items():
                    for item in cohort:
                        lines.append(f"{horizon}到期：{item.get('股票代码','')} {item.get('股票名称','')}｜{item.get(horizon+'涨跌幅%','—')}%")
        except Exception as exc:
            print("feedback summary warning:", exc)
    sa = obs_meta.get("sector_assessment", {}) or {}
    sv = summary.get("sector_validation", {}) or {}
    lines.append(f"<b>板块数据：</b>{sv.get('status','—')}｜AI启用：{'是' if sv.get('ai_enabled') else '否'}")
    if sa.get("summary"):
        lines.append(f"<b>板块判断：</b>{sa.get('summary')}")
    sector_groups = ((summary.get("high_attention_sector_market", {}) or {}).get("groups", {}) or {})
    labels = [
        ("高关注且涨幅靠前", "高关注·涨幅靠前"),
        ("高关注但活跃分化", "高关注·活跃/分化"),
        ("高关注且观点退潮", "高关注·观点退潮"),
        ("高关注但行情未核验", "高关注·行情未核验"),
    ]
    for key, label in labels:
        items = sector_groups.get(key, []) or []
        if not items:
            continue
        rendered = []
        for item in items[:6]:
            pct = item.get("当日涨跌幅%")
            rank = item.get("当日涨幅排名")
            total = item.get("同类板块数")
            fact = f"；{pct:+.2f}%，排名{rank}/{total}" if isinstance(pct, (int, float)) else ""
            rendered.append(f"{item.get('板块','')}（提及{item.get('文章提及数',0)}篇；{item.get('观点状态','不明确')}{fact}）")
        lines.append(f"<b>{label}：</b>" + "、".join(rendered))
    oa = obs_meta.get("opinion_assessment", {}) or {}
    oc = obs_meta.get("opinion_context", {}) or {}
    lines.append(f"<b>正文观点层：</b>{oc.get('status','—')}｜样本 {oc.get('article_count',0)}篇")
    if oa.get("summary"):
        lines.append(f"<b>观点共识：</b>{oa.get('summary')}")
    if obs is not None and not obs.empty:
        lines.append("<br><b>次日观察池：</b>")
        for _, r in obs.sort_values("AI优先级", na_position="last").iterrows():
            code=str(r.get("股票代码","")).zfill(6); name=str(r.get("股票名称","") or "")
            pri=r.get("AI优先级","")
            ev=str(r.get("AI核心证据","") or "")
            risk=str(r.get("AI主要风险","") or "")
            lines.append(f"{pri}. <b>{code} {name}</b><br>证据：{ev}<br>风险：{risk}<br>")
    else:
        lines.append("<br><b>结论：</b>今日OpenAI未选出次日观察标的（0只）。")
    lines.append("<br><small>盘后观察池不是买入名单，需次日14:40–14:45再次确认。</small>")
    pushplus_notify("A股二次启动｜盘后研究完成", "<br>".join(lines))


def notify_tail_success(final_df: pd.DataFrame, meta: dict):
    ma=meta.get("market_assessment",{}) or {}
    selected=set(str(x).zfill(6) for x in meta.get("selected_codes",[]) or [])
    lines=[
        f"<b>交易日：</b>{meta.get('trade_date','—')}",
        f"<b>大盘评分：</b>{ma.get('overall_score_0_100','—')}/100｜{ma.get('trade_suitability','—')}",
        f"<b>实时市场：</b>{ma.get('risk_level','—')}｜相对昨收 {ma.get('change_vs_previous_close','—')}",
        f"<b>总体新仓上限：</b>{_fmt_pct(ma.get('overall_new_position_cap_pct'))}",
        f"<b>最终候选：</b>{meta.get('selected_count',0)}只",
    ]
    if ma.get("summary"): lines.append(f"<b>市场判断：</b>{ma.get('summary')}")
    sv=meta.get("sector_validation",{}) or {}; sa=meta.get("sector_assessment",{}) or {}
    lines.append(f"<b>板块数据：</b>{sv.get('status','—')}｜AI启用：{'是' if sv.get('ai_enabled') else '否'}")
    if sa.get("summary"): lines.append(f"<b>板块判断：</b>{sa.get('summary')}")
    if sa.get("active_sectors"): lines.append(f"<b>主要活跃板块：</b>{'、'.join(map(str,sa.get('active_sectors',[])[:8]))}")
    if sa.get("capital_inflow_leaders"): lines.append(f"<b>资金流入靠前板块：</b>{'、'.join(map(str,sa.get('capital_inflow_leaders',[])[:8]))}")
    if selected and final_df is not None and not final_df.empty:
        lines.append("<br><b>14:45最终结果：</b>")
        for _,r in final_df.iterrows():
            code=str(r.get("股票代码","")).zfill(6)
            if code not in selected: continue
            name=str(r.get("股票名称","") or "")
            lo=r.get("买入区间下沿"); hi=r.get("买入区间上沿"); pos=r.get("建议仓位占总资金%")
            stop=r.get("结构止损参考"); risk=r.get("结构风险距离")
            try: risk_txt=f"{float(risk)*100:.1f}%"
            except Exception: risk_txt="—"
            lines.append(f"<b>{code} {name}</b><br>买入区间：{lo}–{hi}<br>建议仓位：{_fmt_pct(pos)}｜结构止损：{stop}｜结构风险：{risk_txt}<br>证据：{r.get('核心证据','')}<br>风险：{r.get('主要风险','')}<br>")
            lines.append(f"基本面：{r.get('基本面理由','')}<br>技术面：{r.get('技术面理由','')}<br>资金面：{r.get('资金面理由','')}<br>事件面：{r.get('事件面理由','')}<br>板块：{r.get('板块理由','')}<br>")
    else:
        lines.append("<br><b>结论：</b>14:45没有符合条件的交易标的（0只）。")
    if final_df is not None and not final_df.empty:
        others=final_df[~final_df["股票代码"].astype(str).str.zfill(6).isin(selected)]
        if not others.empty:
            lines.append("<br><b>其余观察股决定：</b>")
            for _,r in others.iterrows():
                lines.append(f"{str(r.get('股票代码','')).zfill(6)} {r.get('股票名称','')}｜{r.get('decision','WAIT')}<br>依据：{r.get('核心证据','')}<br>风险：{r.get('主要风险','')}<br>")
    if meta.get("portfolio_note"): lines.append(f"<b>组合说明：</b>{meta.get('portfolio_note')}")
    lines.append("<br><small>T+1：结构止损不是最大亏损保证，隔夜跳空可能扩大实际损失。</small>")
    return pushplus_notify("A股二次启动｜14:45尾盘决策", "<br>".join(lines))


def notify_failure(stage: str, err: Exception | str):
    pushplus_notify(
        f"A股二次启动｜{stage}失败",
        f"<b>时间：</b>{now_cn().isoformat()}<br><b>错误：</b>{type(err).__name__ if isinstance(err, Exception) else 'Error'}: {str(err)}<br><br>本次失败不会被当作‘0只候选’，请检查 GitHub Actions。"
    )


def git_commit(message: str):
    """V5只在阶段完成时提交，避免V4每10只提交一次造成大量额外开销。"""
    try:
        subprocess.run(["git", "config", "user.name", "V5 Automation"], check=False)
        subprocess.run(["git", "config", "user.email", "actions@users.noreply.github.com"], check=False)
        subprocess.run(["git", "add", "v5_data"], check=False)
        diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            return
        subprocess.run(["git", "commit", "-m", message], check=False)
        subprocess.run(["git", "push"], check=False)
    except Exception as e:
        print("git commit warning:", e)


def checkpoint_factory(stage_dir: Path):
    def cp(done, total, code, lastqa):
        save_json(stage_dir / "progress.json", {
            "done": done, "total": total, "code": code,
            "updated_cn": now_cn().isoformat(), "last": lastqa,
        })
    return cp


def _read_pool(path: str | Path | None) -> pd.DataFrame:
    if not path:
        return pd.DataFrame(columns=["股票代码", "股票名称"])
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到提交文件: {p}")
    x = pd.read_csv(p, dtype=str)
    return pool_from_dataframe(x)


def _bootstrap_registry_from_v4() -> pd.DataFrame:
    """第一次升级V5时自动沿用V4最后一次大池，无需用户重新上传500只。"""
    candidates = [OLD_ROOT / "inbox" / "latest_pool.csv"]
    for p in candidates:
        if p.exists():
            raw = pd.read_csv(p, dtype={"股票代码": str})
            stocks, idx = split_stock_and_indices(raw)
            if not stocks.empty:
                today = now_cn().strftime("%Y-%m-%d")
                master = pd.DataFrame({
                    "股票代码": stocks["股票代码"],
                    "股票名称": stocks["股票名称"],
                    "首次进入日期": today,
                    "最近提交日期": today,
                    "提交次数": 1,
                    "当前状态": "活跃",
                    "淘汰日期": "",
                    "淘汰原因": "",
                })
                save_df(ROOT / "master" / "bootstrap_excluded_indices.csv", idx)
                return master
    return load_master_pool(REGISTRY)


def _cache_metrics_for_master(master: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in master.iterrows():
        code = str(r["股票代码"]).zfill(6)
        p = CACHE / f"{code}.csv"
        if not p.exists():
            continue
        try:
            d = pd.read_csv(p, parse_dates=["日期"])
            if d.empty:
                continue
            d.insert(0, "股票名称", str(r.get("股票名称", "") or ""))
            d.insert(0, "股票代码", code)
            rows.append(d)
        except Exception:
            continue
    if not rows:
        return pd.DataFrame()
    return build_metrics(pd.concat(rows, ignore_index=True, sort=False))


def _mark_master_stage(registry: pd.DataFrame, p1: pd.DataFrame, p2: pd.DataFrame) -> pd.DataFrame:
    x = registry.copy()
    active = x["当前状态"].astype(str) != "已淘汰"
    # 保留冷却标签；当天进入筛选层的覆盖成更明确状态。
    p1c = set(p1["股票代码"].astype(str)) if not p1.empty else set()
    p2c = set(p2["股票代码"].astype(str)) if not p2.empty else set()
    x.loc[active & x["股票代码"].astype(str).isin(p1c), "当前状态"] = "一级活跃"
    x.loc[active & x["股票代码"].astype(str).isin(p2c), "当前状态"] = "进入30-50只研究池"
    return x



def update_market_history(snapshot: pd.DataFrame, phase: str = "盘后", keep_days: int = 180) -> tuple[pd.DataFrame, pd.DataFrame]:
    """维护全市场日度宽度历史。真实历史从系统开始记录之日起积累，不伪造缺失日期。"""
    old=pd.DataFrame()
    if MARKET_HISTORY.exists():
        try: old=pd.read_csv(MARKET_HISTORY)
        except Exception: old=pd.DataFrame()
    cur=snapshot.copy() if snapshot is not None else pd.DataFrame()
    if not cur.empty:
        cur["记录阶段"]=phase
        cur["日期"]=cur["日期"].astype(str).str[:10]
        allx=pd.concat([old,cur],ignore_index=True,sort=False) if not old.empty else cur
        allx=allx.drop_duplicates("日期",keep="last").sort_values("日期").tail(keep_days).reset_index(drop=True)
        save_df(MARKET_HISTORY,allx)
    else:
        allx=old.sort_values("日期").tail(keep_days).reset_index(drop=True) if not old.empty else old
    if allx.empty:
        return allx,pd.DataFrame()
    z=allx.copy()
    numeric=["股票数","上涨家数","下跌家数","平盘家数","上涨比例","下跌比例","净上涨家数","涨停家数","跌停家数","涨5%以上家数","跌5%以上家数","全市场成交额"]
    for c in numeric:
        if c in z: z[c]=pd.to_numeric(z[c],errors="coerce")
    latest=z.iloc[-1]
    ctx={"日期":latest.get("日期"),"历史样本天数":len(z),"历史口径":"系统逐日真实快照滚动积累，最多180个记录日；未覆盖的过去日期不人工补造"}
    for c in ["上涨比例","下跌比例","净上涨家数","涨停家数","跌停家数","全市场成交额"]:
        if c not in z: continue
        ser=z[c].dropna()
        if ser.empty: continue
        ctx[c]=float(ser.iloc[-1])
        if len(ser)>=2:
            ctx[f"{c}_较前一日变化"]=float(ser.iloc[-1]-ser.iloc[-2])
            if c=="全市场成交额" and ser.iloc[-2] not in (0,None):
                ctx["成交额较前一日变化率"]=float(ser.iloc[-1]/ser.iloc[-2]-1)
        for w in [5,20,60]:
            tail=ser.tail(w)
            if len(tail)>=min(3,w):
                ctx[f"{c}_{w}日均值"]=float(tail.mean())
                ctx[f"{c}_{w}日分位"]=float((tail<=ser.iloc[-1]).mean())
    return z,pd.DataFrame([ctx])


def _market_sentiment_components(breadth: pd.DataFrame) -> pd.DataFrame:
    rows=[]
    if breadth is None or breadth.empty:
        return pd.DataFrame(columns=["日期","成分类型","股票代码"])
    r=breadth.iloc[0]
    mapping={
        "涨停":"涨停股池代码","跌停":"跌停股池代码","炸板":"炸板股池代码",
        "昨日涨停":"昨日涨停股池代码","强势股":"强势股池代码",
    }
    for kind,col in mapping.items():
        for code in str(r.get(col,"") or "").split("|"):
            code=code.strip()
            if code:
                rows.append({"日期":r.get("日期"),"数据时间":r.get("数据时间"),"成分类型":kind,"股票代码":code,
                             "数据源":"eastmoney_public_pool","阶段":"第一阶段影子记录"})
    return pd.DataFrame(rows)


def _market_review_sheets(indices: pd.DataFrame, breadth: pd.DataFrame, history: pd.DataFrame, context: pd.DataFrame, qa: pd.DataFrame) -> dict:
    return {"五大指数180日":indices,"市场宽度当日":breadth,"市场情绪成分影子层":_market_sentiment_components(breadth),
            "市场宽度历史180":history,"市场滚动上下文":context,"质量校验":qa}


def _json_clean(obj):
    """把 pandas/numpy 的 NaN/时间类型转成 API 可接受的标准 JSON 数据。"""
    if isinstance(obj, pd.DataFrame):
        return _json_clean(obj.to_dict("records"))
    if isinstance(obj, pd.Series):
        return _json_clean(obj.to_dict())
    if isinstance(obj, dict):
        return {str(k): _json_clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_clean(v) for v in obj]
    if pd.isna(obj) if not isinstance(obj, (str, bytes, dict, list, tuple)) else False:
        return None
    if hasattr(obj, "item"):
        try:
            return obj.item()
        except Exception:
            pass
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    return obj


def _parse_json_object(text: str) -> dict:
    text=(text or "").strip()
    if text.startswith("```"):
        text=text.strip("`").strip()
        if text.lower().startswith("json"):
            text=text[4:].strip()
    try:
        obj=json.loads(text)
        if isinstance(obj, dict): return obj
    except Exception:
        pass
    a=text.find("{"); b=text.rfind("}")
    if a>=0 and b>a:
        obj=json.loads(text[a:b+1])
        if isinstance(obj, dict): return obj
    raise ValueError("OpenAI输出不是合法JSON对象")


def next_trade_day(d):
    dates=[x for x in _trade_dates() if x>d]
    if dates:
        return dates[0]
    probe=d+timedelta(days=1)
    for _ in range(15):
        if is_trade_day(probe): return probe
        probe += timedelta(days=1)
    raise RuntimeError("无法确定下一交易日")


def _market_payload(indices: pd.DataFrame, breadth: pd.DataFrame, history: pd.DataFrame | None = None, context: pd.DataFrame | None = None) -> dict:
    idx=[]
    if indices is not None and not indices.empty:
        for name,g in indices.groupby("指数名称", sort=False):
            g=g.sort_values("日期").copy()
            c=pd.to_numeric(g.get("收盘价"),errors="coerce")
            last=float(c.iloc[-1]) if len(c) and pd.notna(c.iloc[-1]) else None
            def r(n):
                if len(c)>n and pd.notna(c.iloc[-n-1]) and c.iloc[-n-1]!=0:
                    return float(c.iloc[-1]/c.iloc[-n-1]-1)
                return None
            idx.append({"指数名称":name,"最新收盘":last,"ret5":r(5),"ret20":r(20),"ret60":r(60),"最新日期":str(g["日期"].iloc[-1])[:10]})
    br=[]
    if breadth is not None and not breadth.empty:
        # 第一阶段新增的市场情绪字段先影子运行，不送入OpenAI，待连续验收后再正式启用。
        approved=[x for x in ["日期","数据时间","数据源","快照数据源","股票数","上涨家数","下跌家数","平盘家数",
                              "上涨比例","下跌比例","净上涨家数","涨停家数","跌停家数","涨5%以上家数",
                              "跌5%以上家数","全市场成交额","市场宽度是否降级","涨跌停是否降级"] if x in breadth.columns]
        br=breadth[approved].to_dict("records")
    hist=[]
    if history is not None and not history.empty:
        cols=[c for c in ["日期","上涨家数","下跌家数","平盘家数","上涨比例","下跌比例","净上涨家数","涨停家数","跌停家数","全市场成交额","记录阶段"] if c in history.columns]
        hist=history[cols].tail(60).to_dict("records")
    ctx=context.to_dict("records") if context is not None and not context.empty else []
    return _json_clean({"指数摘要":idx,"市场宽度当日":br,"市场宽度历史最近60记录日":hist,"市场滚动上下文":ctx})


def _sector_payload(sector_tables: dict[str,pd.DataFrame] | None) -> dict:
    """只向AI提供轻量榜单；板块资金是增强证据，不替代个股结构。"""
    out={}
    for key,df in (sector_tables or {}).items():
        if df is None or df.empty:
            continue
        pct_col="行业-涨跌幅" if "行业-涨跌幅" in df else "阶段涨跌幅" if "阶段涨跌幅" in df else None
        cols=[c for c in ["行业","板块类型","周期",pct_col,"净额","公司家数","交易日期","资金单位"] if c and c in df]
        leaders=df.sort_values(pct_col,ascending=False).head(15)[cols] if pct_col else df.head(15)[cols]
        net=df.sort_values("净额",ascending=False).head(15)[cols] if "净额" in df else pd.DataFrame()
        out[key]={"涨幅前15":leaders.to_dict("records"),"净流入前15":net.to_dict("records")}
    return _json_clean(out)


def _attention_sector_market_groups(sector_tables: dict[str, pd.DataFrame] | None, opinion_context: dict | None) -> dict:
    """在高关注板块内部交叉标注客观涨幅与观点阶段，避免把热度等同于强势。"""
    consensus = (((opinion_context or {}).get("daily_consensus", {}) or {}).get("sector_consensus", []) or [])
    ranked_attention = sorted(
        [x for x in consensus if str(x.get("sector", "")).strip()],
        key=lambda x: int(x.get("mention_count", 0) or 0),
        reverse=True,
    )[:10]
    facts = {}
    for key in ["concept_now", "industry_now"]:
        frame = (sector_tables or {}).get(key)
        if frame is None or frame.empty or "行业" not in frame:
            continue
        pct_col = "行业-涨跌幅" if "行业-涨跌幅" in frame else "阶段涨跌幅" if "阶段涨跌幅" in frame else None
        if pct_col is None:
            continue
        x = frame.copy()
        x[pct_col] = pd.to_numeric(x[pct_col], errors="coerce")
        x = x.dropna(subset=[pct_col]).sort_values(pct_col, ascending=False).reset_index(drop=True)
        total = max(1, len(x))
        for i, row in x.iterrows():
            name = str(row.get("行业", "")).strip()
            if not name:
                continue
            facts[name] = {
                "板块类型": row.get("板块类型", ""),
                "当日涨跌幅%": round(float(row[pct_col]), 4),
                "当日涨幅排名": int(i + 1),
                "同类板块数": total,
                "净额亿元": _json_clean(row.get("净额")) if "净额" in row else None,
            }
    groups = {"高关注且涨幅靠前": [], "高关注但活跃分化": [], "高关注且观点退潮": [], "高关注但行情未核验": []}
    for item in ranked_attention:
        name = str(item.get("sector", "")).strip()
        stance = str(item.get("stance", "") or "不明确")
        fact = facts.get(name)
        row = {
            "板块": name, "文章提及数": int(item.get("mention_count", 0) or 0),
            "观点状态": stance, **(fact or {}),
        }
        if any(k in stance for k in ["退潮", "走弱", "弱化", "冰点"]):
            bucket = "高关注且观点退潮"
        elif fact and fact["当日涨跌幅%"] > 0 and fact["当日涨幅排名"] / fact["同类板块数"] <= 0.25:
            bucket = "高关注且涨幅靠前"
        elif fact:
            bucket = "高关注但活跃分化"
        else:
            bucket = "高关注但行情未核验"
        groups[bucket].append(row)
    return {
        "status": "available" if ranked_attention else "unavailable",
        "groups": groups,
        "method": "高关注=文章提及次数；涨幅靠前=同类即时涨幅前25%且上涨；退潮=正文观点共识。两类证据分开显示。",
    }


def _stock_sector_attribution_payload(candidates: pd.DataFrame) -> dict:
    """逐股加载一股多概念与主导板块候选；保留快照日期和时点限制供AI审计。"""
    path = Path("v5_data/stock_sector_attribution/latest.csv")
    if not path.exists() or candidates is None or candidates.empty:
        return {"status": "unavailable", "stocks": []}
    try:
        frame = pd.read_csv(path, dtype={"股票代码": str})
        frame["股票代码"] = frame["股票代码"].astype(str).str.zfill(6)
        allowed = set(candidates["股票代码"].astype(str).str.zfill(6))
        frame = frame[frame["股票代码"].isin(allowed)]
        rows = []
        for code, group in frame.groupby("股票代码", sort=False):
            ranked = group.sort_values("归因得分", ascending=False)
            primary = ranked.iloc[0]
            concepts = ranked.loc[ranked["板块类型"].astype(str) == "概念", "板块名称"].astype(str).tolist()
            rows.append({
                "股票代码": code, "股票名称": primary.get("股票名称", ""),
                "主导板块候选": primary.get("板块名称", ""),
                "全部概念": list(dict.fromkeys(concepts)),
                "归因得分": primary.get("归因得分"), "归因证据": primary.get("归因证据", ""),
                "快照日期": primary.get("快照日期", ""), "强势观察日期": primary.get("强势观察日期", ""),
                "时点一致": primary.get("时点一致", False), "时点限制": primary.get("时点限制", ""),
            })
        return {
            "status": "available" if rows else "unavailable", "stocks": _json_clean(rows),
            "method": "板块成分×同日行情/资金×正文观点；是关联归因，不是确定因果",
        }
    except Exception as exc:
        return {"status": "invalid", "error": f"{type(exc).__name__}: {exc}", "stocks": []}


def run_openai_after_close(research_pack: pd.DataFrame, indices: pd.DataFrame, breadth: pd.DataFrame, market_history: pd.DataFrame, market_context: pd.DataFrame, base: Path, generated_trade_date, source_summary: dict, sector_tables: dict[str,pd.DataFrame] | None = None) -> tuple[pd.DataFrame, dict, dict]:
    """30 -> 0~10。严格验证代码集合、数量和日期，失败时绝不留下旧观察池冒充新结果。"""
    LATEST.mkdir(parents=True, exist_ok=True)
    for stale in [LATEST/"observation_pool.csv", LATEST/"observation_pool_meta.json", LATEST/"observation_pool_analysis.json"]:
        try:
            if stale.exists(): stale.unlink()
        except Exception:
            pass
    if research_pack is None or research_pack.empty:
        raise RuntimeError("30只研究包为空，不能调用OpenAI。")
    allowed={str(x).zfill(6) for x in research_pack["股票代码"].astype(str)}
    target=next_trade_day(generated_trade_date)
    schema={
        "market_assessment": {"risk_level":"低/中/高", "summary":"基于输入市场数据的简洁判断", "next_day_aggressiveness":"偏防守/中性/偏积极"},
        "sector_assessment": {"status":"正式可用/实验性未启用", "summary":"板块环境判断；无正式数据时明确写未启用"},
        "opinion_assessment": {"status":"可用/未启用", "summary":"公开复盘正文挖掘形成的市场与板块观点共识；明确其不是行情事实"},
        "selected_codes":["最多10个、必须来自输入30只的6位股票代码"],
        "decisions":[{
            "股票代码":"6位代码","股票名称":"输入名称","decision":"SELECT/WAIT/REJECT",
            "priority":1,"evidence":"最关键的2-4项输入证据","risk":"主要风险","next_day_watch":"次日14:40-14:45需要确认什么"
        }],
        "portfolio_note":"只描述观察池层面的风险偏好，不给最终买入仓位"
    }
    opinion_context = load_market_opinion_context(generated_trade_date)
    payload={
        "generated_trade_date":str(generated_trade_date),
        "target_trade_date":str(target),
        "candidate_count":int(len(research_pack)),
        "candidates":_json_clean(research_pack.to_dict("records")),
        "market":_market_payload(indices,breadth,market_history,market_context),
        "sector_data_status":"正式可用" if sector_tables else "实验性未启用",
        "sector_fund_flow_enhancement":_sector_payload(sector_tables),
        "candidate_stock_sector_attribution":_stock_sector_attribution_payload(research_pack),
        "market_opinion_text_mining":_json_clean(opinion_context),
        "hard_constraints":[
            "selected_codes只能来自candidates，最多10只，可以0只",
            "decisions应覆盖全部输入候选；SELECT必须与selected_codes一致",
            "本阶段只形成次日观察池，不得声称已经出现14:45买点",
            "长期下降趋势修复是重要降级证据；40日加速过大是风险提示而非固定一票否决",
            "不要把固定MA距离、固定量缩、固定距20日高点、累计涨幅直接当硬规则",
            "板块/题材/资金只作为增强证据，不能替代个股结构，也不能单独生成候选",
            "sector_data_status为实验性未启用时，不得臆测板块结论，sector_assessment必须明确数据未启用",
            "market_opinion_text_mining只是公开复盘正文的聚合观点，不是行情事实；可作风险提醒和共识/分歧证据，不得单独生成候选",
            "若证据不足，宁可WAIT/REJECT，不要凑数"
        ],
        "required_output_schema":schema,
    }
    raw=openai_analyze("盘后30→0~10次日观察池", payload)
    result=_parse_json_object(raw)
    selected=[str(x).zfill(6) for x in result.get("selected_codes",[]) if str(x).strip()]
    if len(selected)!=len(set(selected)):
        raise ValueError("OpenAI selected_codes存在重复代码")
    if len(selected)>10:
        raise ValueError(f"OpenAI选择了{len(selected)}只，超过10只上限")
    bad=[x for x in selected if x not in allowed]
    if bad:
        raise ValueError(f"OpenAI选择了输入30只之外的代码: {bad}")
    decisions=result.get("decisions",[])
    if not isinstance(decisions,list):
        raise ValueError("OpenAI decisions不是数组")
    decision_by_code={}
    for d in decisions:
        if not isinstance(d,dict): continue
        code=str(d.get("股票代码","")).zfill(6)
        if code in allowed: decision_by_code[code]=d
    missing=sorted(allowed-set(decision_by_code))
    if missing:
        raise ValueError(f"OpenAI decisions未覆盖全部30只，缺少{len(missing)}只: {missing[:8]}")
    for code in selected:
        if str(decision_by_code[code].get("decision","")).upper()!="SELECT":
            raise ValueError(f"selected_codes与decisions不一致: {code}不是SELECT")
    # 观察池保留原始量化证据 + AI判断，便于次日尾盘继续分析。
    rows=[]
    base_map={str(r["股票代码"]).zfill(6):r for r in research_pack.to_dict("records")}
    for code in selected:
        r=dict(base_map[code]); d=decision_by_code[code]
        r.update({
            "AI优先级":d.get("priority"),"AI核心证据":d.get("evidence",""),"AI主要风险":d.get("risk",""),
            "次日尾盘观察重点":d.get("next_day_watch",""),
        })
        rows.append(r)
    obs=pd.DataFrame(rows) if rows else research_pack.head(0).copy()
    for c in ["AI优先级","AI核心证据","AI主要风险","次日尾盘观察重点"]:
        if c not in obs.columns: obs[c]=pd.Series(dtype="object")
    if not obs.empty and "AI优先级" in obs.columns:
        obs=obs.sort_values("AI优先级",na_position="last").reset_index(drop=True)
    model=os.getenv("OPENAI_MODEL") or "gpt-5.6-terra"
    meta={
        "status":"valid","generated_trade_date":str(generated_trade_date),"target_trade_date":str(target),
        "generated_at_cn":now_cn().isoformat(),"source_candidate_count":len(research_pack),"observation_count":len(obs),
        "model":model,"strategy":STRATEGY_VERSION,"source_run":source_summary.get("folder",""),
        "market_assessment":result.get("market_assessment",{}),"sector_assessment":result.get("sector_assessment",{}),
        "opinion_assessment":result.get("opinion_assessment",{}),"opinion_context":opinion_context,
        "portfolio_note":result.get("portfolio_note",""),
        "rule":"仅供次日14:40-14:45尾盘确认；不是盘后直接买入名单",
    }
    save_df(base/"ai"/"observation_pool.csv",obs)
    save_json(base/"ai"/"observation_pool_meta.json",meta)
    save_json(base/"ai"/"observation_pool_analysis.json",result)
    (base/"ai"/"openai_raw.txt").write_text(raw,encoding="utf-8")
    save_df(LATEST/"observation_pool.csv",obs)
    save_json(LATEST/"observation_pool_meta.json",meta)
    save_json(LATEST/"observation_pool_analysis.json",result)
    return obs,meta,result

def run_after_close(batch_path: str | None):
    started = now_cn()
    stamp = started.strftime("%Y%m%d_%H%M%S")
    base = ROOT / "runs" / stamp
    base.mkdir(parents=True, exist_ok=True)

    seed_info = seed_global_cache_from_old_runs(OLD_ROOT, CACHE)
    registry = load_master_pool(REGISTRY)
    bootstrapped = False
    if registry.empty:
        registry = _bootstrap_registry_from_v4()
        bootstrapped = not registry.empty

    daily = _read_pool(batch_path)
    registry, changes = merge_master_pool(registry, daily, asof=started.date())
    # split_stock_and_indices再次保证注册表中不遗留明确指数。
    active_input = registry[registry["当前状态"].astype(str) != "已淘汰"][["股票代码", "股票名称"]]
    active_input, registry_indices = split_stock_and_indices(active_input)
    if not registry_indices.empty:
        bad_codes = set(registry_indices["股票代码"].astype(str))
        registry = registry[~registry["股票代码"].astype(str).isin(bad_codes)].reset_index(drop=True)
        save_df(base / "隔离指数.csv", registry_indices)

    meta = {
        "status": "running", "engine": "V5.3-auditable-market-sector-layer", "strategy": STRATEGY_VERSION,
        "started_cn": started.isoformat(), "batch_count": len(daily),
        "master_before_screen": len(active_input), "bootstrapped_from_v4": bootstrapped,
        "cache_seed": seed_info,
    }
    save_json(base / "meta.json", meta)
    save_df(base / "每日提交变动.csv", changes)

    # 一级：全当前主池，25日宽筛。
    d25, q25 = fetch_pool_history_incremental(active_input, 25, CACHE, checkpoint_factory(base / "25d"))
    m25 = build_metrics(d25)
    s1, a1 = stage1_rank(m25, 150, 200, return_audit=True)
    p1 = s1[["股票代码", "股票名称"]].copy()
    save_df(base / "25d" / "pool_150_200.csv", p1)
    save_df(base / "25d" / "pool_150.csv", p1)  # 兼容旧前端/历史工具
    save_df(base / "25d" / "stage_audit.csv", a1)
    save_bytes(base / "25d" / "result.xlsx", to_excel_bytes({"25日日线": d25, "质量校验": q25, "粗筛指标": m25, "筛选审计": a1, "一级结果": s1}))
    git_commit(f"V5 after-close 25d {stamp}")

    # 二级：150 -> 30。
    d120, q120 = fetch_pool_history_incremental(p1, 120, CACHE, checkpoint_factory(base / "120d"))
    m120 = build_metrics(d120)
    s2, a2 = stage2_rank(m120, 30, 50, return_audit=True)
    p2 = s2[["股票代码", "股票名称"]].copy()
    save_df(base / "120d" / "research_pool_30_50.csv", p2)
    save_df(base / "120d" / "research_pool_30.csv", p2)  # 兼容旧前端/历史工具
    save_df(base / "120d" / "stage_audit.csv", a2)
    save_bytes(base / "120d" / "result.xlsx", to_excel_bytes({"120日日线": d120, "质量校验": q120, "结构指标": m120, "筛选审计": a2, "二级30-50只": s2}))
    git_commit(f"V5 after-close 120d {stamp}")

    # 三级：只给这30-50只补250日生命周期档案；不再由Python截前10。
    d250, q250 = fetch_pool_history_incremental(p2, 250, CACHE, checkpoint_factory(base / "250d"))
    m250 = build_metrics(d250)
    if not s2.empty and "阶段2分" in s2.columns:
        m250 = m250.merge(s2[["股票代码", "阶段2分"]], on="股票代码", how="left")
    _, lifecycle_audit = stage3_rank(m250, max(1, len(m250)), return_audit=True)
    # research_pack保留全部30只，即便生命周期层认为某只应降级，也作为AI后续的排除证据，而不是Python提前丢掉。
    research_pack = p2.merge(lifecycle_audit, on=["股票代码", "股票名称"], how="left")
    save_df(base / "250d" / "research_pack_30_40.csv", research_pack)
    save_df(base / "250d" / "lifecycle_audit.csv", lifecycle_audit)
    save_bytes(base / "250d" / "result.xlsx", to_excel_bytes({"250日日线": d250, "质量校验": q250, "生命周期指标": m250, "生命周期审计": lifecycle_audit, "AI研究输入30-50只": research_pack}))

    # 主池维护：仅自动淘汰“较久未再次提交 + 趋势同步转弱”；淘汰可被以后再次提交重新激活。
    cache_metrics = _cache_metrics_for_master(registry)
    registry, maintenance_audit = maintain_master_pool(registry, cache_metrics, asof=started.date())
    registry = _mark_master_stage(registry, p1, p2)
    current = registry[registry["当前状态"].astype(str) != "已淘汰"].copy().reset_index(drop=True)
    eliminated = registry[registry["当前状态"].astype(str) == "已淘汰"].copy().reset_index(drop=True)
    save_df(REGISTRY, registry)
    save_df(CURRENT_MASTER, current)
    save_df(ELIMINATED, eliminated)
    save_df(base / "master_maintenance_audit.csv", maintenance_audit)

    # 盘后市场层：指数直接保留180日；全市场宽度从系统运行日起逐日积累真实快照，最多180记录日。
    idx, breadth, market_qa = fetch_market_review(180)
    sector_tables, sector_qa = fetch_public_sector_flow(fetched_at=started)
    sector_failures = int((sector_qa.get("状态") == "失败").sum()) if not sector_qa.empty else 0
    sector_warnings = int((sector_qa.get("状态") == "警告").sum()) if not sector_qa.empty else 0
    sector_formal_ready = len(sector_tables) == 10 and sector_failures == 0 and sector_warnings == 0
    # 板块层有任何警告时仍保存完整审计文件，但不送入AI，避免实验性数据被误当正式证据。
    sector_tables_for_ai = sector_tables if sector_formal_ready else {}
    sector_validation = {
        "status": "正式可用" if sector_formal_ready else "实验性有警告",
        "table_count": len(sector_tables),
        "failure_count": sector_failures,
        "warning_count": sector_warnings,
        "ai_enabled": sector_formal_ready,
    }
    market_history, market_context = update_market_history(breadth, phase="盘后", keep_days=180)
    market_sheets=_market_review_sheets(idx,breadth,market_history,market_context,market_qa)
    sector_sheets={**sector_tables,"板块质量校验":sector_qa}
    save_bytes(base / "market_review.xlsx", to_excel_bytes(market_sheets))
    save_bytes(base / "sector_fund_flow.xlsx", to_excel_bytes(sector_sheets))

    LATEST.mkdir(parents=True, exist_ok=True)
    save_df(LATEST / "research_pool_30_50.csv", research_pack)
    save_df(LATEST / "research_pool_30.csv", research_pack)  # 兼容前端
    save_df(LATEST / "current_master_pool.csv", current)
    save_bytes(LATEST / "market_review.xlsx", to_excel_bytes(market_sheets))
    save_bytes(LATEST / "sector_fund_flow.xlsx", to_excel_bytes(sector_sheets))
    # 先持久化全部客观数据，再调用API；即使API报错，研究数据也不会丢。
    git_commit(f"V5.3 data ready before AI {stamp}")

    if d250.empty or "日期" not in d250.columns:
        raise RuntimeError("250日数据缺少日期，无法确定观察池生成交易日。")
    generated_trade_date = pd.to_datetime(d250["日期"], errors="coerce").max().date()
    pre_summary={"folder":str(base)}
    try:
        obs, obs_meta, ai_result = run_openai_after_close(
            research_pack, idx, breadth, market_history, market_context, base, generated_trade_date, pre_summary, sector_tables_for_ai
        )
    except Exception as e:
        err={
            "status":"ai_failed","engine":"V5.3-auditable-market-sector-layer","strategy":STRATEGY_VERSION,
            "time_cn":now_cn().isoformat(),"error_type":type(e).__name__,"error":str(e),
            "generated_trade_date":str(generated_trade_date),"source_candidate_count":len(research_pack),
            "rule":"AI失败时不生成观察池，也不保留旧观察池。"
        }
        save_json(base/"ai"/"ai_error.json",err)
        save_json(LATEST/"latest_ai_error.json",err)
        fail_summary={
            "status":"completed_ai_failed","engine":"V5.3-auditable-market-sector-layer","strategy":STRATEGY_VERSION,
            "started_cn":started.isoformat(),"completed_cn":now_cn().isoformat(),"batch_count":len(daily),
            "master_count":len(current),"eliminated_count":len(eliminated),"stage1":len(p1),"stage2_research_pool":len(p2),
            "observation_pool_count":0,"ai_error":str(e),"sector_validation":sector_validation,"folder":str(base)
        }
        save_json(base/"summary.json",fail_summary); save_json(LATEST/"latest_after_close.json",fail_summary)
        meta.update(fail_summary); save_json(base/"meta.json",meta)
        git_commit(f"V5.3 AI failed {stamp}")
        notify_failure("盘后OpenAI研究", e)
        raise

    change_kind = changes.get("变动", pd.Series(dtype=str)).astype(str) if not changes.empty else pd.Series(dtype=str)
    daily_new_count = int((change_kind == "新增").sum())
    daily_reactivated_count = int((change_kind == "重新激活").sum())
    daily_eliminated_count = int((maintenance_audit.get("淘汰日期", pd.Series(dtype=str)).astype(str) == str(started.date())).sum()) if not maintenance_audit.empty else 0
    cooling_count = int((registry["当前状态"].astype(str) == "冷却观察").sum()) if not registry.empty else 0
    cache_summary = {}
    for label, q in [("25日", q25), ("120日", q120), ("250日", q250)]:
        modes = q.get("缓存模式", pd.Series(dtype=str)).fillna("").astype(str) if not q.empty else pd.Series(dtype=str)
        cache_summary[label] = {
            "命中或增量": int(modes.str.contains("cache|increment", case=False, regex=True).sum()),
            "总数": int(len(q)),
        }

    completed = now_cn()
    summary = {
        "status": "completed", "engine": "V5.3-auditable-market-sector-layer", "strategy": STRATEGY_VERSION,
        "started_cn": started.isoformat(), "completed_cn": completed.isoformat(),
        "elapsed_minutes": round((completed - started).total_seconds() / 60, 2),
        "batch_count": len(daily), "master_count": len(current), "eliminated_count": len(eliminated),
        "daily_new_count": daily_new_count, "daily_reactivated_count": daily_reactivated_count,
        "daily_eliminated_count": daily_eliminated_count, "cooling_count": cooling_count,
        "master_pool_capacity_note": "动态证据池；不按固定500只硬砍，按长期未提交且趋势同步转弱可逆淘汰",
        "cache_summary": cache_summary,
        "stage1": len(p1), "stage2_research_pool": len(p2),
        "python_final": "30-50只软容量研究包（不机械生成前10）",
        "observation_pool_count": len(obs), "target_trade_date": obs_meta.get("target_trade_date"),
        "openai_model": obs_meta.get("model"), "market_assessment": obs_meta.get("market_assessment",{}),
        "sector_validation": sector_validation,
        "high_attention_sector_market": _attention_sector_market_groups(
            sector_tables_for_ai, obs_meta.get("opinion_context", {})
        ),
        "stock_qa_25_success": int((q25.get("状态") == "成功").sum()) if not q25.empty else 0,
        "stock_qa_120_success": int((q120.get("状态") == "成功").sum()) if not q120.empty else 0,
        "stock_qa_250_success": int((q250.get("状态") == "成功").sum()) if not q250.empty else 0,
        "isolated_index_count": len(registry_indices), "cache_seed": seed_info,
        "folder": str(base),
        "next_step": "次日14:40读取带日期锁的0~10只观察池，14:45再做最终0~5确认",
    }
    save_json(base / "summary.json", summary)
    save_json(LATEST / "latest_after_close.json", summary)
    meta.update(summary); save_json(base / "meta.json", meta)
    git_commit(f"V5.3 after-close + AI completed {stamp}")
    notify_after_close_success(summary, obs, obs_meta)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _trade_dates() -> list:
    try:
        import akshare as ak
        cal = ak.tool_trade_date_hist_sina()
        dates = sorted(pd.to_datetime(cal[cal.columns[0]], errors="coerce").dt.date.dropna().unique())
        return dates
    except Exception:
        today = now_cn().date()
        return [today - timedelta(days=i) for i in range(400) if (today - timedelta(days=i)).weekday() < 5][::-1]


def previous_trade_day(d):
    dates = [x for x in _trade_dates() if x < d]
    return dates[-1] if dates else None


def wait_until_cn(hour: int, minute: int):
    now = now_cn(); target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < target:
        sec = (target - now).total_seconds()
        print(f"Waiting {sec:.0f}s until {hour:02d}:{minute:02d} China time...")
        time.sleep(sec)


def run_openai_tail(pool: pd.DataFrame, snap40: pd.DataFrame, snap45: pd.DataFrame, minute45: pd.DataFrame,
                    conf: pd.DataFrame, indices: pd.DataFrame, breadth: pd.DataFrame,
                    market_history: pd.DataFrame, market_context: pd.DataFrame,
                    obs_meta: dict, base: Path, sector_tables: dict[str,pd.DataFrame] | None = None,
                    sector_validation: dict | None = None,
                    candidate_context: dict | None = None, candidate_context_qa: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """14:45：观察池 -> 0~5，输出买入区间/仓位/结构止损；严格验证且允许0只。"""
    allowed={str(x).zfill(6) for x in pool["股票代码"].astype(str)}
    if not allowed: raise RuntimeError("尾盘观察池为空")
    merged=pool.copy(); merged["股票代码"]=merged["股票代码"].astype(str).str.zfill(6)
    for df,suffix in [(snap40,"_1440"),(snap45,"_1445"),(conf,"_确认")]:
        if df is None or df.empty: continue
        x=df.copy(); x["股票代码"]=x["股票代码"].astype(str).str.zfill(6)
        cols=[c for c in x.columns if c not in ["股票名称"]]
        merged=merged.merge(x[cols],on="股票代码",how="left",suffixes=("",suffix))
    schema={
        "market_assessment":{"overall_score_0_100":0,"trade_suitability":"适合/谨慎/不适合","risk_level":"低/中/高","change_vs_previous_close":"改善/接近/恶化","summary":"实时市场判断","overall_new_position_cap_pct":0},
        "sector_assessment":{"status":"正式可用/实验性未启用","active_sectors":["活跃板块及强弱状态"],"capital_inflow_leaders":["资金净流入靠前板块"],"summary":"14:45板块环境判断；无正式数据时明确写未启用"},
        "selected_codes":["最多5个，必须来自观察池；可以为空"],
        "decisions":[{"股票代码":"6位代码","decision":"TRADE/WAIT/REJECT","buy_zone_low":0,"buy_zone_high":0,"position_pct_total_capital":0,"structure_stop_price":0,"fundamental_reason":"基本面与行业定位","technical_reason":"技术结构","capital_reason":"实时及近10日资金","event_reason":"事件驱动；没有则写无明确事件","sector_reason":"所属板块及强弱","evidence":"综合证据","risk":"主要风险"}],
        "portfolio_note":"组合与T+1风险说明"
    }
    payload={
        "trade_date":str(now_cn().date()),"source_observation_meta":_json_clean(obs_meta),
        "observation_candidates":_json_clean(merged.to_dict("records")),
        "market":_market_payload(indices,breadth,market_history,market_context),
        "sector_validation":_json_clean(sector_validation or {}),
        "sector_fund_flow_enhancement":_sector_payload(sector_tables),
        "candidate_stock_sector_attribution":_stock_sector_attribution_payload(pool),
        "candidate_fundamental_capital_event_context":_json_clean(candidate_context or {}),
        "candidate_context_quality":_json_clean(candidate_context_qa.to_dict("records")) if candidate_context_qa is not None else [],
        "hard_constraints":[
            "selected_codes最多5只且只能来自观察池，可以0只，不得凑数",
            "decisions必须覆盖全部观察池；selected_codes对应decision必须为TRADE",
            "market_assessment.overall_new_position_cap_pct范围0-100；所有TRADE仓位合计不得超过该上限",
            "买入区间必须基于14:40-14:45输入价格与结构证据；不得使用输入之外行情",
            "结构止损是结构参考，不是保证最大亏损；A股T+1下当日买入不可卖出，隔夜跳空可能扩大损失",
            "若实时市场恶化、个股重新加速不足/过度、结构破坏或证据冲突，允许WAIT/REJECT",
            "不得仅凭机械确认分做最终决定；确认分只是辅助字段",
            "板块数据只作增强证据；sector_validation.ai_enabled不为true时不得臆测板块结论",
            "基本面、资金面、事件面或个股板块映射缺失时必须明确写未核验，不得用常识补全；TRADE必须分别给出基本面、技术面、资金面、事件面和板块证据"
        ],"required_output_schema":schema
    }
    raw=openai_analyze("14:45尾盘0-5最终确认",payload)
    result=_parse_json_object(raw)
    selected=[str(x).zfill(6) for x in result.get("selected_codes",[]) if str(x).strip()]
    if len(selected)!=len(set(selected)) or len(selected)>5: raise ValueError("尾盘selected_codes重复或超过5只")
    bad=[x for x in selected if x not in allowed]
    if bad: raise ValueError(f"尾盘选择了观察池之外代码: {bad}")
    decisions=result.get("decisions",[])
    if not isinstance(decisions,list): raise ValueError("尾盘decisions不是数组")
    dm={str(d.get("股票代码","")).zfill(6):d for d in decisions if isinstance(d,dict)}
    missing=sorted(allowed-set(dm));
    if missing: raise ValueError(f"尾盘decisions未覆盖全部观察池: {missing}")
    ma=result.get("market_assessment",{}) or {}
    try: market_score=float(ma.get("overall_score_0_100",0) or 0)
    except Exception: raise ValueError("大盘评分不是数字")
    if not 0<=market_score<=100: raise ValueError("大盘评分必须0-100")
    try: cap=float(ma.get("overall_new_position_cap_pct",0) or 0)
    except Exception: raise ValueError("总体新开仓上限不是数字")
    if not 0<=cap<=100: raise ValueError("总体新开仓上限必须0-100")
    rows=[]; total_pos=0.0
    name_map={str(r["股票代码"]).zfill(6):str(r.get("股票名称","") or "") for r in pool.to_dict("records")}
    for code in allowed:
        d=dm[code]; dec=str(d.get("decision","")).upper()
        if code in selected and dec!="TRADE": raise ValueError(f"{code}被selected但decision不是TRADE")
        pos=float(d.get("position_pct_total_capital",0) or 0)
        if pos<0 or pos>100: raise ValueError(f"{code}仓位非法")
        if dec=="TRADE": total_pos += pos
        low=float(d.get("buy_zone_low",0) or 0); high=float(d.get("buy_zone_high",0) or 0); stop=float(d.get("structure_stop_price",0) or 0)
        risk=None
        if dec=="TRADE":
            if low<=0 or high<=0 or low>high: raise ValueError(f"{code}买入区间非法")
            if stop<=0 or stop>=high: raise ValueError(f"{code}结构止损非法")
            mid=(low+high)/2; risk=(mid-stop)/mid if mid>0 else None
        if dec=="TRADE":
            required_reasons=["fundamental_reason","technical_reason","capital_reason","event_reason","sector_reason"]
            empty_reasons=[key for key in required_reasons if not str(d.get(key,"")).strip()]
            if empty_reasons: raise ValueError(f"{code}缺少多维下单理由: {empty_reasons}")
        rows.append({"股票代码":code,"股票名称":name_map.get(code,""),"decision":dec,"买入区间下沿":low if low else None,"买入区间上沿":high if high else None,
                     "建议仓位占总资金%":pos,"结构止损参考":stop if stop else None,"结构风险距离":risk,"核心证据":d.get("evidence",""),"主要风险":d.get("risk","")})
        rows[-1].update({"基本面理由":d.get("fundamental_reason",""),"技术面理由":d.get("technical_reason",""),
                         "资金面理由":d.get("capital_reason",""),"事件面理由":d.get("event_reason",""),"板块理由":d.get("sector_reason","")})
    if total_pos > cap + 1e-6: raise ValueError(f"TRADE仓位合计{total_pos:.2f}%超过总体上限{cap:.2f}%")
    out=pd.DataFrame(rows)
    meta={"status":"valid","trade_date":str(now_cn().date()),"generated_at_cn":now_cn().isoformat(),"selected_codes":selected,"selected_count":len(selected),
          "market_assessment":ma,"sector_assessment":result.get("sector_assessment",{}),
          "sector_validation":sector_validation or {},"portfolio_note":result.get("portfolio_note",""),"model":os.getenv("OPENAI_MODEL") or "gpt-5.6-terra",
          "t1_note":"结构止损不是保证最大亏损；当日买入不可卖出，隔夜跳空可能扩大损失。"}
    save_df(base/"final_decisions.csv",out); save_json(base/"final_decision_meta.json",meta)
    (base/"openai_tail_raw.txt").write_text(raw,encoding="utf-8")
    save_df(LATEST/"final_decisions.csv",out); save_json(LATEST/"final_decision_meta.json",meta)
    return out,meta


def run_tail():
    """安全的14:40/14:45尾盘确认：严格日期锁 + 实时/5分钟 + 市场历史上下文 + OpenAI 0~5。"""
    now0 = now_cn()
    today = now0.date()
    if not is_trade_day(today):
        print("Not a China A-share trading day; skip."); return
    # GitHub cron可能排队。过晚时绝不能用收盘后数据冒充14:45状态；过早手动误触发也不让Runner长时间空等。
    minutes_now = now0.hour * 60 + now0.minute
    if minutes_now < 14 * 60 + 25:
        print(f"Tail task triggered too early at {now0:%H:%M}; safe skip (valid start window >=14:25).")
        return
    if minutes_now > 14 * 60 + 55:
        msg=f"尾盘任务在{now0:%H:%M}才启动，超过14:55安全窗；已停止，未用收盘后数据冒充尾盘信号。"
        print(msg); pushplus_notify("A股二次启动｜尾盘任务迟到", msg); return
    obs_path = LATEST / "observation_pool.csv"
    meta_path = LATEST / "observation_pool_meta.json"
    if not obs_path.exists() or not meta_path.exists():
        msg="今日缺少有效的上一交易日OpenAI观察池；尾盘任务已安全停止。"
        print(msg); pushplus_notify("A股二次启动｜尾盘任务未执行", msg); return
    obs_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if str(obs_meta.get("target_trade_date", "")) != str(today):
        print(f"Observation pool is stale/not for today: {obs_meta.get('target_trade_date')} != {today}; safe skip."); return
    expected_prev = previous_trade_day(today)
    if expected_prev and str(obs_meta.get("generated_trade_date", "")) != str(expected_prev):
        print("Observation pool did not come from previous trading day; safe skip."); return
    pool = pd.read_csv(obs_path, dtype={"股票代码": str})
    pool["股票代码"] = pool["股票代码"].astype(str).str.zfill(6)
    if pool.empty or len(pool) > 10:
        print(f"Invalid observation pool size {len(pool)}; safe skip."); return

    base = ROOT / "tail" / today.strftime("%Y-%m-%d")
    base.mkdir(parents=True, exist_ok=True)
    # workflow在14:40左右触发；若提前则等到14:40。
    wait_until_cn(14, 40)
    snap40, min40, qa40 = fetch_realtime_package(pool)
    save_bytes(base / "1440_precheck.xlsx", to_excel_bytes({"14点40实时快照": snap40, "当日5分钟K线": min40, "数据质量": qa40}))
    candidate_context, candidate_context_qa = fetch_candidate_decision_context(pool)
    save_bytes(base / "candidate_decision_context.xlsx", to_excel_bytes({**candidate_context,"数据质量":candidate_context_qa}))

    wait_until_cn(14, 45)
    snap45, min45, qa45 = fetch_realtime_package(pool)
    conf = confirmation_metrics(snap45, min45)
    idx, breadth, market_qa = fetch_market_review(180)
    sector_tables, sector_qa = fetch_public_sector_flow(fetched_at=now_cn())
    sector_failures = int((sector_qa.get("状态") == "失败").sum()) if not sector_qa.empty else 0
    sector_warnings = int((sector_qa.get("状态") == "警告").sum()) if not sector_qa.empty else 0
    sector_formal_ready = len(sector_tables) == 10 and sector_failures == 0 and sector_warnings == 0
    sector_tables_for_ai = sector_tables if sector_formal_ready else {}
    sector_validation = {
        "status":"正式可用" if sector_formal_ready else "实验性有警告",
        "table_count":len(sector_tables),"failure_count":sector_failures,
        "warning_count":sector_warnings,"ai_enabled":sector_formal_ready,
    }
    market_history, market_context = update_market_history(breadth, phase="14:45", keep_days=180)
    stamp = now_cn().strftime("%H%M%S")
    sheets={"14点45实时快照":snap45,"当日5分钟K线":min45,"确认指标":conf,"实时市场":breadth,
            "市场历史180":market_history,"市场滚动上下文":market_context,"指数180日":idx,
            "数据质量":qa45,"市场质量":market_qa,"板块质量":sector_qa,**sector_tables}
    save_bytes(base / f"1445_confirmation_{stamp}.xlsx", to_excel_bytes(sheets))
    payload = {
        "data_time_cn": now_cn().isoformat(), "trade_date": str(today), "pool_count": len(pool),
        "confirmation": conf.to_dict("records"), "market": breadth.to_dict("records"),
        "market_context": market_context.to_dict("records"), "sector_validation": sector_validation,
        "status": "data_ready_before_ai",
    }
    save_json(base / "tail_payload.json", payload)
    save_json(LATEST / "last_tail_payload.json", payload)
    try:
        final_decisions, final_meta = run_openai_tail(
            pool,snap40,snap45,min45,conf,idx,breadth,market_history,market_context,
            obs_meta,base,sector_tables_for_ai,sector_validation,candidate_context,candidate_context_qa
        )
        # 尾盘一旦产生TRADE即写入独立推荐登记簿。14:45价格仅作参考，
        # 推荐日正式收盘价由15:35反馈任务回填，避免把未收盘价格冒充锚点。
        from research.recommendation_feedback import register_tail_recommendations
        feedback_registration = register_tail_recommendations(
            final_decisions, final_meta, snap45=snap45, obs_meta=obs_meta
        )
        payload["feedback_registration"] = feedback_registration
        payload["final_selected_count"]=final_meta.get("selected_count",0); payload["final_selected_codes"]=final_meta.get("selected_codes",[])
        push_ok = bool(notify_tail_success(final_decisions, final_meta))
        payload["pushplus_delivery_ok"] = push_ok
        payload["status"] = "completed" if push_ok else "completed_push_failed"
        save_json(base/"tail_summary.json",payload); save_json(LATEST/"last_tail_summary.json",payload)
        git_commit(f"V5.3 tail AI completed {today}")
        if not push_ok:
            raise RuntimeError("PushPlus tail delivery exhausted retries")
    except Exception as e:
        delivery_failed = "PushPlus tail delivery" in str(e)
        err={"status":"tail_delivery_failed" if delivery_failed else "tail_ai_failed","trade_date":str(today),"time_cn":now_cn().isoformat(),"error_type":type(e).__name__,"error":str(e),"rule":"失败时不生成伪0-5结果" if not delivery_failed else "OpenAI结果已保存，但微信送达未确认"}
        save_json(base/"tail_ai_error.json",err); save_json(LATEST/"last_tail_ai_error.json",err)
        git_commit(f"V5.3 tail AI failed {today}")
        notify_failure("尾盘微信推送" if delivery_failed else "14:45尾盘OpenAI确认", e)
        raise
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))


def run_backup():
    d = now_cn().strftime("%Y-%m-%d")
    target = ROOT / "backups" / d
    target.mkdir(parents=True, exist_ok=True)
    for p in [REGISTRY, CURRENT_MASTER, ELIMINATED, LATEST / "research_pool_30.csv", LATEST / "latest_after_close.json"]:
        if p.exists(): shutil.copy2(p, target / p.name)
    # Excel快照便于人工查看，但CSV/JSON才是程序恢复主格式。
    registry = load_master_pool(REGISTRY)
    current = pd.read_csv(CURRENT_MASTER, dtype={"股票代码": str}) if CURRENT_MASTER.exists() else pd.DataFrame()
    eliminated = pd.read_csv(ELIMINATED, dtype={"股票代码": str}) if ELIMINATED.exists() else pd.DataFrame()
    save_bytes(target / f"master_pool_backup_{d}.xlsx", to_excel_bytes({"主池注册表": registry, "当前有效主池": current, "已淘汰归档": eliminated}))
    git_commit(f"V5 weekly backup {d}")
    print(f"backup saved: {target}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("after_close")
    p.add_argument("--batch", default="")
    sub.add_parser("tail")
    sub.add_parser("backup")
    a = ap.parse_args()
    if a.cmd == "after_close": run_after_close(a.batch or None)
    elif a.cmd == "tail": run_tail()
    else: run_backup()


if __name__ == "__main__":
    main()
