import io
import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from v5_core import GithubConfig, gh_dispatch, gh_headers, gh_put_bytes, pool_from_text, pool_from_upload, split_stock_and_indices

AFTER_CLOSE_WORKFLOW = "v5_after_close.yml"
TAIL_WORKFLOW = "v5_tail_confirmation.yml"
BACKUP_WORKFLOW = "v5_weekly_backup.yml"

st.set_page_config(page_title="A股二次启动研究系统 V5", page_icon="📈", layout="wide")
st.title("A股强势股二次启动研究系统 V5｜基础架构版")
st.caption("每日只提交当天发现的强势股 → 云端主池自动合并/去重/维护 → Python筛到30只研究包；OpenAI 30→≤10将在下一阶段接入")


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


t1, t2, t3, t4 = st.tabs(["🌙 盘后提交", "☁️ 主池/研究结果", "⏱️ 尾盘任务", "⚙️ 设置与版本"])

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
                gh_dispatch(c, AFTER_CLOSE_WORKFLOW, {"batch_path": path})
                st.success("已提交。可以关闭Safari；后台会维护主池并生成30只研究包。")
                st.link_button("查看盘后任务", actions_url(c, AFTER_CLOSE_WORKFLOW), use_container_width=True)
            except Exception as e: st.error(f"提交失败：{e}")

    if col2.button("今天无新增：只维护现有云端主池", use_container_width=True):
        if not c: st.error("尚未配置 GITHUB_PAT。")
        else:
            try:
                gh_dispatch(c, AFTER_CLOSE_WORKFLOW, {"batch_path": ""})
                st.success("已启动现有主池的盘后研究。")
                st.link_button("查看盘后任务", actions_url(c, AFTER_CLOSE_WORKFLOW), use_container_width=True)
            except Exception as e: st.error(f"触发失败：{e}")

with t2:
    st.subheader("云端主池与最新30只研究包")
    c = cfg()
    if not c:
        st.warning("配置 GITHUB_PAT 后可读取云端结果。")
    else:
        if st.button("刷新云端状态", type="primary"):
            st.rerun()
        summary = gh_get_json(c, "v5_data/latest/latest_after_close.json")
        master = gh_get_csv(c, "v5_data/latest/current_master_pool.csv")
        pool30 = gh_get_csv(c, "v5_data/latest/research_pool_30.csv")
        if summary:
            a,b,c1,d = st.columns(4)
            a.metric("当前云端主池", summary.get("master_count", "-"))
            b.metric("一级", summary.get("stage1", "-"))
            c1.metric("30只研究包", summary.get("stage2_research_pool", "-"))
            d.metric("本次耗时(分钟)", summary.get("elapsed_minutes", "-"))
            st.caption(f"完成时间：{summary.get('completed_cn','-')}｜{summary.get('engine','-')}｜Python正式停在30只")
        else:
            st.info("尚未生成V5盘后结果。")
        if not master.empty:
            st.markdown(f"#### 当前云端主池（{len(master)}只）")
            st.dataframe(master, use_container_width=True, height=330, hide_index=True)
        if not pool30.empty:
            st.markdown(f"#### 最新AI研究输入池（{len(pool30)}只）")
            st.caption("这30只不是最终推荐。下一阶段接OpenAI API后，由研究层从这里形成0–10只次日观察池。")
            st.dataframe(pool30, use_container_width=True, height=400, hide_index=True)
        st.link_button("打开GitHub结果目录", f"https://github.com/{c.repo}/tree/{c.branch}/v5_data", use_container_width=True)

with t3:
    st.subheader("14:40 / 14:45 尾盘任务")
    st.write("V5已把尾盘任务从盘后研究中彻底拆开。定时任务只负责读取‘明确标记给今天使用’的≤10只观察池；没有有效观察池或日期不符就安全退出。")
    st.info("当前基础架构版尚未接OpenAI，因此不会伪造≤10只观察池。接入API后，盘后AI会生成带目标交易日期的观察池，第二天14:40才会自动运行。")
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
    st.subheader("一次性设置与当前开发边界")
    st.markdown("""
当前阶段已经实现/准备实现：

- V4旧池自动迁移到V5云端主池；以后每天只提交当天30–40只强势股。
- 指数与个股彻底隔离，避免000001/000688之类的代码歧义污染筛选。
- 全局历史缓存+增量更新，避免每天重新下载500只完整历史。
- Python只负责约500→150→30，并给30只生成250日生命周期研究包。
- 盘后研究、14:40尾盘确认、每周备份拆成独立Workflow。
- 尾盘任务增加交易日、目标日期、上一交易日来源、池大小等安全锁。
- 每周五自动备份主池到GitHub。

**尚未接入：OpenAI API、30→≤10、14:45 0→2、微信推送。** 这些在基础架构验收稳定后再接，避免把数据/定时/API问题混在一起。
""")
    st.code('''Streamlit Secrets 保持现有：\nGITHUB_PAT = "..."\nGITHUB_REPO = "CyberAI2026/-akshare-mobile"\nGITHUB_BRANCH = "main"''')
    st.warning("旧的 v4_background.yml 必须去掉 schedule；V5安装包中已提供一个‘仅手动兼容版’覆盖文件，防止再次出现#9那种晚上误触发。")
