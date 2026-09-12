# Cloudflare tail scheduler

This Worker is an independent dispatcher for the existing tail-confirmation and
market-opinion workflows. It does not select stocks, fetch articles, call OpenAI, or
send PushPlus itself. It checks nearby GitHub workflow runs and sends an idempotent
`workflow_dispatch` request only when the corresponding GitHub schedule is absent.

## Schedule

Cloudflare cron is UTC. The production checks are:

- tail: 06:26/06:31/06:35 UTC (14:26/14:31/14:35 Shanghai), weekdays;
- opinion mining: 12:30, 13:00-13:50 every ten minutes, and 14:00 UTC
  (20:30, 21:00-21:50, and 22:00 Shanghai), daily;
- opinion delivery fallback: 14:12 UTC (22:12 Shanghai), daily.

The first accepted dispatch normally reaches the workflow before its 14:32 safe
window. Later tail checks skip a queued, in-progress, or successful same-day run. A
completed failed/cancelled run blocks automatic retry because its external side
effects cannot be assumed absent.

Opinion checks are slot-aware: an active or nearby scheduled/externally dispatched
run suppresses a duplicate, but a later collection slot is still allowed. External
mining dispatches carry `scheduler_mode=external_schedule` and an explicit Shanghai
source date, so they do not acquire manual-force semantics. Article/source-set and
delivery receipts remain the final idempotency guards inside the workflow.

GitHub's existing staggered crons and the ChatGPT watchdogs remain fallbacks and
monitors. No scheduler can guarantee terminal WeChat delivery; production acceptance
requires both a successful GitHub run and a separately verified terminal receipt.

## One-time deployment

Prerequisites:

1. Connect the authorized Cloudflare account.
2. Create a fine-grained GitHub token limited to
   `CyberAI2026/-akshare-mobile`, with Actions read/write permission and no broader
   repository access than required.
3. Store it only as the Worker secret `GITHUB_ACTIONS_TOKEN`; never commit it.

The preferred production path is the manually dispatched GitHub Actions workflow
`Deploy Cloudflare Tail Scheduler`. Store these repository Actions secrets first:

- `CLOUDFLARE_API_TOKEN`: a Cloudflare API token limited to Workers deployment;
- `CLOUDFLARE_ACCOUNT_ID`: the target Cloudflare account ID;
- `TAIL_DISPATCH_GITHUB_TOKEN`: the fine-grained GitHub token described above.

Run the workflow only with confirmation value `DEPLOY`. It tests the scheduler,
deploys the Worker, and uploads `TAIL_DISPATCH_GITHUB_TOKEN` to Cloudflare as the
Worker secret `GITHUB_ACTIONS_TOKEN`. Secret values must never be committed or
copied into an issue, log, or chat.

For an authorized local interactive environment, the equivalent commands from this
directory are:

```bash
npm test
npx wrangler secret put GITHUB_ACTIONS_TOKEN
npx wrangler deploy
```

After deployment, verify the Worker exists, all five cron expressions are present,
observability is enabled, and `GET /health` returns `{"status":"ok"}`. Do not use a
manual production dispatch merely to test deployment; verify the next natural
trading-day cycle and its GitHub/PushPlus/terminal-delivery evidence.
