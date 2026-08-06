# $kw: ^tournament-contract --from Tournament.Verdict --from Tournament.Judge --note [CT] judge output is validated at the boundary; verdicts are the entire product, so validation is mandatory rather than opt-in ^<anchor-on-landing>
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

OUTCOME_A = "A"
OUTCOME_B = "B"
OUTCOME_NO_CONTEST = "no_contest"

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

VERDICT_EXPECTS: dict[str, object] = {
    "outcome": [OUTCOME_A, OUTCOME_B, OUTCOME_NO_CONTEST],
    "attribution": ATTRIBUTIONS,
    "reason": "str",
}


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


def validate_verdict_answer(answer: object) -> None:
    """Validate a judge answer against the v0 verdict contract.

    Adds the one cross-field rule the flat schema cannot express: a refusal must
    actually attribute itself, because an unattributed refusal is exactly the
    signal the report would otherwise be unable to count.
    """
    validate(VERDICT_EXPECTS, answer)
    assert isinstance(answer, dict)  # validate() guarantees the shape
    if (
        answer["outcome"] == OUTCOME_NO_CONTEST
        and answer["attribution"] == ATTRIBUTION_NONE
    ):
        raise ContractError(
            "a no_contest answer must attribute the refusal: set attribution to "
            f"{ATTRIBUTION_QUESTION!r}, {ATTRIBUTION_PLAYER!r}, or {ATTRIBUTION_PROMPT!r}"
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
