# Cloudflare tail scheduler

This Worker is an independent scheduler for the existing `V5 Tail Confirmation`
workflow. It does not select stocks, call OpenAI, or send PushPlus messages itself.
It only checks existing workflow runs and sends an idempotent GitHub
`workflow_dispatch` request when no same-day scheduled production run exists.

## Schedule

Cloudflare cron is UTC. The three weekday checks are:

- 06:26 UTC / 14:26 Asia/Shanghai;
- 06:31 UTC / 14:31 Asia/Shanghai;
- 06:35 UTC / 14:35 Asia/Shanghai.

The first accepted dispatch normally reaches the workflow before its 14:32 safe
window. Later checks skip a queued, in-progress, or successful same-day run. A
completed failed/cancelled run blocks automatic retry because its external side
effects cannot be assumed absent.

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

After deployment, verify the Worker exists, all three cron triggers are present,
observability is enabled, and `GET /health` returns `{"status":"ok"}`. Do not use a
manual production dispatch merely to test deployment; verify the next natural
trading-day cycle and its GitHub/PushPlus/terminal-delivery evidence.
