from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class NormalFragment:
    events: tuple[JsonObject, ...]
    chat_messages: tuple[JsonObject, ...]
    loaded_contexts: tuple[JsonObject, ...]
    raw: object | None = None


__all__ = ["JsonObject", "NormalFragment"]
