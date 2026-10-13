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
