"""Prompt text: the entity glossary is added from config, the policy contains the key rules."""

from __future__ import annotations

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
