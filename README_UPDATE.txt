V4 研究引擎审计更新（research_v0.4.1）

本补丁只替换：
- v4_core.py
- v4_cli.py

不需要修改：
- app.py
- requirements.txt
- .github/workflows/v4_background.yml

新增：
1. 25/120/250 每一级 result.xlsx 均增加“筛选审计”工作表。
2. 每一级同时生成 stage_audit.csv。
3. 每只股票记录阶段排名、本阶段入选、决策说明。
4. 分数拆成可审计的贡献项，而不是只输出一个总分。
5. 三级增加生命周期标签与风险提示。
6. summary.json 写入三个阶段最终代码列表与 engine=V4.1-auditable。
7. 策略版本升级为 research_v0.4.1；系统名称仍保持 V4。

重要：这不是把研究规则彻底写死。二三级仍以排序压缩为主，避免把尚未稳定验证的参数变成硬阈值。
