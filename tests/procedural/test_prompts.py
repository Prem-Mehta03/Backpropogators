"""Prompt text: the entity glossary is added from config, the policy contains the key rules."""

from __future__ import annotations

import re

from procedural.prompts import (
    ANSWER_FORMAT,
    EVIDENCE_POLICY,
    SYSTEM_PROMPT,
    build_entity_glossary,
    build_system_prompt,
)

SUBJECTS = {"path_A": "the path ahead", "box_01": "the box", "robot": "this robot"}


def test_without_subjects_the_standard_prompt_is_returned() -> None:
    assert build_system_prompt() == SYSTEM_PROMPT
    assert build_system_prompt({}) == SYSTEM_PROMPT


def test_with_subjects_every_id_and_description_is_listed() -> None:
    prompt = build_system_prompt(SUBJECTS)
    assert prompt.startswith(SYSTEM_PROMPT)
    for entity_id, description in SUBJECTS.items():
        assert f"- {entity_id}: {description}" in prompt
    assert "exact ids" in build_entity_glossary(SUBJECTS)


def test_standard_prompt_hard_codes_no_scenario_entities() -> None:
    for entity_id in (
        "path_A",
        "box_01",
    ):  # "robot" is also an ordinary word in the prompt
        assert entity_id not in SYSTEM_PROMPT


def test_policy_tells_the_model_how_to_look_up_memory() -> None:
    assert "exact entity id" in EVIDENCE_POLICY
    assert "leave out the optional predicate and perspective filters" in EVIDENCE_POLICY
    assert "retry once" in EVIDENCE_POLICY and "NOT_FOUND" in EVIDENCE_POLICY


def test_answer_format_forbids_pasting_raw_json() -> None:
    assert "Never paste raw tool output or JSON" in ANSWER_FORMAT


def test_answer_format_asks_for_decimal_confidence_not_percentages() -> None:
    assert "never as a percentage" in ANSWER_FORMAT


def test_answer_format_requires_disagreements_and_exact_writes_to_be_reported() -> None:
    assert "State every disagreement" in ANSWER_FORMAT
    assert (
        "no resolution was needed" in ANSWER_FORMAT
    )  # the phrase the model must not use
    assert "Report your memory writes exactly" in ANSWER_FORMAT


def test_answer_format_tells_the_model_to_report_a_disputed_status() -> None:
    assert 'status of the\n  belief you recorded is "disputed"' in ANSWER_FORMAT
    assert "do not\n  present it as settled" in ANSWER_FORMAT


def test_answer_format_asks_for_a_closing_memory_status_line() -> None:
    assert "Memory status:" in ANSWER_FORMAT
    assert "while that status is disputed" in ANSWER_FORMAT


def test_answer_format_only_starts_with_no_or_yes_for_yes_no_questions() -> None:
    assert 'begin with\n  "No" or "Yes" only for a yes/no question' in ANSWER_FORMAT


def test_conflict_answer_shape_depends_on_the_kind_of_question() -> None:
    assert "For a yes/no question" in ANSWER_FORMAT
    assert 'Never write\n  "No," as the start of a sentence' in ANSWER_FORMAT


def test_answer_format_asks_for_written_beliefs_by_id() -> None:
    assert "recorded by its belief id" in ANSWER_FORMAT


def test_policy_hands_view_disagreements_to_a_person_and_records_their_answer() -> None:
    assert "perspective user or third_party" in EVIDENCE_POLICY
    assert "Tell me which one to treat as correct" in EVIDENCE_POLICY
    assert "perspective user and source user" in EVIDENCE_POLICY


def test_policy_says_the_downgrade_value_is_set_by_the_system() -> None:
    assert "a\n   downgrade value is set by the system" in EVIDENCE_POLICY


# ---- v6: how to answer in the situations the ten tests cover ------------------------------------
from procedural.prompts import PROMPT_VERSION, SITUATIONS


def test_prompt_version_is_v6_and_the_prompt_includes_the_situations() -> None:
    assert PROMPT_VERSION.startswith(
        "v6"
    )  # v6.N: bumped whenever the prompt text changes
    assert SITUATIONS in SYSTEM_PROMPT
    assert SYSTEM_PROMPT.index(EVIDENCE_POLICY) < SYSTEM_PROMPT.index(SITUATIONS)
    assert SYSTEM_PROMPT.index(SITUATIONS) < SYSTEM_PROMPT.index(ANSWER_FORMAT)


def test_prompt_stays_within_the_token_budget() -> None:
    # Groq's daily token cap is shared by many calls per run, so the prompt must stay compact
    assert len(SYSTEM_PROMPT.split()) < 1900


def test_each_situation_is_covered() -> None:
    for letter in "ABCDEFGH":
        assert f"\n{letter}. " in SITUATIONS
    assert "outdated" in SITUATIONS  # T06 stale
    assert "source is unknown" in SITUATIONS  # T09 missing provenance
    assert "do not\n   call either side the fact" in SITUATIONS  # T04, T05 disputed
    assert "below 0.6" in SITUATIONS and "recheck" in SITUATIONS  # T04 weak
    assert "robot did not move" in " ".join(SITUATIONS.split())  # T08, T10 moves
    assert "evidence is\n   missing and name no value" in SITUATIONS  # T07


def test_three_view_format_names_the_three_lines_and_forbids_inventing_a_reason() -> (
    None
):
    for line in ("Person:", "Stored\n   record:", "My live reading:"):
        assert line in SITUATIONS
    assert "none is treated as the true\n   state" in SITUATIONS
    assert "Give no reason for a difference" in SITUATIONS


def test_situations_hard_code_no_scenario_entities() -> None:
    for word in ("path_A", "box_01", "bot_02", "lidar_front", "brown", "red"):
        assert re.search(rf"\b{word}\b", SITUATIONS) is None


def test_a_persons_statement_about_the_world_is_recorded_but_never_verified() -> None:
    assert "states a fact about the world" in EVIDENCE_POLICY
    assert "never a verified fact" in EVIDENCE_POLICY
