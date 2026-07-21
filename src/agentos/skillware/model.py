"""Skillware src surface model: `.skw.md` parsing.

v2 grammar — the annotation as a *named block*. The surface grammar is the
`$kw` sigil pair on the markdown carrier, but the sigil now rides only the two
**fence** lines:

    > $kw: [address] [--flags]      # opens a block; address is optional identity
    > --flag [value]                # belonging flag lines — self-marked by `--`
    native surface text …           # the block's body (column 0)
    > $kw. end                      # closes a content block (bare `end`)

Features are additive `--flags`, not commands: the binding mode is a flag
(`--derived`/`--copy`/`--pointer`), `--from` is a dependency edge, `--note`
is a typed+anchored documentation line, `--supp` the block's own touched
lines, `--intent` derivation context, `--cont` a generic continuation of the
previous flag, and `--to` a reserved (parsed, inert) flag. Router rows are
nameless child blocks opened with `--when` / `--then`.

**Closure is by role, in three cases** (`Closure.Parser::Skw`):

- a **materializing** block (`--derived`/`--copy`) owns a mandatory `$kw. end`
  (its body is the generated target);
- a **router** block (one that acquires `--when`/`--then` children) owns an
  `$kw. end`, and its rows **peer-close** at the next row or the parent's end;
- a **declaration-only** block (`--from`/`--note`/`--supp`/`--intent` only)
  **self-closes** at its declaration — no `end` — unless it writes one, which
  opts it into fencing a native body.

The parser demands a minimal structure — the `Parse.Floor`: every machinery
line well-formed, every content block explicitly closed, addresses unique,
router rows sane. Below the floor it emits parse errors (`SkwFinding`) and
nothing else — no POIs; linting is the `Poi.Linter`'s job (see
`build.check_skill`). Fenced code lines are inert; headings close nothing;
bodies sit at column 0.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

RECIPE_BINDINGS = ("derived", "copy")
BINDING_FLAGS = ("derived", "copy", "pointer")
ROLE_FLAGS = ("when", "then")
VALUE_FLAGS = ("from", "intent", "to", "note", "supp", "cont")
KNOWN_FLAGS = BINDING_FLAGS + ROLE_FLAGS + VALUE_FLAGS

_OPEN_RE = re.compile(r"^>\s*\$kw:\s?(.*)$")
_CLOSE_RE = re.compile(r"^>\s*\$kw\.\s*(.*)$")
_FLAG_LINE_RE = re.compile(r"^>\s*(--\S.*)$")
_ADDRESS_RE = re.compile(r"^[#^@]?[A-Za-z0-9_./#:^-]+$")
_FLAG_RE = re.compile(rf"(?:^|\s)--({'|'.join(KNOWN_FLAGS)})(?=\s|$)")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_NOTE_TYPE_RE = re.compile(r"^\[([A-Z]{2})\]\s*(.*)$")
_TRAILING_ANCHOR_RE = re.compile(r"\s+(\^[A-Za-z0-9_-]+)\s*$")


@dataclass(frozen=True)
class SkwFinding:
    line: int
    message: str


@dataclass(frozen=True)
class SkwNote:
    """A `--note` (documentation) or `--supp` (own touched line) — a typed,
    anchored `Index.Line` carried by an annotation block."""

    flag: str  # "note" | "supp"
    type: str | None  # the two-letter act code for --note; None for --supp
    text: str
    anchor: str | None
    line: int
    address: str | None


@dataclass(frozen=True)
class SkwRecipe:
    verb: str
    froms: tuple[str, ...]
    intent: str | None
    heading: str | None
    line: int
    ordinal: int
    label: str | None
    address: str | None
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
    address: str | None
    decl_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]


@dataclass(frozen=True)
class SkwDependency:
    froms: tuple[str, ...]
    heading: str | None
    line: int
    label: str | None
    address: str | None
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwSource:
    lines: tuple[str, ...]
    recipes: tuple[SkwRecipe, ...]
    constructs: tuple[SkwConstruct, ...]
    dependencies: tuple[SkwDependency, ...]
    notes: tuple[SkwNote, ...]
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


def _is_bare_end(content: str) -> bool:
    return content.strip() == "end"


def _parse_flag_segments(
    content: str,
    flags: list[tuple[str, str]],
    findings: list[SkwFinding],
    line_no: int,
) -> None:
    """Parse ``--flag value …`` pairs on one segment; a value runs to the next
    registered flag or EOL. ``--cont`` appends to the previous flag's value; a
    bare head continues the previous flag too (value continuation)."""
    matches = list(_FLAG_RE.finditer(content))
    head = content[: matches[0].start()].strip() if matches else content.strip()
    if head:
        if head.startswith("--"):
            # an unrecognized `--token` at a flag position is an unknown flag,
            # never a silent value continuation (known flags match _FLAG_RE)
            findings.append(SkwFinding(line_no, f"unknown flag: {head.split()[0]}"))
        elif flags:
            name, value = flags[-1]
            flags[-1] = (name, f"{value} {head}".strip())
        else:
            findings.append(
                SkwFinding(line_no, f"continuation before any flag: {head!r}")
            )
    for pos, match in enumerate(matches):
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(content)
        name = match.group(1)
        value = content[match.end() : end].strip()
        if name == "cont":
            if flags:
                prev_name, prev_value = flags[-1]
                flags[-1] = (prev_name, f"{prev_value} {value}".strip())
            else:
                findings.append(
                    SkwFinding(line_no, "orphan --cont: no previous flag to continue")
                )
            continue
        flags.append((name, value))


def _read_block(
    lines: list[str], start: int, findings: list[SkwFinding]
) -> tuple[int, str | None, str | None, list[tuple[str, str]]]:
    """Read a ``> $kw:`` open line plus contiguous ``> --flag`` belonging
    lines. Returns (end_exclusive, address, label, flags). The address is the
    first non-flag token on the open line; ``^label`` addresses also yield a
    bare label for lock-key continuity."""
    match = _OPEN_RE.match(lines[start])
    assert match is not None
    content = match.group(1).strip()

    matches = list(_FLAG_RE.finditer(content))
    head = content[: matches[0].start()] if matches else content
    head_tokens = head.split()
    address: str | None = None
    extras: list[str] = []
    for token in head_tokens:
        if address is None and _ADDRESS_RE.match(token):
            address = token
        else:
            extras.append(token)

    flags: list[tuple[str, str]] = []
    if matches:
        _parse_flag_segments(content[matches[0].start() :], flags, findings, start + 1)

    index = start + 1
    while index < len(lines):
        flag_line = _FLAG_LINE_RE.match(lines[index])
        if flag_line is None:
            break
        _parse_flag_segments(flag_line.group(1).strip(), flags, findings, index + 1)
        index += 1

    if extras:
        findings.append(
            SkwFinding(start + 1, f"unexpected tokens on declaration: {extras}")
        )
    label = address[1:] if address and address.startswith("^") else None
    return index, address, label, flags


def _parse_note(flag: str, value: str, line: int, address: str | None) -> SkwNote:
    text = value
    anchor: str | None = None
    anchor_match = _TRAILING_ANCHOR_RE.search(text)
    if anchor_match is not None:
        anchor = anchor_match.group(1)
        text = text[: anchor_match.start()].strip()
    note_type: str | None = None
    if flag == "note":
        type_match = _NOTE_TYPE_RE.match(text)
        if type_match is not None:
            note_type = type_match.group(1)
            text = type_match.group(2).strip()
    return SkwNote(
        flag=flag,
        type=note_type,
        text=text,
        anchor=anchor,
        line=line,
        address=address,
    )


def parse_skw_source(text: str) -> SkwSource:
    lines = text.splitlines()
    recipes: list[SkwRecipe] = []
    constructs: list[SkwConstruct] = []
    dependencies: list[SkwDependency] = []
    notes: list[SkwNote] = []
    machinery_spans: list[tuple[int, int]] = []
    findings: list[SkwFinding] = []

    heading: str | None = None
    stack: list[dict] = []
    heading_counts: dict[str, int] = {}
    seen_addresses: set[str] = set()

    def _has_content(body: tuple[str, ...]) -> bool:
        return any(line.strip() for line in body)

    def emit_frame(frame: dict, end_index: int) -> None:
        span = (frame["body_start"], end_index)
        body = tuple(lines[span[0] : span[1]])
        for note in frame["notes"]:
            notes.append(note)
        if frame["verb"] in RECIPE_BINDINGS:
            key = frame["heading"] or f"line {frame['line']}"
            ordinal = heading_counts.get(key, 0)
            heading_counts[key] = ordinal + 1
            recipes.append(
                SkwRecipe(
                    verb=frame["verb"],
                    froms=frame["froms"],
                    intent=frame["intent"],
                    heading=frame["heading"],
                    line=frame["line"],
                    ordinal=ordinal,
                    label=frame["label"],
                    address=frame["address"],
                    callout_span=frame["decl_span"],
                    body_span=span,
                    body=body,
                )
            )
        elif (
            frame["command"] == "text"
            and frame["froms"]
            and not _has_content(body)
        ):
            # a pure declaration-only `--from` block is the void dependency
            dependencies.append(
                SkwDependency(
                    froms=frame["froms"],
                    heading=frame["heading"],
                    line=frame["line"],
                    label=frame["label"],
                    address=frame["address"],
                    decl_span=frame["decl_span"],
                )
            )
        else:
            constructs.append(
                SkwConstruct(
                    command=frame["command"],
                    heading=frame["heading"],
                    line=frame["line"],
                    label=frame["label"],
                    address=frame["address"],
                    decl_span=frame["decl_span"],
                    body_span=span,
                    body=body,
                )
            )
        parent = stack[-1] if stack else None
        if parent is not None and frame["command"] in ("when", "then"):
            parent["children"].append(frame["command"])
            parent["command"] = "router"
            parent["needs_end"] = True

    def close_top(end_index: int) -> None:
        frame = stack.pop()
        emit_frame(frame, end_index)

    def peer_close_rows(end_index: int) -> None:
        while stack and stack[-1]["command"] in ("when", "then"):
            close_top(end_index)

    def check_router_children(frame: dict) -> None:
        expected = "when"
        for child in frame["children"]:
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

    def force_close(end_index: int, where: str) -> None:
        while stack:
            frame = stack[-1]
            if frame["needs_end"]:
                findings.append(
                    SkwFinding(
                        frame["line"],
                        f"'{frame['command']}' left open at {where} "
                        f"(a content block closes explicitly with $kw. end)",
                    )
                )
            close_top(end_index)
            if frame["command"] == "router":
                check_router_children(frame)

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
            force_close(index, f"heading '{heading_match.group(2).strip()}'")
            heading = heading_match.group(2).strip()
            index += 1
            continue

        close_match = _CLOSE_RE.match(line)
        if close_match is not None:
            content = close_match.group(1).strip()
            if not _is_bare_end(content):
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"$kw. lines take only a bare 'end'; found: {content!r}",
                    )
                )
                machinery_spans.append((index, index + 1))
                index += 1
                continue
            peer_close_rows(index)
            if not stack:
                findings.append(
                    SkwFinding(index + 1, "'end' without an open content block")
                )
            else:
                frame = stack[-1]
                close_top(index)
                if frame["command"] == "router":
                    check_router_children(frame)
            machinery_spans.append((index, index + 1))
            index += 1
            continue

        open_match = _OPEN_RE.match(line)
        if open_match is None:
            flag_match = _FLAG_LINE_RE.match(line)
            if flag_match is not None:
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"stray flag line outside a declaration: {flag_match.group(1).strip()!r}",
                    )
                )
                machinery_spans.append((index, index + 1))
            index += 1
            continue

        decl_end, address, label, flags = _read_block(lines, index, findings)

        if address is not None:
            if address in seen_addresses:
                findings.append(SkwFinding(index + 1, f"duplicate address: {address}"))
            seen_addresses.add(address)

        flag_names = [name for name, _ in flags]
        bindings = [name for name in flag_names if name in BINDING_FLAGS]
        roles = [name for name in flag_names if name in ROLE_FLAGS]
        froms = tuple(value for name, value in flags if name == "from")
        # a binding flag's own trailing text is derivation context, as is --intent
        intent_parts = [
            value
            for name, value in flags
            if name in ("derived", "copy", "pointer", "intent") and value
        ]
        frame_notes = [
            _parse_note(name, value, decl_end, address)
            for name, value in flags
            if name in ("note", "supp")
        ]

        if len(bindings) > 1:
            findings.append(
                SkwFinding(index + 1, f"multiple binding flags: {bindings}")
            )
        if len(roles) > 1:
            findings.append(SkwFinding(index + 1, f"multiple role flags: {roles}"))
        if roles and bindings:
            findings.append(
                SkwFinding(index + 1, "a router row cannot also carry a binding flag")
            )

        role = roles[0] if roles else None
        verb = bindings[0] if bindings else None

        if role is not None:
            if not stack or stack[-1]["command"] in ("when", "then"):
                # rows peer-close, so a sibling row is legal; only a top-level
                # row (no parent block) is orphaned
                if not stack:
                    findings.append(
                        SkwFinding(index + 1, f"'{role}' outside a router")
                    )
                else:
                    peer_close_rows(index)
            command = role
        elif verb in RECIPE_BINDINGS:
            command = verb
        else:
            # `--pointer` binds by reference (non-materializing); with no
            # binding at all the block is either a content span or an
            # annotation — resolved below by whether it carries annotation flags
            command = "text"

        if command in RECIPE_BINDINGS and not froms:
            findings.append(
                SkwFinding(index + 1, f"{command} recipe carries no --from flag")
            )
        if command == "copy" and len(froms) > 1:
            findings.append(SkwFinding(index + 1, "copy takes exactly one --from flag"))

        # closure by role: a recipe or a content span (a flag-less block, incl.
        # a router parent) owns its `end`; a row peer-closes; an annotation
        # block — one carrying only `--from`/`--note`/`--supp` — self-closes at
        # its declaration, and following text stays surface.
        annotation_only = command == "text" and (
            bool(froms) or bool(frame_notes) or verb == "pointer"
        )
        needs_end = command in RECIPE_BINDINGS or (
            command == "text" and not annotation_only
        )

        # nesting guard: a construct may only nest as a when/then row inside a
        # router-capable parent; a plain block may not nest inside a recipe body
        if stack and stack[-1]["verb"] in RECIPE_BINDINGS and role is None:
            findings.append(
                SkwFinding(
                    index + 1,
                    f"blocks may not nest inside a '{stack[-1]['command']}' body",
                )
            )

        frame = {
            "command": command,
            "verb": verb if verb in RECIPE_BINDINGS else None,
            "heading": heading,
            "line": index + 1,
            "label": label,
            "address": address,
            "decl_span": (index, decl_end),
            "body_start": decl_end,
            "froms": froms,
            "intent": " ".join(intent_parts) if intent_parts else None,
            "notes": frame_notes,
            "needs_end": needs_end,
            "children": [],
        }

        machinery_spans.append((index, decl_end))
        if annotation_only:
            # self-close at the declaration: emit now with an empty body so
            # following native text stays surface (void dependency / note attach)
            emit_frame(frame, decl_end)
        else:
            stack.append(frame)
        index = decl_end

    force_close(len(lines), "EOF")
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
        notes=tuple(notes),
        machinery_spans=tuple(machinery_spans),
        findings=tuple(findings),
    )


__all__ = [
    "BINDING_FLAGS",
    "KNOWN_FLAGS",
    "RECIPE_BINDINGS",
    "ROLE_FLAGS",
    "VALUE_FLAGS",
    "SkwConstruct",
    "SkwDependency",
    "SkwFinding",
    "SkwNote",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_source",
    "recipe_key",
]
