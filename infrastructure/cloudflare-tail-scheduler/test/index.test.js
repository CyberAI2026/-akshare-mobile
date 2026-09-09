import assert from "node:assert/strict";
import test from "node:test";

import { dispatchTail, shanghaiDate } from "../src/index.js";

const env = {
  GITHUB_ACTIONS_TOKEN: "test-token",
  GITHUB_REPOSITORY: "CyberAI2026/-akshare-mobile",
  GITHUB_REF: "main",
  TAIL_WORKFLOW_FILE: "v5_tail_confirmation.yml",
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
