# System Stabilization Checkpoint — 2026-10-05

## Ownership and safety

- Task lock: `LOCK-20261005-system-stabilization`.
- The user explicitly changed the prior Trae-first handoff sequence on
  2026-10-05: ChatGPT Work is to restore and observe the system for 1–2 weeks;
  Trae handoff is paused until the stability window is accepted. ChatGPT Work is
  the sole human code operator for this stabilization matter; scheduled
  production workflows continue under their existing idempotency controls.
- No production workflow was dispatched during this checkpoint. No OpenAI,
  PushPlus, market-data, trading-ledger, or deployment side effect was repeated.
- Production baseline: `main` at
  `591d8fc6b950bd4a614979a7c349d4a069d96376`.
- No open PRs or queued/in-progress GitHub Actions were found at acquisition.
- The pre-existing `/workspace/scratch/59b4a2756030/repo` clone was 76 commits
  behind and contained two locally modified XLSX research results. It was not
  edited. Work is isolated in a fresh clone at the production baseline.

## Verified production findings

- The latest completed after-close result is `20260924_201231`, completed
  2026-09-24 20:25 Asia/Shanghai. `v5_after_close.yml` had no `schedule`
  trigger; absent a daily upload or manual dispatch, the pipeline did not run.
- The current Streamlit source contains the one-click THS master-code download
  and full-field snapshot upload. Live deployment URL/rendering is not recorded
  in the repository and remains unverified; the controls are also shown only
  when the master CSV loads non-empty.
- Tail workflow has scheduled runs at 14:32/14:36/14:40 Beijing time and
  same-day idempotency. On 2026-10-05 it correctly skipped because the exchange
  was closed; the SSE 2026 holiday notice says trading resumes 2026-10-08.
- The latest valid rolling tail observation source is stale for the next
  trading session. The prior behavior raised before preparing an auditable
  14:45 result. The patch now fails safely with zero new-trade candidates, no
  OpenAI call, an explicit no-fresh-pool PushPlus message, and still performs
  the existing actual-holdings exit scan.
- The 2026-10-04 opinion retries initially failed to discover same-day articles;
  after the low-sample staging correction, eligible quality sample remained 0,
  below the confirmed 15-article minimum. No formal report/push was expected.
- A pull-request verification on the 2026-10-05 exchange holiday showed both
  Eastmoney and Sina full-market spot endpoints unavailable. Public limit-up/
  down pools and THS tests succeeded; the market-count workflow failed only
  because it incorrectly demanded live spot data on a closed day. The test now
  explicitly skips market snapshots on non-trading days and remains strict on
  trading days; this does not suppress or downgrade a trading-day production
  check.

## Completed in this unit

- Added two weekday after-close maintenance crons (17:32 and 18:02 Beijing).
- Added a schedule precheck that skips known non-trading days, same-day completed
  output, and same-day in-progress state; upload-triggered jobs are unchanged.
- Scheduled validation checks out current `main` so delayed/queued retries see
  the newest completion state and do not duplicate model calls or pushes.
- Added regression tests for holiday skip, completed-run skip, in-progress skip,
  stale-checkpoint run, and workflow schedule wiring.
- Added a stale/missing tail-pool safe path that neither evaluates old
  candidates nor silently labels the condition as a model rejection; coverage
  verifies the 14:40/14:45 path skips OpenAI and preserves the push/idempotency
  receipt.
- Verification: Python compilation passed; 100 focused deterministic tests
  passed, including the new schedule and stale-pool cases; YAML parse and
  `git diff --check` passed.
- PR #32 passed the After-Close validation, calendar-aware market-count check,
  and THS sector-data check, then was squash-merged. Production `main` is now at
  `32ac899041dbb92fafa9aa91c44b7587283e0414`. Merge only caused the existing
  validation/scope workflows; no after-close production analysis, OpenAI call,
  PushPlus send, or live tail decision was dispatched.
- A read-only daily stability review has been scheduled at 22:30 Asia/Shanghai
  for 14 days beginning 2026-10-06. It is explicitly prohibited from rerunning
  workflows or making API, push, trading-ledger, or repository writes.

## Next exact actions

1. Check live Streamlit deployment/rendering and expose a clear load-error state
   if the THS download/upload controls are hidden because the master CSV is empty.
2. Observe natural production runs for 1–2 weeks using Actions, saved outputs,
   OpenAI audit records, and PushPlus receipts. Do not call a holiday skip or a
   confirmed low-sample opinion no-send a system failure.
3. Handoff to Trae only after the agreed stability window has no unresolved
   production-impacting defect, with a fresh checkpoint and exact main SHA.

## Rollback

- If a production regression is confirmed, revert only the stabilization merge
  commit; do not reset or force-update `main`.
