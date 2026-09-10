from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
from unittest.mock import patch

sys.modules.setdefault("akshare", MagicMock())
sys.modules.setdefault("requests", MagicMock())

from v5_cli import (_after_close_response_schema, _apply_sector_evidence_gate,
                    _cap_observation_pool, _post_gate_portfolio_note)
from v5_core import openai_analyze


class AfterCloseAIContractTests(unittest.TestCase):
    def test_schema_requires_all_second_start_dimensions(self):
        schema = _after_close_response_schema()
        item = schema["properties"]["decisions"]["items"]
        self.assertFalse(item["additionalProperties"])
        for field in [
            "confidence_level", "structure_assessment", "volume_assessment",
            "amplitude_assessment", "turnover_assessment", "sector_resonance",
        ]:
            self.assertIn(field, item["required"])

    def test_sector_gate_removes_retreat_but_keeps_unverified_conditionally(self):
        selected = ["000001", "000002", "000003"]
        decisions = {
            code: {"decision": "SELECT", "confidence_level": "高", "risk": ""}
            for code in selected
        }
        context = {"stocks": [
            {"股票代码": "000001", "板块共振状态": "同期概念共振"},
            {"股票代码": "000002", "板块共振状态": "同期概念退潮"},
            {"股票代码": "000003", "板块共振状态": "概念已映射但同期行情未核验"},
        ]}
        kept, retreat, unverified = _apply_sector_evidence_gate(selected, decisions, context)
        self.assertEqual(kept, ["000001", "000003"])
        self.assertEqual(retreat, ["000002"])
        self.assertEqual(unverified, ["000003"])
        self.assertEqual(decisions["000002"]["decision"], "WAIT")
        self.assertEqual(decisions["000003"]["decision"], "SELECT")
        self.assertEqual(decisions["000003"]["confidence_level"], "低")

    def test_pool_over_ten_uses_70_30_ranking(self):
        selected=[f"{i:06d}" for i in range(1,12)]
        decisions={code:{"decision":"SELECT","priority":i+1,"risk":""} for i,code in enumerate(selected)}
        context={"stocks":[]}
        kept,trimmed,scores=_cap_observation_pool(selected,decisions,context)
        self.assertEqual(len(kept),10)
        self.assertEqual(trimmed,["000011"])
        self.assertEqual(decisions["000011"]["decision"],"WAIT")
        self.assertIn("超过10只",decisions["000011"]["risk"])

    def test_sector_divergence_cannot_remain_high_confidence(self):
        decisions = {"000001": {"decision": "SELECT", "confidence_level": "高", "risk": ""}}
        context = {"stocks": [{"股票代码": "000001", "板块共振状态": "同期概念分化"}]}
        kept, retreat, unverified = _apply_sector_evidence_gate(["000001"], decisions, context)
        self.assertEqual(kept, ["000001"])
        self.assertFalse(retreat)
        self.assertFalse(unverified)
        self.assertEqual(decisions["000001"]["confidence_level"], "中")

    def test_post_gate_portfolio_note_uses_final_pool_count(self):
        note = _post_gate_portfolio_note(
            ["002041", "002329", "600368"], [], ["002329", "600368"]
        )
        self.assertIn("正式观察池共3只（002041、002329、600368）", note)
        self.assertIn("002329、600368", note)
        self.assertIn("条件观察", note)

    def test_openai_call_uses_structured_output_contract(self):
        captured = {}

        class FakeResponses:
            def create(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(
                    output_text='{"ok":true}', status="completed", incomplete_details=None,
                    id="resp_test", model="test-model",
                    usage=SimpleNamespace(input_tokens=1, output_tokens=2, total_tokens=3),
                )

        fake_module = SimpleNamespace(OpenAI=lambda api_key: SimpleNamespace(responses=FakeResponses()))
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {"openai": fake_module}), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            previous = Path.cwd()
            os.chdir(td)
            try:
                result = openai_analyze(
                    "盘后观察池", {"x": 1}, output_schema={"type": "object"},
                    schema_name="test_schema", max_output_tokens=20000,
                )
            finally:
                os.chdir(previous)
        self.assertEqual(json.loads(result), {"ok": True})
        self.assertEqual(captured["max_output_tokens"], 20000)
        self.assertEqual(captured["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured["text"]["format"]["strict"])

    def test_incomplete_openai_output_is_not_accepted_as_success(self):
        class FakeResponses:
            def create(self, **kwargs):
                return SimpleNamespace(
                    output_text='{"partial":', status="incomplete",
                    incomplete_details=SimpleNamespace(reason="max_output_tokens"),
                    id="resp_partial", model="test-model",
                    usage=SimpleNamespace(input_tokens=1, output_tokens=12000, total_tokens=12001),
                )

        fake_module = SimpleNamespace(OpenAI=lambda api_key: SimpleNamespace(responses=FakeResponses()))
        with tempfile.TemporaryDirectory() as td, patch.dict(sys.modules, {"openai": fake_module}), \
             patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):
            previous = Path.cwd()
            os.chdir(td)
            try:
                with self.assertRaisesRegex(RuntimeError, "max_output_tokens"):
                    openai_analyze("盘后观察池", {"x": 1})
                audit = json.loads(Path("v5_data/openai_audit/latest.json").read_text(encoding="utf-8"))
                self.assertEqual(audit["status"], "incomplete")
                self.assertEqual(audit["incomplete_reason"], "max_output_tokens")
                self.assertEqual(
                    Path("v5_data/openai_audit/latest_output.txt").read_text(encoding="utf-8"),
                    '{"partial":',
                )
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
