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
