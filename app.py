import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from v4_core import (
    APP_VERSION, GithubConfig, gh_dispatch, gh_list_results, gh_put_bytes, gh_raw_url,
    pool_from_text, pool_from_upload
)

st.set_page_config(page_title="A股二次启动自动研究系统 V4",page_icon="📈",layout="wide")
st.title("A股强势股二次启动自动研究系统 V4")
st.caption("一次上传股票池 → 云端后台完成25/120/250三阶段 → 次日14:45实时+5分钟确认 → 可选OpenAI最终分析")


def secret(name,default=""):
    try: return str(st.secrets.get(name,default)).strip()
    except Exception: return os.getenv(name,default).strip()


def cfg():
    token=secret("GITHUB_PAT"); repo=secret("GITHUB_REPO","CyberAI2026/-akshare-mobile"); branch=secret("GITHUB_BRANCH","main")
    return GithubConfig(token,repo,branch) if token and repo else None


def merge_pools(a,b):
    parts=[x for x in (a,b) if x is not None and not x.empty]
    if not parts: return pd.DataFrame(columns=["股票代码","股票名称"])
    return pd.concat(parts,ignore_index=True).drop_duplicates("股票代码",keep="first")


t1,t2,t3,t4=st.tabs(["🚀 全流程", "⚡ 14:45确认", "☁️ 云端任务", "⚙️ 一次性设置"])

with t1:
    st.subheader("上传一次初始股票池")
    up=st.file_uploader("Excel/CSV（自动识别股票代码、股票名称列）",type=["xlsx","xls","csv"],key="fullpool")
    text=st.text_area("少量股票也可直接粘贴（每行：代码 名称）",height=120,placeholder="600368 五洲交通\n601609 金田股份")
    pool=pd.DataFrame(columns=["股票代码","股票名称"])
    err=""
    try:
        a=pool_from_upload(up.name,up.getvalue()) if up else None
        b=pool_from_text(text) if text.strip() else None
        pool=merge_pools(a,b)
    except Exception as e: err=str(e)
    if err: st.error(err)
    if not pool.empty:
        st.success(f"已识别 {len(pool)} 只股票；代码自动保留6位并去重。")
        st.dataframe(pool.head(30),use_container_width=True,height=260)
    else: st.info("上传股票池后即可提交。500只以上建议直接上传Excel/CSV。")

    c=cfg()
    if st.button("提交全流程云端任务",type="primary",use_container_width=True,disabled=pool.empty):
        if not c:
            st.error("尚未配置 GITHUB_PAT。V4正式后台模式需要一次性配置；请到“⚙️ 一次性设置”查看。")
        else:
            stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
            path=f"v4_data/inbox/pool_{stamp}.csv"
            data=pool.to_csv(index=False).encode("utf-8-sig")
            gh_put_bytes(c,path,data,f"V4 upload pool {stamp}")
            gh_put_bytes(c,"v4_data/inbox/latest_pool.csv",data,f"V4 latest pool {stamp}")
            gh_dispatch(c,"v4_automation.yml",{"job":"full","pool_path":path})
            st.success("任务已交给 GitHub 云端独立执行。现在可以关闭Safari、锁屏或去做别的事情；浏览器不再维持任务。")
            st.write(f"股票数：{len(pool)}；任务输入：`{path}`")

with t2:
    st.subheader("第二个交易日 14:45 实时确认")
    st.write("正式自动化由云端定时任务触发：读取上一轮≤10只观察池，抓取14:45实时快照与当天5分钟K线，再执行最终0–2只确认。")
    c=cfg()
    if st.button("现在手动触发一次14:45确认",use_container_width=True):
        if not c: st.error("尚未配置 GITHUB_PAT。")
        else:
            gh_dispatch(c,"v4_automation.yml",{"job":"1445","pool_path":""})
            st.success("已提交。任务在云端运行，页面可关闭。")
    st.caption("GitHub定时任务采用北京时间14:40预启动，脚本若提前启动会等待到14:45；GitHub Actions本身不承诺秒级准时，因此交易级严格定时后续可无缝迁移到专用Cron服务。")

with t3:
    st.subheader("云端结果")
    c=cfg()
    if not c:
        st.warning("配置GITHUB_PAT后，这里可以直接检查云端任务。")
    else:
        st.markdown(f"**仓库：** `{c.repo}`　**分支：** `{c.branch}`")
        st.link_button("打开 GitHub Actions",f"https://github.com/{c.repo}/actions",use_container_width=True)
        st.link_button("查看最新观察池",gh_raw_url(c,"v4_data/latest/observation_pool.csv"),use_container_width=True)
        st.link_button("查看最新14:45分析",gh_raw_url(c,"v4_data/latest/last_1445_analysis.md"),use_container_width=True)
        if st.button("刷新云端目录"):
            items=gh_list_results(c,"v4_data")
            st.json([{"name":x.get("name"),"type":x.get("type"),"url":x.get("html_url")} for x in items])

with t4:
    st.subheader("一次性配置")
    st.markdown("""
V4 的核心变化是：**真正执行任务的是 GitHub Actions，不是手机 Safari 会话。** 因此你点完以后可以离开半小时，任务仍继续。

在 Streamlit 的 **Manage app → Settings → Secrets** 增加：
```toml
GITHUB_PAT = "你的GitHub Personal Access Token"
GITHUB_REPO = "CyberAI2026/-akshare-mobile"
GITHUB_BRANCH = "main"
```
`GITHUB_PAT` 需要对这个仓库具有 Contents 写入和 Actions 触发权限。不要把 Token 写进代码或公开上传。

如果要让云端最终自动调用 OpenAI，在 GitHub 仓库 **Settings → Secrets and variables → Actions** 增加：
`OPENAI_API_KEY`。模型默认 `gpt-5.6-terra`，也可增加 `OPENAI_MODEL` 覆盖。

V4 把筛选规则放在 `v4_core.py`，抓取/任务基础设施与策略分离。以后规则研究更新，只升级 Strategy Version，不需要重新改整套网站。
""")
    st.info("第一次部署V4还需要把 app.py、v4_core.py、v4_cli.py、requirements.txt 和 .github/workflows/v4_automation.yml 一起放进仓库。")
