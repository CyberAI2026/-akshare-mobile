from pathlib import Path
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_workflow(name: str) -> dict:
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


class WorkflowReliabilityTests(unittest.TestCase):
    def test_all_automatic_jobs_have_a_finite_safety_timeout(self):
        violations = []
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            triggers = workflow.get("on", workflow.get(True, {})) or {}
            automatic = isinstance(triggers, dict) and any(key in triggers for key in ("push", "schedule"))
            if not automatic:
                continue
            for job_name, job in (workflow.get("jobs") or {}).items():
                if "uses" in job:
                    continue
                timeout = job.get("timeout-minutes")
                # The user's 10-minute rule applies to interactive ChatGPT work slices,
                # not to GitHub data jobs. Cloud jobs may run longer, but never unbounded.
                if timeout is None or timeout > 60:
                    violations.append(f"{path.name}:{job_name}:{timeout}")
        self.assertEqual(violations, [])

    def test_opinion_aggregate_pushes_even_if_cron_is_late(self):
        workflow = load_workflow("v5_market_opinion.yml")
        env = workflow["jobs"]["aggregate"]["env"]
        self.assertEqual(str(env["OPINION_PUSH_AFTER_AGGREGATE"]), "1")

    def test_opinion_external_schedule_is_not_treated_as_manual_force(self):
        workflow = load_workflow("v5_market_opinion.yml")
        triggers = workflow.get("on", workflow.get(True, {}))
        inputs = triggers["workflow_dispatch"]["inputs"]
        self.assertIn("scheduler_mode", inputs)
        self.assertIn("source_date", inputs)
        text = (ROOT / ".github" / "workflows" / "v5_market_opinion.yml").read_text(encoding="utf-8")
        self.assertIn('scheduler_mode=="external_schedule"', text)
        self.assertIn("source_date输入超出安全窗口", text)

    def test_delayed_opinion_fallback_keeps_previous_business_date_before_six(self):
        text = (ROOT / ".github" / "workflows" / "v5_market_opinion_2130_fallback.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count("now_cn.hour<6") + text.count("now.hour<6"), 2)
        self.assertIn('"source_date": business_day.isoformat()', text)

    def test_after_close_has_failure_alert(self):
        workflow = load_workflow("v5_after_close.yml")
        alert = workflow["jobs"]["failure-alert"]
        self.assertLessEqual(alert["timeout-minutes"], 5)
        self.assertIn("ai-finalize", alert["needs"])

    def test_long_run_watchdog_checks_every_thirty_minutes(self):
        workflow = load_workflow("v5_workflow_watchdog.yml")
        triggers = workflow.get("on", workflow.get(True, {}))
        self.assertEqual(triggers["schedule"][0]["cron"], "*/30 * * * *")
        self.assertEqual(workflow["permissions"]["actions"], "read")
        self.assertLessEqual(workflow["jobs"]["inspect-progress"]["timeout-minutes"], 5)


if __name__ == "__main__":
    unittest.main()
