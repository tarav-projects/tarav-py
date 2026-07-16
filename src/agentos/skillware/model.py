"""Skillware src surface model: `.skw.md` parsing.

v3 — `Closure.Parser::Skw`. The surface grammar is the `$kw` sigil pair on
the markdown carrier: ``> $kw: <command> [^label] [--flag value …]`` opens a
construct, ``> $kw. …`` lines belong to it — further flags, value
continuations, and the owned closer ``> $kw. end-<command>`` (or
``end-^label``; a multi-close line unwinds innermost-first).

The parser demands a minimal structure — the `Parse.Floor`: every machinery
line well-formed, every construct explicitly closed, labels unique, router
rows sane. Below the floor it emits parse errors (`SkwFinding`) and nothing
else — no POIs; linting is the `Poi.Linter`'s job (see `build.check_skill`).
Above the floor the parse is closed: recognized machinery becomes constructs,
everything else is opaque text, and no finer detail can fail the parse.
Fenced code lines are inert; headings close nothing; bodies sit at column 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RECIPE_VERBS = ("copy", "derived")
PRIMITIVE_COMMANDS = ("text", "copy", "derived")
STRUCTURAL_COMMANDS = ("router", "when", "then")
VOID_COMMANDS = ("depends",)
COMMANDS = PRIMITIVE_COMMANDS + STRUCTURAL_COMMANDS + VOID_COMMANDS
KNOWN_FLAGS = ("from", "intent", "to")

_MACHINERY_RE = re.compile(r"^>\s*\$kw([:.])\s?(.*)$")
_LABEL_RE = re.compile(r"^\^[A-Za-z0-9_-]+$")
# only registered flags bound values: an unregistered --token mid-value is
# prose (registry-driven trait validation), never a silent value splitter
_FLAG_RE = re.compile(rf"(?:^|\s)--({'|'.join(KNOWN_FLAGS)})(?=\s|$)")
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
class SkwDependency:
    froms: tuple[str, ...]
    heading: str | None
    line: int
    label: str | None
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwSource:
    lines: tuple[str, ...]
    recipes: tuple[SkwRecipe, ...]
    constructs: tuple[SkwConstruct, ...]
    dependencies: tuple[SkwDependency, ...]
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


def _is_end_content(content: str) -> bool:
    tokens = content.split()
    return bool(tokens) and all(t == "end" or t.startswith("end-") for t in tokens)


def _parse_flags(
    content: str, flags: list[tuple[str, str]], findings: list[SkwFinding], line_no: int
) -> None:
    """Parse ``--flag value …`` pairs; a value runs to the next registered flag or EOL."""
    matches = list(_FLAG_RE.finditer(content))
    head = content[: matches[0].start()].strip() if matches else content.strip()
    if head:
        if flags:
            # value continuation of the previous flag
            name, value = flags[-1]
            flags[-1] = (name, f"{value} {head}".strip())
        elif head.startswith("--"):
            findings.append(SkwFinding(line_no, f"unknown flag: {head.split()[0]}"))
        else:
            findings.append(
                SkwFinding(line_no, f"continuation before any flag: {head!r}")
            )
    for pos, match in enumerate(matches):
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(content)
        flags.append((match.group(1), content[match.end() : end].strip()))


def _read_declaration(
    lines: list[str], start: int, findings: list[SkwFinding]
) -> tuple[int, str, str | None, list[tuple[str, str]]]:
    """Read a ``$kw:`` line plus contiguous ``$kw.`` belonging lines.

    Returns (end_exclusive, command, label, flags). Closer lines are never
    consumed here — an all-end ``$kw.`` line terminates the block.
    """
    match = _MACHINERY_RE.match(lines[start])
    assert match is not None and match.group(1) == ":"
    content = match.group(2).strip()

    matches = list(_FLAG_RE.finditer(content))
    head = content[: matches[0].start()] if matches else content
    head_tokens = head.split()
    label: str | None = None
    command = ""
    extras: list[str] = []
    for token in head_tokens:
        if _LABEL_RE.match(token):
            if label is None:
                label = token[1:]
            else:
                extras.append(token)
        elif not command:
            command = token
        else:
            extras.append(token)

    flags: list[tuple[str, str]] = []
    if matches:
        _parse_flags(content[matches[0].start() :], flags, findings, start + 1)

    index = start + 1
    while index < len(lines):
        belonging = _MACHINERY_RE.match(lines[index])
        if belonging is None or belonging.group(1) != ".":
            break
        inner = belonging.group(2).strip()
        if _is_end_content(inner):
            break
        _parse_flags(inner, flags, findings, index + 1)
        index += 1
    if extras:
        findings.append(
            SkwFinding(start + 1, f"unexpected tokens on declaration: {extras}")
        )
    return index, command, label, flags


def parse_skw_source(text: str) -> SkwSource:
    lines = text.splitlines()
    recipes: list[SkwRecipe] = []
    constructs: list[SkwConstruct] = []
    dependencies: list[SkwDependency] = []
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

        machinery = _MACHINERY_RE.match(line)
        if machinery is None:
            index += 1
            continue

        sigil, content = machinery.group(1), machinery.group(2).strip()

        if sigil == "." and _is_end_content(content):
            # end lines take no args: consume only the closer line itself
            for token in content.split():
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
            machinery_spans.append((index, index + 1))
            index += 1
            continue

        if sigil == ".":
            findings.append(
                SkwFinding(index + 1, f"stray '$kw.' line outside a declaration: {content!r}")
            )
            machinery_spans.append((index, index + 1))
            index += 1
            continue

        decl_end, command, label, flags = _read_declaration(lines, index, findings)
        if command == "label":
            if label is None:
                findings.append(
                    SkwFinding(index + 1, "'label' requires a ^label token")
                )
            command = "text"
        elif not command:
            findings.append(
                SkwFinding(index + 1, "declaration carries no command (bare labels are invalid; use 'label ^x')")
            )
            index = decl_end
            continue
        if command not in COMMANDS:
            findings.append(SkwFinding(index + 1, f"unknown skw command: {command!r}"))
            index = decl_end
            continue
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

        froms = tuple(value for name, value in flags if name == "from")
        if command in RECIPE_VERBS and not froms:
            findings.append(
                SkwFinding(index + 1, f"{command} recipe carries no --from flag")
            )
        if command == "copy" and len(froms) > 1:
            findings.append(
                SkwFinding(index + 1, "copy takes exactly one --from flag")
            )
        if command in VOID_COMMANDS:
            if not froms:
                findings.append(
                    SkwFinding(index + 1, f"{command} declaration carries no --from flag")
                )
            if decl_end > index + 1:
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"{command} is void and cannot carry $kw. body or continuation lines",
                    )
                )
            dependencies.append(
                SkwDependency(
                    froms=froms,
                    heading=heading,
                    line=index + 1,
                    label=label,
                    decl_span=(index, decl_end),
                )
            )
            machinery_spans.append((index, decl_end))
            index = decl_end
            continue
        intent_parts = [value for name, value in flags if name == "intent"]
        stack.append(
            {
                "command": command,
                "heading": heading,
                "line": index + 1,
                "label": label,
                "decl_span": (index, decl_end),
                "body_start": decl_end,
                "froms": froms,
                "intent": " ".join(intent_parts) if intent_parts else None,
                "children": [],
            }
        )
        machinery_spans.append((index, decl_end))
        index = decl_end

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
        dependencies=tuple(dependencies),
        machinery_spans=tuple(machinery_spans),
        findings=tuple(findings),
    )


__all__ = [
    "COMMANDS",
    "KNOWN_FLAGS",
    "PRIMITIVE_COMMANDS",
    "RECIPE_VERBS",
    "STRUCTURAL_COMMANDS",
    "VOID_COMMANDS",
    "SkwConstruct",
    "SkwDependency",
    "SkwFinding",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
    "recipe_key",
]
