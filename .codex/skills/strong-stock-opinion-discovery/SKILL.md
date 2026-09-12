---
name: strong-stock-opinion-discovery
description: Use when operating, diagnosing, changing, recovering, or accepting the strong-stock project's daily market-opinion collection and PushPlus summary. Covers 淘股吧 #复盘/#每日复盘 discovery, same-day article validation, the 20:30-22:00 collection window, the 15-article publication floor, source-set idempotency, and separation of article opinions from 同花顺 objective concept-index facts.
---

# Strong Stock Opinion Discovery

Apply this skill to the market-opinion workflow in
`CyberAI2026/-akshare-mobile`. Read `references/discovery-policy.md` completely
before changing or recovering the workflow.

## Required operating sequence

1. Use the project's resumable-operations skill and verify the live repository SHA,
   Actions state, write lock, latest opinion artifacts, and delivery receipt.
2. Resolve one explicit source date in Asia/Shanghai. A delayed run after midnight
   must retain its intended business date and must not create a new-day trigger.
3. Discover from the dedicated `#复盘` feed first and `#每日复盘` feed second; visible
   list pages are fallbacks, not substitutes for article-page validation.
4. Require the article page's publication date to equal the source date and require
   substantive market plus sector/cycle content. Never fill the count with old,
   single-stock, short, or unverifiable posts.
5. Accumulate through 22:00. Publish only at/after 22:00 when at least 15 articles
   pass all quality gates. Fifteen is a floor, not a send-immediately target.
6. Keep subjective article consensus separate from objective 同花顺 concept-index
   data. Never present mentions as price performance or recommendations.
7. Before any OpenAI or PushPlus call, verify the saved source-set fingerprint and
   delivery receipt. The same qualified source set must not be summarized or sent
   twice. `request_accepted` does not prove terminal WeChat receipt.

For read-only diagnosis or validation-only commits, do not fetch new articles, call
OpenAI, or send PushPlus. Record evidence and update the unified checkpoint.
