const GITHUB_API = "https://api.github.com";
const SHANGHAI_TZ = "Asia/Shanghai";

export function shanghaiDate(date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: SHANGHAI_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}

function githubHeaders(env) {
  if (!env.GITHUB_ACTIONS_TOKEN) {
    throw new Error("GITHUB_ACTIONS_TOKEN is not configured");
  }
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${env.GITHUB_ACTIONS_TOKEN}`,
    "User-Agent": "strong-stock-tail-dispatcher",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

async function githubJson(fetchImpl, url, options) {
  const response = await fetchImpl(url, options);
  if (!response.ok) {
    throw new Error(`GitHub API ${response.status}: ${await response.text()}`);
  }
  return response.status === 204 ? null : response.json();
}

async function workflowRuns(env, workflow, fetchImpl) {
  const repository = env.GITHUB_REPOSITORY || "CyberAI2026/-akshare-mobile";
  const workflowPath = encodeURIComponent(workflow);
  const url = `${GITHUB_API}/repos/${repository}/actions/workflows/${workflowPath}/runs?per_page=30`;
  return githubJson(fetchImpl, url, { headers: githubHeaders(env) });
}

async function dispatchWorkflow(env, workflow, inputs, fetchImpl) {
  const repository = env.GITHUB_REPOSITORY || "CyberAI2026/-akshare-mobile";
  const ref = env.GITHUB_REF || "main";
  const workflowPath = encodeURIComponent(workflow);
  const url = `${GITHUB_API}/repos/${repository}/actions/workflows/${workflowPath}/dispatches`;
  const body = { ref };
  if (inputs && Object.keys(inputs).length) body.inputs = inputs;
  await githubJson(fetchImpl, url, {
    method: "POST",
    headers: { ...githubHeaders(env), "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return { action: "dispatched", workflow, ref };
}

export async function dispatchTail(env, now = new Date(), fetchImpl = fetch) {
  const workflow = env.TAIL_WORKFLOW_FILE || "v5_tail_confirmation.yml";
  const data = await workflowRuns(env, workflow, fetchImpl);
  const today = shanghaiDate(now);
  const scheduledRuns = (data.workflow_runs || []).filter((run) =>
    ["schedule", "workflow_dispatch"].includes(run.event) &&
    shanghaiDate(new Date(run.created_at)) === today
  );

  const active = scheduledRuns.find((run) => ["queued", "in_progress"].includes(run.status));
  if (active) {
    return { action: "skip_active", run_id: active.id, trade_date: today };
  }
  const success = scheduledRuns.find((run) => run.status === "completed" && run.conclusion === "success");
  if (success) {
    return { action: "skip_success", run_id: success.id, trade_date: today };
  }
  const uncertainFailure = scheduledRuns.find((run) => run.status === "completed");
  if (uncertainFailure) {
    return {
      action: "block_failed_run",
      run_id: uncertainFailure.id,
      conclusion: uncertainFailure.conclusion,
      trade_date: today,
    };
  }

  return { ...(await dispatchWorkflow(env, workflow, null, fetchImpl)), trade_date: today };
}

async function dispatchRecentSlot(env, workflow, now, lookbackMinutes, inputs, fetchImpl) {
  const data = await workflowRuns(env, workflow, fetchImpl);
  const today = shanghaiDate(now);
  const relevant = (data.workflow_runs || []).filter((run) =>
    ["schedule", "workflow_dispatch"].includes(run.event) &&
    shanghaiDate(new Date(run.created_at)) === today
  );
  const active = relevant.find((run) => ["queued", "in_progress", "waiting", "pending"].includes(run.status));
  if (active) return { action: "skip_active", run_id: active.id, source_date: today };

  const cutoff = now.getTime() - lookbackMinutes * 60 * 1000;
  const recent = relevant.find((run) => new Date(run.created_at).getTime() >= cutoff);
  if (recent) {
    return {
      action: recent.conclusion === "success" ? "skip_recent_success" : "block_recent_run",
      run_id: recent.id,
      conclusion: recent.conclusion,
      source_date: today,
    };
  }
  return {
    ...(await dispatchWorkflow(env, workflow, inputs, fetchImpl)),
    source_date: today,
  };
}

export async function dispatchOpinion(env, now = new Date(), fetchImpl = fetch) {
  const workflow = env.OPINION_WORKFLOW_FILE || "v5_market_opinion.yml";
  const sourceDate = shanghaiDate(now);
  return dispatchRecentSlot(
    env, workflow, now, 8,
    { scheduler_mode: "external_schedule", source_date: sourceDate },
    fetchImpl,
  );
}

export async function dispatchOpinionDelivery(env, now = new Date(), fetchImpl = fetch) {
  const workflow = env.OPINION_DELIVERY_WORKFLOW_FILE || "v5_market_opinion_delivery.yml";
  return dispatchRecentSlot(env, workflow, now, 8, null, fetchImpl);
}

export async function routeSchedule(cron, env, now = new Date(), fetchImpl = fetch) {
  if (cron === "26,31,35 6 * * 1-5") return dispatchTail(env, now, fetchImpl);
  if (["30 12 * * *", "0,10,20,30,40,50 13 * * *", "0 14 * * *"].includes(cron)) {
    return dispatchOpinion(env, now, fetchImpl);
  }
  if (cron === "12 14 * * *") return dispatchOpinionDelivery(env, now, fetchImpl);
  return { action: "ignored_unknown_cron", cron };
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      routeSchedule(controller.cron, env).then((result) => console.log(JSON.stringify(result)))
    );
  },

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ status: "ok", timezone: SHANGHAI_TZ, workflows: ["tail", "opinion", "opinion-delivery"] });
    }
    return new Response("Method not allowed", { status: 405 });
  },
};
