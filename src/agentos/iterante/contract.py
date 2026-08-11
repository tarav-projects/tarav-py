"""Typed submit contract — validate a submission against a call's `expects`.

A call may declare `expects` (its return type). The Runtime renders it to the
agent and validates the submission against it here. Dependency-free, hand-rolled.

`expects` vocabulary (JSON-safe — calls are serialized into run.json + the frame):
- ``None``                         -> the turn takes no payload
- ``{field: marker, ...}``         -> an object; every field required, no extras
- marker ``"bool"|"str"|"int"|"float"`` -> a typed scalar
- marker ``["a", "b", ...]``       -> an enum (value must be a member)
- marker ``{...}``                 -> a nested object (recurses)
"""

from __future__ import annotations

_TYPE_MARKERS = ("bool", "str", "int", "float")


class ContractError(ValueError):
    """The submission does not satisfy the call's `expects`. Message is
    actionable and agent-facing — the Runtime surfaces it as an `AgentError`."""


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


def _validate_field(name: str, marker: object, value: object) -> None:
    if isinstance(marker, str):
        if not _matches_type(marker, value):
            raise ContractError(f"field {name!r} must be {marker} (got {type(value).__name__})")
    elif isinstance(marker, list):
        if value not in marker:
            raise ContractError(f"field {name!r} must be one of {marker}")
    elif isinstance(marker, dict):
        _validate_object(marker, value, where=name)
    else:
        raise ContractError(f"invalid contract marker for field {name!r}: {marker!r}")


def _validate_object(schema: dict, value: object, where: str = "submit") -> None:
    if not isinstance(value, dict):
        raise ContractError(f"{where} must be an object with fields {sorted(schema)}")
    for extra in value:
        if extra not in schema:
            raise ContractError(f"{where} has unexpected field {extra!r}; expects {sorted(schema)}")
    for field, marker in schema.items():
        if field not in value:
            raise ContractError(f"{where} is missing required field {field!r}")
        _validate_field(field, marker, value[field])


def validate(expects: object, submit_result: object) -> None:
    """Raise ContractError if `submit_result` does not satisfy `expects`."""
    if expects is None:
        if submit_result not in (None, {}):
            raise ContractError("this turn takes no payload (submit with no --answer/--data)")
        return
    if not isinstance(expects, dict):
        raise ContractError(f"invalid contract: {expects!r}")
    _validate_object(expects, submit_result)
