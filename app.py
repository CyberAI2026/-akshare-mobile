import hmac
import io
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from v5_core import GithubConfig, gh_dispatch, gh_headers, gh_put_bytes, pool_from_text, pool_from_upload, split_stock_and_indices
from research.private_trade_ledger import (
    TRANSACTION_COLUMNS,
    append_transactions,
    build_positions,
    decrypt_transactions,
    empty_transactions,
    encrypt_transactions,
    normalize_code,
    normalize_transactions,
)

AFTER_CLOSE_WORKFLOW = "v5_after_close.yml"
TAIL_WORKFLOW = "v5_tail_confirmation.yml"
BACKUP_WORKFLOW = "v5_weekly_backup.yml"
TRADE_LEDGER_PATH = "v5_data/private/trades.enc"
CN_TZ = ZoneInfo("Asia/Shanghai")

st.set_page_config(page_title="A股二次启动研究系统 V5.4", page_icon="📈", layout="wide")
st.title("A股强势股二次启动研究系统 V5.4｜研究、交易与持仓闭环")
st.caption("每日提交强势股 → 云端主池维护 → Python约500→150–200→30–40 → OpenAI研究层30–40→0–10只次日观察池")


def secret(name, default=""):
    try:
        return str(st.secrets.get(name, default)).strip()
    except Exception:
        return str(os.getenv(name, default)).strip()


def cfg():
    token = secret("GITHUB_PAT")
    repo = secret("GITHUB_REPO", "CyberAI2026/-akshare-mobile")
    branch = secret("GITHUB_BRANCH", "main")
    return GithubConfig(token, repo, branch) if token and repo else None


def merge_pools(a, b):
    parts = [x for x in (a, b) if x is not None and not x.empty]
    if not parts:
        return pd.DataFrame(columns=["股票代码", "股票名称"])
    return pd.concat(parts, ignore_index=True).drop_duplicates("股票代码", keep="first")


def gh_get_file(c, path):
    r = requests.get(f"{c.api}/contents/{path}", headers=gh_headers(c), params={"ref": c.branch}, timeout=20)
    if r.status_code != 200:
        return None
    obj = r.json(); dl = obj.get("download_url") if isinstance(obj, dict) else None
    if not dl: return None
    rr = requests.get(dl, timeout=30)
    return rr.content if rr.status_code == 200 else None


def gh_get_json(c, path):
    b = gh_get_file(c, path)
    if not b: return None
    try:
        import json
        return json.loads(b.decode("utf-8"))
    except Exception:
        return None


def gh_get_csv(c, path):
    b = gh_get_file(c, path)
    if not b: return pd.DataFrame()
    try: return pd.read_csv(io.BytesIO(b), dtype={"股票代码": str})
    except Exception: return pd.DataFrame()


def actions_url(c, workflow=None):
    return f"https://github.com/{c.repo}/actions/workflows/{workflow}" if workflow else f"https://github.com/{c.repo}/actions"


t1, t2, t3, t4, t5 = st.tabs(["🌙 盘后提交", "☁️ 主池/研究结果", "⏱️ 尾盘任务", "📒 交易与持仓", "⚙️ 设置与版本"])

with t1:
    st.subheader("每天只提交你今天看到的强势股")
    st.write("不用判断这些股票以前是否已经在池中。系统会与云端主池自动合并、按代码去重；明确指数会被隔离，不参与个股筛选。")
    up = st.file_uploader("上传今日强势股 Excel/CSV/XLS（30–40只或更多均可）", type=["xlsx", "xls", "csv"], key="dailybatch")
    text = st.text_area("也可直接粘贴（每行：代码 名称）", height=120, placeholder="600368 五洲交通\n601609 金田股份")
    batch = pd.DataFrame(columns=["股票代码", "股票名称"])
    try:
        a = pool_from_upload(up.name, up.getvalue()) if up else None
        b = pool_from_text(text) if text.strip() else None
        batch = merge_pools(a, b)
    except Exception as e:
        st.error(f"识别失败：{e}")

    stocks, indices = split_stock_and_indices(batch)
    if not batch.empty:
        st.success(f"共识别 {len(batch)} 条；其中个股 {len(stocks)} 只，隔离指数/非个股 {len(indices)} 条。")
        st.dataframe(stocks, use_container_width=True, height=360, hide_index=True)
        if not indices.empty:
            with st.expander("查看被隔离的指数/非个股"):
                st.dataframe(indices, use_container_width=True, hide_index=True)
    else:
        st.info("如果今天没有新增，也可以直接点击“只维护现有云端主池”。第一次V5运行会优先自动沿用V4最后保存的完整股票池。")

    c = cfg()
    col1, col2 = st.columns(2)
    if col1.button("提交今日强势股并启动盘后研究", type="primary", use_container_width=True, disabled=stocks.empty):
        if not c: st.error("尚未配置 GITHUB_PAT。")
        else:
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"v5_data/inbox/daily_{stamp}.csv"
                data = stocks.to_csv(index=False).encode("utf-8-sig")
                gh_put_bytes(c, path, data, f"V5 daily strong batch {stamp}")
                gh_put_bytes(c, "v5_data/inbox/latest_daily_batch.csv", data, f"V5 latest daily batch {stamp}")
                st.success("已提交。可以关闭Safari；后台会维护主池、生成30–40只研究包，并调用OpenAI形成0–10只次日观察池。")
                st.link_button("查看盘后任务", actions_url(c, AFTER_CLOSE_WORKFLOW), use_container_width=True)
            except Exception as e: st.error(f"提交失败：{e}")

    if col2.button("今天无新增：只维护现有云端主池", use_container_width=True):
        if not c: st.error("尚未配置 GITHUB_PAT。")
        else:
            try:
                gh_dispatch(c, AFTER_CLOSE_WORKFLOW, {"batch_path": ""})
                st.success("已启动现有主池的盘后研究；完成30–40只研究包后会继续调用OpenAI。")
                st.link_button("查看盘后任务", actions_url(c, AFTER_CLOSE_WORKFLOW), use_container_width=True)
            except Exception as e: st.error(f"触发失败：{e}")

with t2:
    st.subheader("云端主池与最新30–40只研究包")
    c = cfg()
    if not c:
        st.warning("配置 GITHUB_PAT 后可读取云端结果。")
    else:
        if st.button("刷新云端状态", type="primary"):
            st.rerun()
        summary = gh_get_json(c, "v5_data/latest/latest_after_close.json")
        master = gh_get_csv(c, "v5_data/latest/current_master_pool.csv")
        pool30 = gh_get_csv(c, "v5_data/latest/research_pool_30.csv")
        obs = gh_get_csv(c, "v5_data/latest/observation_pool.csv")
        obs_meta = gh_get_json(c, "v5_data/latest/observation_pool_meta.json")
        if summary:
            a,b,c1,d = st.columns(4)
            a.metric("当前云端主池", summary.get("master_count", "-"))
            b.metric("一级", summary.get("stage1", "-"))
            c1.metric("30–40只研究包", summary.get("stage2_research_pool", "-"))
            d.metric("AI观察池", summary.get("observation_pool_count", "-"))
            st.caption(f"完成时间：{summary.get('completed_cn','-')}｜{summary.get('engine','-')}｜耗时 {summary.get('elapsed_minutes','-')} 分钟｜Python采用30–40只软容量，OpenAI再形成观察池")
            st.caption(
                f"本次主池：新增 {summary.get('daily_new_count',0)}｜重新激活 {summary.get('daily_reactivated_count',0)}｜"
                f"新淘汰 {summary.get('daily_eliminated_count',0)}｜冷却 {summary.get('cooling_count',0)}"
            )
            sv=summary.get("sector_validation",{}) or {}
            st.caption(f"板块数据：{sv.get('status','-')}｜送入AI：{'是' if sv.get('ai_enabled') else '否'}｜缓存：{summary.get('cache_summary',{})}")
        else:
            st.info("尚未生成V5盘后结果。")
        if not master.empty:
            st.markdown(f"#### 当前云端主池（{len(master)}只）")
            st.dataframe(master, use_container_width=True, height=330, hide_index=True)
        if not pool30.empty:
            st.markdown(f"#### 最新AI研究输入池（{len(pool30)}只）")
            st.caption("这30–40只是OpenAI研究输入，不是买入名单。")
            st.dataframe(pool30, use_container_width=True, height=360, hide_index=True)
        if obs_meta:
            st.markdown(f"#### 次日AI观察池（{obs_meta.get('observation_count', 0)}只）")
            st.caption(f"生成交易日：{obs_meta.get('generated_trade_date','-')} → 适用交易日：{obs_meta.get('target_trade_date','-')}｜模型：{obs_meta.get('model','-')}")
            ma=obs_meta.get("market_assessment",{}) or {}
            if ma:
                st.info(f"市场风险：{ma.get('risk_level','-')}｜{ma.get('next_day_aggressiveness','-')}｜{ma.get('summary','')}")
            if not obs.empty:
                st.dataframe(obs, use_container_width=True, height=360, hide_index=True)
            else:
                st.warning("OpenAI本次选择0只，属于允许结果，不会强行凑数。")
        st.link_button("打开GitHub结果目录", f"https://github.com/{c.repo}/tree/{c.branch}/v5_data", use_container_width=True)

with t3:
    st.subheader("14:40 / 14:45 尾盘任务")
    st.write("V5.3已把尾盘任务从盘后研究中彻底拆开。定时任务只负责读取‘明确标记给今天使用’的≤10只观察池；没有有效观察池或日期不符就安全退出。")
    st.info("V5.3盘后OpenAI生成带目标交易日期的0–10只观察池；尾盘任务只接受日期锁通过的观察池，并在14:45调用OpenAI做最终0–2确认，输出买入区间、总体/个股仓位和结构止损参考。")
    c = cfg()
    if c:
        if st.button("手动测试尾盘任务（安全校验）", use_container_width=True):
            try:
                gh_dispatch(c, TAIL_WORKFLOW, {"manual": "true"})
                st.success("已触发。若没有今天有效观察池，它会安全退出，不会读取旧测试池。")
            except Exception as e: st.error(f"触发失败：{e}")
        st.link_button("查看尾盘Workflow", actions_url(c, TAIL_WORKFLOW), use_container_width=True)
    st.caption("正式定时：工作日 UTC 06:40 = 北京时间14:40。GitHub cron可能有排队延迟，因此未来仍保留手动备用触发。")

with t4:
    st.subheader("加密交易台账与当前持仓")
    st.caption("盘后录入实际买卖成交。后台只用仍有持仓的股票代码阻止重复推荐；成交价、数量、金额和成本不会送入OpenAI。")
    c = cfg()
    trade_key = secret("TRADING_DATA_KEY")
    trade_password = secret("TRADING_UI_PASSWORD")

    if not c:
        st.warning("尚未配置 GITHUB_PAT，无法读取或保存加密交易台账。")
    elif not trade_key or not trade_password:
        st.warning("交易台账尚未启用。请先在 Streamlit Secrets 配置 TRADING_DATA_KEY 和 TRADING_UI_PASSWORD，并在 GitHub Actions Secrets 配置同一 TRADING_DATA_KEY。")
        st.info("在密钥配置完成前，本页不会接收交易数据，避免把个人成交信息写入公开仓库明文。")
    else:
        if "trade_access_ok" not in st.session_state:
            st.session_state.trade_access_ok = False
        if "trade_access_attempts" not in st.session_state:
            st.session_state.trade_access_attempts = 0

        if not st.session_state.trade_access_ok:
            access_password = st.text_input("交易台账访问口令", type="password", key="trade_access_password")
            locked = st.session_state.trade_access_attempts >= 5
            if st.button("进入交易台账", type="primary", disabled=locked):
                if hmac.compare_digest(access_password, trade_password):
                    st.session_state.trade_access_ok = True
                    st.session_state.trade_access_attempts = 0
                    st.rerun()
                else:
                    st.session_state.trade_access_attempts += 1
                    st.error("访问口令不正确。")
            if locked:
                st.error("本次会话连续失败5次，请关闭页面后重新进入。")
        else:
            top_left, top_right = st.columns([4, 1])
            top_left.success("交易台账已解锁；数据仅在本次页面会话中解密。")
            if top_right.button("退出台账", use_container_width=True):
                st.session_state.trade_access_ok = False
                st.rerun()

            ledger_error = None
            try:
                encrypted_blob = gh_get_file(c, TRADE_LEDGER_PATH)
                transactions = decrypt_transactions(encrypted_blob, trade_key) if encrypted_blob else empty_transactions()
            except Exception as exc:
                ledger_error = str(exc)
                transactions = empty_transactions()
                st.error(f"无法读取交易台账：{exc}")

            if ledger_error is None:
                name_master = gh_get_csv(c, "v5_data/reference/a_share_code_name_master.csv")
                name_map = {}
                if not name_master.empty and {"股票代码", "股票名称"}.issubset(name_master.columns):
                    for _, name_row in name_master.iterrows():
                        try:
                            name_map[normalize_code(name_row["股票代码"])] = str(name_row["股票名称"]).strip()
                        except Exception:
                            pass

                positions = build_positions(transactions)
                active_positions = positions[positions["持仓数量"] > 0].copy() if not positions.empty else positions
                m1, m2, m3 = st.columns(3)
                m1.metric("当前持仓股票", len(active_positions))
                m2.metric("当前持仓股数", int(active_positions["持仓数量"].sum()) if not active_positions.empty else 0)
                m3.metric("累计交易记录", len(transactions))
                if not active_positions.empty:
                    st.markdown("#### 当前持仓")
                    st.dataframe(active_positions, use_container_width=True, hide_index=True)
                else:
                    st.info("当前没有已登记持仓。")

                manual_tab, upload_tab, history_tab = st.tabs(["手工录入", "批量上传", "交易历史"])
                with manual_tab:
                    with st.form("manual_trade_form", clear_on_submit=True):
                        a1, a2, a3 = st.columns(3)
                        trade_date = a1.date_input("交易日期", value=datetime.now(CN_TZ).date())
                        trade_time = a2.time_input("交易时间", value=datetime.now(CN_TZ).time().replace(microsecond=0))
                        account = a3.text_input("账户", value="默认账户")
                        b1, b2, b3 = st.columns(3)
                        side = b1.selectbox("操作", ["买入", "卖出"])
                        code = b2.text_input("股票代码", placeholder="600801")
                        manual_name = b3.text_input("股票名称（可留空自动回填）")
                        c1, c2, c3 = st.columns(3)
                        price = c1.number_input("成交价格", min_value=0.0, step=0.01, format="%.4f")
                        quantity = c2.number_input("成交数量（股）", min_value=0, step=100)
                        fee = c3.number_input("手续费", min_value=0.0, step=0.01, format="%.2f")
                        note = st.text_input("备注（可选）")
                        submitted = st.form_submit_button("确认并加密保存", type="primary", use_container_width=True)
                    if submitted:
                        try:
                            normalized_code = normalize_code(code)
                            current_name = name_map.get(normalized_code, manual_name.strip())
                            if not current_name:
                                raise ValueError("代码名称主表没有匹配结果，请手工填写股票名称")
                            incoming = normalize_transactions(pd.DataFrame([{
                                "交易日期": trade_date, "交易时间": trade_time, "账户": account,
                                "操作": side, "股票代码": normalized_code, "股票名称": current_name,
                                "成交价格": price, "成交数量": quantity, "手续费": fee, "备注": note,
                            }]))
                            updated = append_transactions(transactions, incoming)
                            if len(updated) == len(transactions):
                                st.info("这笔完全相同的记录已经存在，本次未重复写入。")
                            else:
                                gh_put_bytes(c, TRADE_LEDGER_PATH, encrypt_transactions(updated, trade_key), "Update encrypted private trade ledger")
                                st.success(f"已加密保存：{side} {normalized_code} {current_name}，成交金额 {float(price) * int(quantity):,.2f} 元。")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"保存失败：{exc}")

                with upload_tab:
                    template = pd.DataFrame(columns=["交易日期", "交易时间", "账户", "操作", "股票代码", "股票名称", "成交价格", "成交数量", "成交金额", "手续费", "备注"])
                    st.download_button("下载批量录入模板CSV", template.to_csv(index=False).encode("utf-8-sig"), file_name="trade_import_template.csv", mime="text/csv")
                    trade_upload = st.file_uploader("上传成交记录 Excel/CSV/XLS", type=["xlsx", "xls", "csv"], key="tradebatch")
                    prepared = None
                    if trade_upload:
                        try:
                            raw_bytes = trade_upload.getvalue()
                            if trade_upload.name.lower().endswith(".csv"):
                                try:
                                    raw_trades = pd.read_csv(io.BytesIO(raw_bytes), dtype={"股票代码": str}, encoding="utf-8-sig")
                                except UnicodeDecodeError:
                                    raw_trades = pd.read_csv(io.BytesIO(raw_bytes), dtype={"股票代码": str}, encoding="gb18030")
                            else:
                                raw_trades = pd.read_excel(io.BytesIO(raw_bytes), dtype={"股票代码": str})
                            prepared = normalize_transactions(raw_trades)
                            for idx, trade_row in prepared.iterrows():
                                if not str(trade_row["股票名称"]).strip():
                                    prepared.at[idx, "股票名称"] = name_map.get(trade_row["股票代码"], "")
                            st.dataframe(prepared, use_container_width=True, hide_index=True)
                        except Exception as exc:
                            st.error(f"文件识别失败：{exc}")
                    if st.button("确认导入并加密保存", type="primary", disabled=prepared is None or prepared.empty, use_container_width=True):
                        try:
                            unnamed = prepared[prepared["股票名称"].astype(str).str.strip().eq("")]
                            if not unnamed.empty:
                                raise ValueError("以下代码无法自动补全名称：" + "、".join(unnamed["股票代码"].tolist()))
                            updated = append_transactions(transactions, prepared)
                            added = len(updated) - len(transactions)
                            if added <= 0:
                                st.info("上传内容均已存在，本次未重复写入。")
                            else:
                                gh_put_bytes(c, TRADE_LEDGER_PATH, encrypt_transactions(updated, trade_key), "Update encrypted private trade ledger")
                                st.success(f"已加密导入 {added} 笔交易记录。")
                                st.rerun()
                        except Exception as exc:
                            st.error(f"导入失败：{exc}")

                with history_tab:
                    if transactions.empty:
                        st.info("尚无交易历史。")
                    else:
                        display_columns = [col for col in TRANSACTION_COLUMNS if col != "交易ID"]
                        st.dataframe(transactions[display_columns].sort_values(["交易日期", "交易时间"], ascending=False), use_container_width=True, hide_index=True)
                        with st.expander("查看已清仓汇总"):
                            closed = positions[positions["持仓数量"] == 0] if not positions.empty else positions
                            st.dataframe(closed, use_container_width=True, hide_index=True)


with t5:
    st.subheader("一次性设置与当前开发边界")
    st.markdown("""
当前阶段已经实现/准备实现：

- V4旧池自动迁移到V5云端主池；以后每天只提交当天30–40只强势股。
- 指数与个股彻底隔离，避免000001/000688之类的代码歧义污染筛选。
- 全局历史缓存+增量更新，避免每天重新下载500只完整历史。
- Python只负责约500→150–200→30–40，并给30–40只生成250日生命周期研究包；容量是软区间，不为凑数降低资格线。
- 盘后研究、14:40尾盘确认、每周备份拆成独立Workflow。
- 尾盘任务增加交易日、目标日期、上一交易日来源、池大小等安全锁。
- 每周五自动备份主池到GitHub。

**已接入：OpenAI API盘后30–40→0–10 + 14:45最终0→2，并通过 PushPlus 推送微信通知。**
""")
    st.code('''Streamlit Secrets 保持现有：\nGITHUB_PAT = "..."\nGITHUB_REPO = "CyberAI2026/-akshare-mobile"\nGITHUB_BRANCH = "main"''')
    st.warning("旧的 v4_background.yml 必须去掉 schedule；V5安装包中已提供一个‘仅手动兼容版’覆盖文件，防止再次出现#9那种晚上误触发。")
