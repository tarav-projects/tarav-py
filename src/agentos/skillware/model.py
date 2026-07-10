"""Skillware src surface model: `.skw.md` parsing.

A `.skw.md` is markdown plus `[!skw]` callout recipes. A recipe is a
blockquote whose first line is ``> [!skw]- <verb>`` placed first in a
section; ``> key: value`` field lines feed the schema; the produced body
sits outside the callout, from the recipe to a ``> [!skw] end`` marker or
the next heading. Everything else is hand-owned prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RECIPE_VERBS = ("copy", "derived")

_CALLOUT_RE = re.compile(r"^>\s*\[!skw\](-)?\s*(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
_FIELD_RE = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass(frozen=True)
class SkwFinding:
    line: int
    message: str


@dataclass(frozen=True)
class SkwRecipe:
    verb: str
    froms: tuple[str, ...]
    intent: str | None
    heading: str | None
    line: int
    callout_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]

    def body_text(self) -> str:
        return "\n".join(_trimmed(list(self.body)))


@dataclass(frozen=True)
class SkwSource:
    lines: tuple[str, ...]
    recipes: tuple[SkwRecipe, ...]
    end_spans: tuple[tuple[int, int], ...]
    findings: tuple[SkwFinding, ...]


def _trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _read_callout(lines: list[str], start: int) -> tuple[int, str, dict[str, list[str]]]:
    """Read one skw callout block; return (end_exclusive, verb, fields)."""
    match = _CALLOUT_RE.match(lines[start])
    assert match is not None
    verb = match.group(2).strip()
    fields: dict[str, list[str]] = {}
    last_key: str | None = None
    index = start + 1
    while index < len(lines):
        quote = _QUOTE_RE.match(lines[index])
        if quote is None:
            break
        content = quote.group(1).strip()
        field = _FIELD_RE.match(content)
        if field is not None:
            last_key = field.group(1)
            fields.setdefault(last_key, []).append(field.group(2).strip())
        elif last_key is not None and content:
            fields[last_key][-1] = f"{fields[last_key][-1]} {content}".strip()
        index += 1
    return index, verb, fields


def parse_skw_source(text: str) -> SkwSource:
    lines = text.splitlines()
    recipes: list[SkwRecipe] = []
    end_spans: list[tuple[int, int]] = []
    findings: list[SkwFinding] = []

    heading: str | None = None
    section_has_content = False
    open_recipe: dict | None = None

    def close_body(end_index: int) -> None:
        nonlocal open_recipe
        if open_recipe is None:
            return
        span = (open_recipe["body_start"], end_index)
        body = tuple(lines[span[0] : span[1]])
        recipes.append(
            SkwRecipe(
                verb=open_recipe["verb"],
                froms=open_recipe["froms"],
                intent=open_recipe["intent"],
                heading=open_recipe["heading"],
                line=open_recipe["line"],
                callout_span=open_recipe["callout_span"],
                body_span=span,
                body=body,
            )
        )
        open_recipe = None

    index = 0
    in_fence = False
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            section_has_content = True
            index += 1
            continue
        if in_fence:
            if line.strip():
                section_has_content = True
            index += 1
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            close_body(index)
            heading = heading_match.group(2).strip()
            section_has_content = False
            index += 1
            continue

        if _CALLOUT_RE.match(line) is not None:
            callout_end, verb, fields = _read_callout(lines, index)
            if verb == "end":
                if open_recipe is None:
                    findings.append(SkwFinding(index + 1, "[!skw] end without an open produced body"))
                else:
                    close_body(index)
                end_spans.append((index, callout_end))
            elif verb in RECIPE_VERBS:
                close_body(index)
                froms = tuple(fields.get("from", ()))
                if not froms:
                    findings.append(SkwFinding(index + 1, f"{verb} recipe carries no from: line"))
                if section_has_content:
                    findings.append(
                        SkwFinding(index + 1, "recipe is not first in its section (v1 convention)")
                    )
                intent_parts = fields.get("intent", [])
                open_recipe = {
                    "verb": verb,
                    "froms": froms,
                    "intent": " ".join(intent_parts) if intent_parts else None,
                    "heading": heading,
                    "line": index + 1,
                    "callout_span": (index, callout_end),
                    "body_start": callout_end,
                }
            else:
                findings.append(SkwFinding(index + 1, f"unknown skw verb: {verb!r}"))
            index = callout_end
            continue

        if line.strip():
            section_has_content = True
        index += 1

    close_body(len(lines))
    return SkwSource(
        lines=tuple(lines),
        recipes=tuple(recipes),
        end_spans=tuple(end_spans),
        findings=tuple(findings),
    )


__all__ = [
    "RECIPE_VERBS",
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
]
