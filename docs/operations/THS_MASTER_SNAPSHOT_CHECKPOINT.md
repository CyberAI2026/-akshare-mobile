# THS Full-Master Snapshot Checkpoint

- Operation lock: `LOCK-20260923-ths-master-snapshot-entry`; sole executor is
  the current maintenance account/window. Production baseline at acquisition:
  `b73f04da61715885cb6459d09872a0219cb710a6`; the local worktree was clean and
  the historical production write lock was closed.
- User-approved scope: add a one-click TXT download for all 794 current master
  codes and a separate upload entry for the enriched Tonghuashun export. This
  upload must not add/reactivate stocks, alter submission dates, dispatch
  after-close research, call OpenAI, or send PushPlus.
- Implemented on branch `codex/ths-master-snapshot-20260923`: six-digit
  code-only TXT generation; XLSX/XLS/CSV/TXT/TSV full-field ingestion; explicit
  matched/unmatched/missing counts; duplicate/invalid-code rejection; and one
  compressed date-addressed snapshot under `v5_data/ths_snapshots/YYYY-MM-DD/`.
- Real-file replay: `Table(1).xls` retained 122 rows and all 60 source fields;
  105 codes matched the 794-stock master, 17 were outside it, and 689 master
  codes were absent. The generated TXT has exactly 794 lines and preserves
  leading zeroes.
- Verification: Python compilation passed; six focused tests passed; full
  deterministic suite passed 157/157. No production upload, workflow, OpenAI,
  PushPlus, screening, trade, holding, stop-loss, or take-profit action occurred.
- Latest reliable checkpoint: implementation and offline validation complete.
  Local commit before remote transport adjustment: `299abcd96cd4c00dad6bd50954574fa823924771`.
  Exact next unit: publish the bounded diff to the already-created feature
  branch, open/merge the engineering PR after CI, then verify the live page.

Updated: 2026-09-23 20:45 Asia/Shanghai
