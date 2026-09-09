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

export async function dispatchTail(env, now = new Date(), fetchImpl = fetch) {
  const repository = env.GITHUB_REPOSITORY || "CyberAI2026/-akshare-mobile";
  const workflow = env.TAIL_WORKFLOW_FILE || "v5_tail_confirmation.yml";
  const ref = env.GITHUB_REF || "main";
  const headers = githubHeaders(env);
  const workflowPath = encodeURIComponent(workflow);
  const runsUrl = `${GITHUB_API}/repos/${repository}/actions/workflows/${workflowPath}/runs?per_page=30`;
  const data = await githubJson(fetchImpl, runsUrl, { headers });
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

  const dispatchUrl = `${GITHUB_API}/repos/${repository}/actions/workflows/${workflowPath}/dispatches`;
  await githubJson(fetchImpl, dispatchUrl, {
    method: "POST",
    headers: { ...headers, "Content-Type": "application/json" },
    body: JSON.stringify({ ref }),
  });
  return { action: "dispatched", workflow, ref, trade_date: today };
}

export default {
  async scheduled(controller, env, ctx) {
    ctx.waitUntil(
      dispatchTail(env).then((result) => console.log(JSON.stringify(result)))
    );
  },

  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "GET" && url.pathname === "/health") {
      return Response.json({ status: "ok", timezone: SHANGHAI_TZ });
    }
    return new Response("Method not allowed", { status: 405 });
  },
};
