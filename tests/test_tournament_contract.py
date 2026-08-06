# $kw: ^test-tournament-contract --from Tournament.Verdict --from Tournament.Judge --note [DF] boundary tests for mandatory judge-output validation and its actionable failures ^<anchor-on-landing>
from __future__ import annotations

import pytest

from agentos.tournament import (
    ContractError,
    parse_judge_answer,
    validate,
    validate_verdict_answer,
)


VERDICT_EXPECTS = {
    "outcome": ["A", "B", "no_contest"],
    "attribution": ["question", "player", "prompt", "none"],
    "reason": "str",
}


def test_valid_preferred_answer_passes() -> None:
    validate(VERDICT_EXPECTS, {"outcome": "A", "attribution": "none", "reason": "A states one act"})


def test_unknown_outcome_is_rejected_with_the_allowed_values() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "maybe", "attribution": "none", "reason": "unsure"})
    message = str(excinfo.value)
    assert "outcome" in message
    assert "no_contest" in message


def test_missing_field_is_rejected_by_name() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "A", "attribution": "none"})
    assert "reason" in str(excinfo.value)


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "A", "attribution": "none", "reason": "r", "score": 9})
    assert "score" in str(excinfo.value)


def test_wrong_scalar_type_names_the_expected_marker() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate({"count": "int"}, {"count": "seven"})
    assert "int" in str(excinfo.value)


def test_nested_object_recurses() -> None:
    schema = {"outcome": ["A", "B"], "detail": {"confidence": "int"}}
    validate(schema, {"outcome": "A", "detail": {"confidence": 3}})
    with pytest.raises(ContractError):
        validate(schema, {"outcome": "A", "detail": {"confidence": "high"}})


def test_bool_is_not_accepted_as_int() -> None:
    with pytest.raises(ContractError):
        validate({"count": "int"}, {"count": True})


def test_judge_answer_parses_a_bare_json_object() -> None:
    answer = parse_judge_answer('{"outcome": "B", "reason": "B is atomic"}')
    assert answer == {"outcome": "B", "reason": "B is atomic"}


def test_judge_answer_parses_a_fenced_json_object() -> None:
    answer = parse_judge_answer(
        'thinking out loud\n```json\n{"outcome": "A", "reason": "clearer"}\n```\ndone'
    )
    assert answer["outcome"] == "A"


def test_judge_answer_takes_the_last_object_when_several_appear() -> None:
    answer = parse_judge_answer(
        '{"outcome": "A", "reason": "first"}\n{"outcome": "B", "reason": "final"}'
    )
    assert answer["reason"] == "final"


def test_unparseable_judge_answer_is_actionable() -> None:
    with pytest.raises(ContractError) as excinfo:
        parse_judge_answer("I prefer the first one.")
    assert "JSON object" in str(excinfo.value)


def test_validation_is_mandatory_rather_than_opt_in() -> None:
    with pytest.raises(ContractError):
        validate(None, {"outcome": "A"})


def test_no_contest_must_attribute_the_refusal() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(
            {"outcome": "no_contest", "attribution": "none", "reason": "unsure"}
        )
    assert "attribute" in str(excinfo.value)


def test_attributed_no_contest_passes() -> None:
    validate_verdict_answer(
        {"outcome": "no_contest", "attribution": "question", "reason": "not comparable"}
    )


def test_a_decided_answer_may_attribute_nothing() -> None:
    validate_verdict_answer({"outcome": "B", "attribution": "none", "reason": "clearer"})
