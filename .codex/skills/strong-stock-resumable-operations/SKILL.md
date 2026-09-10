---
name: strong-stock-resumable-operations
description: Use for every long-running, multi-stage, interruption-prone, production-operations, recovery, or new-window handoff task in the strong-stock project. Enforces small verified units, durable checkpoints, single-writer locks, idempotent external effects, context/usage limits, and evidence-based resumption. Do not use for a simple one-step read-only answer.
---

# Strong Stock Resumable Operations

Apply this skill before any substantial production or maintenance work in
`CyberAI2026/-akshare-mobile` or related operational coordination with
`CyberAI2026/strong-stock-research-assets`.

## Required startup

1. Read `references/operating-policy.md` completely.
2. Read `docs/operations/WORK_PROGRESS.md` from the production repository.
3. Read the task-specific checkpoint and the assets-repository ownership/handoff policy.
4. Verify the live full `main` SHA of both repositories, recent Actions, queued or running work, active locks, saved artifacts, delivery receipts, and idempotency state.
5. Report the latest actually persisted and verifiable checkpoint before continuing.

## Execution rule

Work only in small units:

`inspect -> choose one unit -> execute -> verify -> persist -> update checkpoint -> commit when appropriate -> reassess usage/context`

Before any production mutation, declare the matter, lock ID, live full production
SHA, exact scope, Actions/OpenAI/PushPlus effect, strategy effect, and sole executing
account/context. Never duplicate a confirmed model call or delivery.

## Required closeout

Update the unified checkpoint after every meaningful unit. If work is interrupted,
at risk of exhausting usage/context, or transferred to a new window, leave a durable
handoff that names the next incomplete action and work that must not be repeated.

