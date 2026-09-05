from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

import v5_cli as cli
from v5_core import (
    STRATEGY_VERSION,
    build_metrics,
    fetch_market_review,
    fetch_pool_history_incremental,
    fetch_public_sector_flow,
    load_master_pool,
    maintain_master_pool,
    merge_master_pool,
    seed_global_cache_from_old_runs,
    split_stock_and_indices,
    stage1_rank,
    stage2_rank,
    stage3_rank,
    to_excel_bytes,
)


STATE = cli.ROOT / "staging" / "after_close_current.json"


def _save_state(state: dict) -> None:
    cli.save_json(STATE, state)


def _load_state(required_stage: str | None = None) -> tuple[dict, Path]:
    if not STATE.exists():
        raise FileNotFoundError("盘后分段状态不存在；请先运行 init 阶段")
    state = json.loads(STATE.read_text(encoding="utf-8"))
    if required_stage and state.get("stage") != required_stage:
        raise RuntimeError(f"阶段顺序错误：需要 {required_stage}，当前为 {state.get('stage')}")
    base = Path(state["folder"])
    if not base.exists():
        raise FileNotFoundError(f"盘后运行目录不存在: {base}")
    return state, base


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"阶段产物不存在: {path}")
    try:
        return pd.read_csv(path, dtype={"股票代码": str})
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _qa_cache_summary(qa: pd.DataFrame) -> dict:
    modes = qa.get("缓存模式", pd.Series(dtype=str)).fillna("").astype(str) if not qa.empty else pd.Series(dtype=str)
    return {
        "命中或增量": int(modes.str.contains("cache|increment", case=False, regex=True).sum()),
        "总数": int(len(qa)),
        "成功": int((qa.get("状态") == "成功").sum()) if not qa.empty else 0,
    }


def run_init(batch_path: str | None) -> None:
    started = cli.now_cn()
    stamp = started.strftime("%Y%m%d_%H%M%S")
    base = cli.ROOT / "runs" / stamp
    base.mkdir(parents=True, exist_ok=True)

    seed_info = seed_global_cache_from_old_runs(cli.OLD_ROOT, cli.CACHE)
    registry = load_master_pool(cli.REGISTRY)
    bootstrapped = False
    if registry.empty:
        registry = cli._bootstrap_registry_from_v4()
        bootstrapped = not registry.empty
    daily = cli._read_pool(batch_path)
    registry, changes = merge_master_pool(registry, daily, asof=started.date())
    registry = cli.refresh_stock_names(registry)
    active_input = registry[registry["当前状态"].astype(str) != "已淘汰"][["股票代码", "股票名称"]]
    active_input, registry_indices = split_stock_and_indices(active_input)
    if not registry_indices.empty:
        bad_codes = set(registry_indices["股票代码"].astype(str))
        registry = registry[~registry["股票代码"].astype(str).isin(bad_codes)].reset_index(drop=True)
        cli.save_df(base / "隔离指数.csv", registry_indices)

    cli.save_df(base / "stages" / "registry_merged.csv", registry)
    cli.save_df(base / "stages" / "active_input.csv", active_input)
    cli.save_df(base / "每日提交变动.csv", changes)
    state = {
        "status": "running",
        "stage": "initialized",
        "engine": "V5.3-auditable-market-sector-layer",
        "strategy": STRATEGY_VERSION,
        "started_cn": started.isoformat(),
        "stamp": stamp,
        "folder": str(base),
        "batch_path": batch_path or "",
        "batch_count": len(daily),
        "master_before_screen": len(active_input),
        "bootstrapped_from_v4": bootstrapped,
        "cache_seed": seed_info,
        "isolated_index_count": len(registry_indices),
    }
    _save_state(state)
    cli.save_json(base / "meta.json", state)
    cli.git_commit(f"V5 after-close init {stamp}")
    print(f"AFTER_CLOSE_STAGE_OK stage=init folder={base} stocks={len(active_input)}")


def run_25d() -> None:
    state, base = _load_state("initialized")
    active_input = _read_csv(base / "stages" / "active_input.csv")
    d25, q25 = fetch_pool_history_incremental(active_input, 25, cli.CACHE, cli.checkpoint_factory(base / "25d"))
    m25 = build_metrics(d25)
    s1, a1 = stage1_rank(m25, 150, 200, return_audit=True)
    p1 = s1[["股票代码", "股票名称"]].copy()
    cli.save_df(base / "25d" / "pool_150_200.csv", p1)
    cli.save_df(base / "25d" / "pool_150.csv", p1)
    cli.save_df(base / "25d" / "stage_audit.csv", a1)
    cli.save_df(base / "stages" / "q25.csv", q25)
    cli.save_bytes(base / "25d" / "result.xlsx", to_excel_bytes({"25日日线": d25, "质量校验": q25, "粗筛指标": m25, "筛选审计": a1, "一级结果": s1}))
    state.update({"stage": "screen25_complete", "stage1": len(p1), "qa25": _qa_cache_summary(q25)})
    _save_state(state)
    cli.git_commit(f"V5 after-close 25d {state['stamp']}")
    print(f"AFTER_CLOSE_STAGE_OK stage=25d selected={len(p1)}")


def run_120d() -> None:
    state, base = _load_state("screen25_complete")
    p1 = _read_csv(base / "25d" / "pool_150_200.csv")
    d120, q120 = fetch_pool_history_incremental(p1, 120, cli.CACHE, cli.checkpoint_factory(base / "120d"))
    m120 = build_metrics(d120)
    s2, a2 = stage2_rank(m120, 30, 50, return_audit=True)
    p2 = s2[["股票代码", "股票名称"]].copy()
    cli.save_df(base / "120d" / "research_pool_30_50.csv", p2)
    cli.save_df(base / "120d" / "research_pool_30.csv", p2)
    cli.save_df(base / "120d" / "stage_audit.csv", a2)
    cli.save_df(base / "stages" / "q120.csv", q120)
    cli.save_bytes(base / "120d" / "result.xlsx", to_excel_bytes({"120日日线": d120, "质量校验": q120, "结构指标": m120, "筛选审计": a2, "二级30-50只": s2}))
    state.update({"stage": "screen120_complete", "stage2_research_pool": len(p2), "qa120": _qa_cache_summary(q120)})
    _save_state(state)
    cli.git_commit(f"V5 after-close 120d {state['stamp']}")
    print(f"AFTER_CLOSE_STAGE_OK stage=120d selected={len(p2)}")


def run_250d() -> None:
    state, base = _load_state("screen120_complete")
    p2 = _read_csv(base / "120d" / "research_pool_30_50.csv")
    d250, q250 = fetch_pool_history_incremental(p2, 250, cli.CACHE, cli.checkpoint_factory(base / "250d"))
    if d250.empty or "日期" not in d250.columns:
        raise RuntimeError("250日数据缺少日期，无法确定观察池生成交易日")
    m250 = build_metrics(d250)
    stage2_audit = _read_csv(base / "120d" / "stage_audit.csv")
    if not stage2_audit.empty and "阶段2分" in stage2_audit.columns:
        m250 = m250.merge(stage2_audit[["股票代码", "阶段2分"]], on="股票代码", how="left")
    _, lifecycle_audit = stage3_rank(m250, max(1, len(m250)), return_audit=True)
    research_pack = p2.merge(lifecycle_audit, on=["股票代码", "股票名称"], how="left")
    cli.save_df(base / "250d" / "research_pack_30_40.csv", research_pack)
    cli.save_df(base / "250d" / "lifecycle_audit.csv", lifecycle_audit)
    cli.save_df(base / "stages" / "q250.csv", q250)
    cli.save_bytes(base / "250d" / "result.xlsx", to_excel_bytes({"250日日线": d250, "质量校验": q250, "生命周期指标": m250, "生命周期审计": lifecycle_audit, "AI研究输入30-50只": research_pack}))

    registry = _read_csv(base / "stages" / "registry_merged.csv")
    cache_metrics = cli._cache_metrics_for_master(registry)
    registry, maintenance_audit = maintain_master_pool(registry, cache_metrics, asof=pd.Timestamp(state["started_cn"]).date())
    p1 = _read_csv(base / "25d" / "pool_150_200.csv")
    registry = cli._mark_master_stage(registry, p1, p2)
    current = registry[registry["当前状态"].astype(str) != "已淘汰"].copy().reset_index(drop=True)
    eliminated = registry[registry["当前状态"].astype(str) == "已淘汰"].copy().reset_index(drop=True)
    cli.save_df(cli.REGISTRY, registry)
    cli.save_df(cli.CURRENT_MASTER, current)
    cli.save_df(cli.ELIMINATED, eliminated)
    cli.save_df(base / "master_maintenance_audit.csv", maintenance_audit)
    cli.save_df(cli.LATEST / "research_pool_30_50.csv", research_pack)
    cli.save_df(cli.LATEST / "research_pool_30.csv", research_pack)
    cli.save_df(cli.LATEST / "current_master_pool.csv", current)

    changes = _read_csv(base / "每日提交变动.csv")
    change_kind = changes.get("变动", pd.Series(dtype=str)).astype(str) if not changes.empty else pd.Series(dtype=str)
    state.update({
        "stage": "lifecycle250_complete",
        "generated_trade_date": str(pd.to_datetime(d250["日期"], errors="coerce").max().date()),
        "master_count": len(current),
        "eliminated_count": len(eliminated),
        "daily_new_count": int((change_kind == "新增").sum()),
        "daily_reactivated_count": int((change_kind == "重新激活").sum()),
        "daily_eliminated_count": int((maintenance_audit.get("淘汰日期", pd.Series(dtype=str)).astype(str) == str(pd.Timestamp(state["started_cn"]).date())).sum()) if not maintenance_audit.empty else 0,
        "cooling_count": int((registry["当前状态"].astype(str) == "冷却观察").sum()) if not registry.empty else 0,
        "qa250": _qa_cache_summary(q250),
    })
    _save_state(state)
    cli.git_commit(f"V5 after-close 250d {state['stamp']}")
    print(f"AFTER_CLOSE_STAGE_OK stage=250d research_pool={len(research_pack)}")


def run_market() -> None:
    state, base = _load_state("lifecycle250_complete")
    started = pd.Timestamp(state["started_cn"]).to_pydatetime()
    idx, breadth, market_qa = fetch_market_review(180)
    sector_tables, sector_qa = fetch_public_sector_flow(fetched_at=started)
    _, sector_validation = cli._sector_readiness(sector_tables, sector_qa)
    market_history, market_context = cli.update_market_history(breadth, phase="盘后", keep_days=180)
    market_sheets = cli._market_review_sheets(idx, breadth, market_history, market_context, market_qa)
    sector_sheets = {**sector_tables, "板块质量校验": sector_qa}
    cli.save_bytes(base / "market_review.xlsx", to_excel_bytes(market_sheets))
    cli.save_bytes(base / "sector_fund_flow.xlsx", to_excel_bytes(sector_sheets))
    cli.save_bytes(cli.LATEST / "market_review.xlsx", to_excel_bytes(market_sheets))
    cli.save_bytes(cli.LATEST / "sector_fund_flow.xlsx", to_excel_bytes(sector_sheets))
    state.update({"stage": "market_context_complete", "sector_validation": sector_validation})
    _save_state(state)
    cli.git_commit(f"V5.3 market context ready {state['stamp']}")
    print(f"AFTER_CLOSE_STAGE_OK stage=market sector_status={sector_validation.get('status')}")


def run_ai() -> None:
    state, base = _load_state("market_context_complete")
    research_pack = _read_csv(base / "250d" / "research_pack_30_40.csv")
    market_sheets = pd.read_excel(base / "market_review.xlsx", sheet_name=None)
    sector_sheets = pd.read_excel(base / "sector_fund_flow.xlsx", sheet_name=None)
    idx = market_sheets.get("五大指数180日", pd.DataFrame())
    breadth = market_sheets.get("市场宽度当日", pd.DataFrame())
    market_history = market_sheets.get("市场宽度历史180", pd.DataFrame())
    market_context = market_sheets.get("市场滚动上下文", pd.DataFrame())
    sector_qa = sector_sheets.pop("板块质量校验", pd.DataFrame())
    sector_tables_for_ai, sector_validation = cli._sector_readiness(sector_sheets, sector_qa)
    generated_trade_date = pd.Timestamp(state["generated_trade_date"]).date()
    try:
        obs, obs_meta, _ = cli.run_openai_after_close(
            research_pack, idx, breadth, market_history, market_context, base,
            generated_trade_date, {"folder": str(base)}, sector_tables_for_ai,
        )
    except Exception as exc:
        err = {
            "status": "ai_failed", "engine": state["engine"], "strategy": STRATEGY_VERSION,
            "time_cn": cli.now_cn().isoformat(), "error_type": type(exc).__name__, "error": str(exc),
            "generated_trade_date": str(generated_trade_date), "source_candidate_count": len(research_pack),
            "rule": "AI失败时不生成观察池，也不保留旧观察池。",
        }
        cli.save_json(base / "ai" / "ai_error.json", err)
        cli.save_json(cli.LATEST / "latest_ai_error.json", err)
        state.update({"status": "completed_ai_failed", "stage": "ai_failed", "ai_error": str(exc)})
        _save_state(state)
        cli.save_json(base / "summary.json", state)
        cli.save_json(cli.LATEST / "latest_after_close.json", state)
        cli.git_commit(f"V5.3 AI failed {state['stamp']}")
        cli.notify_failure("盘后OpenAI研究", exc)
        raise

    completed = cli.now_cn()
    started = pd.Timestamp(state["started_cn"]).to_pydatetime()
    summary = {
        **state,
        "status": "completed", "stage": "completed", "completed_cn": completed.isoformat(),
        "elapsed_minutes": round((completed - started).total_seconds() / 60, 2),
        "cache_summary": {"25日": state.get("qa25", {}), "120日": state.get("qa120", {}), "250日": state.get("qa250", {})},
        "python_final": "30-50只软容量研究包（不机械生成前10）",
        "observation_pool_count": len(obs), "target_trade_date": obs_meta.get("target_trade_date"),
        "openai_model": obs_meta.get("model"), "market_assessment": obs_meta.get("market_assessment", {}),
        "sector_validation": sector_validation,
        "high_attention_sector_market": cli._attention_sector_market_groups(sector_tables_for_ai, obs_meta.get("opinion_context", {})),
        "stock_qa_25_success": state.get("qa25", {}).get("成功", 0),
        "stock_qa_120_success": state.get("qa120", {}).get("成功", 0),
        "stock_qa_250_success": state.get("qa250", {}).get("成功", 0),
        "next_step": "次日14:40读取带日期锁的0~10只观察池，14:45再做最终0~5确认",
    }
    cli.save_json(base / "summary.json", summary)
    cli.save_json(cli.LATEST / "latest_after_close.json", summary)
    cli.save_json(base / "meta.json", summary)
    _save_state(summary)
    cli.git_commit(f"V5.3 after-close + AI completed {state['stamp']}")
    cli.notify_after_close_success(summary, obs, obs_meta)
    print(f"AFTER_CLOSE_STAGE_OK stage=ai observation_pool={len(obs)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["init", "25d", "120d", "250d", "market", "ai"])
    parser.add_argument("--batch", default="")
    args = parser.parse_args()
    actions = {
        "init": lambda: run_init(args.batch or None),
        "25d": run_25d,
        "120d": run_120d,
        "250d": run_250d,
        "market": run_market,
        "ai": run_ai,
    }
    actions[args.stage]()


if __name__ == "__main__":
    main()
