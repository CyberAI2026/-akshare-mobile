from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import pandas as pd

import v5_cli as cli
from research.after_close_stages import _attach_stage2_evidence, _build_after_close_holding_review
from v5_core import (
    PRE_AI_CANDIDATE_CAP,
    STRATEGY_VERSION,
    align_pre_ai_candidates,
    build_metrics,
    stage1_rank,
    stage2_rank,
    stage3_rank,
)


CONTROL = cli.ROOT / "control" / "effective_breakout_revision_20260921.json"
REVISION_RUN = cli.ROOT / "runs" / "20260921_effective_breakout_v1"


def _load_control() -> dict:
    return json.loads(CONTROL.read_text(encoding="utf-8")) if CONTROL.exists() else {}


def _save_control(state: dict) -> None:
    cli.save_json(CONTROL, state)


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"股票代码": str})


def _load_cached_histories(active: pd.DataFrame) -> pd.DataFrame:
    active = active.copy()
    active["股票代码"] = active["股票代码"].astype(str).str.zfill(6)
    names = dict(zip(active["股票代码"], active["股票名称"]))
    parts = []
    missing = []
    for code in active["股票代码"]:
        path = cli.CACHE / f"{code}.csv"
        if not path.exists():
            missing.append(code)
            continue
        frame = pd.read_csv(path, dtype={"股票代码": str}).tail(260).copy()
        frame["股票代码"] = code
        frame["股票名称"] = names.get(code, "")
        parts.append(frame)
    if missing:
        raise RuntimeError(f"今日缓存不完整，禁止联网补抓或生成修订池: missing={len(missing)}")
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def prepare(source_run: str) -> None:
    state = _load_control()
    if state.get("status") in {"prepared", "ai_complete", "delivered"}:
        print(f"EFFECTIVE_BREAKOUT_REVISION_PREPARE_ALREADY_DONE status={state['status']}")
        return
    source = Path(source_run)
    summary_path = source / "summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(f"source run missing: {summary_path}")
    source_summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if source_summary.get("status") != "completed" or not source_summary.get("pushplus_delivery_ok"):
        raise RuntimeError("源盘后运行不是已完成且已送达状态，禁止建立修订版")
    active = _read_csv(source / "stages" / "active_input.csv")
    history = _load_cached_histories(active)
    metrics = build_metrics(history)
    stage1, audit1 = stage1_rank(metrics, return_audit=True)
    stage2, audit2 = stage2_rank(stage1, return_audit=True)
    lifecycle, audit3 = stage3_rank(stage2, return_audit=True)
    research_pack, pre_ai_audit = align_pre_ai_candidates(audit3, cap=PRE_AI_CANDIDATE_CAP)
    research_pack = _attach_stage2_evidence(research_pack, audit2)
    if research_pack.empty:
        raise RuntimeError("有效突破新规则没有任何OpenAI前置候选；禁止用旧池或凑数")

    for folder in ["25d", "120d", "250d", "ai", "holdings", "rollback"]:
        (REVISION_RUN / folder).mkdir(parents=True, exist_ok=True)
    cli.save_df(REVISION_RUN / "25d" / "stage_audit.csv", audit1)
    cli.save_df(REVISION_RUN / "25d" / "pool_stage1.csv", stage1)
    cli.save_df(REVISION_RUN / "120d" / "stage_audit.csv", audit2)
    cli.save_df(REVISION_RUN / "120d" / "research_pool_stage2.csv", stage2)
    cli.save_df(REVISION_RUN / "250d" / "lifecycle_audit.csv", pre_ai_audit)
    cli.save_df(REVISION_RUN / "250d" / "research_pack_30_40.csv", research_pack)
    for name in ["market_review.xlsx", "sector_fund_flow.xlsx"]:
        shutil.copy2(source / name, REVISION_RUN / name)
    for name in ["observation_pool.csv", "observation_pool_meta.json", "observation_pool_analysis.json"]:
        prior = source / "ai" / name
        if prior.exists():
            shutil.copy2(prior, REVISION_RUN / "rollback" / name)

    generated = str(source_summary.get("generated_trade_date") or "2026-09-21")
    state = {
        "status": "prepared",
        "lock": "LOCK-20260921-effective-breakout-v1",
        "source_run": str(source),
        "revision_run": str(REVISION_RUN),
        "strategy": STRATEGY_VERSION,
        "generated_trade_date": generated,
        "target_trade_date": str(source_summary.get("target_trade_date") or "2026-09-22"),
        "source_delivery_preserved": True,
        "network_history_refetch": False,
        "counts": {
            "active": len(active), "stage1": len(stage1), "stage2": len(stage2),
            "lifecycle": len(lifecycle), "pre_ai": len(research_pack),
        },
        "openai_calls": 0,
        "corrected_push_attempts": 0,
    }
    _save_control(state)
    cli.git_commit("Prepare effective-breakout revision from 2026-09-21 cache")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def analyze() -> None:
    state = _load_control()
    if state.get("status") in {"ai_complete", "delivered"}:
        print(f"EFFECTIVE_BREAKOUT_REVISION_AI_ALREADY_DONE status={state['status']}")
        return
    if state.get("status") != "prepared" or state.get("openai_calls") != 0:
        raise RuntimeError(f"修订AI阶段状态不安全: {state}")
    pack = _read_csv(REVISION_RUN / "250d" / "research_pack_30_40.csv")
    market = pd.read_excel(REVISION_RUN / "market_review.xlsx", sheet_name=None)
    sectors = pd.read_excel(REVISION_RUN / "sector_fund_flow.xlsx", sheet_name=None)
    sector_qa = sectors.pop("板块质量校验", pd.DataFrame())
    sector_tables, sector_validation = cli._sector_readiness(sectors, sector_qa)
    generated = pd.Timestamp(state["generated_trade_date"]).date()
    try:
        obs, meta, result = cli.run_openai_after_close(
            pack,
            market.get("五大指数180日", pd.DataFrame()),
            market.get("市场宽度当日", pd.DataFrame()),
            market.get("市场宽度历史180", pd.DataFrame()),
            market.get("市场滚动上下文", pd.DataFrame()),
            REVISION_RUN,
            generated,
            {"folder": str(REVISION_RUN)},
            sector_tables,
        )
    except Exception:
        # The ordinary writer clears latest before an API call. A failed correction
        # must restore the already-delivered original pool instead of leaving no pool.
        for name in ["observation_pool.csv", "observation_pool_meta.json", "observation_pool_analysis.json"]:
            prior = REVISION_RUN / "rollback" / name
            if prior.exists():
                shutil.copy2(prior, cli.LATEST / name)
        raise
    holding_review = _build_after_close_holding_review(REVISION_RUN, generated)
    summary = {
        "status": "ai_complete", "stage": "revision_ai_complete", "strategy": STRATEGY_VERSION,
        "source_run": state["source_run"], "folder": str(REVISION_RUN),
        "generated_trade_date": state["generated_trade_date"], "target_trade_date": meta["target_trade_date"],
        "master_count": state["counts"]["active"], "stage1": state["counts"]["stage1"],
        "stage2_research_pool": state["counts"]["stage2"], "stage3_research_pool": state["counts"]["pre_ai"],
        "observation_pool_count": len(obs), "market_assessment": meta.get("market_assessment", {}),
        "sector_validation": sector_validation,
        "high_attention_sector_market": cli._attention_sector_market_groups(sector_tables, meta.get("opinion_context", {})),
        "cache_summary": {"修订来源": "2026-09-21已保存缓存；未联网重抓"},
        "daily_new_count": 0, "daily_reactivated_count": 0, "daily_eliminated_count": 0, "cooling_count": "沿用源运行",
        "revision_notice": "原盘后推送已送达；本条是有效突破新规则的正式更正版本",
    }
    cli.save_json(REVISION_RUN / "summary.json", summary)
    state.update({
        "status": "ai_complete", "openai_calls": 1, "observation_count": len(obs),
        "market_pool_policy": meta.get("market_pool_policy", {}),
        "pool_minimum_shortfall": meta.get("pool_minimum_shortfall", 0),
        "sector_validation": sector_validation,
    })
    _save_control(state)
    cli.git_commit("Complete effective-breakout revision AI checkpoint")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def deliver() -> None:
    state = _load_control()
    if state.get("status") == "delivered":
        print("EFFECTIVE_BREAKOUT_REVISION_DELIVERY_ALREADY_ACCEPTED")
        return
    if state.get("status") != "ai_complete" or state.get("openai_calls") != 1:
        raise RuntimeError(f"修订推送阶段状态不安全: {state}")
    obs = _read_csv(REVISION_RUN / "ai" / "observation_pool.csv")
    meta = json.loads((REVISION_RUN / "ai" / "observation_pool_meta.json").read_text(encoding="utf-8"))
    summary = json.loads((REVISION_RUN / "summary.json").read_text(encoding="utf-8"))
    holding_review = cli.load_private_exit_decisions(REVISION_RUN / "holdings" / "after_close_holding_review.enc")
    ok = bool(cli.notify_after_close_success(
        summary, obs, meta, holding_review,
        title="A股二次启动｜盘后研究更正（有效突破新规则）",
    ))
    state["corrected_push_attempts"] = int(state.get("corrected_push_attempts", 0)) + 1
    state["pushplus_delivery_ok"] = ok
    state["status"] = "delivered" if ok else "ai_complete"
    summary["status"] = "completed" if ok else "completed_push_failed"
    summary["pushplus_delivery_ok"] = ok
    summary["pushplus_delivery_status"] = "request_accepted" if ok else "failed"
    cli.save_json(REVISION_RUN / "summary.json", summary)
    cli.save_json(cli.LATEST / "latest_after_close.json", summary)
    _save_control(state)
    cli.git_commit("Deliver effective-breakout after-close correction")
    if not ok:
        raise RuntimeError("修订版PushPlus未确认接受")
    print(json.dumps(state, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "ai", "deliver"])
    parser.add_argument("--source-run", default="v5_data/runs/20260921_223444")
    args = parser.parse_args()
    {"prepare": lambda: prepare(args.source_run), "ai": analyze, "deliver": deliver}[args.stage]()


if __name__ == "__main__":
    main()
