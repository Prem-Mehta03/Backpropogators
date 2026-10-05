"""Answer-text clean-up: fixes look-alike characters, leaves everything else alone."""

from __future__ import annotations

from typing import Any

import pytest

from procedural.agent import AgentResult
from procedural.agent import run_agent as _run_agent
from procedural.answer_text import normalize_answer_text
from scripts.tool_wiring import build_tool_registry
from tests.procedural.scripted_llm import ScriptedLLM, call, say


def run_agent(*args: Any, **kwargs: Any) -> AgentResult:
    """These tests exercise the loop itself, so the evidence checklist is switched off here.

    The checklist has its own tests in test_checklist_enforcement.py.
    """
    kwargs.setdefault("required_evidence", ())
    return _run_agent(*args, **kwargs)


REGISTRY, _ = build_tool_registry(use_real=False)


@pytest.mark.parametrize("dash", ["‐", "‑", "‒", "–", "—", "−"])
def test_dash_look_alikes_inside_dates_become_plain_hyphens(dash: str) -> None:
    text = f"recorded 2026{dash}10{dash}03T09:16:02Z"
    assert normalize_answer_text(text) == "recorded 2026-10-03T09:16:02Z"


def test_no_break_spaces_become_ordinary_spaces() -> None:
    assert normalize_answer_text("12 cm and 5 cm") == "12 cm and 5 cm"


def test_prose_dashes_words_and_numbers_are_untouched() -> None:
    text = "Stored evidence – clear; range 5–10 cm; confidence 0.98; path_A"
    assert normalize_answer_text(text) == text


def test_plain_text_is_unchanged_and_the_function_is_idempotent() -> None:
    plain = "No. LiDAR: 12 cm, blocked, 2026-10-03T09:16:02Z."
    assert normalize_answer_text(plain) == plain
    mangled = "2026‑10‑03"
    once = normalize_answer_text(mangled)
    assert normalize_answer_text(once) == once


def test_run_agent_returns_clean_answer_but_keeps_what_the_model_said() -> None:
    said = "Blocked at 12 cm on 2026‑10‑03."
    llm = ScriptedLLM([call("read_lidar", {}), say(said)])
    out = run_agent("lidar?", llm, REGISTRY)
    assert out.answer == "Blocked at 12 cm on 2026-10-03."
    assert out.answer_normalized is True
    assert out.messages[-1]["content"] == said  # history is the model's own text


def test_run_agent_flags_nothing_when_no_change_was_needed() -> None:
    out = run_agent("lidar?", ScriptedLLM([say("12 cm, blocked.")]), REGISTRY)
    assert out.answer == "12 cm, blocked." and out.answer_normalized is False
