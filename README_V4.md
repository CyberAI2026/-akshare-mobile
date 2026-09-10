# A股强势股二次启动自动研究系统 V4

## 目标体验

上传一次初始股票池 → 点击一次 → 关闭手机页面 → GitHub Actions 云端独立执行：

1. 25日粗筛：初始池 → 最多150只
2. 120日结构筛选：→ 最多30只
3. 250日生命周期筛选：→ 最多10只观察池
4. 第二个交易日14:45：抓实时快照 + 当天5分钟K线 → 最终0–2只确认

所有阶段结果自动保存到仓库 `v4_data/`。如果配置 `OPENAI_API_KEY`，三级复核和14:45最终确认会调用 OpenAI Responses API。

## 重要边界

- V4 的后台任务不依赖 Safari 会话；网页仅负责“下单/查看”。
- GitHub Actions 的定时计划不是交易所级实时调度，可能排队延迟。V4采用14:40预启动并在脚本内等待到14:45降低风险；若后续实测仍不够准，可把同一个 `v4_cli.py 1445` 无缝迁移到专用云Cron/任务服务。
- 当前 Strategy Version 为 `research_v0.4`：自动筛选使用已验证方向做“排序+宽松约束”，不是宣称已经得到最终稳定交易规则。策略层与抓取层分开，可持续替换。
- OpenAI API 不等于“ChatGPT登录网站”。是后台在数据完成后主动调用模型进行分析。

## 一次性部署

将以下文件放到仓库：
- `app.py`
- `v4_core.py`
- `v4_cli.py`
- `requirements.txt`
- `.github/workflows/v4_automation.yml`

Streamlit Secrets：
```toml
GITHUB_PAT = "..."
GITHUB_REPO = "CyberAI2026/-akshare-mobile"
GITHUB_BRANCH = "main"
```

GitHub Actions Secrets（可选但最终自动AI需要）：
- `OPENAI_API_KEY`

GitHub Actions Variable（可选）：
- `OPENAI_MODEL`，不填默认 `gpt-5.6-terra`

## Excel/CSV 股票池识别

程序自动寻找类似以下列名：
- 股票代码 / 证券代码 / 代码 / code / symbol
- 股票名称 / 证券简称 / 名称 / name

代码统一转为6位字符串并去重；支持约500只或更多批量输入。
