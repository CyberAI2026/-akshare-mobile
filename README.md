# A股行情抓取与质量校验工具

一个适合手机浏览器操作的 Streamlit + AKShare 小工具。

## 功能
- 25日粗筛数据抓取
- 120日结构筛选数据抓取（含5日成交量比，可选主要指数）
- 250日生命周期筛选数据抓取
- 股票代码/名称强制校验
- 重复日期、OHLC逻辑、成交量/成交额异常检查
- Excel 自动导出

## 本地运行
```bash
pip install -r requirements.txt
streamlit run app.py
```

浏览器会打开本地页面。电脑与手机在同一局域网时，也可用电脑局域网IP从手机访问。

## 云端部署（推荐）
可部署到 Streamlit Community Cloud、Render、Railway 或自己的云服务器。

最简单的 Streamlit Community Cloud 流程：
1. 创建 GitHub 仓库，把 `app.py` 和 `requirements.txt` 上传。
2. 登录 Streamlit Community Cloud。
3. 选择该仓库，入口文件填 `app.py`。
4. 部署后会得到一个网页地址，手机直接打开即可。

## 重要说明
AKShare 的上游数据源可能变化或临时限制访问。工具已做输入与结果校验，但仍建议每次先查看“数据质量校验表”，确认无异常后再用于策略研究。
