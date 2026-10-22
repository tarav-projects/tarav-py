"""Shared label syntax values, independent of Kernel and Workflow assembly."""
# tarav.breadcrumb bd694381bb92

import re
from typing import ClassVar

from pydantic_core import core_schema


class DottedFormat:
    """At least two capitalized alphanumeric words joined by literal dots."""

    pattern = r"[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+"

    @classmethod
    def matches(cls, text: str) -> bool:
        return re.fullmatch(cls.pattern, text) is not None


class JSONPointerFormat:
    """RFC 6901 string syntax, including the empty pointer to the root."""

    pattern = r"(?:/(?:[^~]|~[01])*)*"

    @classmethod
    def matches(cls, text: str) -> bool:
        return re.fullmatch(cls.pattern, text) is not None


class Label(str):
    """An unnormalized label accepted by any of its declared formats.

    Subclasses may narrow or extend formats; consumers retain identity separately.
    """

    formats: ClassVar[tuple[type, ...]] = (DottedFormat, JSONPointerFormat)

    def __new__(cls, value: str):
        if not isinstance(value, str):
            raise TypeError("Label must be a string")
        if not any(fmt.matches(value) for fmt in cls.formats):
            raise ValueError("Label must match a supported format: " +
                             ", ".join(fmt.__name__ for fmt in cls.formats))
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        # Every parse revalidates, including instances of a broader Label subtype.
        return core_schema.no_info_after_validator_function(
            cls, core_schema.str_schema(strict=True))

    @classmethod
    def __get_pydantic_json_schema__(cls, _schema, _handler):
        return {"anyOf": [{"type": "string", "pattern": "^(?:" + fmt.pattern + ")$"}
                          for fmt in cls.formats]}


__all__ = ["Label", "DottedFormat", "JSONPointerFormat"]
