"""Small deterministic Records for identity coordinates and similar values."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import json
import math
import re
from typing import Any

from .identity import Ship, TypeShip


_TAG = "$tarav.lite"
_EXTENSION_TAG = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class LiteRecordSerializer:
    """Trusted exact-type extension for values outside LiteRecord's foundation."""

    tag: str
    value_type: type
    encode: Callable[[object], object]

    def __post_init__(self) -> None:
        if not _EXTENSION_TAG.fullmatch(self.tag):
            raise ValueError("LiteRecord serializer tag must be a stable name")
        if not isinstance(self.value_type, type):
            raise TypeError("LiteRecord serializer value_type must be a class")
        if not callable(self.encode):
            raise TypeError("LiteRecord serializer encode must be callable")


# tarav.breadcrumb 637336c58587
class LiteRecord(Mapping[str, object]):
    """A detached mapping with deterministic JSON-compatible encoding.

    JSON values stay readable. Dates, Ships, Tarav Types, and trusted extension
    values use an explicit tagged representation. A caller dictionary using the
    reserved tag is escaped as an ordinary mapping, so it cannot impersonate a
    native value.
    """

    __slots__ = ("_canonical", "_value")

    def __init__(
        self,
        value: Mapping[str, object] | LiteRecord,
        *,
        serializers: Sequence[LiteRecordSerializer] = (),
    ) -> None:
        if isinstance(value, LiteRecord):
            if serializers:
                raise ValueError("Serializers cannot reinterpret an existing LiteRecord")
            encoded = value.to_json_value()
        else:
            registry = _serializer_registry(serializers)
            encoded = _encode(value, registry, set())
        if not isinstance(encoded, dict):  # defensive: the public root is a mapping
            raise TypeError("LiteRecord root must be a mapping")
        self._value = encoded
        self._canonical = _canonical(encoded)

    @classmethod
    def from_json_value(cls, value: object) -> LiteRecord:
        """Validate an already encoded retained value without native reconstruction."""

        encoded = deepcopy(value)
        _validate_encoded(encoded)
        if not isinstance(encoded, dict):
            raise TypeError("LiteRecord root must be a mapping")
        result = cls.__new__(cls)
        result._value = encoded
        result._canonical = _canonical(encoded)
        return result

    @property
    def canonical(self) -> str:
        return self._canonical

    def to_json_value(self) -> dict[str, object]:
        return deepcopy(self._value)

    def __getitem__(self, key: str) -> object:
        return deepcopy(self._value[key])

    def __iter__(self) -> Iterator[str]:
        return iter(self._value)

    def __len__(self) -> int:
        return len(self._value)

    def __repr__(self) -> str:
        return f"LiteRecord({self._value!r})"


def _serializer_registry(
    serializers: Sequence[LiteRecordSerializer],
) -> dict[type, LiteRecordSerializer]:
    by_type: dict[type, LiteRecordSerializer] = {}
    tags: set[str] = set()
    for serializer in serializers:
        if not isinstance(serializer, LiteRecordSerializer):
            raise TypeError("Expected LiteRecordSerializer")
        if serializer.value_type in by_type:
            raise ValueError("Duplicate LiteRecord serializer value type")
        if serializer.tag in tags:
            raise ValueError("Duplicate LiteRecord serializer tag")
        by_type[serializer.value_type] = serializer
        tags.add(serializer.tag)
    return by_type


def _wrapper(kind: str, value: object) -> dict[str, object]:
    return {_TAG: {"type": kind, "value": value}}


def _encode(
    value: object,
    serializers: Mapping[type, LiteRecordSerializer],
    active: set[int],
) -> Any:
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("LiteRecord numbers must be finite")
        return value
    if isinstance(value, datetime):
        return _wrapper("datetime", value.isoformat())
    if isinstance(value, date):
        return _wrapper("date", value.isoformat())
    if isinstance(value, Ship):
        return _wrapper("ship", str(value))

    from .records import TaravType, entity

    if isinstance(value, type) and issubclass(value, TaravType):
        return _wrapper("type", str(entity(value).id))

    serializer = serializers.get(type(value))
    if serializer is not None:
        identity = id(value)
        if identity in active:
            raise ValueError("LiteRecord values must not contain cycles")
        active.add(identity)
        try:
            encoded = _encode(serializer.encode(value), serializers, active)
        finally:
            active.remove(identity)
        return _wrapper(f"extension:{serializer.tag}", encoded)

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in active:
            raise ValueError("LiteRecord values must not contain cycles")
        if any(not isinstance(key, str) for key in value):
            raise TypeError("LiteRecord mapping keys must be strings")
        active.add(identity)
        try:
            encoded = {
                key: _encode(child, serializers, active)
                for key, child in value.items()
            }
        finally:
            active.remove(identity)
        if _TAG in encoded:
            return _wrapper("mapping", [[key, encoded[key]] for key in sorted(encoded)])
        return encoded
    if type(value) is list:
        identity = id(value)
        if identity in active:
            raise ValueError("LiteRecord values must not contain cycles")
        active.add(identity)
        try:
            return [_encode(child, serializers, active) for child in value]
        finally:
            active.remove(identity)
    raise TypeError(f"Unsupported LiteRecord value: {type(value).__name__}")


def _validate_encoded(value: object) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("LiteRecord numbers must be finite")
        return
    if type(value) is list:
        for child in value:
            _validate_encoded(child)
        return
    if not isinstance(value, Mapping):
        raise TypeError(f"Invalid encoded LiteRecord value: {type(value).__name__}")
    if any(not isinstance(key, str) for key in value):
        raise TypeError("LiteRecord mapping keys must be strings")
    if _TAG not in value:
        for child in value.values():
            _validate_encoded(child)
        return
    if set(value) != {_TAG}:
        raise ValueError("Malformed LiteRecord tagged value")
    payload = value[_TAG]
    if not isinstance(payload, Mapping) or set(payload) != {"type", "value"}:
        raise ValueError("Malformed LiteRecord tag payload")
    kind = payload["type"]
    encoded = payload["value"]
    if kind == "ship":
        Ship(encoded)
    elif kind == "type":
        TypeShip(encoded)
    elif kind == "date":
        if not isinstance(encoded, str) or date.fromisoformat(encoded).isoformat() != encoded:
            raise ValueError("Malformed LiteRecord date")
    elif kind == "datetime":
        if (
            not isinstance(encoded, str)
            or datetime.fromisoformat(encoded).isoformat() != encoded
        ):
            raise ValueError("Malformed LiteRecord datetime")
    elif kind == "mapping":
        if not isinstance(encoded, list):
            raise ValueError("Malformed escaped LiteRecord mapping")
        keys = []
        for item in encoded:
            if type(item) is not list or len(item) != 2 or not isinstance(item[0], str):
                raise ValueError("Malformed escaped LiteRecord mapping entry")
            keys.append(item[0])
            _validate_encoded(item[1])
        if keys != sorted(set(keys)):
            raise ValueError("Escaped LiteRecord mapping keys must be unique and sorted")
    elif isinstance(kind, str) and kind.startswith("extension:"):
        if not _EXTENSION_TAG.fullmatch(kind.removeprefix("extension:")):
            raise ValueError("Malformed LiteRecord extension tag")
        _validate_encoded(encoded)
    else:
        raise ValueError(f"Unknown LiteRecord tag: {kind!r}")


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )


__all__ = ["LiteRecord", "LiteRecordSerializer"]
