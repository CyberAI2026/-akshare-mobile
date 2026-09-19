# Strong Stock Production Operations — Unified Checkpoint

## 2026-09-16 formal Work-window handoff

- Outgoing Work window has completed its smallest safe closure and is now
  read-only. It must not perform further production writes.
- Pre-handoff main: `b68dabaea8708e8888a48af1f5d4dced95846c4e`.
- Durable handoff commit:
  `1512bb1e6c592b88888f6042624125ed8ba244b5`.
- At the final read-only check: queued Actions 0; in-progress Actions 0; active
  production lock none.
- Completed side effects are persisted. Do not repeat the 2026-09-15 OpenAI
  request, formal PushPlus delivery, saved market-data stages, or latest
  encrypted-ledger update.
- Pending work is analysis only until separately authorized: compare the current
  3/3 structural gate with a 3/3-priority plus 2/3 supplemental pool capped at
  50.
- Successor window must read
  `docs/operations/PROJECT_HANDOFF_CHECKPOINT.md`, re-check current main and
  Actions, and report its read-only takeover assessment before acquiring a
  write lock.
- This checkpoint update is documentation-only and triggers no production
  workflow, API, notification, trading, sizing, stop-loss, or take-profit action.

Updated: 2026-09-16 00:13 Asia/Shanghai

## 2026-09-16 Project/Work automatic handoff mechanism

- Long-term mechanism active: Project-level continuity + phased Work conversations +
  durable automatic handoff.
- Unified handoff file:
  `docs/operations/PROJECT_HANDOFF_CHECKPOINT.md`.
- Context policy: approximately 70% compress/update checkpoint; 80% prepare
  handoff; 85% stop new large tasks, close the smallest safe unit, persist all
  state, and instruct the user to open a new Work conversation in the same
  Project.
- If an exact context percentage is unavailable, estimate conservatively from
  conversation length, tool/file volume, historical dependency, and task
  complexity.
- New Work conversations must begin read-only: verify current main SHA, running
  Actions, state files, receipts, and locks before acquiring sole-writer
  authority.
- Production baseline before this documentation unit:
  `36566aa793e91cf9aa8409bb224b7b5ee5961761`; no queued or in-progress
  Actions. Handoff publication commit:
  `9e9d7c43abf4f70b2e1df8f2c7aca3c6e3c719ea`.
- The encrypted private trade ledger update is complete and verified; do not
  duplicate the latest transaction. No plaintext trade details are recorded in
  this public checkpoint.
- Documentation-only lock `LOCK-20260916-project-handoff-policy`: closed.
- This unit did not trigger OpenAI, PushPlus, stock screening, position sizing,
  stop-loss, take-profit, or other production workflow side effects.

Updated: 2026-09-16 00:07 Asia/Shanghai

## 2026-09-15 staged pre-AI gate recovery

- Operation lock `LOCK-20260915-2245-staged-pre-ai-recovery`: closed after guarded production recovery.
- Baseline at acquisition: production main
  `409297dac66f661f59a889fb2e874312c6273e96`; zero queued or in-progress
  Actions. The 2026-09-15 natural after-close run folder is
  `v5_data/runs/20260915_213543`.
- The first <=50 patch correctly added the gate to the monolithic
  `v5_cli.run_after_close` path and its API fail-closed assertion. Production,
  however, uses `research.after_close_stages`; its 250-day stage retained 97
  candidates. The API assertion blocked the request before OpenAI, proving the
  safety boundary worked but revealing incomplete staged-runner integration.
- Natural run facts: active 689; 25-day 408; 120-day 159; old staged 250-day
  output 97. Error: `OpenAI候选超过硬上限：97 > 50`. No OpenAI request was
  made. The failed run may already have emitted failure alerts; do not replay
  those alerts.
- Current correction: apply the same lifecycle+3/3 maturity gate and complete
  reason audit in the staged 250-day function; re-apply it defensively when
  resuming an older `ai_failed` state; then use the existing dedicated AI
  recovery workflow to resume only the failed AI stage from saved market/data
  artifacts.
- Recovery must send at most one formal recommendation delivery, only after a
  successful OpenAI result. It must not re-run the 25-day/120-day fetches or
  reconstruct the market context.
- Recovery branch: `codex/staged-pre-ai-gate-recovery-20260915`; current head
  before this checkpoint commit:
  `a25173389a55368afb948665b306fd2a2a91e9ed`.
- Historical note: the encrypted ledger was still unchanged at this recovery
  checkpoint; the later online ledger update completed successfully and is
  recorded in the 2026-09-16 handoff section above.
- Production merges: staged-runner gate `aa6c02e5075d8504f78e25bd47f068a206d0843f`;
  recovery-test isolation `6fc06c29ab05cc4086c968e9f0111f3f8a1f309c`.
- Guarded recovery run `34984834690` completed successfully. The saved 159-row
  250-day audit contains 97 lifecycle-qualified stocks; 82 were rejected as
  `STRUCTURE_NOT_MATURE`, 62 as `MID_TERM_TREND_WEAK`, and 15 entered OpenAI.
  All 159 rows have nonblank elimination/qualification reasons; no capacity trim
  was needed because 15 is below the hard cap of 50.
- One OpenAI request completed: model `gpt-5.6-terra`, input 50,832 tokens,
  output 1,764, total 52,596. The next-day observation pool contains one
  conditional candidate (603011), and the formal PushPlus delivery was accepted
  on the first production attempt.
- Exact next state: after-close run `20260915_213543` is `completed:completed`;
  do not replay AI or PushPlus. The later authenticated online ledger update also
  completed; do not duplicate it.

Updated: 2026-09-15 23:00 Asia/Shanghai

## 2026-09-15 pre-AI capacity and decision-alignment revision

- Operation lock `LOCK-20260915-1618-pre-ai-cap-alignment`: closed after PR validation and production merge.
- Sole executor: current maintenance account/current window. Baseline production
  main: `b878937618893c1cc44241e157d22b897cdb290d`; zero open pull requests and
  zero queued or in-progress Actions at acquisition and at the post-interruption
  resume check.
- User-approved requirements: record an actual sale of `002902` for 900 shares
  at CNY 29.22 on 2026-09-15 before close; keep the 25-day and 120-day stages free
  from numeric quotas; ensure the final 250-day/pre-AI research pool never exceeds
  50 stocks; preserve a complete per-stock elimination reason; align deterministic
  program decisions with the OpenAI reason taxonomy before the API call.
- The sale must be appended through the encrypted private ledger. Do not expose the
  plaintext ledger or key, and do not fabricate an account when the existing active
  position is ambiguous. The Streamlit secure-login request was interrupted before
  any credentials or trade data were submitted, so this transaction remains pending.
- Latest verified screening evidence: the 2026-09-14 run was 681 -> 408 -> 172 ->
  114 -> 1. The 113-stock API request used 171,555 input tokens. Among its outcomes,
  79 were `STRUCTURE_NOT_MATURE`; all 79 had only two of the three deterministic
  convergence supports, while the sole SELECT had all three.
- Implemented an explicit pre-AI gate after the quota-free 120-day stage: candidates
  must pass the 250-day lifecycle gate and have all three program evidence families
  (amplitude contraction, volume/turnover contraction, and short-term decline
  stopped). Eligible stocks are then ranked using the same structure/lifecycle/
  overheating evidence families and hard-capped at 50.
- Every 250-day audit row now receives `OpenAI前置判定代码` and
  `OpenAI前置判定原因`. The output distinguishes
  `STRUCTURE_NOT_MATURE`, `MID_TERM_TREND_WEAK`, `LOWER_PRIORITY`, and
  `QUALIFIED_FOR_OPENAI`; capacity trimming is therefore never silent.
- A second fail-closed guard blocks the OpenAI function itself if more than 50
  candidates reach it. No after-close replay, OpenAI call, or PushPlus delivery
  occurred.
- Offline verification before the execution environment disconnected: Python
  compilation passed; all 131 deterministic tests passed. Replay against the saved
  2026-09-14 172-row lifecycle audit produced 22 API candidates, 92 program-side
  `STRUCTURE_NOT_MATURE` outcomes, 58 `MID_TERM_TREND_WEAK` outcomes, and zero
  blank reasons. It made no network or model call.
- Recovery branch: `codex/pre-ai-cap-alignment-20260915`; latest saved branch
  commit before this checkpoint update: `6bc4072227821f8ab340556d1a5f7bcdb226d43a`.
  The local execution environment later became unavailable, so the already-tested
  change was reconstructed on this branch from the verified patch units rather than
  modifying production main directly.
- PR #13 was squash-merged to production main as
  `f1c52f586074ef9be39def90be7ecf3dae625322`. THS public-sector validation
  succeeded. The official-market workflow's deterministic data-layer suite also
  succeeded; its later live snapshot step failed only because Eastmoney closed both
  requests and Sina timed out then returned HTML. This upstream result does not
  exercise or invalidate the screening revision.
- Final reliable checkpoint: the <=50 fail-closed API boundary, aligned maturity
  gate, complete per-stock audit, run summary fields, and UI wording are live on
  production main. The encrypted 002902 trade append remains a separate pending unit
  because the secure Streamlit login was interrupted before submission; it must not
  be claimed as completed until the live ledger confirms it.

## 2026-09-15 opinion-delivery rollover incident

- Operation lock `LOCK-20260915-opinion-delivery-rollover`: closed after merge,
  validation, Worker deployment, and health verification.
- Baseline production main: `ebbea4c0da5f8730b00e1c92810574af79e66de8`;
  assets main: `3ede4b8deb9c8e77bd3add81a379e629fe1254f7`; zero queued or
  in-progress Actions at acquisition.
- The 2026-09-14 formal report is complete: 37 quality-approved articles,
  generated at 22:21:17 Asia/Shanghai. Delivery receipt
  `v5_data/opinion/delivery/2026-09-14.json` records `request_accepted` at
  22:21:19 with source-set SHA-256
  `9bb4c13b2aeaf50a16df1a4409c887fd65baf4308a1e77b056e23308ca07bb44`.
  The user's screenshot independently verifies WeChat terminal receipt.
- False-alert run `34886191363` started at 03:19 on 2026-09-15. Its delivery
  step used the actual start date (`2026-09-15`) instead of the intended
  scheduled source date (`2026-09-14`), then sent one erroneous missing-report
  alert at 03:20. Earlier delayed delivery run `34880510837` shows the same
  rollover defect; only the final cron is allowed to alert.
- This is a delivery-guard defect, not a missing report or a low-sample result.
  No report replay, OpenAI call, summary resend, or compensating PushPlus call
  is authorized.
- Current unit: make the delivery source date delay-safe, check the matching
  accepted receipt before entering the push stage, and add deterministic
  cross-midnight regression tests. Strategy impact: none.
- Reliable resume point: incident evidence and lock are durable here; resume
  with the delivery guard implementation and offline validation.
- Delivery guard implementation completed locally. Scheduled delivery starts
  before 20:00 Asia/Shanghai now resolve to the previous calendar day's report,
  covering both the observed 03:19 delay and longer daytime queue delays.
- The workflow now accepts an optional bounded `source_date`, exports the
  resolved date to the push subprocess, and exits before that subprocess when
  an accepted receipt matches the exact quality-approved source set.
- Focused verification: Python compilation plus 30 opinion/workflow tests passed.
  External OpenAI calls: 0. External PushPlus calls: 0; the one test response is
  mocked. Next unit: run the wider reliability suite and inspect the final diff.
- Full deterministic Python suite: 129 tests passed. Cloudflare scheduler suite:
  10 tests passed. The Worker now passes its Shanghai `source_date` explicitly
  to the delivery workflow so runner queue delay cannot change the business date.
- Production-artifact dry check for the observed 03:20 start resolved
  `2026-09-14`, found 37 articles, and matched the exact accepted source-set
  receipt. It did not invoke the delivery stage. A first dry-check command from
  the Worker subdirectory could not locate the repository Python module; rerun
  from the repository root succeeded. This had no production side effect.
- Reliable resume point: implementation and offline acceptance are complete;
  inspect/commit the bounded engineering diff, then verify only CI validation.
- Engineering PR: `#11`, head commit
  `610f15deb8c996f7df4a59053c47d5d7e57d7c20`.
- PR CI: THS public-sector run `34911565624` succeeded. Official-market-count
  run `34911565616` passed its deterministic data-layer tests, then failed only
  because Eastmoney closed both full-market snapshot requests and Sina timed out
  once then returned HTML. The fallback data and public limit pools were obtained;
  this upstream snapshot failure does not exercise the opinion delivery patch.
- No PR job called OpenAI or PushPlus. Next unit: confirm unchanged main, merge
  PR #11, then inspect push-triggered validation jobs only.
- PR #11 was squash-merged to production main as
  `17e5efcd28c4f8dc9a01f2fce272c9ca247adb66`.
- Push validation run `34911874638` succeeded. Only preflight and deterministic
  validation ran; concept refresh, discovery, all article batches, aggregation,
  and failure alert were skipped. OpenAI calls: 0. PushPlus calls: 0.
- Cloudflare deployment run `34912073032` succeeded at the production main.
  Scheduler tests, secret checks, Worker upload, and all five cron triggers passed.
  Deployed Worker version: `46369bae-a758-4639-a9b8-aba7e392b34a`.
  `GET /health` returned `status=ok`, `timezone=Asia/Shanghai`, and the expected
  tail/opinion/opinion-delivery workflow list.
- Final reliable checkpoint: the GitHub delivery guard and Cloudflare explicit
  source-date handoff are live. The 2026-09-14 report remains the single valid
  37-article delivery; no replay or resend occurred. Next action is read-only
  acceptance of the natural 2026-09-15 20:30-22:12 opinion cycle.

## 2026-09-14 upload recovery checkpoint

- Active operation lock: `LOCK-20260914-upload-name-resolution-recovery`.
- Baseline production main: `d4d563ec07bf1a29ae60e67b43895ffa6c2ab9fe`;
  assets main: `3ede4b8deb9c8e77bd3add81a379e629fe1254f7`; zero queued or
  in-progress Actions at acquisition.
- User workbook `Table.xlsx` is a valid OOXML workbook with one 73-row sheet
  (one header plus 72 stocks) and 60 columns. It contains stock names but no stock
  code column; the previous rejection is therefore a name-resolution failure, not
  a corrupt-file failure.
- The current code-name master resolves 71 names uniquely. The remaining input
  `贵州三力` is the former name of code `603439`, whose registered current short
  name is `三力制药`; the code remained unchanged. No input row is an ST stock and
  no duplicate name was found.
- Current unit: add deterministic Unicode/whitespace name normalization, a reviewed
  historical-short-name registry, and offline upload regression tests. This is an
  engineering reliability change only; screening and trading rules are unchanged.
- No OpenAI or PushPlus call has occurred in this operation. No 2026-09-14 daily
  batch has been committed or dispatched yet.
- Reliable resume point: workbook structure and 71 current-name mappings are
  verified; resume with local tests, then generate the 72-row canonical CSV.
- Extraction unit completed locally: the repaired offline parser produced 72
  unique A-share codes, zero indices, zero duplicates, and zero ST rows. The only
  historical-name conversion is `贵州三力 -> 603439 三力制药`.
- Source workbook SHA-256:
  `5626f2ee5289233282d5123a4eca3d1df394dc7d0d8e31db53994ede0f4253be`.
  Canonical CSV SHA-256:
  `a9fda869cd2c44ce8114de3973146c0804d4c3817165f258de02d3790b1a61d7`.
- Three focused upload tests and Python compilation passed. Next resume point:
  run the complete data-layer test module, commit the engineering-only patch, and
  verify it before any daily-batch production commit.
- Engineering PR `#9` was squash-merged as
  `c41d7bbd51129764e2d5559f185414478b2e5ae0`. Local compilation and all 27
  data-layer tests passed. GitHub Runner deterministic data-layer tests also passed
  in run `34842422445`.
- PR public-source checks were non-blocking upstream failures: run `34842422441`
  obtained the complete THS concept/industry fund-flow tables but the separate THS
  concept-index page returned unparsable HTML; run `34842422445` obtained Legulegu
  and index evidence but Eastmoney closed both snapshot requests and Sina timed out
  or returned HTML. These failures did not exercise the name resolver and made zero
  OpenAI or PushPlus calls.
- Production batch prepared as `v5_data/inbox/daily_20260914_201843.csv`, with an
  identical `latest_daily_batch.csv`. Both contain the verified 72-row canonical
  list. The atomic batch commit is intentionally deferred until all engineering
  push checks finish and queued/in-progress Actions are rechecked as zero.
- Batch commit `7f0c1beca1a8085965d44c4348146e9164731a33` triggered exactly one
  after-close run, `34843004136`. Saved run folder `20260914_202417` contains an
  initialized 681-stock active pool; 25-day selected 408, 120-day selected 172,
  and 250-day retained 114. All deterministic/data/market stages completed.
- AI finalization failed after two calls with the same prompt because both responses
  reached the 20,000-token output ceiling. The durable audit records the second
  response as `resp_05559ecc2fbda243006aa7ead3b21887d29020aac99c0694d3`,
  171,369 input and 20,000 output tokens; the first response ID was not persisted.
  Neither partial response is valid JSON, so it cannot safely become an observation
  pool. No formal recommendation delivery occurred.
- The AI job sent one failure notification accepted by PushPlus with receipt
  `19770984aa494676bc4acbc5b5be3cf4`; the workflow-level failure-alert job also
  completed successfully and may represent a second accepted failure alert because
  that inline path does not persist its receipt. Neither alert may be repeated.
- Recovery unit: keep all 114 candidates and the maximum-10 observation rule, but
  make the structured output proportional to the selected pool: detailed evidence
  for at most 10 SELECT rows and compact code/reason outcomes for all other rows.
  A max-output incomplete response becomes non-retryable because the identical
  request cannot cure a deterministic size overflow. This is engineering
  reliability only; candidate eligibility and ranking rules do not change.
- Reliable resume point: all pre-AI artifacts are durable on main
  `3c8a43d3398ba233224708064495b61bd68ac373`; no Actions are queued or running.
  Validate and merge the compact-output contract without triggering a new full
  pipeline, then rerun only failed AI job `103976139300` and its downstream job.
- Compact-output implementation is locally complete: selected detail remains fully
  dimensioned for at most 10 stocks; every other candidate must appear exactly once
  as a compact WAIT/REJECT plus enumerated reason. Coverage, duplicate, overlap,
  outside-pool, and maximum-10 checks remain hard validation failures.
- Max-output incomplete responses now stop after one API attempt instead of issuing
  the same deterministic request twice. Compilation plus 48 AI-contract,
  after-close-stage, and data-layer tests passed; all external calls in tests were
  mocked. Next resume point: commit this engineering-only unit, verify PR checks,
  merge, then recheck main/Actions/delivery state before one failed-job rerun.

## 2026-09-14 upload and after-close recovery completion

- Upload resolver fix merged in PR `#9` as
  `c41d7bbd51129764e2d5559f185414478b2e5ae0`. Name-only XLSX/XLS/CSV
  uploads now use deterministic Unicode/whitespace normalization plus an audited
  former-name registry. The supplied 72-row workbook is fully resolved; former name
  `贵州三力` maps to unchanged code `603439` and current name `三力制药`.
- Atomic daily batch commit:
  `7f0c1beca1a8085965d44c4348146e9164731a33`. It produced exactly one
  after-close run, `34843004136`, with saved folder `20260914_202417`.
  Active pool 681; current 25-session evidence 680; stale/deferred 1; stage1 408;
  stage2 172; stage3 114.
- Initial AI attempt failed because the old schema required long-form detail for all
  114 candidates. Two identical calls reached 20,000 output tokens; no valid JSON,
  observation pool, or formal recommendation delivery was created. The last
  incomplete response ID is
  `resp_05559ecc2fbda243006aa7ead3b21887d29020aac99c0694d3`.
- Failure notifications: the AI job persisted PushPlus receipt
  `19770984aa494676bc4acbc5b5be3cf4`; the workflow-level alert also succeeded
  without a persisted receipt and may have produced a second alert. These alerts
  must not be replayed. This known duplicate-failure-alert path remains a separate
  engineering follow-up.
- Compact-output recovery merged in PR `#10` as
  `b017a914625cf435b37f9a057b0ff50675abf85a`. It keeps all candidates and
  the 0-10 observation cap, retains full evidence for SELECT rows, compactly audits
  every non-selected code, and prevents a deterministic max-output response from
  being retried unchanged. Forty-eight local tests passed; GitHub deterministic
  checks passed. No screening or trading rule changed.
- Only failed AI job `103976139300` was rerun. Workflow attempt 2 completed
  successfully; every pre-AI stage reused its saved success state. OpenAI made one
  successful call: response
  `resp_0c77cd657702875d006aa7eea8b9e887d18b69f19c7f99401c`,
  171,555 input tokens, 3,769 output tokens, 175,324 total.
- Final observation pool for target trade date 2026-09-15 contains one conditional
  watch: `603980 吉华集团`. It remains a 14:40-14:45 confirmation candidate,
  not a direct buy instruction. Formal PushPlus request was accepted once with
  receipt `aaef2c82591143b490fbe1a2816e5b32`; terminal WeChat delivery is
  unverified.
- Completion main before this checkpoint commit:
  `9880a5bd6b27abf5a89616b47d95891757e76102`. Run `34843004136`
  conclusion is success, feedback refresh succeeded with no delivery, failure alert
  skipped on attempt 2, and zero Actions are queued or in progress.
- Operation lock `LOCK-20260914-upload-name-resolution-recovery`: closed by this
  checkpoint. Do not rerun the batch, AI job, or PushPlus delivery. The next natural
  production acceptance is the 2026-09-15 14:40-14:45 tail cycle.

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


## 2026-09-16 trading-page password removal

- Operation lock: `LOCK-20260916-trading-page-password-removal`.
- Authorized by the user to remove the Trading & Positions page password prompt and allow direct page access.
- Baseline production main: `c1af60e613c9a550c6dd48310442e5711253b925`.
- At acquisition: queued Actions 0; in-progress Actions 0.
- Scope: `app.py`, deterministic validation/tests if needed, and this checkpoint.
- Preserve `TRADING_DATA_KEY` encryption, encrypted ledger storage, GitHub credentials, position de-duplication, and all trading/recommendation rules.
- `TRADING_UI_PASSWORD` may remain configured in Streamlit Secrets but will be ignored by the application after this change.
- Allowed side effects: validation-only GitHub Actions and Streamlit source refresh after merge.
- Forbidden side effects: OpenAI, PushPlus, stock screening, recommendations, trades, ledger mutations, position sizing, stop-loss, or take-profit changes.
- Security acceptance: removal of the UI password intentionally makes the page accessible to anyone who obtains the site URL; encrypted-at-rest storage does not itself prevent an authorized running app from displaying decrypted data.
- Status: active; code change not yet merged.


### Closure

- Status: completed and merged through PR #16.
- Production merge commit: `4e9eefc73029232c1eb6c57941f8bac8c2d34d7a`.
- Direct-access assertions and Python compilation passed in GitHub Actions run `35091563053` before merge.
- THS public-sector live validation passed in run `35090355901`.
- Market-count live probe run `35090355844` failed only after deterministic tests passed because Eastmoney disconnected and Sina timed out; no market-fetch code was changed.
- The page no longer reads or checks `TRADING_UI_PASSWORD`; `TRADING_DATA_KEY`, encrypted ledger storage, and transaction logic remain in place.
- No OpenAI, PushPlus, stock-screening, recommendation, trade, or ledger-write side effect was triggered by this change.
- Lock status: `LOCK-20260916-trading-page-password-removal` closed.


## 2026-09-16 actual-exit feedback and after-close holding review

- Operation lock: `LOCK-20260916-actual-exit-feedback-holding-review`.
- Authorized goal: stop D+3/D+5/D+10 cohort tracking after a recommended stock has a real fully closed trade; classify the real exit as profit/loss/breakeven and report actual win rate, average return, and payoff ratio.
- Authorized goal: every natural after-close run must review all actual open holdings and report hold/exit guidance plus current stop-loss and take-profit references.
- Baseline production main: `40a6c52d34fbb2e29fb1db20bc712cb5942709e6`.
- At acquisition: queued Actions 0; in-progress Actions 0.
- Data authority: encrypted `v5_data/private/trades.enc`; an exit suggestion alone must never be recorded as an executed sale.
- Privacy: account, quantity, cost, and holding-level decisions remain encrypted; only aggregate actual-trade statistics may be written in plaintext feedback summaries.
- Preserve existing 14:45 exit rules, selection rules, position sizing, and recommendation gates unless explicitly required for this linkage.
- Allowed side effects: validation-only Actions and one no-notify encrypted-ledger reconciliation after merge.
- Forbidden side effects: duplicate OpenAI calls, PushPlus deliveries, stock screening, recommendations, or synthetic/manual transaction creation.
- Status: active; implementation not yet merged.

### Unit 1 checkpoint

- Implemented real recommendation-to-trade-cycle linkage from the encrypted ledger. Multiple accounts for the same recommendation are aggregated; only a fully closed real position cycle ends D+3/D+5/D+10 tracking.
- Added plaintext-safe result fields only: real trade status, entry/exit dates, actual return percentage, and profit/loss/breakeven result. Account, quantity, cost basis, prices, and cash P/L remain outside plaintext feedback artifacts.
- Added aggregate real-trade metrics: completed trades, wins/losses/breakevens, win rate, mean actual return, average win, average loss, and payoff ratio.
- Added deterministic after-close review for every encrypted active holding, including hold/next-session exit/reduce guidance, non-decreasing structural stop, profit-trailing activation price, and 5% pullback trigger. Detailed reviews are encrypted, including an explicit encrypted empty review to prevent stale holdings.
- Added the holding section and real-trade aggregate line to the normal after-close message; no message was sent during implementation.
- Verification: Python compilation; 64 targeted tests; 140 full unit tests; workflow YAML parsing; and `git diff --check` all passed. OpenAI and PushPlus outputs in tests were mocks only.
- Changed files: `research/private_trade_ledger.py`, `research/recommendation_feedback.py`, `research/holding_exit.py`, `research/after_close_stages.py`, `v5_cli.py`, both related workflows, three test modules, and `docs/HOLDING_EXIT_POLICY.md`.
- Next action: commit this unit to the task branch, open a PR, accept validation-only Actions, merge once, then run exactly one no-notify encrypted-ledger reconciliation.

### Reconciliation correction

- PR #17 merged as `f32682818d37d6b3498887c44c578f75b8175aa1` after validation run `35101468009` succeeded; all production stages after validation were skipped. THS run `35101467602` and official market-count run `35101467590` also succeeded.
- The single automatic no-notify reconciliation run `35101895093` failed before reading the encrypted ledger because direct script execution could not import the `research` package (`ModuleNotFoundError`). Deterministic tests passed; no feedback commit, OpenAI call, PushPlus request, screening, recommendation, or transaction mutation occurred.
- Forward correction: use module execution (`python -m research.recommendation_feedback`) in every workflow, retain a direct-script compatibility import, and supply `TRADING_DATA_KEY` to the close-audit backfill path.
- Next action: validate and merge the forward correction, then retry exactly one no-notify reconciliation.

### Closure

- PR #18 merged as `fd4b69de4bcbbe2273e0e3cbf3abc759ed10620c`; validation run
  `35102238798` succeeded and production stages were skipped.
- The one authorized no-notify reconciliation retry, run `35102358586`, succeeded
  and persisted commit `c53af8f`. It made no OpenAI call, PushPlus request,
  screening decision, recommendation, or ledger mutation.
- The encrypted ledger classified recommendation `600801` as fully closed on
  2026-09-16 and the plaintext-safe feedback result as `亏损卖出`, actual return
  `-4.1129%`. It is absent from all D+3/D+5/D+10 due cohorts.
- The latest verified aggregate on 2026-09-18 contains two completed real trades:
  one win and one loss, 50.0% win rate, 0.9125% mean actual return, and 1.4437
  payoff ratio. No account, quantity, cost, price, or cash-P/L detail was exposed.
- Natural after-close run `35437037831` on 2026-09-19 successfully exercised the
  production holding-review path. Exact-duplicate pending run `35437040173` was
  cancelled before any stage ran, preventing duplicate OpenAI/PushPlus effects.
- Lock status: `LOCK-20260916-actual-exit-feedback-holding-review` closed.


## 2026-09-19 tail-delivery reliability incident

- Operation lock: `LOCK-20260919-tail-delivery-reliability`.
- Baseline production main: `cfb789fbec7fc4150c58690e0e35a4ef4d24cb08`.
- At acquisition: queued Actions 0; in-progress Actions 0; pending Actions 0.
- Authorized goal: establish the 2026-09-17 and 2026-09-18 14:40-14:45 failure
  chains, repair the proven causes, and keep the production tail task independent
  of ChatGPT Work conversation/usage state.
- Evidence established: 2026-09-17 external run `35189873338` started at 14:27
  China time, but `precheck-1440` exceeded its 25-minute job timeout during market
  data collection and was cancelled at 14:53. `finalize-1445`, OpenAI, and the
  formal trade PushPlus delivery never ran.
- Evidence established: no external 14:26/14:31/14:35 workflow run exists for
  2026-09-18. The three delayed native GitHub schedules reached Actions only at
  19:40-19:47 China time and all failed validation because a code-name fixture's
  insignificant internal whitespace changed. No market fetch, OpenAI request,
  decision, or formal trade PushPlus delivery ran.
- Quota separation: the workflow uses repository `OPENAI_API_KEY` in GitHub
  Actions and has no ChatGPT Work session dependency. A separate after-close API
  call succeeded on 2026-09-17 at 18:28 on its first attempt (response
  `resp_082299bfa956a1d2006aabc0b3b09487d29c83d40752caa611`), so the Thursday tail
  miss was not a ChatGPT Work-usage or API-quota failure. Friday tail never called
  the API, so no Friday tail billing/rate/auth response exists.
- Allowed side effects: validation-only PR Actions and one Cloudflare scheduler
  deployment after verified merge. Deployment itself must not dispatch the tail
  workflow, call OpenAI, or send PushPlus.
- Forbidden side effects: reconstructing either missed day's tail signal after
  close; manual tail dispatch; duplicate OpenAI/PushPlus; trading-ledger mutation;
  recommendation/position/risk-rule changes.
- Next unit: bound realtime/minute upstream calls, move time-insensitive candidate
  context before 14:40, remove the brittle display-whitespace assertion, split the
  external cron slots, and make scheduler/cancelled-run failures observable.
- Unit 1 implementation complete locally:
  - Eastmoney/Sina realtime and 5-minute calls now have an 8-second per-source
    hard deadline and preserve provider fallback/error evidence.
  - Candidate profile/fund-flow/news context is fetched before the 14:40 wait;
    only the actual quote/minute snapshot remains in the short time window.
  - The precheck job limit is 30 minutes, but bounded calls prevent that extra
    allowance from accepting an unbounded late snapshot.
  - The unstable display-whitespace fixture now asserts the deterministic
    normalized stock-name key, preserving the intended name-to-code gate.
  - A cancelled/timed-out stage now reaches the failure alert. One same-day
    Actions-cache receipt suppresses duplicate alerts from the staggered native
    cron runs.
  - Cloudflare now has four independent weekday tail cron expressions at
    14:26/14:31/14:35/14:38 China time. A GitHub API route failure produces a
    direct Cloudflare-to-PushPlus fault alert; it never constructs a trade signal.
- Verification: 61 targeted Python tests passed; 142 full Python tests passed;
  12 Worker tests passed; both modified workflow YAML files parsed; Python
  compilation and `git diff --check` passed. Two initial test commands were run
  from the wrong working directory (`npm test` at repository root and Python
  discovery inside the Worker folder); both failed before tests and were corrected
  without changing production state.
- Next unit: publish the implementation on the locked branch, open a PR, accept
  validation-only Actions, merge once, then deploy the Worker exactly once without
  dispatching a tail workflow.
- PR #19 merged as `48c92701751ffc811650925cdbe4214760d9948e` after
  validation runs `35438285929`, `35438285810`, and `35438285809` all succeeded.
  Merge validation run `35438457032` succeeded with precheck/finalize/alert all
  skipped; no tail production side effect occurred.
- Deployment run `35438570230` uploaded the Worker code and both secrets, then
  failed while updating schedules because the eight requested cron expressions
  exceeded the Cloudflare Workers Free account limit of five (API code 10072).
  Cloudflare reported that successful trigger changes were not rolled back, so
  schedule state is treated as uncertain until the forward deployment succeeds.
- Forward correction: keep the four independent tail expressions and consolidate
  opinion mining/delivery into one fifth routing-grid expression. Worker time-slot
  checks preserve only the prior 20:30, 21:00-21:50, 22:00, and 22:12 Shanghai
  executions; all other grid ticks are deterministic no-ops.
- Next unit: validate and merge the five-cron correction, deploy once, and verify
  the deployed trigger list/health without dispatching tail production.
- Status: active.

Updated: 2026-09-19
