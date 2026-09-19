import assert from "node:assert/strict";
import test from "node:test";

import {
  dispatchOpinion,
  dispatchOpinionDelivery,
  dispatchTail,
  routeSchedule,
  sendSchedulerFailureAlert,
  shanghaiDate,
} from "../src/index.js";

const env = {
  GITHUB_ACTIONS_TOKEN: "test-token",
  GITHUB_REPOSITORY: "CyberAI2026/-akshare-mobile",
  GITHUB_REF: "main",
  TAIL_WORKFLOW_FILE: "v5_tail_confirmation.yml",
  OPINION_WORKFLOW_FILE: "v5_market_opinion.yml",
  OPINION_DELIVERY_WORKFLOW_FILE: "v5_market_opinion_delivery.yml",
};
const now = new Date("2026-09-10T06:26:00Z");

function response(status, body = null) {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

test("Shanghai date conversion is explicit", () => {
  assert.equal(shanghaiDate(now), "2026-09-10");
});

test("dispatches when no scheduled run exists", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return calls.length === 1 ? response(200, { workflow_runs: [] }) : response(204);
  };
  const result = await dispatchTail(env, now, fakeFetch);
  assert.equal(result.action, "dispatched");
  assert.equal(calls.length, 2);
  assert.equal(calls[1].options.method, "POST");
});

test("skips an active same-day workflow", async () => {
  const fakeFetch = async () => response(200, { workflow_runs: [{
    id: 101,
    event: "workflow_dispatch",
    status: "in_progress",
    conclusion: null,
    created_at: "2026-09-10T06:25:00Z",
  }] });
  const result = await dispatchTail(env, now, fakeFetch);
  assert.deepEqual(result, { action: "skip_active", run_id: 101, trade_date: "2026-09-10" });
});

test("skips a successful same-day schedule", async () => {
  const fakeFetch = async () => response(200, { workflow_runs: [{
    id: 102,
    event: "schedule",
    status: "completed",
    conclusion: "success",
    created_at: "2026-09-10T06:20:00Z",
  }] });
  const result = await dispatchTail(env, now, fakeFetch);
  assert.equal(result.action, "skip_success");
});

test("does not automatically retry an uncertain failed run", async () => {
  const fakeFetch = async () => response(200, { workflow_runs: [{
    id: 103,
    event: "workflow_dispatch",
    status: "completed",
    conclusion: "failure",
    created_at: "2026-09-10T06:24:00Z",
  }] });
  const result = await dispatchTail(env, now, fakeFetch);
  assert.equal(result.action, "block_failed_run");
  assert.equal(result.run_id, 103);
});

test("a documentation push run does not block production dispatch", async () => {
  let calls = 0;
  const fakeFetch = async () => {
    calls += 1;
    return calls === 1 ? response(200, { workflow_runs: [{
      id: 104,
      event: "push",
      status: "completed",
      conclusion: "success",
      created_at: "2026-09-10T02:00:00Z",
    }] }) : response(204);
  };
  const result = await dispatchTail(env, now, fakeFetch);
  assert.equal(result.action, "dispatched");
});

test("opinion dispatch carries an audited external-schedule source date", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return calls.length === 1 ? response(200, { workflow_runs: [] }) : response(204);
  };
  const opinionNow = new Date("2026-09-11T12:30:00Z");
  const result = await dispatchOpinion(env, opinionNow, fakeFetch);
  assert.equal(result.action, "dispatched");
  const body = JSON.parse(calls[1].options.body);
  assert.deepEqual(body.inputs, {
    scheduler_mode: "external_schedule",
    source_date: "2026-09-11",
  });
});

test("opinion slot skips a nearby GitHub schedule", async () => {
  const fakeFetch = async () => response(200, { workflow_runs: [{
    id: 201,
    event: "schedule",
    status: "completed",
    conclusion: "success",
    created_at: "2026-09-11T12:27:00Z",
  }] });
  const result = await dispatchOpinion(env, new Date("2026-09-11T12:30:00Z"), fakeFetch);
  assert.equal(result.action, "skip_recent_success");
  assert.equal(result.run_id, 201);
});

test("opinion delivery uses its dedicated workflow", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return calls.length === 1 ? response(200, { workflow_runs: [] }) : response(204);
  };
  const result = await dispatchOpinionDelivery(env, new Date("2026-09-11T14:12:00Z"), fakeFetch);
  assert.equal(result.workflow, "v5_market_opinion_delivery.yml");
  assert.deepEqual(JSON.parse(calls[1].options.body).inputs, {
    source_date: "2026-09-11",
  });
});

test("cron routing separates tail, mining, and delivery", async () => {
  const fakeFetch = async (_url, options = {}) =>
    options.method === "POST" ? response(204) : response(200, { workflow_runs: [] });
  const tail = await routeSchedule("26 6 * * 1-5", env, now, fakeFetch);
  const mining = await routeSchedule("30 12 * * *", env, now, fakeFetch);
  const delivery = await routeSchedule("12 14 * * *", env, now, fakeFetch);
  assert.equal(tail.workflow, "v5_tail_confirmation.yml");
  assert.equal(mining.workflow, "v5_market_opinion.yml");
  assert.equal(delivery.workflow, "v5_market_opinion_delivery.yml");
});

test("each independent tail cron routes to the tail workflow", async () => {
  const fakeFetch = async (_url, options = {}) =>
    options.method === "POST" ? response(204) : response(200, { workflow_runs: [] });
  for (const cron of [
    "26 6 * * 1-5",
    "31 6 * * 1-5",
    "35 6 * * 1-5",
    "38 6 * * 1-5",
  ]) {
    const result = await routeSchedule(cron, env, now, fakeFetch);
    assert.equal(result.workflow, "v5_tail_confirmation.yml");
  }
});

test("scheduler failures can alert independently of GitHub Actions", async () => {
  const calls = [];
  const fakeFetch = async (url, options = {}) => {
    calls.push({ url, options });
    return response(200, { code: 200, data: "receipt" });
  };
  const result = await sendSchedulerFailureAlert(
    { ...env, PUSHPLUS_TOKEN: "push-token" },
    "26 6 * * 1-5",
    new Error("GitHub API 503"),
    fakeFetch,
  );
  assert.equal(result.action, "alert_accepted");
  assert.equal(calls.length, 1);
  const body = JSON.parse(calls[0].options.body);
  assert.equal(body.token, "push-token");
  assert.match(body.content, /GitHub API 503/);
});
