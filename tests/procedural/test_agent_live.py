"""Behaviour check against the REAL model (skipped without a key; uses stub tools).

This is the regression test for the first-run failure where the model queried memory with the
invented subject "route" instead of the entity id. It is not deterministic, so run it several
times and record the pass rate (Guidelines 8).
"""

from __future__ import annotations

import os

import pytest

from procedural.agent import run_agent
from procedural.llm_client import LLMClient
from procedural.state import MEMORY_TOOLS, subjects_outside
from scripts.ask_agent import DEFAULT_QUESTION, DEFAULT_SUBJECTS
from scripts.tool_wiring import build_tool_registry

pytestmark = pytest.mark.skipif(
    not os.getenv("GROQ_API_KEY"), reason="needs GROQ_API_KEY"
)


def test_first_memory_lookup_uses_a_known_entity_id() -> None:
    registry, _ = build_tool_registry(use_real=False)
    out = run_agent(
        DEFAULT_QUESTION, LLMClient(), registry, known_subjects=DEFAULT_SUBJECTS
    )
    assert out.finished, out.error
    lookups = [c for c in out.tool_calls if c["tool"] in MEMORY_TOOLS]
    assert lookups, "the model never looked at memory"
    assert subjects_outside(lookups[:1], DEFAULT_SUBJECTS) == []
