"""Source-relative file references with optional RFC 6901 JSON selection."""
import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path

from tarav.harness import TypeShip
from . import Reference


class StructuredFileReference(Reference):
    type_name = "Tarav.Reference.StructuredFile"
    type_ship = TypeShip("d8e8b967-b3a2-4c62-9fa7-d6604b95d3c0")

    def locate(self, locator):
        if not isinstance(locator, Mapping) or set(locator) - {"path", "pointer"}:
            raise ValueError("Locator requires path and optional pointer")
        raw = locator.get("path")
        if not isinstance(raw, str) or not raw:
            raise ValueError("Expected nonempty path")
        path = Path(raw)
        if not path.is_absolute():
            if self.source is None:
                raise ValueError("Relative reference requires containing source")
            path = self.source.parent / path
        payload = path.read_bytes()
        if "pointer" not in locator:
            return payload
        pointer = locator["pointer"]
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise ValueError("Expected JSON Pointer")
        value = json.loads(payload)
        for token in pointer.split("/")[1:]:
            if re.search(r"~(?![01])", token):
                raise ValueError("Invalid JSON Pointer escape")
            token = token.replace("~1", "/").replace("~0", "~")
            if isinstance(value, list):
                if not re.fullmatch(r"0|[1-9][0-9]*", token) or int(token) >= len(value):
                    raise ValueError("JSON Pointer array index missing")
                value = value[int(token)]
            elif isinstance(value, dict):
                value = value[token]
            else:
                raise ValueError("JSON Pointer traverses a scalar")
        return value

    def check_target(self, target, check):
        if check is None or check == {}:
            return True
        if not isinstance(check, Mapping) or set(check) != {"sha256"}:
            raise ValueError("Check requires sha256")
        payload = target if isinstance(target, bytes) else json.dumps(
            target, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        return hashlib.sha256(payload).hexdigest() == check["sha256"]
