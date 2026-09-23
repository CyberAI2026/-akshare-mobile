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
- Engineering PR `#29` passed all three checks: THS public-sector data test
  `35862211351`, official-market-count test `35862211379`, and after-close
  validation `35862211662`. It was squash-merged to production as
  `b50e887e692cb575df8741fcb73d341ce3e0d324`.
- Production main was read back after merge and contains both independent UI
  controls. The separate natural after-close run `20260923_202109` remained
  `running:initialized` with `master_before_screen=810`; this engineering rollout
  did not restart, cancel, replay, or otherwise mutate that run.
- Latest reliable checkpoint: the download/upload entry is live in production.
  The operation lock is closed. Next functional unit, after the first full-master
  snapshot is uploaded, is shadow analysis only; do not promote THS factors to
  hard screening rules before longitudinal validation.

Updated: 2026-09-23 21:00 Asia/Shanghai
