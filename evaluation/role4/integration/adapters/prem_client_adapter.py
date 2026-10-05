"""Observe Prem's public chat boundary; no tool dispatch or agent-loop emulation."""

from copy import deepcopy
from dataclasses import asdict

from procedural.llm_client import LLMBackend, LLMResponse, ToolCall
from evaluation.role4.contracts.events import ContractError, nonempty
from evaluation.role4.models import validate_json, utc_now


class PremClientAdapter:
    """Forward chat unchanged, retain detached request/reply/error observations.

    Backend provenance describes implementation ownership; model mode describes
    execution. Neither a parsed tool request nor arbitrary text is sensor evidence.
    Exceptions propagate after an error observation; no fallback answer is created.
    """

    def __init__(self, backend: LLMBackend, *, backend_provenance, model_mode):
        if backend_provenance not in {"reference", "real"}:
            raise ContractError("A single client must be labelled reference or real")
        if model_mode not in {"fake_api", "scripted_llm", "hosted"}:
            raise ContractError("Client model_mode must be fake_api, scripted_llm or hosted")
        self.backend = backend
        self.labels = {
            "backend_provenance": backend_provenance,
            "model_mode": model_mode,
            "integration_scope": "partial_pipeline",
            "pipeline_stage": "client_chat_only",
            "source_layer": "procedural",
            "implementation": f"{type(backend).__module__}.{type(backend).__name__}",
            "tools_executed": False,
            "human_review": "not_reviewed",
        }
        self.events = []
        self._calls = 0

    def _record(self, kind, call_id, payload):
        self.events.append({
            "timestamp": utc_now(), "event_type": kind, "call_id": call_id,
            **self.labels, "payload": deepcopy(payload),
        })

    def chat(self, messages, tools=None, tool_choice=None) -> LLMResponse:
        """Use only backend.chat; record actual normalised reply and propagate errors."""
        request = {"messages": messages, "tools": tools, "tool_choice": tool_choice}
        validate_json(request)
        self._calls += 1
        call_id = f"client_{self._calls:03}"
        self._record("client_request", call_id, request)
        try:
            response = self.backend.chat(messages, tools, tool_choice)
            if not isinstance(response, LLMResponse):
                raise ContractError("Prem chat boundary requires an LLMResponse")
            if response.content is not None and not isinstance(response.content, str):
                raise ContractError("Client content must be text or null")
            if not isinstance(response.tool_calls, list):
                raise ContractError("Client tool_calls must be a list")
            for call in response.tool_calls:
                if not isinstance(call, ToolCall) or not isinstance(call.arguments, dict):
                    raise ContractError("Client tool calls require ToolCall and object arguments")
                nonempty(call.id, "client tool call ID")
                nonempty(call.name, "client tool name")
                if call.arguments_error is not None and not isinstance(call.arguments_error, str):
                    raise ContractError("Client argument errors must be text or null")
            payload = asdict(response)
            validate_json(payload)
        except Exception as exc:
            self._record("client_error", call_id, {
                "error_type": type(exc).__name__, "message": str(exc),
                "answer_created": False,
            })
            raise
        self._record("client_response", call_id, payload)
        return response
