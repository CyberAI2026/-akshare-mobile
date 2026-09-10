# Resumable production-operations policy

This is the canonical project-level form of the nine long-work rules. It applies
to production operations, engineering changes, data processing, incident recovery,
research coordination, and window handoff.

## 1. Every long task is resumable

Split work into small stages. For each stage: execute, verify, persist, update the
checkpoint, and commit when appropriate before starting the next stage. Split any
stage that is too large to close safely.

## 2. Persist frequently; never depend on transient chat context

Save every meaningful result as a file, database record, log, run result, artifact,
commit, or checkpoint. Critical progress, decisions, and recovery instructions must
not exist only in conversation memory or temporary reasoning.

## 3. Maintain one unified checkpoint

Maintain `docs/operations/WORK_PROGRESS.md` as the operational index and link any
task-specific checkpoint from it. Record at least:

- overall goal and current production baseline;
- completed, verified, in-progress, and pending work;
- files added or modified and important data artifacts;
- full GitHub commit SHAs and relevant run/job IDs;
- known issues, unresolved risks, and rollback points;
- latest reliable checkpoint, exact next action, and last-updated time.

Update the checkpoint from actual saved evidence, never from an assumption that a
tool call probably finished.

## 4. Protect against usage, token, and execution limits

Before opening a new unit, assess whether it can be closed with the remaining
resources. When resources may be insufficient, stop expansion, finish only the
smallest safe closure, save results, update the checkpoint, commit verified work,
and record the next action.

## 5. Monitor context capacity

When a precise percentage is available:

- Near 70%: compress repetition, refresh checkpoints, and reduce unit size.
- Near 80%: prepare a complete new-window handoff and refresh all durable state.
- At or near 85%: warn the user that the context is near its safe limit, stop new
  large work, close the current safe unit, persist everything, and recommend an
  immediate window switch.

When no percentage is available, estimate conservatively from conversation length,
large file/log reads, tool-call count, repeated summaries, reliance on old context,
or weakening constraint recall. Prepare handoff around an estimated 75-80%; never
wait for an actual overflow.

## 6. Generate a complete handoff package before switching windows

The handoff must include:

- project and current task;
- production and assets repositories and both live full `main` SHAs;
- production state, queued/running runs, and active lock;
- completed and pending work and the latest reliable checkpoint;
- recent commits, artifacts, delivery receipts, and known issues;
- exact next action and work that must not be repeated;
- mandatory read-only checks for the new window;
- conditions that must be satisfied before the new window may acquire a write lock.

The handoff's first instruction must invoke `$strong-stock-resumable-operations`.

## 7. Preserve a single writer during handoff

Production authority belongs to the authorized maintenance account; exclusivity
belongs to one concrete operation lock. Multiple windows/accounts may inspect in
parallel but may not recover or mutate the same matter concurrently.

Before a switch: stop new production writes, close the smallest safe unit, record
or release the lock, update checkpoints, and record all active runs. The incoming
window begins read-only, verifies the old writer is no longer acting and no duplicate
run is queued/in progress, then acquires or continues the one lock. Every mutation
declaration must include matter, lock, full baseline SHA, scope, Actions/OpenAI/
PushPlus effect, strategy effect, and the sole executor.

## 8. A failed subtask must not destroy the project checkpoint

Record the failure and evidence, persist successful work, update the checkpoint,
mark the unit `blocked` or `retry`, and continue independent safe work when possible.
Never leave the whole project unrecoverable because one subtask failed.

## 9. Never silently overwrite an incorrect old result

Record the previous result, the defect, the reason for correction, every changed
item, downstream impact, and all steps requiring revalidation. Preserve an audit
trail and rollback point.

## Fixed operating loop

Repeat:

1. Inspect current saved state.
2. Assess usage and context risk.
3. Select one small execution unit.
4. Execute and verify it.
5. Persist results and update checkpoints.
6. Commit when appropriate.
7. Reassess usage/context before continuing.

## Production-specific invariants

- Check idempotency before every rerun, model call, or PushPlus request.
- A PushPlus `request_accepted` receipt proves only API acceptance, not WeChat
  terminal delivery.
- Engineering reliability changes and trading-strategy changes are separate.
- Without explicit user approval, do not change stock selection, observation-pool
  capacity, position sizing, capital, stop-loss, or take-profit rules.
- Never backfill a missed intraday recommendation with post-close data while
  representing it as an intraday signal.

