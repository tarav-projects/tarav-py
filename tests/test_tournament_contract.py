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
    "reason": "str",
}


def test_valid_preferred_answer_passes() -> None:
    validate(VERDICT_EXPECTS, {"outcome": "A", "reason": "A states one act"})


def test_a_decided_answer_needs_only_its_ranking() -> None:
    validate_verdict_answer({"outcome": ["B", "A"]}, arity=2)


def test_a_refusal_requires_a_stated_reason() -> None:
    validate_verdict_answer(
        {"outcome": "no_contest", "refusal_reason": "not comparable"}, arity=4
    )
    for bad in ({"outcome": "no_contest"}, {"outcome": "no_contest", "refusal_reason": "  "}):
        with pytest.raises(ContractError) as excinfo:
            validate_verdict_answer(bad, arity=4)
        assert "refusal_reason" in str(excinfo.value)


def test_the_contract_asks_the_judge_for_no_attribution() -> None:
    """Which player or question a refusal indicts is read from the records."""
    import agentos.tournament.contract as contract

    assert not hasattr(contract, "ATTRIBUTIONS")
    assert "attribution" not in contract.validate_verdict_answer.__doc__


def test_unknown_outcome_is_rejected_with_the_allowed_values() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "maybe", "reason": "unsure"})
    message = str(excinfo.value)
    assert "outcome" in message
    assert "no_contest" in message


def test_missing_field_is_rejected_by_name() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "A"})
    assert "reason" in str(excinfo.value)


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate(VERDICT_EXPECTS, {"outcome": "A", "reason": "r", "score": 9})
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






def test_a_decided_answer_may_attribute_nothing() -> None:
    validate_verdict_answer(
        {"outcome": ["B", "A"], "reason": "clearer"}, arity=2
    )


# --- ordering outcomes -------------------------------------------------------


def _answer(outcome, attribution="none", reason="because"):
    return {"outcome": outcome, "attribution": attribution, "reason": reason}


def test_a_valid_permutation_of_the_presented_labels_passes() -> None:
    validate_verdict_answer(_answer(["C", "A", "D", "B"]), arity=4)


def test_a_two_player_ordering_still_validates() -> None:
    validate_verdict_answer(_answer(["B", "A"]), arity=2)


def test_a_missing_label_is_rejected_by_name() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(_answer(["A", "B", "C"]), arity=4)
    message = str(excinfo.value)
    assert "D" in message


def test_a_repeated_label_is_rejected_as_an_equal_rank() -> None:
    """A strict total ordering places no two players at equal rank."""
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(_answer(["A", "B", "B", "C"]), arity=4)
    message = str(excinfo.value)
    assert "B" in message
    assert "once" in message or "rank" in message


def test_an_invented_label_is_rejected() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(_answer(["A", "B", "Z"]), arity=3)
    assert "Z" in str(excinfo.value)


def test_a_wrong_length_ordering_is_rejected() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(_answer(["A", "B"]), arity=4)
    assert "4" in str(excinfo.value)


def test_an_outcome_that_is_neither_no_contest_nor_a_list_is_rejected() -> None:
    for bad in ["A", 7, {"A": 1}, None]:
        with pytest.raises(ContractError):
            validate_verdict_answer(_answer(bad), arity=2)




def test_the_error_names_the_labels_the_judge_should_have_ordered() -> None:
    with pytest.raises(ContractError) as excinfo:
        validate_verdict_answer(_answer(["B", "A", "C"]), arity=4)
    message = str(excinfo.value)
    assert "A" in message and "D" in message


def test_position_labels_cover_the_supported_arity() -> None:
    from agentos.tournament.contract import MAX_ARITY, POSITION_LABELS

    assert POSITION_LABELS[:4] == ("A", "B", "C", "D")
    assert len(POSITION_LABELS) == MAX_ARITY == 26
