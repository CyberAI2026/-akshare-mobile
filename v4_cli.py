from __future__ import annotations
import argparse
import json
import os
import subprocess
import time
from datetime import datetime, time as dtime
from pathlib import Path

import pandas as pd

from v4_core import (
    STRATEGY_VERSION, build_metrics, confirmation_metrics, fetch_pool_history, fetch_realtime_package,
    is_trade_day, openai_analyze, stage1_rank, stage2_rank, stage3_rank, to_excel_bytes
)

ROOT=Path("v4_data")


def save_bytes(path: Path, data: bytes):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)


def save_df(path: Path, df: pd.DataFrame):
    path.parent.mkdir(parents=True,exist_ok=True); df.to_csv(path,index=False,encoding="utf-8-sig")


def git_commit(message: str):
    try:
        subprocess.run(["git","config","user.name","V4 Automation"],check=False)
        subprocess.run(["git","config","user.email","actions@users.noreply.github.com"],check=False)
        subprocess.run(["git","add","v4_data"],check=False)
        subprocess.run(["git","commit","-m",message],check=False)
        subprocess.run(["git","push"],check=False)
    except Exception as e:
        print("git commit warning:",e)


def checkpoint_factory(stage_dir: Path):
    def cp(done,total,code,lastqa):
        (stage_dir/"progress.json").write_text(json.dumps({"done":done,"total":total,"code":code,"updated":datetime.now().isoformat(),"last":lastqa},ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    return cp


def run_full(pool_path: str):
    pool=pd.read_csv(pool_path,dtype={"股票代码":str}); pool["股票代码"]=pool["股票代码"].str.zfill(6)
    stamp=Path(pool_path).stem.replace("pool_", ""); base=ROOT/"runs"/stamp
    base.mkdir(parents=True,exist_ok=True)
    meta_path=base/"meta.json"
    meta={"status":"running","strategy":STRATEGY_VERSION,"started":datetime.now().isoformat(),"initial_count":len(pool)}
    meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")

    cp25=checkpoint_factory(base/"25d")
    d25,q25=fetch_pool_history(pool,25,lambda d,t,c,q:(cp25(d,t,c,q), git_commit(f"V4 checkpoint 25d {d}/{t}") if d%10==0 else None), cache_dir=base/"25d"/"cache"); m25=build_metrics(d25); s1,a1=stage1_rank(m25,150,return_audit=True)
    p1=s1[["股票代码","股票名称"]].copy(); save_df(base/"25d"/"pool_150.csv",p1); save_df(base/"25d"/"stage_audit.csv",a1)
    save_bytes(base/"25d"/"result.xlsx",to_excel_bytes({"25日日线":d25,"质量校验":q25,"粗筛指标":m25,"筛选审计":a1,"一级结果":s1}))

    cp120=checkpoint_factory(base/"120d")
    d120,q120=fetch_pool_history(p1,120,lambda d,t,c,q:(cp120(d,t,c,q), git_commit(f"V4 checkpoint 120d {d}/{t}") if d%10==0 else None), cache_dir=base/"120d"/"cache"); m120=build_metrics(d120); s2,a2=stage2_rank(m120,30,return_audit=True)
    p2=s2[["股票代码","股票名称"]].copy(); save_df(base/"120d"/"pool_30.csv",p2); save_df(base/"120d"/"stage_audit.csv",a2)
    save_bytes(base/"120d"/"result.xlsx",to_excel_bytes({"120日日线":d120,"质量校验":q120,"结构指标":m120,"筛选审计":a2,"二级结果":s2}))

    cp250=checkpoint_factory(base/"250d")
    d250,q250=fetch_pool_history(p2,250,lambda d,t,c,q:(cp250(d,t,c,q), git_commit(f"V4 checkpoint 250d {d}/{t}") if d%10==0 else None), cache_dir=base/"250d"/"cache"); m250=build_metrics(d250); s3,a3=stage3_rank(m250,10,return_audit=True)
    p3=s3[["股票代码","股票名称"]].copy(); save_df(base/"250d"/"observation_pool.csv",p3); save_df(base/"250d"/"stage_audit.csv",a3)
    save_bytes(base/"250d"/"result.xlsx",to_excel_bytes({"250日日线":d250,"质量校验":q250,"生命周期指标":m250,"筛选审计":a3,"三级结果":s3}))

    latest=ROOT/"latest"; latest.mkdir(parents=True,exist_ok=True); save_df(latest/"observation_pool.csv",p3)
    summary={"strategy":STRATEGY_VERSION,"engine":"V4.1-auditable","initial":len(pool),"stage1":len(p1),"stage2":len(p2),"stage3":len(p3),"stage1_codes":p1["股票代码"].astype(str).tolist(),"stage2_codes":p2["股票代码"].astype(str).tolist(),"stage3_codes":p3["股票代码"].astype(str).tolist(),"completed":datetime.now().isoformat(),"folder":str(base)}
    try:
        summary["ai_precheck"]=openai_analyze("三级生命周期筛选复核",{"stage3":s3.to_dict("records")})
    except Exception as e: summary["ai_precheck"]=f"AI调用失败:{e}"
    (base/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    (latest/"latest_run.json").write_text(json.dumps(summary,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    meta.update({"status":"completed","completed":summary["completed"],"stage1":len(p1),"stage2":len(p2),"stage3":len(p3)})
    meta_path.write_text(json.dumps(meta,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    git_commit(f"V4 full pipeline {stamp}")
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def wait_until_1445():
    now=datetime.now(); target=datetime.combine(now.date(),dtime(14,45))
    if now<target:
        seconds=(target-now).total_seconds()
        if seconds<=900:
            print(f"Waiting {seconds:.0f}s until 14:45..."); time.sleep(seconds)


def run_1445():
    if not is_trade_day():
        print("Not a trading day; skip."); return
    wait_until_1445()
    pool_path=ROOT/"latest"/"observation_pool.csv"
    if not pool_path.exists():
        raise FileNotFoundError("没有找到 v4_data/latest/observation_pool.csv，请先完成全流程。")
    pool=pd.read_csv(pool_path,dtype={"股票代码":str}); pool["股票代码"]=pool["股票代码"].str.zfill(6)
    snap,minute,qa=fetch_realtime_package(pool); conf=confirmation_metrics(snap,minute)
    stamp=datetime.now().strftime("%Y-%m-%d_%H%M%S"); base=ROOT/datetime.now().strftime("%Y-%m-%d")/"1445"; base.mkdir(parents=True,exist_ok=True)
    save_bytes(base/f"实时确认_{stamp}.xlsx",to_excel_bytes({"14点45实时快照":snap,"当日5分钟K线":minute,"数据质量":qa,"确认指标":conf}))
    payload={"timestamp":datetime.now().isoformat(),"confirmation":conf.head(10).to_dict("records"),"snapshot":snap.to_dict("records")}
    try: analysis=openai_analyze("14:45最终确认",payload)
    except Exception as e: analysis=f"AI调用失败:{e}"
    (base/f"最终分析_{stamp}.md").write_text(analysis,encoding="utf-8")
    latest=ROOT/"latest"; (latest/"last_1445_analysis.md").write_text(analysis,encoding="utf-8")
    (latest/"last_1445.json").write_text(json.dumps(payload,ensure_ascii=False,default=str,indent=2),encoding="utf-8")
    git_commit(f"V4 14:45 confirmation {stamp}")
    print(analysis)


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    p=sub.add_parser("full"); p.add_argument("--pool",required=True)
    sub.add_parser("1445")
    a=ap.parse_args()
    if a.cmd=="full": run_full(a.pool)
    else: run_1445()

if __name__=="__main__": main()
