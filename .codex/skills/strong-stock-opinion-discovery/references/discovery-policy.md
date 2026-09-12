# Market Opinion Discovery and Delivery Policy

## Scope and source of truth

This policy governs the daily public-article opinion summary. Runtime behavior lives
in `research/market_opinion_mining.py` and the market-opinion workflows; the skill is
the reusable operating contract and does not itself schedule or deliver anything.

## Time and source-date contract

- Business timezone: `Asia/Shanghai`.
- Collection begins at 20:30.
- Additional collections occur at 21:00, 21:10, 21:20, 21:30, 21:40, and 21:50.
- At 22:00, aggregate the complete qualified set collected for that source date.
- A run delayed past midnight must continue using the scheduled source date. It must
  not create a fallback trigger for the new calendar date merely because GitHub
  started the job late.
- GitHub scheduled workflows are best-effort. Preserve them as fallbacks, but use an
  independently deployed scheduler for production dispatch and monitor both paths.

## Discovery contract

Primary public endpoint: `https://www.tgb.cn/talk/getTalkByFlag`.

| Order | Tag | `talkSeq` | Role |
| --- | --- | --- | --- |
| 1 | `#复盘` | `143895` | Primary same-day review discovery |
| 2 | `#每日复盘` | `21325` | Additional same-day review discovery |

Inspect bounded pages from both tags. HTML list pages may supplement discovery when
the topic API is unavailable, but a list timestamp or title is never final proof.

For every candidate:

- Confirm the article's own publication timestamp equals the source date.
- Accept common review-title dates such as `YYYY年M月D日`, `YYYY.M.D`, `YYYY-M-D`,
  `YYYY/M/D`, `M月D日`, `M.D`, and `MMDD复盘`.
- Reject an explicitly old review date. A date attached only to “明日策略” is not
  automatically the review date.
- Require a substantial full article, a market dimension, and a sector/theme/cycle
  dimension. Reject short posts, replies, videos, single-stock diaries, advertising,
  and pages whose date cannot be verified.
- Deduplicate by canonical article identity/URL across tags, pages, collection runs,
  and batches.

## Aggregation and delivery contract

- Save discovery and per-batch results before aggregation so failures resume from
  saved evidence rather than refetching or repeating model calls.
- Accumulate every qualified article through 22:00. Do not publish immediately when
  the count first reaches 15.
- At 22:00, fewer than 15 qualified articles means no low-sample summary and no old
  article padding. Record the block reason and allow only an authorized bounded
  recovery for the same source date.
- Aggregate all qualified articles, not an arbitrary fixed count. Model quality
  validation may remove articles that still violate the formal content contract.
- Compute and persist a stable fingerprint of the final qualified source set.
  Unchanged source sets must not cause a second aggregation or PushPlus request.
- Persist the PushPlus request receipt and delivery key. Treat API code 200 as
  `request_accepted`; terminal WeChat receipt remains unverified unless separately
  observed.

## Objective data separation

Article-derived market and sector views are attributed subjective opinions.
同花顺 concept-index returns, volume, and state labels are objective market data.
Store and display them in separate fields/sections, including their dates and data
sources. A high article mention count is not evidence that a concept rose and is not
a buy recommendation.

## Recovery safety

Before recovery, inspect the source-date staging file, batch outputs, latest summary,
source-set fingerprint, delivery receipt, queued/running Actions, and failure alerts.
Resume only the first incomplete stage. Never rerun a confirmed OpenAI response or
resend a confirmed delivery key. Validation-only code pushes must keep discovery,
OpenAI, and PushPlus jobs skipped.
