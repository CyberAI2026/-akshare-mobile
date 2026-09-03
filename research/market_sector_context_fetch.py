from __future__ import annotations

import argparse
import concurrent.futures
import json
import random
import shutil
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd

TZ = ZoneInfo("Asia/Shanghai")
VERSION = "sector-membership-shadow-v0.2"
SOURCE = "eastmoney_board_membership_via_akshare"


def now_cn() -> datetime:
    return datetime.now(TZ)


def norm_code(value) -> str:
    raw=str(value or "").strip()
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw=raw[:-2]
    digits="".join(ch for ch in raw if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def find_col(columns, aliases):
    pairs=[(c,str(c).strip()) for c in columns]
    normalized={v.replace(" ","").lower():k for k,v in pairs}
    for alias in aliases:
        key=alias.replace(" ","").lower()
        if key in normalized:
            return normalized[key]
    for original,cleaned in pairs:
        low=cleaned.replace(" ","").lower()
        if any(a.replace(" ","").lower() in low for a in aliases):
            return original
    return None


def retry(function, label: str, attempts: int = 3):
    errors=[]
    for attempt in range(1, attempts+1):
        try:
            value=function()
            if value is None or (hasattr(value,"empty") and value.empty):
                raise RuntimeError("empty result")
            return value,errors
        except Exception as exc:
            errors.append(f"{label}/{attempt}:{type(exc).__name__}:{exc}")
            if attempt<attempts:
                time.sleep((1.4**attempt)+random.uniform(0.1,0.5))
    return pd.DataFrame(),errors


def load_master(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"master pool not found: {path}")
    frame=pd.read_csv(path,dtype={"股票代码":str})
    code_col=find_col(frame.columns,["股票代码","证券代码","代码"])
    name_col=find_col(frame.columns,["股票名称","证券名称","名称"])
    if code_col is None:
        raise ValueError("master pool lacks stock code column")
    out=pd.DataFrame({"股票代码":frame[code_col].map(norm_code)})
    out["股票名称"]=frame[name_col].astype(str).str.strip() if name_col else ""
    out=out[out["股票代码"].str.fullmatch(r"\d{6}",na=False)]
    return out.drop_duplicates("股票代码").reset_index(drop=True)


def normalize_board_names(frame: pd.DataFrame) -> list[str]:
    col=find_col(frame.columns,["板块名称","概念名称","行业名称","名称"])
    if col is None:
        raise ValueError(f"board name column missing: {list(frame.columns)}")
    return frame[col].dropna().astype(str).str.strip().loc[lambda x:x.ne("")].drop_duplicates().tolist()


def normalize_constituents(frame: pd.DataFrame, board_type: str, board_name: str,
                           wanted: set[str], captured_at: datetime) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    code_col=find_col(frame.columns,["代码","股票代码","证券代码","code"])
    name_col=find_col(frame.columns,["名称","股票名称","证券名称","name"])
    if code_col is None:
        raise ValueError(f"constituent code column missing: {list(frame.columns)}")
    out=pd.DataFrame({"股票代码":frame[code_col].map(norm_code)})
    out["股票名称_板块源"]=frame[name_col].astype(str).str.strip() if name_col else ""
    out=out[out["股票代码"].isin(wanted)].drop_duplicates("股票代码")
    if out.empty:
        return out
    out.insert(0,"板块名称",board_name)
    out.insert(0,"板块类型",board_type)
    out.insert(0,"抓取时间",captured_at.strftime("%Y-%m-%d %H:%M:%S%z"))
    out.insert(0,"业务时区","Asia/Shanghai")
    out.insert(0,"快照日期",captured_at.strftime("%Y-%m-%d"))
    out["数据源"]=SOURCE
    out["数据源URL"]="https://quote.eastmoney.com/center/boardlist.html"
    out["映射口径"]="采集当日公开板块成分；不可用于倒推此前日期"
    out["版本"]=VERSION
    return out


def fetch_type(board_type: str, list_fn, cons_fn, wanted: set[str],
               captured_at: datetime, workers: int = 6, max_boards: int | None = None):
    board_frame,list_errors=retry(list_fn,f"{board_type}:list",4)
    qa=[]
    if board_frame.empty:
        qa.append({"板块类型":board_type,"板块名称":"__LIST__","状态":"失败","匹配主池数":0,"错误":" | ".join(list_errors)})
        return pd.DataFrame(),qa,0
    names=normalize_board_names(board_frame)
    if max_boards:
        names=names[:max_boards]
    qa.append({"板块类型":board_type,"板块名称":"__LIST__","状态":"成功","匹配主池数":0,
               "板块总数":len(names),"错误":" | ".join(list_errors)})
    frames=[]
    def one(name):
        raw,errors=retry(lambda:cons_fn(symbol=name),f"{board_type}:{name}",3)
        if raw.empty:
            return name,pd.DataFrame(),errors
        try:
            return name,normalize_constituents(raw,board_type,name,wanted,captured_at),errors
        except Exception as exc:
            errors.append(f"normalize:{type(exc).__name__}:{exc}")
            return name,pd.DataFrame(),errors
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures=[executor.submit(one,name) for name in names]
        for number,future in enumerate(concurrent.futures.as_completed(futures),1):
            name,matched,errors=future.result()
            status="失败" if errors and matched.empty else "警告" if errors else "成功"
            qa.append({"板块类型":board_type,"板块名称":name,"状态":status,
                       "匹配主池数":len(matched),"错误":" | ".join(errors)})
            if not matched.empty:
                frames.append(matched)
            if number%50==0 or number==len(names):
                print(f"{board_type} progress={number}/{len(names)}",flush=True)
    result=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    return result,qa,len(names)


def is_trade_day(day) -> bool:
    try:
        cal=ak.tool_trade_date_hist_sina()
        dates=set(pd.to_datetime(cal[cal.columns[0]],errors="coerce").dt.date.dropna())
        return day in dates
    except Exception:
        return day.weekday()<5


def save_outputs(output_root: Path, master: pd.DataFrame, mapping: pd.DataFrame,
                 qa: pd.DataFrame, summary: dict):
    output_root.mkdir(parents=True,exist_ok=True)
    mapping.to_csv(output_root/"sector_membership.csv.gz",index=False,encoding="utf-8-sig",compression="gzip")
    qa.to_csv(output_root/"qa.csv.gz",index=False,encoding="utf-8-sig",compression="gzip")
    mapped=set(mapping["股票代码"].astype(str)) if not mapping.empty else set()
    unmapped=master[~master["股票代码"].isin(mapped)].copy()
    unmapped.to_csv(output_root/"unmapped_stocks.csv",index=False,encoding="utf-8-sig")
    (output_root/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")


def persist_library(output_root: Path, persist_root: Path, snapshot_date: str, formal_ready: bool):
    history=persist_root/"history"/snapshot_date
    history.mkdir(parents=True,exist_ok=True)
    for name in ["sector_membership.csv.gz","qa.csv.gz","unmapped_stocks.csv","summary.json"]:
        shutil.copy2(output_root/name,history/name)
    (persist_root/"latest_status.json").write_text((output_root/"summary.json").read_text(encoding="utf-8"),encoding="utf-8")
    if formal_ready:
        persist_root.mkdir(parents=True,exist_ok=True)
        shutil.copy2(output_root/"sector_membership.csv.gz",persist_root/"latest.csv.gz")
        shutil.copy2(output_root/"unmapped_stocks.csv",persist_root/"latest_unmapped.csv")
        shutil.copy2(output_root/"summary.json",persist_root/"latest_summary.json")


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--master-pool",default="v5_data/master/current_master_pool.csv")
    parser.add_argument("--output-root",default="sector_membership_run")
    parser.add_argument("--persist-root",default="")
    parser.add_argument("--workers",type=int,default=6)
    parser.add_argument("--max-boards",type=int,default=0)
    parser.add_argument("--skip-non-trading-day",action="store_true")
    args=parser.parse_args()

    captured=now_cn()
    if args.skip_non_trading_day and not is_trade_day(captured.date()):
        print("Non-trading day; safe skip.")
        return
    master=load_master(Path(args.master_pool))
    wanted=set(master["股票代码"])
    specs=[
        ("行业",ak.stock_board_industry_name_em,ak.stock_board_industry_cons_em),
        ("概念",ak.stock_board_concept_name_em,ak.stock_board_concept_cons_em),
    ]
    frames=[];qa_rows=[];board_counts={}
    for board_type,list_fn,cons_fn in specs:
        frame,qa,count=fetch_type(board_type,list_fn,cons_fn,wanted,captured,args.workers,args.max_boards or None)
        if not frame.empty:
            frames.append(frame)
        qa_rows.extend(qa);board_counts[board_type]=count
    mapping=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    if not mapping.empty:
        mapping=mapping.merge(master,on="股票代码",how="left")
        mapping["股票名称"]=mapping["股票名称"].where(mapping["股票名称"].astype(str).ne(""),mapping["股票名称_板块源"])
        mapping=mapping.drop(columns=["股票名称_板块源"]).drop_duplicates(["股票代码","板块类型","板块名称"])
        mapping=mapping.sort_values(["股票代码","板块类型","板块名称"]).reset_index(drop=True)
    qa=pd.DataFrame(qa_rows)
    mapped_any=set(mapping["股票代码"]) if not mapping.empty else set()
    industry=set(mapping.loc[mapping["板块类型"]=="行业","股票代码"]) if not mapping.empty else set()
    concept=set(mapping.loc[mapping["板块类型"]=="概念","股票代码"]) if not mapping.empty else set()
    total=len(master)
    failures=int((qa.get("状态",pd.Series(dtype=str))=="失败").sum())
    board_rows=max(1,len(qa)-2)
    failure_rate=failures/board_rows
    any_coverage=len(mapped_any)/total if total else 0
    industry_coverage=len(industry)/total if total else 0
    concept_coverage=len(concept)/total if total else 0
    formal_ready=bool(total and any_coverage>=0.95 and industry_coverage>=0.90 and failure_rate<=0.10)
    summary={
        "status":"FORMAL_READY" if formal_ready else "PROVISIONAL",
        "phase":"第二阶段板块映射影子库","version":VERSION,
        "snapshot_date":captured.strftime("%Y-%m-%d"),"captured_at_cn":captured.isoformat(),
        "master_stock_count":total,"mapping_rows":len(mapping),
        "mapped_stock_count":len(mapped_any),"any_coverage":round(any_coverage,6),
        "industry_coverage":round(industry_coverage,6),"concept_coverage":round(concept_coverage,6),
        "board_counts":board_counts,"failed_board_requests":failures,"board_failure_rate":round(failure_rate,6),
        "formal_ready":formal_ready,
        "ai_enabled":False,
        "point_in_time_warning":"本快照只代表采集当日公开分类，不得倒推此前日期。",
    }
    output=Path(args.output_root)
    save_outputs(output,master,mapping,qa,summary)
    if args.persist_root:
        persist_library(output,Path(args.persist_root),summary["snapshot_date"],formal_ready)
    print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
    if mapping.empty or any_coverage<0.80:
        raise SystemExit("FAIL: sector membership coverage below shadow-layer minimum")


if __name__=="__main__":
    main()
