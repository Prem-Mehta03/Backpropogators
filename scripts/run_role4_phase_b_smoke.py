"""Offline smoke of the unchanged Prem client using its supported injected API."""

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import argparse
import json
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from procedural.llm_client import LLMClient, LLMClientError
from evaluation.role4.integration.adapters.prem_client_adapter import PremClientAdapter
from evaluation.role4.logger import write_json


class FakeChatAPI:
    """Role 4 transport fixture shaped like the API already injected by Prem's tests."""

    def __init__(self, response=None, error=None):
        self.response, self.error = response, error
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(deepcopy(kwargs))
        if self.error is not None:
            raise self.error
        return deepcopy(self.response)


def raw_reply(content=None, arguments=None):
    calls = [] if arguments is None else [SimpleNamespace(
        id="requested_tool_001",
        function=SimpleNamespace(name="read_lidar", arguments=arguments),
    )]
    message = SimpleNamespace(content=content, tool_calls=calls)
    return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def run_smoke(output_dir):
    events, cases = [], []
    fixtures = (
        ("plain_reply", raw_reply("offline pong"), None),
        ("parsed_tool_request", raw_reply(arguments='{"direction":"front"}'), None),
        ("malformed_tool_arguments", raw_reply(arguments="{broken"), None),
        ("transport_error", None, TimeoutError("Phase B injected transport timeout")),
    )
    for name, raw, injected_error in fixtures:
        api = FakeChatAPI(raw, injected_error)
        client = LLMClient(client=api, model="phase-b-offline-fixture")
        adapter = PremClientAdapter(client, backend_provenance="real", model_mode="fake_api")
        reply = None
        error = None
        try:
            reply = adapter.chat([{"role": "user", "content": "Offline client boundary probe."}])
        except LLMClientError as exc:
            error = {"type": type(exc).__name__, "message": str(exc)}
        if name == "plain_reply":
            verified = reply is not None and reply.content == "offline pong" and not reply.tool_calls
        elif name == "parsed_tool_request":
            verified = (reply is not None and len(reply.tool_calls) == 1 and
                        reply.tool_calls[0].arguments == {"direction": "front"} and
                        reply.tool_calls[0].arguments_error is None)
        elif name == "malformed_tool_arguments":
            verified = (reply is not None and len(reply.tool_calls) == 1 and
                        reply.tool_calls[0].arguments == {} and
                        reply.tool_calls[0].arguments_error is not None)
        else:
            verified = error is not None and reply is None
        verified = bool(verified and len(api.calls) == 1 and len(adapter.events) == 2)
        for event in adapter.events:
            events.append({"case": name, **event})
        cases.append({
            "case": name, **adapter.labels,
            "expected_outcome_confirmed": verified, "error": error,
            "actual_api_requests": api.calls,
            "observed_reply": adapter.events[-1]["payload"] if reply is not None else None,
        })
    summary = {
        "phase": "NEW_B", "backend_provenance": "real", "model_mode": "fake_api",
        "integration_scope": "partial_pipeline", "pipeline_stage": "client_chat_only",
        "layer_provenance": {"procedural": "real"},
        "unexercised_layers": ["declarative", "sensorimotor"],
        "complete_agent_integrated": False, "tools_executed": False,
        "hosted_reliability_measured": False, "human_review": "not_reviewed",
        "cases": cases, "all_expectations_met": all(c["expected_outcome_confirmed"] for c in cases),
    }
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "prem_client_trace.jsonl").open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, sort_keys=True, allow_nan=False) + "\n")
    write_json(output / "prem_client_result.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "evaluation/logs/role4/phase_b")
    args = parser.parse_args(argv)
    result = run_smoke(args.output_dir)
    for case in result["cases"]:
        print(f"{case['case']}: {'verified' if case['expected_outcome_confirmed'] else 'unexpected'}")
    print("Prem client=real; model=fake_api; scope=client_chat_only; tools executed=false.")
    print("Single-tool pipeline blocked by missing official modules; no hosted trial or prose review.")
    return 0 if result["all_expectations_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
