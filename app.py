import io
import os
from datetime import datetime

import pandas as pd
import requests
import streamlit as st

from v4_core import GithubConfig, gh_dispatch, gh_headers, gh_put_bytes, pool_from_text, pool_from_upload

WORKFLOW_FILE = "v4_background.yml"

st.set_page_config(page_title="A股二次启动自动研究系统 V4", page_icon="📈", layout="wide")
st.title("A股强势股二次启动自动研究系统 V4")
st.caption("上传一次股票池 → GitHub云端后台完成25/120/250三阶段 → 次日14:45实时+5分钟确认")


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


def gh_get_json(c, path):
    r = requests.get(f"{c.api}/contents/{path}", headers=gh_headers(c), params={"ref": c.branch}, timeout=20)
    if r.status_code != 200:
        return None
    obj = r.json()
    dl = obj.get("download_url") if isinstance(obj, dict) else None
    if not dl:
        return None
    rr = requests.get(dl, timeout=20)
    return rr.json() if rr.status_code == 200 else None


def gh_get_csv(c, path):
    r = requests.get(f"{c.api}/contents/{path}", headers=gh_headers(c), params={"ref": c.branch}, timeout=20)
    if r.status_code != 200:
        return pd.DataFrame()
    obj = r.json()
    dl = obj.get("download_url") if isinstance(obj, dict) else None
    if not dl:
        return pd.DataFrame()
    rr = requests.get(dl, timeout=20)
    if rr.status_code != 200:
        return pd.DataFrame()
    return pd.read_csv(io.BytesIO(rr.content), dtype={"股票代码": str})


def actions_url(c):
    return f"https://github.com/{c.repo}/actions/workflows/{WORKFLOW_FILE}"


t1, t2, t3, t4 = st.tabs(["🚀 全流程", "⚡ 14:45确认", "☁️ 任务/结果", "⚙️ 一次性设置"])

with t1:
    st.subheader("上传一次初始股票池")
    up = st.file_uploader("Excel/CSV（自动识别股票代码、股票名称列）", type=["xlsx", "xls", "csv"], key="fullpool")
    text = st.text_area("少量股票也可直接粘贴（每行：代码 名称）", height=120, placeholder="600368 五洲交通\n601609 金田股份")
    pool = pd.DataFrame(columns=["股票代码", "股票名称"])
    try:
        a = pool_from_upload(up.name, up.getvalue()) if up else None
        b = pool_from_text(text) if text.strip() else None
        pool = merge_pools(a, b)
    except Exception as e:
        st.error(f"股票池识别失败：{e}")

    if not pool.empty:
        st.success(f"已识别 {len(pool)} 只股票；代码已统一为6位并去重。")
        st.dataframe(pool.head(50), use_container_width=True, height=280)
    else:
        st.info("500只以上建议直接上传Excel/CSV；程序会自动识别股票代码和名称。")

    c = cfg()
    if st.button("启动完整后台分析", type="primary", use_container_width=True, disabled=pool.empty):
        if not c:
            st.error("尚未配置 GITHUB_PAT，请先完成“一次性设置”。")
        else:
            try:
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                path = f"v4_data/inbox/pool_{stamp}.csv"
                data = pool.to_csv(index=False).encode("utf-8-sig")
                gh_put_bytes(c, path, data, f"V4 upload pool {stamp}")
                gh_put_bytes(c, "v4_data/inbox/latest_pool.csv", data, f"V4 latest pool {stamp}")
                gh_dispatch(c, WORKFLOW_FILE, {"job": "full", "pool_path": path})
                st.success("任务已交给GitHub云端。现在可以关闭Safari、锁屏或去做别的事情。")
                st.code(path)
                st.link_button("查看云端任务", actions_url(c), use_container_width=True)
            except Exception as e:
                st.error(f"提交失败：{e}")

with t2:
    st.subheader("第二个交易日 14:45 实时确认")
    st.write("云端会读取上一轮≤10只观察池，抓取14:45实时快照与当日5分钟K线，再生成最终确认数据。")
    c = cfg()
    if st.button("现在手动触发14:45确认", use_container_width=True):
        if not c:
            st.error("尚未配置 GITHUB_PAT。")
        else:
            try:
                gh_dispatch(c, WORKFLOW_FILE, {"job": "1445", "pool_path": ""})
                st.success("已提交14:45确认任务。页面可以关闭。")
                st.link_button("查看云端任务", actions_url(c), use_container_width=True)
            except Exception as e:
                st.error(f"触发失败：{e}")
    st.caption("工作日北京时间14:40预启动，脚本若提前会等待到14:45；GitHub Actions不保证秒级准时。")

with t3:
    st.subheader("云端任务与最新结果")
    c = cfg()
    if not c:
        st.warning("配置 GITHUB_PAT 后，这里会显示最新运行结果。")
    else:
        if st.button("刷新状态", type="primary"):
            st.rerun()
        latest = gh_get_json(c, "v4_data/latest/latest_run.json")
        if latest:
            cols = st.columns(4)
            cols[0].metric("初始股票", latest.get("initial", "-"))
            cols[1].metric("一级结果", latest.get("stage1", "-"))
            cols[2].metric("二级结果", latest.get("stage2", "-"))
            cols[3].metric("三级观察池", latest.get("stage3", "-"))
            st.caption(f"最近完成：{latest.get('completed','-')}　策略版本：{latest.get('strategy','-')}")
        else:
            st.info("暂未读取到 latest_run.json。")
        obs = gh_get_csv(c, "v4_data/latest/observation_pool.csv")
        if not obs.empty:
            st.markdown("#### 最新≤10只观察池")
            st.dataframe(obs, use_container_width=True, hide_index=True)
        st.link_button("打开 GitHub Actions", actions_url(c), use_container_width=True)
        st.link_button("打开仓库结果目录", f"https://github.com/{c.repo}/tree/{c.branch}/v4_data", use_container_width=True)

with t4:
    st.subheader("一次性配置")
    st.markdown("""
V4 的后台任务由 **GitHub Actions** 执行，而不是手机 Safari 会话，所以提交后可以离开页面。

在 Streamlit：**Manage app → Settings → Secrets** 中加入：

```toml
GITHUB_PAT = "你的GitHub Personal Access Token"
GITHUB_REPO = "CyberAI2026/-akshare-mobile"
GITHUB_BRANCH = "main"
```

`GITHUB_PAT` 不要写进公开代码。它需要对该仓库具有 Contents 与 Actions 的读写权限。

OpenAI 分析层后续在 GitHub 仓库 **Settings → Secrets and variables → Actions** 中增加 `OPENAI_API_KEY`。
""")
    st.info("当前正式工作流文件：.github/workflows/v4_background.yml")
