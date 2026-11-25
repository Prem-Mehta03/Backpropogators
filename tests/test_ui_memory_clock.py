"""The live UI must use the same clock as the acceptance runner: the simulator clock.

Review of PR #9: the live UI stamped seeded beliefs with the PC clock while the readings carry the
simulator clock, so a clear LiDAR reading could be recorded as disputed instead of superseding the
blocked map (T02). evaluation/runner.py builds the memory with clock=world.env.now_iso; so must the UI.
"""

from __future__ import annotations

from typing import Any

import pytest

import procedural.llm_client as llm_client
import scripts.live_ui as live_ui
from evaluation.stretch_specs import CASES, ScriptedModel
from scripts.tool_wiring import build_memory

SIM_DAY = "2026-10-03"  # every simulator scenario starts on this day


def test_build_memory_uses_the_clock_it_is_given() -> None:
    memory = build_memory(seed=False, clock=lambda: "2026-10-03T09:16:00Z")
    assert memory.now() == "2026-10-03T09:16:00Z"


def _run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, scenario: str, test_id: str
) -> tuple:
    class Scripted:
        model = "scripted_llm"
        switched_from = None

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.script: ScriptedModel | None = None

        def chat(
            self,
            messages: list,
            tools: list | None = None,
            tool_choice: str | None = None,
        ) -> Any:
            if self.script is None or len(messages) <= 2:
                self.script = ScriptedModel(test_id)
            return self.script.chat(messages, tools, tool_choice)

    monkeypatch.setattr(llm_client, "LLMClient", Scripted)
    monkeypatch.setattr(
        live_ui, "LOG_DIR", tmp_path
    )  # keep the run log out of evaluation/logs
    session = live_ui.LiveSession(scenario, False)
    assert session.error is None
    events: list[dict[str, Any]] = []
    session.ask(CASES[test_id].question, events.append)
    final = [e for e in events if e.get("type") == "final"][-1]
    assert final["error"] is None
    beliefs = [e for e in events if e.get("type") == "session"][-1]["beliefs"]
    return session, beliefs


def test_t02_in_the_ui_supersedes_the_blocked_map(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    session, beliefs = _run(monkeypatch, tmp_path, "scenario_map_blocked", "T02")
    lidar = [b for b in beliefs if b["source"] == "lidar_front"]
    assert [(b["object"], b["status"]) for b in lidar] == [("clear", "active")]
    assert all(
        b["timestamp"].startswith(SIM_DAY) for b in beliefs
    )  # no PC-clock timestamps
    assert session.memory.now().startswith(SIM_DAY)


@pytest.mark.parametrize(
    ("scenario", "test_id"),
    [
        ("scenario_t05_sensor_disagreement", "T05"),
        ("scenario_t04_low_confidence", "T04"),
        ("scenario_t06_stale_map", "T06"),
    ],
)
def test_other_scenarios_keep_their_seeded_state_on_the_simulator_clock(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any, scenario: str, test_id: str
) -> None:
    _, beliefs = _run(monkeypatch, tmp_path, scenario, test_id)
    assert all(b["timestamp"].startswith(("2026-10-0", "2026-09")) for b in beliefs)
    if test_id in ("T04", "T05"):
        assert any(b["status"] == "disputed" for b in beliefs)
