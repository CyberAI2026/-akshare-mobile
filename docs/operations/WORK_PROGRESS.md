# Strong Stock Production Operations — Unified Checkpoint

Updated: 2026-09-09 19:40 Asia/Shanghai

## Overall goal

Operate and maintain the production recommendation system reliably while preserving
single-writer ownership, idempotent external effects, auditable recovery, and strict
separation between engineering reliability and trading strategy.

Canonical long-work policy:
`.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.

## Current production baseline

- Production repository: `CyberAI2026/-akshare-mobile`.
- Production `main`: `e515f3745e101cef279cc0de5c0b5c4284624444`.
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

Task-specific detail: `docs/operations/OPINION_TASK_CHECKPOINT.md`.

## In progress

- Operation `LOCK-20260909-strong-stock-resumable-policy`: project-level skill and
  unified checkpoint are being added. Scope is documentation/skill metadata only;
  no Actions, OpenAI, PushPlus, or strategy effect is authorized.

## Pending

- Commit and validate the project-level resumable-operations skill.
- Select and deploy an external reliable scheduler for tail workflow dispatch,
  retaining GitHub cron and ChatGPT checks as fallbacks/monitors.
- Resolve whether the user's requested `16:40` means a post-close next-day list or
  whether the intended requirement remains the established `14:40` intraday tail
  recommendation. Do not change the production schedule until resolved.
- Verify the next natural tail cycle without backfilling the missed date.
- Verify the next natural 20:30-22:15 opinion cycle.

## Files in this unit

- `.codex/skills/strong-stock-resumable-operations/SKILL.md`.
- `.codex/skills/strong-stock-resumable-operations/references/operating-policy.md`.
- `.codex/skills/strong-stock-resumable-operations/agents/openai.yaml`.
- `docs/operations/WORK_PROGRESS.md`.

## Important artifacts and receipts

- Opinion source date 2026-09-08: 33 formal-quality articles.
- THS objective concept facts: 10 ready, 0 failed.
- Latest final PushPlus business receipt: `request_accepted`, short code
  `e59ae4a019d34db8a466603c8c9acec3`; WeChat terminal receipt remains unverified.
- Tail decision and close-audit artifacts remain dated 2026-09-04; no 2026-09-09
  tail OpenAI call or PushPlus request exists.

## Known issues and risks

- GitHub scheduled workflows are best-effort and have delayed or failed to start.
- ChatGPT scheduled tasks are also not a hard-real-time production scheduler.
- No independent external scheduler is deployed yet.
- API acceptance does not prove terminal WeChat receipt.
- Time semantics (`14:40` intraday versus `16:40` post-close) must be explicit.

## Latest reliable checkpoint

Production remains at `e515f3745e101cef279cc0de5c0b5c4284624444`,
with no running Actions and no active manual lock before this documentation-only
unit. The next safe action is to validate and commit the new project skill, then
close its lock. External scheduler deployment is a separate operation and requires
live authorization plus an explicit schedule decision.

## Rollback point

- Before this documentation/skill unit:
  `e515f3745e101cef279cc0de5c0b5c4284624444`.

