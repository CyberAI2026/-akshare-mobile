# Strong Stock Production Operations — Unified Checkpoint

Updated: 2026-09-12 17:32 Asia/Shanghai

## 2026-09-12 takeover and reliability correction checkpoint

- Read-only takeover baseline: production `main`
  `13b87496ec89b12007762e708b1084ec981e0675`; assets `main`
  `3ede4b8deb9c8e77bd3add81a379e629fe1254f7`; no queued or in-progress Actions
  were present at the baseline check. Recheck immediately before any remote merge,
  deployment, or manual recovery.
- Sole executor: current maintenance account/current window. Active locks:
  `LOCK-20260910-limitup-25d-strategy-replay` (ST hard-rule closure only),
  `LOCK-20260909-cloudflare-ci-deploy`, and
  `LOCK-20260912-opinion-discovery-reliability`. No historical tail/opinion replay
  or duplicate external delivery is authorized.
- Latest natural after-close run `34683308527` completed from folder
  `v5_data/runs/20260912_162833`: uploaded active pool 672, 669 symbols with current
  25-session evidence, 3 stale/deferred, stage1 402, stage2 161, stage3 93, and one
  final OpenAI observation. The 25-session hard gate is already in production:
  402/669 had at least one board-specific actual limit-up and all 402 passed stage1;
  zero selected symbols lacked that evidence. Main board uses 10%, ChiNext/STAR 20%,
  and BSE 30%, with regulatory price rounding.
- ST hard-exclusion unit is saved locally in commit
  `8abdea55aa24d38b946962a8146c60834a6d7315`. New or existing names beginning with
  `ST`, `*ST`, `SST`, or `S*ST` cannot enter, remain in, or be reactivated into the
  current observation pool. `002743 ST富煌` was removed from both current-pool
  exports; the active count is now 671. The registry retains its single historical
  record as `已淘汰`, and `eliminated_archive.csv` records the reason and date rather
  than silently erasing history. Compilation, diff validation, and 46 deterministic
  tests passed; external calls in tests were mocked.
- Opinion discovery policy/parser unit is saved locally in commit
  `3de064437de4e192e7138d9091831062fc7d7209`. The project skill
  `.codex/skills/strong-stock-opinion-discovery/` now fixes the two tag IDs, bounded
  collection times, 22:00/15-article gate, same-source-set idempotency, article-page
  date/content validation, objective THS separation, and late-run business-date
  safety. The title parser now accepts full-year dotted/dashed/slashed dates such as
  `2026.9.11操作复盘` without misreading `26.9` as month/day. Twenty-five opinion and
  workflow reliability tests plus skill validation passed. No live discovery,
  OpenAI, or PushPlus action occurred.
- Independent scheduler expansion is saved locally in commit
  `0976d50122612241e5fee1e0ed9e876d82af93d0`. One Cloudflare Worker now routes
  tail dispatch at 14:26/14:31/14:35 on trading weekdays, opinion collection at
  20:30, every ten minutes from 21:00 through 21:50, final aggregation at 22:00,
  and a delivery fallback at 22:12 (all Asia/Shanghai). It checks active/recent
  Actions before dispatch; external opinion dispatches carry an explicit source
  date and do not acquire manual-force semantics. The 21:30 GitHub fallback also
  retains the previous business date when a delayed run starts before 06:00.
  Ten Worker tests, 27 opinion/workflow tests, YAML parsing, compilation, and diff
  validation passed. Deployment is still blocked until the three existing GitHub
  Actions secrets are configured and one `DEPLOY` run is explicitly performed.
- PR `#6` was squash-merged into production as
  `6dfe80b33c636e0c6f533addfa515b631b85035b`. Opinion validation run
  `34685913114` succeeded with only preflight/validate; discovery, article batches,
  aggregation, concept refresh, failure alert, OpenAI, and PushPlus were all skipped.
  THS public-sector checks `34685876806` and `34685913120` succeeded. Official
  market-count checks `34685876803` and `34685913122` failed without retry because
  both full-market snapshot candidates were unavailable: Eastmoney closed both
  connections and Sina timed out twice. Their saved artifacts show index histories,
  Legulegu cross-check, and Eastmoney limit/failed-limit pools succeeded; this is a
  non-blocking upstream snapshot acceptance issue, not evidence of a regression in
  the ST, opinion, or scheduler changes. No Actions remain queued or in progress.
- 2026-09-11 tail diagnosis: scheduled runs `34595324289`, `34595459197`, and
  `34595713585` did trigger, but GitHub did not start their prechecks until
  19:43/19:45/19:48 Asia/Shanghai. The safe-time gate correctly refused to fabricate
  a post-close recommendation. The independent Cloudflare dispatcher exists but is
  not deployed; this remains the direct reliability blocker.
- 2026-09-11 opinion diagnosis: run `34623365526` started around 00:40 on 2026-09-12,
  about 2h40 after the 22:00 target. Tag discovery found 55 candidates, deterministic
  article/date checks retained 21, and model quality validation retained 17. The
  PushPlus API accepted the request at 00:46 with short receipt
  `3e5ddb03704e417b9c95cafa2211a79b`; terminal WeChat receipt is unverified. The
  correct `#复盘`/`#每日复盘` topic endpoints were used; the late delivery is a
  scheduler failure, while a separate date-parser defect may reject titles written
  as `YYYY.M.D复盘` and still requires a tested correction.
- Current reliable checkpoint: ST hard-rule/current-pool cleanup is closed at local
  commit `8abdea55...`; opinion parser and reusable project skill are closed at
  `3de06443...`; scheduler expansion and rollover repair are closed at
  `0976d501...`, and all three units are live at production commit `6dfe80b33...`.
  No live article fetch, OpenAI request, PushPlus request, historical replay, or
  Cloudflare deployment occurred in this correction. Next unit is credential-gated
  Cloudflare deployment, health/cron verification, and natural-cycle acceptance.

## Overall goal

Operate and maintain the production recommendation system reliably while preserving
single-writer ownership, idempotent external effects, auditable recovery, and strict
separation between engineering reliability and trading strategy.

Canonical long-work policy:
`.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.

## Current production baseline

- Production repository: `CyberAI2026/-akshare-mobile`.
- Production `main` before the 2026-09-10 after-close incident repair:
  `20308a749d543e63e2f5ee99659d3358d2cb479e`.
- Current production `main` after completed recovery and feedback refresh:
  `42f887f2b4a99b586ea6b0d3ee4670590bf8ed9f`.
- Assets repository: `CyberAI2026/strong-stock-research-assets`.
- Assets `main` last reverified in this resumed operation:
  `8b174581cef6e7ffc3906d089ede69da04a203da`.
- Queued/in-progress GitHub Actions at recovery check: none.
- Active manual production write lock at recovery check: none.

## Completed and verified

- The 2026-09-08 opinion recovery is complete: 33 quality articles and 10 objective
  THS concept series were saved; no rerun is authorized for that source date.
- Opinion publication requires 22:00 and at least 15 quality articles; delivery is
  idempotent by the quality-approved source collection.
- Opinion hardening commit `d3e9b9ad1bb9086d672f84bca67fcc8ae1cfca4a`
  passed validation-only run `34312385306` with zero OpenAI and PushPlus calls.
- The missed 2026-09-09 tail run is recorded without post-close fabrication.
- Both ChatGPT tail-watchdog prompts were hardened in place; no duplicate automation
  was created and no production side effect occurred during that correction.
- The canonical nine-rule resumable-operations skill was committed as
  `94d963c045596a52820ebd333efe66a7e6ffca55`; skill validation and
  `git diff --check` succeeded, and the commit started no GitHub Actions run.
- External scheduler implementation commit:
  `e371ae2a4e5011eeeaf6576f22ee6735ca914b50`.
- Duplicate late-alert correction commit:
  `bb4656cda80f633581d59547791d5a2b7bbfcd32`.
- Local verification: Python compilation, 41 deterministic Python tests, 6 Worker
  idempotency tests, workflow YAML parsing, and `git diff --check` all succeeded.
- Tail validation-only push run `34347518574` succeeded; precheck, finalize, and
  failure-alert were skipped, with zero OpenAI and PushPlus calls.
- Recommendation D+3 defect repair commit:
  `654bff49f7d542851be61d6f8bac130385e8afb4`. The defect was that cached bars use
  `收盘价`/`最低价` while feedback evaluation only accepted `收盘`/`最低`; therefore the
  2026-09-04 recommendation was incorrectly recorded as `推荐日收盘缺失` and the
  2026-09-09 scheduled report showed a zero D+3 sample.
- The repair normalizes cached/raw bar columns, evaluates cache before importing
  the live-data dependency, adds durable delivery-key receipts, and refreshes
  feedback after the final after-close cache commit. It does not change selection,
  watch-pool, position, capital, stop-loss, or take-profit strategy.
- Ten deterministic recommendation-feedback tests, workflow YAML parsing,
  `git diff --check`, and a real cached-data no-notify rebuild passed. The rebuild
  matured `600801 华新建材` on D+3 (2026-09-09) at `25.10`, return `+1.2097%`, with
  no three-day stop touch.
- Validation runs `34365360439` and `34365361053` completed successfully with no
  OpenAI call and no PushPlus request. Run `34365360439` committed the corrected
  recommendation artifacts.
- One explicit idempotent correction was requested by commit
  `b63581f334dc12cff29126d6789c1a455fc34412`; run `34365758249` succeeded and
  committed its durable receipt in `512c30f367ddf96f7d654ce9aa3815995eab586f`.
  No second request with the same delivery key is permitted.
- D+3 repair checkpoint commit `8941b270a2652049e228ad78f17d18f399271dff`
  was followed by routine sector-library run `34367940059` and no-notify feedback
  refresh run `34369050929`; both succeeded. Their data commits advanced `main` to
  `0a830869c09c2faf35c22115782327741bd25165` without OpenAI or PushPlus calls.

Task-specific detail: `docs/operations/OPINION_TASK_CHECKPOINT.md`.

## In progress

- `LOCK-20260909-cloudflare-ci-deploy`: the ChatGPT Cloudflare plugin installation
  failed although its catalog status is enabled/available and it has no unresolved
  dependencies. A non-interactive GitHub Actions deployment path is being added so
  credentials can stay in repository Secrets rather than chat or a temporary Work
  environment. No deployment has been triggered.
- `LOCK-20260910-limitup-25d-strategy-replay`: user-authorized strategy revision.
  Require at least one actual board-specific limit-up in the latest 25 completed
  trading sessions including the generated trade date; remove fixed minimum/target
  counts from the 25-day, 120-day, and 250-day filters; replace the programmatic
  after-close observation-pool cap of 3 with a hard maximum of 10. The current
  652-symbol active pool will be recomputed once after deterministic validation.
  Replay may use at most one OpenAI call and defaults to no PushPlus delivery so the
  already accepted 2026-09-10 formal message is not duplicated.
  Unit 1 is durable: board-specific rounded limit prices and raw-close evidence were
  committed in `3d0b92f0f572ce35f78e730d205534877eb75eb0`; deterministic coverage for
  main-board 10%, ChiNext/STAR 20%, BSE 30%, and low-price rounding was committed in
  `ebc3a7d7ebd970371a33607c9c84f2bb86fa4224`. Ten targeted tests passed with no
  external OpenAI or PushPlus call. Next unit: remove stage count forcing and change
  the post-model observation cap from 3 to 10.
  Unit 2 is verified on branch `codex/limitup-25d-v07-20260910`: every stale active
  cache is attempted; 26 closes support exactly 25 session-to-session limit checks;
  all eligible names advance through 25d, 120d, and 250d without count targets;
  250d now filters rather than audit-only pass-through; the post-model hard cap is
  10; and a zero-candidate path saves a valid empty pool without OpenAI. Manual
  strategy replay supports `notify=false`, which suppresses both formal and failure
  PushPlus messages. Python compilation, workflow YAML parsing, `git diff --check`,
  29 targeted tests, and 106 broader non-historical operational tests passed. Test
  OpenAI/PushPlus output was mocked. Next unit: merge once to main, accept the single
  validation-only workflow, then dispatch exactly one no-notify replay.
- `LOCK-20260910-after-close-25d-recovery` is closed. The repaired recovery run
  `34471878484` completed successfully through feedback refresh. No manual rerun is
  pending and the failure-alert job for the successful run was skipped.

## Pending

- Select and deploy an external reliable scheduler for tail workflow dispatch,
  retaining GitHub cron and ChatGPT checks as fallbacks/monitors.
- Store `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and the repository-scoped
  `TAIL_DISPATCH_GITHUB_TOKEN` as GitHub Actions secrets; never commit or paste them.
- Manually dispatch `Deploy Cloudflare Tail Scheduler` with confirmation `DEPLOY`.
- Deploy and inspect the Worker health endpoint, observability, and three cron
  triggers at 14:26, 14:31, and 14:35 Asia/Shanghai.
- Treat data-test runs `34347519957` and `34347518649` as `retry` only if a later
  production task depends on fresh live-source acceptance; do not rerun them merely
  to turn the checks green.
- Verify the next natural tail cycle without backfilling the missed date.
- Verify the next natural 20:30-22:15 opinion cycle.

## Files in this unit

- `.codex/skills/strong-stock-resumable-operations/SKILL.md`.
- `.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.
- `.codex/skills/strong-stock-resumable-operations/agents/openai.yaml`.
- `docs/operations/WORK_PROGRESS.md`.
- `.github/workflows/v5_tail_confirmation.yml`.
- `v5_cli.py` and `tests/test_tail_stages.py`.
- `infrastructure/cloudflare-tail-scheduler/`.
- `research/recommendation_feedback.py`.
- `tests/test_recommendation_feedback.py`.
- `.github/workflows/v5_recommendation_feedback.yml`.
- `.github/workflows/v5_after_close.yml`.
- `v5_data/control/feedback_correction_trigger.json`.
- `v5_data/feedback/delivery_receipts.json`.
- `.github/workflows/deploy_cloudflare_tail_scheduler.yml`.

## Important artifacts and receipts

- Opinion source date 2026-09-08: 33 formal-quality articles.
- THS objective concept facts: 10 ready, 0 failed.
- Latest final PushPlus business receipt: `request_accepted`, short code
  `e59ae4a019d34db8a466603c8c9acec3`; WeChat terminal receipt remains unverified.
- Tail decision and close-audit artifacts remain dated 2026-09-04; no 2026-09-09
  tail OpenAI call or PushPlus request exists.
- Delayed schedule run `34347240627` started at 19:45 and was rejected by the safe
  time gate at 19:47. It made no OpenAI call and produced no recommendation, but
  sent two accepted failure-notification requests under the old duplicate-alert
  behavior. The first short code was `7e8402e1f789438ca33773ec007c3cc6`;
  neither API acceptance proves terminal WeChat receipt. The duplicate path is
  removed by `bb4656cda80f633581d59547791d5a2b7bbfcd32`.
- The original incorrect 2026-09-09 feedback request was accepted under short code
  `120236caa21a4922968952c6bd23b6bc`; it reported zero D+3 samples and is superseded,
  not silently overwritten.
- The correction request used delivery key
  `feedback-correction-2026-09-09-d3-schema-v1` and was accepted at 22:46 China time
  with short code `f50cf6d28d6a400aab2c62f8aa8a811f`. The persisted status is
  `request_accepted`; terminal WeChat delivery remains unverified.

## Known issues and risks

- GitHub scheduled workflows are best-effort and have delayed or failed to start.
- ChatGPT scheduled tasks are also not a hard-real-time production scheduler.
- No independent external scheduler is deployed yet.
- The ChatGPT Cloudflare plugin connection attempt failed. Its catalog metadata is
  available/enabled with no missing dependency, so the failure is recorded as a
  connector/OAuth installation issue; GitHub Actions deployment is the fallback.
- API acceptance does not prove terminal WeChat receipt.
- The D+3 cache-schema and refresh-order defects are repaired. The next natural
  recommendation-feedback cycle remains an acceptance check for the new chain;
  it is not authorization to replay the corrected 2026-09-09 delivery.
- The user confirmed the formal requirement is the 14:40 intraday tail notification,
  not a 16:40 post-close list.
- Shared-path validation run `34347519957` failed because Eastmoney closed both
  candidate requests; deterministic tests passed. Run `34347518649` failed because
  two THS responses ended prematurely; 8 of 10 tables succeeded. These transient
  source failures are independent of the scheduler implementation and are recorded
  without automatic rerun.

## Latest reliable checkpoint

The D+3 repair is committed through `654bff49f7d542851be61d6f8bac130385e8afb4`.
Corrected data and the one allowed correction receipt are durably committed through
`512c30f367ddf96f7d654ce9aa3815995eab586f`. Runs `34365360439`, `34365361053`,
and `34365758249` all succeeded; no run is queued or in progress. This repair used
zero OpenAI calls and exactly one correction PushPlus request. Its delivery key is
now protected against replay. The D+3 repair locks are closed.
`LOCK-20260909-cloudflare-ci-deploy` is active only for the deployment workflow and
documentation unit. The exact next action after its verified commit is user-side
creation of the three GitHub Actions secrets, followed by one confirmed deployment
run and natural-cycle acceptance.

## Rollback point

- Before the D+3 engineering repair:
  `dc724dcb0910fda903cd0609d0b35b05d91e7fc5`.

## 2026-09-10 After-Close 25-Day Incident

- Failed production run: `34468821550`; failed job: `102844755037`.
- The daily batch and immutable initialization completed. Commit
  `20308a749d543e63e2f5ee99659d3358d2cb479e` preserves the 652-symbol active pool,
  120-symbol daily batch, cache manifest, and run folder `20260910_185940`.
- Both bulk spot sources failed during initialization: Eastmoney closed the
  connection and Sina returned non-JSON HTML. The bounded per-symbol refresh then
  obtained current 25-day history for 148 of the planned 150 symbols.
- The hard 150-symbol capacity gate correctly refused to rank stale history. This
  failure is not a zero-stock observation-pool result.
- The 120-day, 250-day, market-context, AI-finalize, feedback-refresh, and formal
  after-close delivery jobs did not execute. OpenAI calls: 0. Formal PushPlus calls:
  0. One failure alert was already sent and must not be duplicated.
- Engineering correction: retry only failed history symbols once and sequentially;
  if the capacity gate still fails, persist successful cache updates, refresh QA,
  current manifest, shortfall, and state before raising. The minimum capacity and
  every screening/trading rule remain unchanged.
- Verification before production commit: 18 targeted tests and 102 broader
  non-historical operational tests passed; Python compilation, workflow-independent
  behavior, and `git diff --check` passed. Test OpenAI/PushPlus messages were mocked;
  no external call occurred.
- Latest reliable checkpoint: initialization data is committed at `20308a...`; the
  verified engineering patch is local and not yet in production. Next action: commit
  the patch atomically, verify validation-only Actions, then rerun only the failed
  job and its previously skipped downstream jobs after rechecking idempotency.
- Incident rollback point: `20308a749d543e63e2f5ee99659d3358d2cb479e`.

### Recovery correction record

- Engineering commit `b361cbc5d4b93ee4b3fb3dccae01bcc953414c9d` was created through
  the GitHub tree API, but the API did not inherit the supplied base tree. Its root
  contained only the five modified files (nine recursive tree entries), temporarily
  omitting the rest of the repository from `main`. The complete parent tree and all
  initialized production data remain intact at `20308a749d543e63e2f5ee99659d3358d2cb479e`.
- Failed-jobs attempt 2 checked out `b361cbc...` and stopped in `actions/setup-python`
  because `requirements.txt` was absent. The 25-day code did not run, no history was
  fetched, OpenAI calls were 0, and formal after-close PushPlus calls were 0.
- The non-idempotent `failure-alert` job sent another failure alert on attempt 2.
  This duplicate is recorded explicitly and requires a separate idempotency fix;
  no further failed-job rerun is allowed before that fix.
- Immediate next action: create a normal forward correction commit whose full tree
  reproduces the complete `20308a...` parent plus only the five verified incident
  repair files. Verify repository completeness before any workflow recovery.

### Completed recovery acceptance

- Forward correction commit `b0dd5596ce525ec81708e8fedb2af5acf63e507c`
  restored the complete repository tree and retained the five verified incident
  repair files. Required files including `requirements.txt` and both staged
  after-close workflows were reverified before the recovered pipeline advanced.
- Because the forward correction necessarily appeared as a wide path addition from
  the malformed parent, GitHub path filters started several workflows. The new
  after-close run `34471878484` became the sole recovery run; no third run was
  dispatched. An unintended historical-market workflow also ran to completion, but
  its outputs were not inspected, interpreted, or used by this operations window.
- Saved production run `v5_data/runs/20260910_193457` completed at
  2026-09-10 19:53:54 Asia/Shanghai in 18.95 minutes. The 25-day stage refreshed only
  29 remaining stale symbols, ranked 594 current symbols, and selected 197. All four
  120-day shards succeeded; aggregate selected 39. The 250-day stage retained the
  same 39-symbol research pool.
- Market context completed successfully. Sector flow was recorded separately as
  `实验性有警告`; it was disabled as AI evidence and did not masquerade as verified
  same-day concept performance.
- AI finalize made exactly one successful OpenAI call using `gpt-5.6-terra`:
  response `resp_002d03320acdd8e9006aa29a09efa887d1abfecb178d20ef41`,
  48,698 input tokens, 9,030 output tokens, 57,728 total tokens. It produced two
  conditional observation symbols for target trade date 2026-09-11: `600165` and
  `600368`. These remain a 14:40-14:45 confirmation pool, not a direct buy list.
- Formal PushPlus request succeeded once on attempt 1 with API receipt
  `6d64d6a046344907bd6760a1e1ab5dbc`. Persisted status is
  `pushplus_delivery_ok=true`; API acceptance still does not prove terminal WeChat
  receipt. The final feedback refresh was `--no-notify` and succeeded.
- Workflow run `34471878484` finished with every production stage successful and
  `failure-alert` skipped. Artifact `V5-after-close-34`, id `10150582374`, digest
  `sha256:05f5970d34a52b917e487292da85b8d52b02845c033903bd8002be55a2966f38`,
  is retained through 2026-09-24.
- Final recovery commits: AI result
  `e81b340e4510367c258a1bd5f5c45ddc30172e2b`; no-notify feedback refresh and current
  production baseline `42f887f2b4a99b586ea6b0d3ee4670590bf8ed9f`.
- Known follow-up: the inline after-close `failure-alert` is not idempotent across
  rerun attempts and produced a duplicate alert during failed attempt 2. Repair it
  as a separate engineering-only task before authorizing any failed-job rerun.
- Latest reliable checkpoint: production results, run metadata, observation pool,
  model evidence, API receipt, feedback refresh, and artifact are all durable at
  `42f887f2b4a99b586ea6b0d3ee4670590bf8ed9f`. No after-close recovery write lock or
  rerun remains active.


## Cloudflare Scheduler Deployment — 2026-09-12

- Operation lock `LOCK-20260909-cloudflare-ci-deploy` was resumed by the authorized
  current maintenance account after verifying production main
  `4e4a62c6a54b66faeae350d699c53e360f0031f7`, assets main
  `3ede4b8deb9c8e77bd3add81a379e629fe1254f7`, and zero queued/in-progress Actions.
- The user confirmed the three required repository Actions secrets were configured.
  Secret values were never read, displayed, written to chat, or committed.
- Exactly one deployment was dispatched: workflow run `34687460024`, job
  `103536842683`, event `workflow_dispatch`, conclusion `success`.
- The required-secret check succeeded, all 10 scheduler tests passed, and Cloudflare
  created and deployed Worker `strong-stock-tail-dispatcher`.
- Worker version: `3d3a16b4-26cf-49fc-ab4d-3888c7d457bf`.
- Health endpoint returned
  `{"status":"ok","timezone":"Asia/Shanghai","workflows":["tail","opinion","opinion-delivery"]}`.
- Active UTC cron triggers: `26,31,35 6 * * 1-5` (14:26/14:31/14:35 Shanghai
  weekday tail dispatch); `30 12 * * *` (20:30 opinion); `0,10,20,30,40,50 13 * * *`
  (21:00-21:50 opinion accumulation); `0 14 * * *` (22:00 opinion finalization);
  `12 14 * * *` (22:12 delivery fallback).
- No OpenAI or PushPlus call occurred during deployment. No stock-selection,
  observation-pool, position, capital, stop-loss, or take-profit rule changed.
- Idempotency checkpoint: do not repeat deployment run `34687460024`. The next
  acceptance units are the next natural opinion cycle and the next A-share trading
  day's natural tail cycle. API request acceptance remains distinct from terminal
  WeChat receipt.
- Lock status: `LOCK-20260909-cloudflare-ci-deploy` closed after successful
  deployment and health verification.
