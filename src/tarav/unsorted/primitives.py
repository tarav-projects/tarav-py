"""tarav.unsorted.primitives: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l0.kernel import RecordTypeReference
from uuid import UUID
from tarav.unsorted.constants import _SHA256
from datetime import datetime
from tarav.l0.kernel import locate_record_type
from datetime import timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from collections.abc import Iterable
    from tarav.unsorted.constants import JsonObject
    from collections.abc import Mapping
    from tarav.l0.kernel import TaravObject

class DiagramError(RuntimeError):
    pass


class DiagramModelError(ValueError):
    pass


class DiagramAnnotationSpecializationError(DiagramError):
    pass


class DiagramShipSpecializationError(DiagramError):
    pass


def _semantic_record(record: Mapping[str, Any]) -> JsonObject:
    return {
        key: value
        for key, value in record.items()
        if key not in {"recorded_at", "updated_at"}
    }


def _edition_id(edition: Mapping[str, object]) -> str:
    return _uuid(edition.get("id"), field="Ship.Edition.id")


def _validate_editions(editions: Iterable[Mapping[str, object]], *, field: str) -> None:
    seen: set[str] = set()
    for index, edition in enumerate(editions):
        edition_id = _edition_id(edition)
        if edition_id in seen:
            raise DiagramModelError(f"{field}[{index}].id is duplicated")
        seen.add(edition_id)


def _edition_payload(edition: Mapping[str, object]) -> JsonObject:
    return {key: value for key, value in edition.items() if key != "id"}


def _authorization_gate_ids(record: Mapping[str, Any]) -> tuple[str, ...]:
    values = tuple(
        _uuid(item, field="Edition.authorization_gates[]")
        for item in _array(
            record.get("authorization_gates", []),
            field="Edition.authorization_gates",
        )
    )
    if len(values) != len(set(values)):
        raise DiagramModelError("Edition.authorization_gates contains duplicates")
    return values


def _object(value: object, *, field: str) -> JsonObject:
    if not isinstance(value, dict):
        raise DiagramModelError(f"{field} must be an object")
    return dict(value)


def _array(value: object, *, field: str) -> list[object]:
    if not isinstance(value, list):
        raise DiagramModelError(f"{field} must be an array")
    return value


def _record_type_reference(
    record: Mapping[str, Any], *, field: str
) -> RecordTypeReference:
    """Read one Record's Type reference through the Harness resolution path."""

    location = locate_record_type(record)
    if location is None:
        raise DiagramModelError(f"{field} carries no Tarav Type reference")
    reference = RecordTypeReference.parse(location.value)
    if reference.ship is None and reference.label is None:
        raise DiagramModelError(
            f"{field}.{location.field} is not a Tarav Type reference: "
            f"{location.value!r}"
        )
    return reference


def _record_type_name(record: Mapping[str, Any], *, field: str) -> str:
    reference = _record_type_reference(record, field=field)
    if reference.label is None:
        raise DiagramModelError(f"{field} carries no human-facing Type label")
    return reference.label


def _record_is(record: Mapping[str, Any], record_type: type[TaravObject]) -> bool:
    """Whether one Record's Type reference designates a registered class."""

    location = locate_record_type(record)
    if location is None:
        return False
    return record_type.matches(RecordTypeReference.parse(location.value))


def _record_is_any(
    record: Mapping[str, Any], record_types: tuple[type[TaravObject], ...]
) -> bool:
    return any(_record_is(record, item) for item in record_types)


def _string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise DiagramModelError(f"{field} must be a non-empty string")
    return value


def _digest(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    if not _SHA256.fullmatch(text):
        raise DiagramModelError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _uuid(value: object, *, field: str) -> str:
    text = _string(value, field=field)
    try:
        parsed = UUID(text)
    except ValueError as exc:
        raise DiagramModelError(f"{field} must be a UUID") from exc
    if str(parsed) != text:
        raise DiagramModelError(f"{field} must be a canonical lowercase UUID")
    return text


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _optional_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
