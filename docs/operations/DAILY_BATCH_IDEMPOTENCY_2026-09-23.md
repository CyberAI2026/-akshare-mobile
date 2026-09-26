# Daily Strong-Batch Idempotency — 2026-09-23 Incident

## Evidence

- The user submitted two batch files at 20:19 and 20:21 Asia/Shanghai on
  2026-09-23.
- `daily_20260923_121943.csv` and `daily_20260923_122136.csv` each contain 122
  stocks and have the identical SHA-256
  `f0e7056079a939aee210466c5296d2aa43663e05af970cad995a919cbd1792d3`.
- The first workflow persisted run `20260923_202109` only through
  `running:initialized`; there is no 25-day stage or later completion commit.
- The next dated run, `20260924_201231`, completed every stage and superseded
  the stale September 23 state. The stale run must not be replayed because its
  next-day trading signal is no longer temporally valid.

## Repair

- Every submitted code set now receives a deterministic identity formed from
  the Asia/Shanghai business date plus a SHA-256 fingerprint of the sorted,
  unique six-digit stock codes.
- The inbox path is deterministic for that business date and code set. If it
  already exists, the page reports that the same list was submitted and makes
  no GitHub write, workflow dispatch, OpenAI request, or PushPlus request.
- Reordering rows or changing display names cannot bypass the guard. A different
  business date or genuinely different code set still creates a new batch.

## Boundaries and Checkpoint

- Operation lock: `LOCK-20260927-daily-batch-idempotency`.
- Production baseline: `4df255db51ebe88c4cd9888abb7af82ee73638ed`.
- This change affects submission idempotency only. It does not alter screening,
  observation pools, trading, positions, capital, stop-loss, or take-profit.
- No stale workflow recovery or production side effect is authorized during
  validation.
- Verification completed: Python compilation passed; all four focused upload
  tests passed; the complete deterministic suite passed 159/159. No workflow,
  OpenAI request, PushPlus request, or production data write occurred.
- Latest reliable checkpoint: implementation and offline verification are
  complete.
- PR `#31` passed after-close validation run `36259155367`, THS public-sector
  run `36259155243`, and official-market-count run `36259155261`. It was
  squash-merged as `452072c02586468085fd7cf5ee950c86c330a53d`.
- All cloud checks were validation/data-source checks only. No daily batch,
  after-close production run, OpenAI request, PushPlus request, or stale-date
  replay occurred.
- Operation lock `LOCK-20260927-daily-batch-idempotency` is closed. The next
  acceptance point is the next natural user submission; an identical second
  click on the same business date must produce only the on-page duplicate
  notice.

Updated: 2026-09-27 02:05 Asia/Shanghai
