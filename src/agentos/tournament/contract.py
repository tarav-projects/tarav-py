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

# A refusal is attributable three ways, and which one it is decides who to look
# at: scattered `question` indicts the definition, clustered `player` indicts that
# player, and `prompt` indicts the rendering the judge was given. Free text alone
# cannot be counted, so the axis is a required enum beside it.
ATTRIBUTION_QUESTION = "question"
ATTRIBUTION_PLAYER = "player"
ATTRIBUTION_PROMPT = "prompt"
ATTRIBUTION_NONE = "none"

ATTRIBUTIONS = [
    ATTRIBUTION_QUESTION,
    ATTRIBUTION_PLAYER,
    ATTRIBUTION_PROMPT,
    ATTRIBUTION_NONE,
]

# `outcome` is validated by hand against the run's arity rather than declared
# here: the declarative markers cannot express "a permutation of exactly these
# labels", and the label set is only known once a match has been composed.
VERDICT_EXPECTS: dict[str, object] = {
    "attribution": ATTRIBUTIONS,
    "reason": "str",
}


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

    Two rules the flat schema cannot express. The outcome must be a strict total
    ordering of exactly the labels presented, because a dropped or repeated label
    is a comparison the record would otherwise silently lose. And a refusal must
    attribute itself, because an unattributed refusal is exactly the signal the
    report would be unable to count.
    """
    labels = position_labels(arity)
    if not isinstance(answer, dict):
        raise ContractError("answer must be an object")
    outcome = answer.get("outcome")
    if outcome is None and "outcome" not in answer:
        raise ContractError("answer is missing required field 'outcome'")
    validate(VERDICT_EXPECTS, {k: v for k, v in answer.items() if k != "outcome"})
    if outcome != OUTCOME_NO_CONTEST:
        _validate_ordering(outcome, labels)
    elif answer["attribution"] == ATTRIBUTION_NONE:
        raise ContractError(
            "a no_contest answer must attribute the refusal: set attribution to "
            f"{ATTRIBUTION_QUESTION!r}, {ATTRIBUTION_PLAYER!r}, or {ATTRIBUTION_PROMPT!r}"
        )


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
