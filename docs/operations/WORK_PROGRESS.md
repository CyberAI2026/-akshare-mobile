# Strong Stock Production Operations — Unified Checkpoint

Updated: 2026-09-09 23:02 Asia/Shanghai

## Overall goal

Operate and maintain the production recommendation system reliably while preserving
single-writer ownership, idempotent external effects, auditable recovery, and strict
separation between engineering reliability and trading strategy.

Canonical long-work policy:
`.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.

## Current production baseline

- Production repository: `CyberAI2026/-akshare-mobile`.
- Production `main` before the Cloudflare deployment-workflow commit:
  `0a830869c09c2faf35c22115782327741bd25165`.
- Assets repository: `CyberAI2026/strong-stock-research-assets`.
- Assets `main` last reverified in this resumed operation:
  `e9dd4f86e2776a018a05dd2e1d3186de1a710457`.
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
