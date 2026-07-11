"""Skillware src surface model: `.skw.md` parsing.

v2 — the universal `Skillware.Construct`: every piece of machinery is one
form, ``> [!skw]- <command>`` (+ ``> key: value`` arg lines), a flat markdown
body at column 0, and a mandatory owned closer ``> [!skw]- end-<command>``.
Closure is fully explicit: bare ``end`` is invalid, headings close nothing
(a construct still open at a heading or EOF is a finding), and a multi-close
line (``end-a end-b``) unwinds the open stack innermost-first.

Primitives (``text``, ``copy``, ``derived``) are position-free leaves;
structural commands (``router`` with ``when``/``then`` children) compose
them. Fenced code lines are inert. Everything outside constructs is
hand-owned prose.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RECIPE_VERBS = ("copy", "derived")
PRIMITIVE_COMMANDS = ("text", "copy", "derived")
STRUCTURAL_COMMANDS = ("router", "when", "then")
COMMANDS = PRIMITIVE_COMMANDS + STRUCTURAL_COMMANDS

_CALLOUT_RE = re.compile(r"^>\s*\[!skw\](-)?\s*(.*)$")
_LABEL_RE = re.compile(r"^\^[A-Za-z0-9_-]+$")
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
    ordinal: int
    label: str | None
    callout_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]

    def body_text(self) -> str:
        return "\n".join(_trimmed(list(self.body)))


@dataclass(frozen=True)
class SkwConstruct:
    command: str
    heading: str | None
    line: int
    label: str | None
    decl_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]


@dataclass(frozen=True)
class SkwSource:
    lines: tuple[str, ...]
    recipes: tuple[SkwRecipe, ...]
    constructs: tuple[SkwConstruct, ...]
    machinery_spans: tuple[tuple[int, int], ...]
    findings: tuple[SkwFinding, ...]


def recipe_key(recipe: SkwRecipe) -> str:
    if recipe.label is not None:
        return f"^{recipe.label}"
    base = recipe.heading or f"line {recipe.line}"
    return base if recipe.ordinal == 0 else f"{base}@{recipe.ordinal}"


def _trimmed(lines: list[str]) -> list[str]:
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _read_callout(lines: list[str], start: int) -> tuple[int, str, dict[str, list[str]]]:
    """Read one skw callout block; return (end_exclusive, decl, fields)."""
    match = _CALLOUT_RE.match(lines[start])
    assert match is not None
    decl = match.group(2).strip()
    fields: dict[str, list[str]] = {}
    last_key: str | None = None
    index = start + 1
    while index < len(lines):
        if _CALLOUT_RE.match(lines[index]) is not None:
            break
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
        elif last_key is None:
            break  # a plain blockquote before any field is body, not an arg
        index += 1
    return index, decl, fields


def parse_skw_source(text: str) -> SkwSource:
    lines = text.splitlines()
    recipes: list[SkwRecipe] = []
    constructs: list[SkwConstruct] = []
    machinery_spans: list[tuple[int, int]] = []
    findings: list[SkwFinding] = []

    heading: str | None = None
    stack: list[dict] = []
    heading_counts: dict[str, int] = {}
    seen_labels: set[str] = set()

    def close_top(end_index: int) -> None:
        frame = stack.pop()
        span = (frame["body_start"], end_index)
        body = tuple(lines[span[0] : span[1]])
        if frame["command"] in RECIPE_VERBS:
            key = frame["heading"] or f"line {frame['line']}"
            ordinal = heading_counts.get(key, 0)
            heading_counts[key] = ordinal + 1
            recipes.append(
                SkwRecipe(
                    verb=frame["command"],
                    froms=frame["froms"],
                    intent=frame["intent"],
                    heading=frame["heading"],
                    line=frame["line"],
                    ordinal=ordinal,
                    label=frame["label"],
                    callout_span=frame["decl_span"],
                    body_span=span,
                    body=body,
                )
            )
        else:
            constructs.append(
                SkwConstruct(
                    command=frame["command"],
                    heading=frame["heading"],
                    line=frame["line"],
                    label=frame["label"],
                    decl_span=frame["decl_span"],
                    body_span=span,
                    body=body,
                )
            )
        parent = stack[-1] if stack else None
        if parent is not None and parent["command"] == "router":
            parent["children"].append(frame["command"])

    def force_close_open(end_index: int, where: str) -> None:
        while stack:
            frame = stack[-1]
            findings.append(
                SkwFinding(
                    frame["line"],
                    f"'{frame['command']}' left open at {where} "
                    f"(closure is explicit: end-{frame['command']})",
                )
            )
            close_top(end_index)
            if frame["command"] == "router":
                check_router_children(frame)

    def check_router_children(frame: dict) -> None:
        expected = "when"
        for child in frame["children"]:
            if child not in ("when", "then"):
                continue
            if child != expected:
                findings.append(
                    SkwFinding(
                        frame["line"],
                        f"router rows must alternate when/then: found '{child}' "
                        f"where '{expected}' was expected",
                    )
                )
                return
            expected = "then" if expected == "when" else "when"
        if expected == "then":
            findings.append(
                SkwFinding(frame["line"], "router ends with a 'when' that has no 'then'")
            )

    index = 0
    in_fence = False
    fence_line = 0
    while index < len(lines):
        line = lines[index]
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            fence_line = index + 1
            index += 1
            continue
        if in_fence:
            index += 1
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match is not None:
            force_close_open(index, f"heading '{heading_match.group(2).strip()}'")
            heading = heading_match.group(2).strip()
            index += 1
            continue

        callout_match = _CALLOUT_RE.match(line)
        if callout_match is not None:
            decl = callout_match.group(2).strip()
            tokens = decl.split()
            if tokens and all(token == "end" or token.startswith("end-") for token in tokens):
                # end callouts take no args: consume only the declaration line
                callout_end = index + 1
                for token in tokens:
                    owner = token[4:] if token.startswith("end-") else ""
                    if not owner:
                        findings.append(
                            SkwFinding(
                                index + 1,
                                "bare 'end' is invalid; close with end-<command>",
                            )
                        )
                        continue
                    if not stack:
                        findings.append(
                            SkwFinding(index + 1, f"'end-{owner}' without an open construct")
                        )
                        continue
                    top = stack[-1]
                    if owner.startswith("^"):
                        matches = top["label"] == owner[1:]
                    else:
                        matches = top["command"] == owner
                    if not matches:
                        accepted = f"end-{top['command']}"
                        if top["label"] is not None:
                            accepted += f" or end-^{top['label']}"
                        findings.append(
                            SkwFinding(
                                index + 1,
                                f"mismatched close: expected {accepted}, found end-{owner}",
                            )
                        )
                    frame = stack[-1]
                    close_top(index)
                    if frame["command"] == "router":
                        check_router_children(frame)
                machinery_spans.append((index, callout_end))
                index = callout_end
                continue

            callout_end, decl, fields = _read_callout(lines, index)
            tokens = decl.split()
            label: str | None = None
            command_tokens: list[str] = []
            bad_tokens: list[str] = []
            for token in tokens:
                if _LABEL_RE.match(token):
                    if label is None:
                        label = token[1:]
                    else:
                        bad_tokens.append(token)
                else:
                    command_tokens.append(token)
            command = command_tokens[0] if command_tokens else ("text" if label else "")
            if command not in COMMANDS:
                findings.append(SkwFinding(index + 1, f"unknown skw command: {command!r}"))
                index = callout_end
                continue
            if len(command_tokens) > 1 or bad_tokens:
                extra = command_tokens[1:] + bad_tokens
                findings.append(
                    SkwFinding(index + 1, f"unexpected tokens on declaration: {extra}")
                )
            if label is not None:
                if label in seen_labels:
                    findings.append(SkwFinding(index + 1, f"duplicate label: ^{label}"))
                seen_labels.add(label)

            if stack and stack[-1]["command"] in PRIMITIVE_COMMANDS:
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"constructs may not nest inside a '{stack[-1]['command']}' body",
                    )
                )
            if command in ("when", "then") and (
                not stack or stack[-1]["command"] != "router"
            ):
                findings.append(SkwFinding(index + 1, f"'{command}' outside a router"))

            froms = tuple(fields.get("from", ()))
            if command in RECIPE_VERBS and not froms:
                findings.append(
                    SkwFinding(index + 1, f"{command} recipe carries no from: line")
                )
            if command == "copy" and len(froms) > 1:
                findings.append(
                    SkwFinding(index + 1, "copy takes exactly one from: line")
                )
            intent_parts = fields.get("intent", [])
            stack.append(
                {
                    "command": command,
                    "heading": heading,
                    "line": index + 1,
                    "label": label,
                    "decl_span": (index, callout_end),
                    "body_start": callout_end,
                    "froms": froms,
                    "intent": " ".join(intent_parts) if intent_parts else None,
                    "children": [],
                }
            )
            machinery_spans.append((index, callout_end))
            index = callout_end
            continue

        index += 1

    force_close_open(len(lines), "EOF")
    if in_fence:
        findings.append(
            SkwFinding(
                fence_line,
                "unclosed code fence at EOF — everything after it parsed as inert",
            )
        )
    return SkwSource(
        lines=tuple(lines),
        recipes=tuple(recipes),
        constructs=tuple(constructs),
        machinery_spans=tuple(machinery_spans),
        findings=tuple(findings),
    )


__all__ = [
    "COMMANDS",
    "PRIMITIVE_COMMANDS",
    "RECIPE_VERBS",
    "STRUCTURAL_COMMANDS",
    "SkwConstruct",
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
    "recipe_key",
]
