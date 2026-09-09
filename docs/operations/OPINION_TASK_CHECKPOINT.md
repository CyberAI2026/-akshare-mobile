# V5 Market Opinion Mining — Task Checkpoint

Updated: 2026-09-09 11:52 Asia/Shanghai

## Goal

Reliably discover at least 15 same-day Taoguba market-review articles, retain only articles with market and sector/cycle analysis, aggregate a complete market-opinion report, enrich it with objective THS concept-index facts, and prevent duplicate AI calls or PushPlus requests for unchanged output.

## Completed

- Added Taoguba topic feeds:
  - #复盘: talkSeq 143895
  - #每日复盘: talkSeq 21325
- Added browser-compatible, cache-bypassed requests and incremental cross-run quality-pool deduplication.
- Partial samples now receive a complete consensus summary rather than hard-coded empty fields.
- Identical source sets skip aggregate and PushPlus.
- Added bounded previous-source-date recovery and fixed delayed post-midnight finalization.
- Added composite-sector splitting and bounded alias/substring matching for THS concepts.
- Added a dedicated concept-refresh stage that reuses the saved report and does not call OpenAI.

## 2026-09-08 Final Production Result

- Discovery candidates: 76.
- Persisted formal-quality articles: 33 (minimum: 15).
- latest.json source date: 2026-09-08.
- Sample status: formal.
- Consensus populated:
  - market consensus and 4 disagreements;
  - 7 sector-consensus groups;
  - 8 high-attention stocks;
  - 6 next-day watch items.
- Objective THS concept facts: 10 ready, 0 failed, as of 2026-09-08.
- Final PushPlus business receipt: request_accepted.
- PushPlus short code: e59ae4a019d34db8a466603c8c9acec3.
- WeChat terminal delivery: unverified.

## Production Runs

- Main recovery pipeline: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34307582599
  - preflight, validate, discover, 8 article batches, aggregate: success.
  - failure-alert: skipped.
  - aggregate job: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34307582599/job/102327990123
- No-AI THS refresh: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34308530507
  - preflight, validate, concept-refresh: success.
  - discover, article batches, aggregate, failure-alert: skipped.
  - concept-refresh job: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34308530507/job/102330314282

## AI and Delivery Audit

Recovery pipeline new work:

- Article-analysis calls: 3.
  - input tokens: 14,417.
  - output tokens: 4,250.
- Aggregate call: 1.
  - input tokens: 20,567.
  - output tokens: 4,152.
- Total: 4 calls, 34,984 input tokens, 8,402 output tokens.
- THS concept refresh: 0 OpenAI calls.
- Aggregate PushPlus receipt at 11:38: request_accepted for 33 articles.
- Final concept-enriched PushPlus receipt at 11:50: request_accepted for 33 articles.
- Neither receipt proves WeChat terminal delivery.

## Commits and Verification

Discovery and finalization:

- d574797ccfc5556884b541c08f64d8c7177d8f76 — add generic #复盘 source.
- bc86a5dac921f6bfcf55cd80fa012051e7263961 — finalize delayed pools after midnight.
- 30e64c9ab942af83f86ae7a40e4528295d9dd570 — test overnight finalization.
- 727af22090ed74921fc9ba989321718aa55b092a — bounded source-date recovery.
- 90d0b01285e9db2314229dec39228e72c88e9220 — workflow source-date routing.
- ab131596321ec02e6985fff4e22ccc69b5acf3f1 — test bounded recovery.
- ad3747d363ce87fd4ede34dd2979f53ec26674fb — production trigger.
- 2afda51aeb36236305120575c1e8ea95c50b5f24 — 33-article production data.

THS concepts:

- 191a35447ba125629f82cb3cbab8b8f34105cf60 — composite concept matching.
- e24d151402588f5dabad32ad9b26e8c5a0c4814e — initial test; validation failed because exact/fuzzy order and two-character alias handling were incomplete.
- f61303d55d6b1d4a2a5d245c417b207ebba69903 — corrected exact-first matching; validation run 34308264359 succeeded.
- 6bbf4dbca73f4c3f10298738ca7d406bb9d425f1 — no-AI concept-refresh stage; validation run 34308367306 succeeded.
- 3939726132009a398757d7eea8450142707bd77d — workflow route; validation run 34308388300 succeeded.
- f3f9e758fa519adcef0418c1e8f83b61b386a897 — dedicated concept-refresh trigger.
- 50e49dca0a5afe3a33408b6189bea9b5eb7aa358 — final concept-enriched production data.

## Known Issues

- Some Taoguba topic-feed titles label 2026-09-08 but their article pages report publication on 2026-09-07; these remain rejected by the authoritative page-date gate.
- THS matching is deterministic and bounded but still maps broad merged themes to the nearest available catalog concept; output must continue to show exact matched concept names and codes.
- PushPlus request acceptance remains distinct from terminal WeChat receipt.

## Latest Reliable Checkpoint

The 2026-09-08 repair is complete. The final saved production report contains 33 articles plus 10 objective THS concept series. No further rerun is authorized or needed for this source date. Future scheduled runs should start from the current code and preserve the same idempotency gates.

Rollback points:

- Before historical recovery: a597c6fb756a87291baddda9a482e83764d84877.
- Before THS matching/refresh changes: 2afda51aeb36236305120575c1e8ea95c50b5f24.


## Policy Correction — 2026-09-09

User-confirmed release policy supersedes the earlier partial-deadline behavior:

- 15 quality articles is the minimum release threshold, not an immediate-send target.
- Scheduled runs from 20:30 through 21:50 continue discovery and accumulate every quality-approved article.
- No aggregate report or PushPlus request is allowed before 22:00, even when 15 or more articles are already present.
- At or after 22:00, publish only when the quality pool contains at least 15 articles.
- Include the entire quality pool (bounded by the configured discovery safety limit), not only the first 15.
- If fewer than 15 quality articles exist at the deadline, persist the staging pool and the real insufficiency state but do not publish a low-sample summary.

Implementation:

- f6e31ad9b76d1d2e4735c74a66cfc031fc665a8a — enforce the 22:00 and minimum-15 gates.
- b99ce197401e686037cbd5b2a5c3e5234c241353 — update deterministic gate tests.
- d572b0488952cbc26ade5aa33c093b5c3a51a591 — align workflow documentation.
- Final validation run: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34309692212
- Validation job: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34309692212/job/102333653120
- Production stages skipped during validation: concept-refresh, discover, article batches, aggregate, failure alert.
- OpenAI calls: 0.
- PushPlus calls: 0.
- Production data changes: none.

Correction history:

- Run 34309655031 failed because the implementation commit ran against the preceding test expectations.
- Run 34309682420 was superseded and cancelled after the workflow-comment commit.
- Run 34309692212 validated the complete combined state successfully.

Latest reliable checkpoint: the corrected release gate is committed and validated. The next natural 20:30–22:00 cycle should be observed without a manual production trigger. Rollback point before this policy correction: ddb85e9b76b3be709c6a45fa2d8d4d607b6dd184.

## Reliability Hardening — 2026-09-09 Account Handoff

Operation lock: `LOCK-20260909-1238-opinion-tail-reliability`.

Scope and policy impact:

- Removed the remaining `deadline_partial` completion paths from the primary and 21:30 fallback workflows.
- Delivery now enforces the 22:00/minimum-15 gate independently of aggregation.
- Delivery idempotency now keys on the quality-approved source collection, so a concept-only refresh cannot cause another PushPlus request for the same sources.
- The legacy full-stage path now persists an insufficient quality pool without creating a low-sample `latest.json` report.
- Existing ChatGPT Work opinion automations were updated in place; no duplicate automation was created.
- The available automation plan has a five-active-task limit, so the existing 14:38 secondary tail watchdog could not be enabled. The 14:32 tail watchdog remains enabled and the repository retains three staggered tail crons.
- No stock-selection, observation-pool, position, capital, stop-loss, or take-profit rule changed.

Local verification before commit:

- `python -m py_compile research/market_opinion_mining.py`: success.
- 59 deterministic opinion, tail, holding-exit, data-layer, and feedback tests: success.
- OpenAI calls: 0.
- PushPlus calls: 0 (tests use mocked responses only).

Next verification unit:

- Push the single engineering commit and confirm the resulting Market Opinion workflow runs validation only.
- Observe the natural 14:32–14:45 tail cycle; never backfill the missed 2026-09-08 tail signal.
- Observe the natural 20:30–22:15 opinion cycle for source-set idempotency and the hard no-low-sample rule.

Verification result:

- Production commit: `d3e9b9ad1bb9086d672f84bca67fcc8ae1cfca4a`.
- Validation run: https://github.com/CyberAI2026/-akshare-mobile/actions/runs/34312385306 — success.
- Executed jobs: preflight and validate only.
- Skipped jobs: discover, opinion batches, aggregate, concept refresh, and failure alert.
- OpenAI calls: 0.
- PushPlus calls: 0.
- Production opinion and delivery artifacts: unchanged.
- Lock status after this checkpoint commit: closed; natural-cycle observation does not hold an artificial manual write lock.

Latest reliable checkpoint: release and source-set idempotency hardening is committed and validation-only tested. The next incomplete unit is the natural 2026-09-09 tail cycle, followed by the natural opinion cycle.
