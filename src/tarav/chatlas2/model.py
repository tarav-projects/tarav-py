# $kw: ^chatlas2-model-v1 --from Session.Event.Tape --from Event.Annotation --note [CT] the Chatlas2 model keeps a chronological event tape and shallow annotations while retaining raw observations --supp ^c20260814-16u ^c20260814-18u ^c20260814-19u ^c20260814-20u
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class NormalFragment:
    events: tuple[JsonObject, ...]
    chat_messages: tuple[JsonObject, ...]
    agent_loaded_contexts: tuple[JsonObject, ...]


__all__ = ["JsonObject", "NormalFragment"]
