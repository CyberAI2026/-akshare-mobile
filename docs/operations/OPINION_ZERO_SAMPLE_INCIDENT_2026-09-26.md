# 2026-09-26 Market Opinion Zero-Sample Incident

## Incident

- Business source date: `2026-09-26` (Asia/Shanghai).
- The first post-deadline aggregate had one analyzed article, but that article
  failed the existing AI quality gate. The resulting quality pool was empty.
- The pre-fix aggregate path raised `RuntimeError` when all articles were
  rejected. GitHub Actions therefore classified a legitimate sample shortage as
  a pipeline failure and the failure-alert job sent the market-opinion fault
  notification.
- This was not an OpenAI quota, billing, authentication, ChatGPT Work usage, or
  PushPlus transport failure.

## Production Evidence

- Hotfix commit: `34ad666677e62e886fc66366167d2979c901c85c` — zero qualified
  articles now follow the normal `minimum_not_met` path instead of raising.
- Durable empty-pool record: `d1541be4cda240e47b682171279f69701697850a`.
- Later natural retries saved updated shortage pools at
  `73f6254291df7744a709ad15e77ef451b2e5ce88` and
  `2d5b53df0bedec50cbff6140c01ff6fd1d3ae3a7`; the latest pool contains one
  qualified article, still below the formal minimum of 15.
- There is no `2026-09-26` delivery receipt and no formal `latest.json` report
  for this source date. The last formal report remains `2026-09-24`. Therefore
  no formal report should be replayed or fabricated for September 26.

## Completion Unit

- Added an end-to-end regression covering the observed condition: every mined
  article is rejected by the quality gate.
- Acceptance requires the aggregate stage to return successfully, persist an
  empty shortage pool, commit the pool, and make zero aggregate-OpenAI and zero
  PushPlus calls.
- Verification completed: Python compilation passed; all 24 opinion-specific
  tests passed; the complete deterministic suite passed 158/158. The new test
  observed `OPINION_WAIT_FOR_MORE` and verified that aggregate OpenAI and
  PushPlus were not invoked.
- This repair changes failure classification only. It does not change the
  15-article release minimum, article-quality rules, stock selection, positions,
  stop-loss, take-profit, or any trading decision.

## Lock and Next Checkpoint

- Operation lock: `LOCK-20260927-opinion-zero-sample-regression`.
- Sole executor: current maintenance account/window.
- Production baseline: `2d5b53df0bedec50cbff6140c01ff6fd1d3ae3a7`.
- No production opinion rerun, OpenAI request, PushPlus request, or historical
  resend is authorized for this completion unit.
- Latest reliable checkpoint: incident diagnosis, production evidence,
  regression implementation, and offline verification are complete. Next
  action: publish the regression-only branch, verify validation-only CI, merge,
  then close the lock. Do not run the production opinion pipeline.

Updated: 2026-09-27 01:30 Asia/Shanghai
