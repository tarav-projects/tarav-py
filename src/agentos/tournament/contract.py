# $kw: ^tournament-contract --from Tournament.Verdict --from Tournament.Judge --note [CT] an outcome is either a strict total ordering of the match's players or a no-contest, validated against the actual arity --supp ^c20260806-54u ^<anchor-on-landing>
"""Typed judge-answer contract — validate an answer against a declared schema.

``expects`` vocabulary (JSON-safe, dependency-free):

- ``{field: marker, ...}``              -> an object; every field required, no extras
- marker ``"bool"|"str"|"int"|"float"`` -> a typed scalar
- marker ``["a", "b", ...]``            -> an enum (value must be a member)
- marker ``{...}``                      -> a nested object (recurses)

Unlike the iterante contract this adapts, ``expects`` is never optional: a
tournament's verdicts are its whole product, so an unvalidated answer is not a
lenient path but a silently corrupt record.
"""

from __future__ import annotations

import json

from agentos.tournament.model import TournamentError

_TYPE_MARKERS = ("bool", "str", "int", "float")

OUTCOME_NO_CONTEST = "no_contest"

# Positions, not players: the judge orders labels and the engine decodes them
# back through the order it ran, so nothing a consumer wrote can invert a verdict.
POSITION_LABELS = tuple(chr(ord("A") + index) for index in range(26))
MAX_ARITY = len(POSITION_LABELS)
MIN_ARITY = 2

# A decided answer is its ranking alone. A refusal adds a reason in the judge's
# own words — no attribution axis: which player or question a refusal indicts is
# read from the records, which already carry who was in which refused match.
REFUSAL_REASON_FIELD = "refusal_reason"


def position_labels(arity: int) -> tuple[str, ...]:
    """The labels a match of this size presents to its judge."""
    if not isinstance(arity, int) or isinstance(arity, bool):
        raise ContractError(f"match arity must be an integer (got {arity!r})")
    if arity < MIN_ARITY or arity > MAX_ARITY:
        raise ContractError(
            f"match arity must be between {MIN_ARITY} and {MAX_ARITY} (got {arity})"
        )
    return POSITION_LABELS[:arity]


class ContractError(TournamentError):
    """The judge's answer does not satisfy the declared contract.

    The message is agent-facing and actionable so an orchestrator can re-run the
    match with a corrective instruction.
    """


def validate(expects: object, answer: object) -> None:
    """Raise ContractError if ``answer`` does not satisfy ``expects``."""
    if not isinstance(expects, dict):
        raise ContractError(
            "a judge contract is required: expects must be an object of field markers"
        )
    _validate_object(expects, answer)


def validate_verdict_answer(answer: object, *, arity: int) -> None:
    """Validate a judge answer for a match of ``arity`` players.

    A decided answer is a strict total ordering of exactly the labels presented:
    a dropped or repeated label is a comparison the record would otherwise
    silently lose. A refusal carries a stated reason instead, so declining is an
    answer rather than an abstention.
    """
    labels = position_labels(arity)
    if not isinstance(answer, dict):
        raise ContractError("answer must be an object")
    if "outcome" not in answer:
        raise ContractError("answer is missing required field 'outcome'")
    outcome = answer["outcome"]
    if outcome == OUTCOME_NO_CONTEST:
        reason = answer.get(REFUSAL_REASON_FIELD)
        if not isinstance(reason, str) or not reason.strip():
            raise ContractError(
                f"a {OUTCOME_NO_CONTEST!r} answer must state why in "
                f"{REFUSAL_REASON_FIELD!r}"
            )
        return
    _validate_ordering(outcome, labels)


def _validate_ordering(outcome: object, labels: tuple[str, ...]) -> None:
    expected = ", ".join(labels)
    if not isinstance(outcome, list) or isinstance(outcome, str):
        raise ContractError(
            f"field 'outcome' must be {OUTCOME_NO_CONTEST!r} or an array ranking "
            f"all {len(labels)} labels best first: [{expected}]"
        )
    if len(outcome) != len(labels):
        raise ContractError(
            f"field 'outcome' must rank all {len(labels)} labels ({expected}) "
            f"best first; got {len(outcome)} entries"
        )
    seen: list[str] = []
    for item in outcome:
        if not isinstance(item, str):
            raise ContractError(
                f"field 'outcome' must contain only labels ({expected}); "
                f"got {item!r}"
            )
        if item not in labels:
            raise ContractError(
                f"field 'outcome' names {item!r}, which was not presented; "
                f"rank exactly these labels: {expected}"
            )
        if item in seen:
            raise ContractError(
                f"field 'outcome' names {item!r} more than once; each label appears "
                "exactly once because two players may not share a rank"
            )
        seen.append(item)
    missing = [label for label in labels if label not in seen]
    if missing:
        raise ContractError(
            "field 'outcome' omits " + ", ".join(missing) + f"; rank exactly: {expected}"
        )


def parse_judge_answer(text: str | None) -> dict[str, object]:
    """Extract the judge's JSON answer object from its captured output."""
    if not text or not text.strip():
        raise ContractError(
            "the judge produced no output; answer with a single JSON object"
        )
    candidate = _last_json_object(text)
    if candidate is None:
        raise ContractError(
            "the judge's answer contained no JSON object; answer with a single "
            'JSON object such as {"outcome": "A", "reason": "..."}'
        )
    return candidate


def _last_json_object(text: str) -> dict[str, object] | None:
    found: dict[str, object] | None = None
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _end = decoder.raw_decode(text[index:])
        except ValueError:
            continue
        if isinstance(value, dict):
            found = value
    return found


def _validate_object(schema: dict, value: object, where: str = "answer") -> None:
    if not isinstance(value, dict):
        raise ContractError(
            f"{where} must be an object with fields {sorted(schema)}"
        )
    for extra in value:
        if extra not in schema:
            raise ContractError(
                f"{where} has unexpected field {extra!r}; expects {sorted(schema)}"
            )
    for field, marker in schema.items():
        if field not in value:
            raise ContractError(f"{where} is missing required field {field!r}")
        _validate_field(field, marker, value[field])


def _validate_field(name: str, marker: object, value: object) -> None:
    if isinstance(marker, str):
        if not _matches_type(marker, value):
            raise ContractError(
                f"field {name!r} must be {marker} (got {type(value).__name__})"
            )
    elif isinstance(marker, list):
        if value not in marker:
            raise ContractError(f"field {name!r} must be one of {marker}")
    elif isinstance(marker, dict):
        _validate_object(marker, value, where=name)
    else:
        raise ContractError(f"invalid contract marker for field {name!r}: {marker!r}")


def _matches_type(marker: str, value: object) -> bool:
    if marker == "bool":
        return isinstance(value, bool)
    if marker == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if marker == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if marker == "str":
        return isinstance(value, str)
    raise ContractError(f"unknown type marker {marker!r} in contract")
