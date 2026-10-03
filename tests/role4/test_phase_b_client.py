"""Conservative compatibility checks around actual Prem chat implementations."""

from copy import deepcopy
import unittest

from procedural.llm_client import LLMClient, LLMClientError, LLMResponse
from tests.procedural.scripted_llm import ScriptedLLM
from evaluation.role4.contracts.events import ContractError
from evaluation.role4.integration.adapters.prem_client_adapter import PremClientAdapter
from evaluation.role4.integration.runner import ROOT
from scripts.run_role4_phase_b_smoke import FakeChatAPI, raw_reply, run_smoke


class PhaseBClientTests(unittest.TestCase):
    def adapter(self, raw=None, error=None):
        api = FakeChatAPI(raw, error)
        adapter = PremClientAdapter(
            LLMClient(client=api, model="offline-fixture"),
            backend_provenance="real", model_mode="fake_api",
        )
        return adapter, api

    def test_actual_prem_client_forwards_request_and_records_normalised_reply(self):
        adapter, api = self.adapter(raw_reply("reply"))
        messages = [{"role": "user", "content": "probe"}]
        tools = [{"type": "function", "function": {"name": "fixture_only"}}]
        response = adapter.chat(messages, tools, "none")
        self.assertEqual(response.content, "reply")
        self.assertEqual(api.calls[0]["messages"], messages)
        self.assertEqual(api.calls[0]["tools"], tools)
        self.assertEqual(api.calls[0]["tool_choice"], "none")
        self.assertEqual(api.calls[0]["temperature"], 0.0)
        self.assertEqual([e["event_type"] for e in adapter.events], ["client_request", "client_response"])
        self.assertEqual(adapter.events[0]["call_id"], adapter.events[1]["call_id"])
        self.assertEqual(adapter.events[1]["payload"]["content"], response.content)

    def test_existing_scripted_llm_is_exercised_through_public_chat_only(self):
        backend = ScriptedLLM([LLMResponse("scripted reply")])
        adapter = PremClientAdapter(backend, backend_provenance="reference", model_mode="scripted_llm")
        messages = [{"role": "user", "content": "probe"}]
        self.assertEqual(adapter.chat(messages).content, "scripted reply")
        self.assertEqual(backend.seen, [messages])
        self.assertEqual(backend.tool_choices, [None])
        self.assertEqual(adapter.events[1]["backend_provenance"], "reference")
        self.assertFalse(adapter.events[1]["tools_executed"])

    def test_client_error_is_recorded_and_propagates_without_fallback_answer(self):
        adapter, api = self.adapter(error=TimeoutError("injected timeout"))
        with self.assertRaises(LLMClientError):
            adapter.chat([{"role": "user", "content": "probe"}])
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(adapter.events[-1]["event_type"], "client_error")
        self.assertFalse(adapter.events[-1]["payload"]["answer_created"])
        self.assertFalse(any(e["event_type"] == "client_response" for e in adapter.events))

    def test_malformed_tool_arguments_remain_parsing_errors_not_tool_results(self):
        adapter, _ = self.adapter(raw_reply(arguments="[1,2]"))
        response = adapter.chat([{"role": "user", "content": "probe"}])
        self.assertIsNotNone(response.tool_calls[0].arguments_error)
        self.assertEqual(response.tool_calls[0].arguments, {})
        self.assertEqual(adapter.events[-1]["payload"]["tool_calls"][0]["id"], "requested_tool_001")
        self.assertFalse(adapter.events[-1]["tools_executed"])
        self.assertNotIn("evidence", adapter.events[-1]["payload"])

    def test_invalid_public_response_is_a_contract_error_not_a_passing_smoke(self):
        backend = ScriptedLLM([{"content": "not the published response type"}])
        adapter = PremClientAdapter(backend, backend_provenance="reference", model_mode="scripted_llm")
        with self.assertRaises(ContractError):
            adapter.chat([{"role": "user", "content": "probe"}])
        self.assertEqual(adapter.events[-1]["event_type"], "client_error")

    def test_observations_are_detached_from_later_caller_and_reply_mutation(self):
        adapter, _ = self.adapter(raw_reply(arguments='{"direction":"front"}'))
        messages = [{"role": "user", "content": "original"}]
        response = adapter.chat(messages)
        events = deepcopy(adapter.events)
        messages[0]["content"] = "changed"
        response.tool_calls[0].arguments["direction"] = "changed"
        self.assertEqual(adapter.events, events)

    def test_repeated_smoke_is_deterministic_and_does_not_claim_complete_integration(self):
        output = ROOT / "evaluation/logs/role4/phase_b/tests/client_repeat"
        first = run_smoke(output)
        second = run_smoke(output)
        self.assertEqual(first, second)
        self.assertTrue(first["all_expectations_met"])
        self.assertEqual(len(first["cases"]), 4)
        self.assertEqual(first["layer_provenance"], {"procedural": "real"})
        self.assertEqual(first["model_mode"], "fake_api")
        self.assertFalse(first["complete_agent_integrated"])
        self.assertFalse(first["hosted_reliability_measured"])
        self.assertFalse(first["tools_executed"])
        self.assertEqual(first["human_review"], "not_reviewed")

    def test_backend_and_model_labels_are_explicit_and_validated(self):
        backend = ScriptedLLM([LLMResponse("reply")])
        for ownership, mode in (("mixed", "fake_api"), ("unknown", "fake_api"), ("real", "unknown")):
            with self.subTest(ownership=ownership, mode=mode), self.assertRaises(ContractError):
                PremClientAdapter(backend, backend_provenance=ownership, model_mode=mode)


if __name__ == "__main__":
    unittest.main()
