"""Native marker positions in JSON metadata and TOML comments."""

from dataclasses import dataclass
import json
import tomllib

from .store import BreadcrumbError
from .workflows import SurfaceMarker


@dataclass(frozen=True, slots=True)
class DataMarker:
    position: SurfaceMarker
    text: str


def data_markers(text: str, language: str) -> tuple[DataMarker, ...]:
    """Only explicit JSON metadata strings or genuine TOML comments are active."""
    if language == "json":
        return _json_markers(text)
    if language == "toml":
        return _toml_comments(text)
    raise BreadcrumbError(f"Unsupported data surface: {language}")


def _marker(text: str, start: int, end: int, value: str) -> DataMarker:
    line = text.count("\n", 0, start) + 1
    offset = text.rfind("\n", 0, start) + 1
    return DataMarker(SurfaceMarker(line, start - offset, end - offset), value)


def _json_markers(text: str) -> tuple[DataMarker, ...]:
    try:
        json.loads(text)
    except ValueError as exc:
        raise BreadcrumbError(f"Invalid JSON surface: {exc}") from exc
    decoder = json.JSONDecoder()
    result = []

    def space(index):
        while index < len(text) and text[index].isspace():
            index += 1
        return index

    def value(index, *, metadata=False):
        index = space(index)
        if metadata:
            if text[index] != "[":
                raise BreadcrumbError("JSON tarav.breadcrumbs must be an array of strings")
            index = space(index + 1)
            while text[index] != "]":
                start = index
                item, index = decoder.raw_decode(text, index)
                if not isinstance(item, str):
                    raise BreadcrumbError("JSON tarav.breadcrumbs entries must be strings")
                result.append(_marker(text, start, index, item))
                index = space(index)
                if text[index] == ",":
                    index = space(index + 1)
            return index + 1
        if text[index] == "{":
            index = space(index + 1)
            seen = set()
            while text[index] != "}":
                key, index = decoder.raw_decode(text, index)
                if key == "tarav.breadcrumbs" and key in seen:
                    raise BreadcrumbError("Duplicate JSON tarav.breadcrumbs member")
                seen.add(key)
                index = value(space(index) + 1, metadata=key == "tarav.breadcrumbs")
                index = space(index)
                if text[index] == ",":
                    index = space(index + 1)
            return index + 1
        if text[index] == "[":
            index = space(index + 1)
            while text[index] != "]":
                index = space(value(index))
                if text[index] == ",":
                    index = space(index + 1)
            return index + 1
        return decoder.raw_decode(text, index)[1]

    value(0)
    return tuple(result)


def _toml_comments(text: str) -> tuple[DataMarker, ...]:
    try:
        tomllib.loads(text)
    except ValueError as exc:
        raise BreadcrumbError(f"Invalid TOML surface: {exc}") from exc
    result = []
    quote = None
    multiline = False
    index = 0
    while index < len(text):
        char = text[index]
        if quote is not None:
            if quote == '"' and char == "\\":
                index += 2
                continue
            if char == quote:
                count = 1
                while index + count < len(text) and text[index + count] == quote:
                    count += 1
                if not multiline or count >= 3:
                    quote = None
                    index += count if multiline else 1
                    continue
            index += 1
        elif char in ("'", '"'):
            quote = char
            multiline = text.startswith(char * 3, index)
            index += 3 if multiline else 1
        elif char == "#":
            end = text.find("\n", index)
            end = len(text) if end == -1 else end
            result.append(_marker(text, index, end, text[index:end].rstrip("\r")))
            index = end
        else:
            index += 1
    return tuple(result)
