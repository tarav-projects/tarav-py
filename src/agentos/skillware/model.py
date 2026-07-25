# $kw: ^skw-model --note [DF] the skw parser — a surface-agnostic $kw frame core plus per-surface Carrier adapters ^c20260722-24u
# --supp context assemblies are whole-file modules declared at the file point; dependency roles remain distinct ^c20260725-27u
"""Skillware src surface model: `.skw.md` parsing.

v2 grammar — the annotation as a *named block*. The surface grammar is the
`$kw` sigil pair on the markdown carrier, but the sigil now rides only the two
**fence** lines:

    > $kw: [address] [--flags]      # opens a block; address is optional identity
    > --flag [value]                # belonging flag lines — self-marked by `--`
    native surface text …           # the block's body (column 0)
    > $kw. end                      # closes a content block (bare `end`)

Features are additive `--flags`, not commands: the binding mode is a flag
(`--derived`/`--copy`/`--pointer`), `--from` is a generic dependency edge,
`--dev-from` is builder context, `--cite` is a visible citation obligation,
`--context-assembly` marks the whole source file as a context assembly,
`--note` is a typed+anchored documentation line, `--supp` the block's own
touched lines, `--unlock-surface` marks a context surface represented by an
unlock registry, `--intent` derivation context, `--cont` a generic
continuation of the previous flag, and `--to` a reserved (parsed, inert) flag.
Router rows are nameless child blocks opened with `--when` / `--then`.

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
VALUE_FLAGS = ("from", "dev-from", "cite", "intent", "to", "note", "supp", "cont")
BOOLEAN_FLAGS = ("unlock-surface", "context-assembly")
KNOWN_FLAGS = BINDING_FLAGS + ROLE_FLAGS + VALUE_FLAGS + BOOLEAN_FLAGS

_ADDRESS_RE = re.compile(r"^[#^@]?[A-Za-z0-9_./#:^-]+$")
_FLAG_RE = re.compile(rf"(?:^|\s)--({'|'.join(KNOWN_FLAGS)})(?=\s|$)")
_NOTE_TYPE_RE = re.compile(r"^\[([A-Z]{2})\]\s*(.*)$")
_TRAILING_ANCHOR_RE = re.compile(r"\s+(\^[A-Za-z0-9_-]+)\s*$")


@dataclass(frozen=True)
class Carrier:
    """Surface-specific recognition of skw machinery (`Skw.Backend` carrier).

    The `$kw` frame core is surface-agnostic; only *how a raw line carries
    machinery* is per-surface. A carrier answers five questions about one line —
    is it an open, a close, a belonging flag, a fence toggle, or a structural
    boundary that force-closes open blocks — returning the carrier-stripped
    machinery content so the shared core never sees the carrier syntax.
    """

    name: str
    open_re: re.Pattern
    close_re: re.Pattern
    flag_re: re.Pattern
    fence_re: re.Pattern | None
    boundary_re: re.Pattern | None
    boundary_label: str = "boundary"

    def open_content(self, line: str) -> str | None:
        match = self.open_re.match(line)
        return match.group(1) if match is not None else None

    def close_content(self, line: str) -> str | None:
        match = self.close_re.match(line)
        return match.group(1) if match is not None else None

    def flag_content(self, line: str) -> str | None:
        match = self.flag_re.match(line)
        return match.group(1) if match is not None else None

    def is_fence(self, line: str) -> bool:
        return self.fence_re is not None and self.fence_re.match(line) is not None

    def boundary_name(self, line: str) -> str | None:
        if self.boundary_re is None:
            return None
        match = self.boundary_re.match(line)
        return match.group("name").strip() if match is not None else None


# The markdown carrier: machinery rides `>` blockquote lines; ``` / ~~~ fence
# code inert; ATX headings are the structural boundary. The original grammar.
MARKDOWN_CARRIER = Carrier(
    name="skw-skills",
    open_re=re.compile(r"^>\s*\$kw:\s?(.*)$"),
    close_re=re.compile(r"^>\s*\$kw\.\s*(.*)$"),
    flag_re=re.compile(r"^>\s*(--\S.*)$"),
    fence_re=re.compile(r"^\s*(?:```|~~~)"),
    boundary_re=re.compile(r"^#{1,6}\s+(?P<name>.*)$"),
    boundary_label="heading",
)

# The code carrier (carrier B): the comment *is* the carrier — `# $kw: …`. No
# blockquote, no markdown fence; boundaries (def/class Annotation.Points) are a
# per-language concern layered in Slice 3.
CODE_CARRIER = Carrier(
    name="skw-code",
    open_re=re.compile(r"^#\s*\$kw:\s?(.*)$"),
    close_re=re.compile(r"^#\s*\$kw\.\s*(.*)$"),
    flag_re=re.compile(r"^#\s*(--\S.*)$"),
    fence_re=None,
    boundary_re=None,
)


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
    dev_froms: tuple[str, ...]
    cites: tuple[str, ...]
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
    froms: tuple[str, ...]
    dev_froms: tuple[str, ...]
    cites: tuple[str, ...]
    decl_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]


@dataclass(frozen=True)
class SkwDependency:
    froms: tuple[str, ...]
    dev_froms: tuple[str, ...]
    cites: tuple[str, ...]
    unlock_surface: bool
    context_assembly: bool
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
    lines: list[str], start: int, findings: list[SkwFinding], carrier: Carrier
) -> tuple[int, str | None, str | None, list[tuple[str, str]]]:
    """Read a ``$kw:`` open line plus contiguous ``--flag`` belonging lines.
    Returns (end_exclusive, address, label, flags). The address is the first
    non-flag token on the open line; ``^label`` addresses also yield a bare
    label for lock-key continuity. Carrier-agnostic: the carrier strips its own
    syntax before this sees machinery content."""
    open_content = carrier.open_content(lines[start])
    assert open_content is not None
    content = open_content.strip()

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
        flag_content = carrier.flag_content(lines[index])
        if flag_content is None:
            break
        _parse_flag_segments(flag_content.strip(), flags, findings, index + 1)
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


@dataclass
class _Frame:
    """A block open on the parse stack, closed when its `end` (or a peer/EOF)
    arrives. Mutable: a router parent's `command`/`needs_end`/`children` are
    updated in place as its `--when`/`--then` rows attach."""

    command: str
    verb: str | None
    heading: str | None
    line: int
    label: str | None
    address: str | None
    decl_span: tuple[int, int]
    body_start: int
    froms: tuple[str, ...]
    dev_froms: tuple[str, ...]
    cites: tuple[str, ...]
    unlock_surface: bool
    context_assembly: bool
    intent: str | None
    notes: list[SkwNote]
    needs_end: bool
    children: list[str] = field(default_factory=list)


def _parse_source(text: str, carrier: Carrier) -> SkwSource:
    lines = text.splitlines()
    recipes: list[SkwRecipe] = []
    constructs: list[SkwConstruct] = []
    dependencies: list[SkwDependency] = []
    notes: list[SkwNote] = []
    machinery_spans: list[tuple[int, int]] = []
    findings: list[SkwFinding] = []

    heading: str | None = None
    stack: list[_Frame] = []
    heading_counts: dict[str, int] = {}
    seen_addresses: set[str] = set()

    def _has_content(body: tuple[str, ...]) -> bool:
        return any(line.strip() for line in body)

    def emit_frame(frame: _Frame, end_index: int) -> None:
        span = (frame.body_start, end_index)
        body = tuple(lines[span[0] : span[1]])
        notes.extend(frame.notes)
        if frame.verb in RECIPE_BINDINGS:
            key = frame.heading or f"line {frame.line}"
            ordinal = heading_counts.get(key, 0)
            heading_counts[key] = ordinal + 1
            recipes.append(
                SkwRecipe(
                    verb=frame.verb,
                    froms=frame.froms,
                    dev_froms=frame.dev_froms,
                    cites=frame.cites,
                    intent=frame.intent,
                    heading=frame.heading,
                    line=frame.line,
                    ordinal=ordinal,
                    label=frame.label,
                    address=frame.address,
                    callout_span=frame.decl_span,
                    body_span=span,
                    body=body,
                )
            )
        elif (
            frame.command == "text"
            and (frame.froms or frame.dev_froms or frame.cites)
            and not _has_content(body)
        ):
            # A declaration-only dependency block owns no native body.
            dependencies.append(
                SkwDependency(
                    froms=frame.froms,
                    dev_froms=frame.dev_froms,
                    cites=frame.cites,
                    unlock_surface=frame.unlock_surface,
                    context_assembly=frame.context_assembly,
                    heading=frame.heading,
                    line=frame.line,
                    label=frame.label,
                    address=frame.address,
                    decl_span=frame.decl_span,
                )
            )
        else:
            constructs.append(
                SkwConstruct(
                    command=frame.command,
                    heading=frame.heading,
                    line=frame.line,
                    label=frame.label,
                    address=frame.address,
                    froms=frame.froms,
                    dev_froms=frame.dev_froms,
                    cites=frame.cites,
                    decl_span=frame.decl_span,
                    body_span=span,
                    body=body,
                )
            )
        parent = stack[-1] if stack else None
        if parent is not None and frame.command in ("when", "then"):
            parent.children.append(frame.command)
            parent.command = "router"
            parent.needs_end = True

    def close_top(end_index: int) -> None:
        frame = stack.pop()
        emit_frame(frame, end_index)

    def peer_close_rows(end_index: int) -> None:
        while stack and stack[-1].command in ("when", "then"):
            close_top(end_index)

    def check_router_children(frame: _Frame) -> None:
        expected = "when"
        for child in frame.children:
            if child != expected:
                findings.append(
                    SkwFinding(
                        frame.line,
                        f"router rows must alternate when/then: found '{child}' "
                        f"where '{expected}' was expected",
                    )
                )
                return
            expected = "then" if expected == "when" else "when"
        if expected == "then":
            findings.append(
                SkwFinding(frame.line, "router ends with a 'when' that has no 'then'")
            )

    def force_close(end_index: int, where: str) -> None:
        while stack:
            frame = stack[-1]
            if frame.needs_end:
                findings.append(
                    SkwFinding(
                        frame.line,
                        f"'{frame.command}' left open at {where} "
                        f"(a content block closes explicitly with $kw. end)",
                    )
                )
            close_top(end_index)
            if frame.command == "router":
                check_router_children(frame)

    index = 0
    in_fence = False
    fence_line = 0
    while index < len(lines):
        line = lines[index]
        if carrier.is_fence(line):
            in_fence = not in_fence
            fence_line = index + 1
            index += 1
            continue
        if in_fence:
            index += 1
            continue

        boundary = carrier.boundary_name(line)
        if boundary is not None:
            force_close(index, f"{carrier.boundary_label} {boundary!r}")
            heading = boundary
            index += 1
            continue

        close_content = carrier.close_content(line)
        if close_content is not None:
            content = close_content.strip()
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
                if frame.command == "router":
                    check_router_children(frame)
            machinery_spans.append((index, index + 1))
            index += 1
            continue

        if carrier.open_content(line) is None:
            flag_content = carrier.flag_content(line)
            if flag_content is not None:
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"stray flag line outside a declaration: {flag_content.strip()!r}",
                    )
                )
                machinery_spans.append((index, index + 1))
            index += 1
            continue

        decl_end, address, label, flags = _read_block(lines, index, findings, carrier)

        if address is not None:
            if address in seen_addresses:
                findings.append(SkwFinding(index + 1, f"duplicate address: {address}"))
            seen_addresses.add(address)

        flag_names = [name for name, _ in flags]
        bindings = [name for name in flag_names if name in BINDING_FLAGS]
        roles = [name for name in flag_names if name in ROLE_FLAGS]
        froms = tuple(value for name, value in flags if name == "from")
        dev_froms = tuple(value for name, value in flags if name == "dev-from")
        cites = tuple(value for name, value in flags if name == "cite")
        unlock_surface_values = [
            value for name, value in flags if name == "unlock-surface"
        ]
        unlock_surface = bool(unlock_surface_values)
        context_assembly_values = [
            value for name, value in flags if name == "context-assembly"
        ]
        context_assembly = bool(context_assembly_values)
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
            if not stack or stack[-1].command in ("when", "then"):
                # rows peer-close, so a sibling row is legal; only a top-level
                # row (no parent block) is orphaned
                if not stack:
                    findings.append(SkwFinding(index + 1, f"'{role}' outside a router"))
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
        if len(unlock_surface_values) > 1:
            findings.append(
                SkwFinding(index + 1, "--unlock-surface may appear only once")
            )
        if any(unlock_surface_values):
            findings.append(SkwFinding(index + 1, "--unlock-surface takes no value"))
        if unlock_surface and address is None:
            findings.append(
                SkwFinding(index + 1, "--unlock-surface requires an explicit address")
            )
        if unlock_surface and len(froms) != 1:
            findings.append(
                SkwFinding(index + 1, "--unlock-surface requires exactly one --from")
            )
        if unlock_surface and (verb is not None or role is not None):
            findings.append(
                SkwFinding(
                    index + 1,
                    "--unlock-surface cannot carry a binding or router role",
                )
            )
        if len(context_assembly_values) > 1:
            findings.append(
                SkwFinding(index + 1, "--context-assembly may appear only once")
            )
        if any(context_assembly_values):
            findings.append(SkwFinding(index + 1, "--context-assembly takes no value"))
        if context_assembly and index != 0:
            findings.append(
                SkwFinding(
                    index + 1,
                    "--context-assembly must be declared at the file point (line 1)",
                )
            )
        if context_assembly and not froms:
            findings.append(
                SkwFinding(
                    index + 1, "--context-assembly requires at least one --from"
                )
            )
        if context_assembly and (address is not None or verb is not None or role is not None):
            findings.append(
                SkwFinding(
                    index + 1,
                    "--context-assembly is a self-closing file declaration",
                )
            )

        # closure by role: a recipe or a content span (a flag-less block, incl.
        # a router parent) owns its `end`; a row peer-closes; an annotation
        # block — one carrying only `--from`/`--note`/`--supp` — self-closes at
        # its declaration, and following text stays surface.
        annotation_only = command == "text" and (
            bool(froms)
            or bool(dev_froms)
            or bool(cites)
            or bool(frame_notes)
            or verb == "pointer"
            or unlock_surface
            or context_assembly
        )
        needs_end = command in RECIPE_BINDINGS or (
            command == "text" and not annotation_only
        )

        # nesting guard: a construct may only nest as a when/then row inside a
        # router-capable parent; a plain block may not nest inside a recipe body
        if stack and stack[-1].verb in RECIPE_BINDINGS and role is None:
            findings.append(
                SkwFinding(
                    index + 1,
                    f"blocks may not nest inside a '{stack[-1].command}' body",
                )
            )

        frame = _Frame(
            command=command,
            verb=verb if verb in RECIPE_BINDINGS else None,
            heading=heading,
            line=index + 1,
            label=label,
            address=address,
            decl_span=(index, decl_end),
            body_start=decl_end,
            froms=froms,
            dev_froms=dev_froms,
            cites=cites,
            unlock_surface=unlock_surface,
            context_assembly=context_assembly,
            intent=" ".join(intent_parts) if intent_parts else None,
            notes=frame_notes,
            needs_end=needs_end,
        )

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


def parse_skw_source(text: str) -> SkwSource:
    """Parse a markdown `.skw.md` source (the skw-skills backend carrier)."""
    return _parse_source(text, MARKDOWN_CARRIER)


def parse_skw_code(text: str) -> SkwSource:
    """Parse a code source carrying skw machinery in `# $kw:` comments
    (the skw-code backend carrier, carrier B)."""
    return _parse_source(text, CODE_CARRIER)


__all__ = [
    "BINDING_FLAGS",
    "BOOLEAN_FLAGS",
    "CODE_CARRIER",
    "KNOWN_FLAGS",
    "MARKDOWN_CARRIER",
    "RECIPE_BINDINGS",
    "ROLE_FLAGS",
    "VALUE_FLAGS",
    "Carrier",
    "SkwConstruct",
    "SkwDependency",
    "SkwFinding",
    "SkwNote",
    "SkwRecipe",
    "SkwSource",
    "parse_skw_code",
    "parse_skw_source",
    "recipe_key",
]
