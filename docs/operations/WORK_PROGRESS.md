# Strong Stock Production Operations — Unified Checkpoint

Updated: 2026-09-09 19:55 Asia/Shanghai

## Overall goal

Operate and maintain the production recommendation system reliably while preserving
single-writer ownership, idempotent external effects, auditable recovery, and strict
separation between engineering reliability and trading strategy.

Canonical long-work policy:
`.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.

## Current production baseline

- Production repository: `CyberAI2026/-akshare-mobile`.
- Production `main` at this checkpoint: `37464d5ff9e508827a321dd8c472eef473908b93`.
- Assets repository: `CyberAI2026/strong-stock-research-assets`.
- Assets `main`: `a1cd70e5e124cbd0474f599e380cb5f2a54491e7`.
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

Task-specific detail: `docs/operations/OPINION_TASK_CHECKPOINT.md`.

## In progress

- None. `LOCK-20260909-tail-external-scheduler` is closed after the verified code
  and checkpoint commits. Cloudflare deployment requires a new lock after account
  connection and secret availability are verified.

## Pending

- Select and deploy an external reliable scheduler for tail workflow dispatch,
  retaining GitHub cron and ChatGPT checks as fallbacks/monitors.
- Connect the authorized Cloudflare account and store a repository-scoped GitHub
  Actions token as Worker secret `GITHUB_ACTIONS_TOKEN`; never commit the token.
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

## Known issues and risks

- GitHub scheduled workflows are best-effort and have delayed or failed to start.
- ChatGPT scheduled tasks are also not a hard-real-time production scheduler.
- No independent external scheduler is deployed yet.
- API acceptance does not prove terminal WeChat receipt.
- The user confirmed the formal requirement is the 14:40 intraday tail notification,
  not a 16:40 post-close list.
- Shared-path validation run `34347519957` failed because Eastmoney closed both
  candidate requests; deterministic tests passed. Run `34347518649` failed because
  two THS responses ended prematurely; 8 of 10 tables succeeded. These transient
  source failures are independent of the scheduler implementation and are recorded
  without automatic rerun.

## Latest reliable checkpoint

The nine-rule skill is durable. The external scheduler code and duplicate-alert
correction are committed through `bb4656cda80f633581d59547791d5a2b7bbfcd32`,
with checkpoint commit `37464d5ff9e508827a321dd8c472eef473908b93`.
Tail validation-only run `34347518574` succeeded with no production side effect;
all runs are complete. Two unrelated live-source tests failed transiently and are
recorded as `retry`, not rerun. The operation lock is closed. The exact next action
is read-only verification of the Cloudflare connection, followed by a new deployment
lock, secret configuration, Worker deployment, and natural-cycle acceptance.

## Rollback point

- Before this documentation/skill unit:
  `e515f3745e101cef279cc0de5c0b5c4284624444`.
