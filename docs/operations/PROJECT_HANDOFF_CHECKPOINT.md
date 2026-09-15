# 强势股二次启动研究 — 统一 Project Handoff / Checkpoint

## 0. 2026-09-16 正式窗口交接状态

- 旧Work窗口：已进入正式交接；本次checkpoint写入完成后永久转为只读，不再开启新的生产写入。
- 交接前main完整SHA：`b68dabaea8708e8888a48af1f5d4dced95846c4e`。
- queued Actions：0；in_progress Actions：0。
- 活动生产写锁：无。
- 已完成：2026-09-15盘后筛选、单次OpenAI恢复、正式PushPlus送达、反馈/板块归因、加密交易台账更新、上下文监测机制固化。
- 未完成但未获生产修改授权：验证3/3结构门槛与“3/3优先、2/3补充且API输入≤50”方案；只能由新窗口先做只读接管和方案分析。
- 最新可靠断点：所有已发生副作用均已落盘；没有需要恢复的运行中任务。
- 禁止重复：不得重放2026-09-15 OpenAI、PushPlus、盘后数据抓取或最新交易台账写入。
- 新窗口取得写权前必须重新读取main、Actions、状态文件、receipt和本文件，确认旧窗口只读且无任务冲突。
- 本次属于交接文档写入，不触发选股、OpenAI、PushPlus、交易、仓位、止损或止盈。
- 正式交接更新时间：2026-09-16 00:12 Asia/Shanghai。

## 1. 项目身份与长期目标

- 项目名称：强势股二次启动研究。
- 生产仓库：`CyberAI2026/-akshare-mobile`，默认分支 `main`。
- 总目标：把每日强势股名单经过25日、120日、250日和OpenAI研究层形成次日观察池；次日尾盘结合实时行情形成0–2只决策；持续维护真实交易、持仓去重、跟踪回测、市场/板块/观点数据和微信送达。
- 运行原则：T+1真实执行；右侧二次启动；允许0只；实际持仓不得重复推荐；所有外部调用与推送必须可审计、可恢复、幂等。

## 2. 长期 Project + 分阶段 Work 对话机制

本项目永久采用：

`长期 Project → Work A → checkpoint/handoff → Work B → checkpoint/handoff → Work C`

单个Work对话只承担一个阶段，不作为长期生产状态的唯一载体。

### 上下文监测阈值

- 约70%：压缩重复信息，确认checkpoint已更新，减少上下文累积。
- 约80%：进入交接准备；立即更新checkpoint，生成完整接管资料。
- 约85%：停止开启新的大型任务；先完成当前最小安全闭环，然后发出：
  “当前 Work 对话上下文已接近安全上限，建议现在在同一 Project 中新建一个 Work 对话继续。”
- 无准确百分比时，根据聊天长度、工具调用量、文件读取量、历史依赖和任务复杂度保守估计；宁可提前交接。

### 正式交接纪律

进入正式交接后，旧窗口不得开启新的生产写入，仅可：

1. 完成当前最小安全闭环；
2. 保存成果与验证证据；
3. 更新本文件及相关专项checkpoint；
4. 保存GitHub、运行日志、数据与任务状态；
5. 核对queued/in_progress任务；
6. 记录写锁与禁止重复的副作用；
7. 提醒用户在同一Project中新建Work对话。

当前产品未向本工作环境暴露“直接创建同一Project新Work对话”的可靠能力时，不得声称已创建；应由用户在当前Project中新建Work对话，并复制本文件中的标准接管指令。

## 3. 当前生产基线

- 基线核对时间：2026-09-16 00:05 Asia/Shanghai。
- 核对时main完整SHA：`36566aa793e91cf9aa8409bb224b7b5ee5961761`。
- 该SHA内容：更新加密私有交易台账；公开仓库中不得记录明文交易数据。
- 本checkpoint发布属于文档性后续提交；新窗口必须重新读取main完整SHA，不得仅依赖本处基线。
- 当前没有queued或in_progress GitHub Actions。
- 当前没有活动生产写锁；本次仅使用临时文档锁 `LOCK-20260916-project-handoff-policy`，发布并验证后关闭。

## 4. 最近关键提交

- `36566aa793e91cf9aa8409bb224b7b5ee5961761` — Update encrypted private trade ledger。
- `93beaba7a33c02d43d9c396cb7f2b9997b88d4ee` — V5 recommendation feedback 2026-09-15-2341。
- `614a5f87a493c6c8bf4ead425ada562e753edb69` — V5 sector attribution 2026-09-15-2337。
- `df16910987b5de76a14c041187b8890a1d8ed825` — V5 daily sector membership snapshot 2026-09-15。
- `bf61708fdfa6ec9d5e0cd380c4ea215800ed577d` — Close staged pre-AI recovery checkpoint。
- `bde8281b3a47df3e01b696cde0be5ee226996b9d` — 2026-09-15盘后+AI完成。
- `aa6c02e5075d8504f78e25bd47f068a206d0843f` — 分阶段生产runner加入≤50的OpenAI前置门禁。

## 5. 已完成并验证

- 2026-09-15盘后运行 `v5_data/runs/20260915_213543` 已完成，状态 `completed:completed`。
- 实际漏斗：689 → 408 → 159 → 97（生命周期合格）→ 15（3/3结构门禁）→ 1（次日条件观察）。
- 159行250日审计全部保存判定原因：
  - 15：`QUALIFIED_FOR_OPENAI`
  - 82：`STRUCTURE_NOT_MATURE`
  - 62：`MID_TERM_TREND_WEAK`
  - 空白原因：0
- OpenAI恢复run：`34984834690`，成功；模型 `gpt-5.6-terra`；输入50,832 tokens，输出1,764，总计52,596。
- 正式PushPlus送达成功；不得重放该次OpenAI或PushPlus。
- 次日观察池：1只条件观察，代码603011，目标交易日2026-09-16；不是直接买入指令。
- THS公共板块数据测试成功。
- 加密交易台账已通过Streamlit在线系统更新，页面持仓与交易历史核验通过；明文成交数据不得写入公开checkpoint。
- 交易台账最新加密文件blob在更新后已变化，提交为 `36566aa793e91cf9aa8409bb224b7b5ee5961761`。

## 6. 当前运行任务与外部服务

- queued Actions：0。
- in_progress Actions：0。
- 最近成功：
  - `34990046546` Recommendation Feedback and Sector Attribution。
  - `34989174099` Daily Sector Membership Library。
  - `34984834690` After-Close AI Recovery。
- GitHub：连接可用。
- Streamlit：交易台账页面可用，访问口令与Data Key配置有效。
- OpenAI API：最近一次调用成功。
- PushPlus：最近一次正式盘后送达成功。
- AKShare/公共行情源：东方财富连接仍可能间歇中断；新浪备用可用但也可能超时。
- Official Market Count Test最近在实时公共行情探测步骤失败；同一工作流内确定性数据层测试成功。不得把上游实时探测失败误判为本次筛选代码失败。

## 7. 已知故障与待修复/待验证事项

- 已知故障：Official Market Count实时数据源存在连接中断或超时；需要按上游故障处理，不要无条件重复运行。
- 策略待验证：当前97→15使用振幅收敛、流动性收敛、短期止跌3/3硬门槛。用户已提出该门槛可能过严。
- 下一研究问题：用历史样本比较“仅3/3”和“3/3优先、2/3补充且总输入≤50”两种方案的成功率、盈亏比、漏选率。
- 在用户明确要求修改前，不得擅自改变生产门槛。
- 尾盘、盘后和观点任务曾有延迟/漏推历史；处理任何异常前先核对任务状态、receipt和已保存产物，避免重复API与重复推送。

## 8. 重要文件与可靠断点

- 统一总checkpoint：`docs/operations/WORK_PROGRESS.md`。
- 本统一窗口接管文件：`docs/operations/PROJECT_HANDOFF_CHECKPOINT.md`。
- 观点专项checkpoint：`docs/operations/OPINION_TASK_CHECKPOINT.md`。
- 最新盘后状态：`v5_data/latest/latest_after_close.json`。
- 当前分阶段状态：`v5_data/staging/after_close_current.json`。
- 250日/OpenAI门禁审计：`v5_data/runs/20260915_213543/250d/pre_ai_gate_audit.csv`。
- 观察池元数据：`v5_data/latest/observation_pool_meta.json`。
- 加密交易台账：`v5_data/private/trades.enc`。
- 最新可靠断点：2026-09-15盘后、AI、PushPlus、交易台账、反馈与板块归因均已落盘；无运行中任务。

## 9. 不得重复执行

- 不得重放2026-09-15盘后OpenAI调用。
- 不得重发该次正式盘后PushPlus。
- 不得重复录入最新加密交易台账交易。
- 不得重新抓取已经保存的25日/120日/250日数据，除非新的交易日任务按正常调度需要。
- 不得因Official Market Count上游失败而反复触发生产筛选。
- 不得在未核对receipt、状态文件和Actions前手工重试任何定时任务。
- 不得让两个Work窗口同时持有同一事项的写锁。

## 10. 新窗口首先执行的只读验收

新Work对话必须按顺序：

1. 读取Project指令、本文件、`WORK_PROGRESS.md`和必要专项checkpoint。
2. 读取GitHub main当前完整SHA及最近commits；把本文件中的基线视为历史核对点。
3. 列出Actions并检查queued/in_progress。
4. 核对 `after_close_current.json`、`latest_after_close.json`、观察池meta及相关receipt。
5. 核对活动写锁；确认旧窗口已停止生产写入。
6. 识别已经完成的外部副作用，建立“不得重复”清单。
7. 先向用户报告：项目、生产基线、可靠断点、已完成、未完成、运行任务、重复风险、是否可取得写权、下一动作。
8. 只有确认无冲突后，才能取得或续接唯一写锁；不得从头重做分析。

## 11. 下一步动作

- 当前没有需要立即恢复的失败生产任务。
- 下一个正常生产动作由既有定时流程触发。
- 如继续讨论筛选规则，先只读分析3/3门槛与2/3补充方案；用户批准后再改生产代码。
- 如发生尾盘/盘后/观点异常，先读取最新状态和receipt，禁止盲目重跑。

## 12. 新Work对话标准接管指令

> 接管当前 Project 的上一 Work 对话。  
> 请读取本 Project 的最新 checkpoint / handoff 和已有项目上下文，  
> 先进行只读恢复检查，  
> 确认最近可靠断点、当前生产状态、活动任务和写锁状态。  
> 不要重复已经完成的工作。  
> 确认接管安全后，从最近可靠断点继续。  
> 继续遵守本 Project 已确定的所有长期运行、断点恢复、上下文监测和单写者规则。

## 13. 更新时间

- 2026-09-16 00:05 Asia/Shanghai。
- 文档锁状态：发布并验证后关闭。
