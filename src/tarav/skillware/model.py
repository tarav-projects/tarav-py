# $kw: ^skw-model --from Skw.Language --from Closure.Parser --from Floor.Model --note [DF] the shared skw parser consumes a host-independent carrier model ^c20260722-24u
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
`--context-loading-path` declares one normal runtime loading path for the
current file,
`--reachable-from` asserts that some typed loading path reaches the current
file from a named runtime file,
`--note` is a typed+anchored documentation line, `--supp` the block's own
touched lines, `--unlock-surface` marks a context surface represented by an
unlock registry, `--intent` derivation context, `--cont` a generic
continuation of the previous flag, and `--to` names a routed destination.
`Routing.Table`s and their addressed `Batchy.Router.Row` annotations use
`--routing-table`, `--router-row`, and `--routing-view`; legacy positional
`--when` / `--then` router blocks remain parseable while packages migrate.

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
from pathlib import PurePosixPath

from tarav.index_model.label import split_trailing_address

from .surface_model import SkwSurfaceLine, SkwSurfaceModel

RECIPE_BINDINGS = ("derived", "copy")
BINDING_FLAGS = ("derived", "copy", "pointer")
ROLE_FLAGS = ("when", "then")
ROUTING_VALUE_FLAGS = (
    "routing-view",
    "table",
    "select",
    "flag",
    "alias",
    "match",
    "default",
    "load",
)
CONTEXT_LOADING_VALUE_FLAGS = ("step", "loading-dep", "reachable-from")
VALUE_FLAGS = (
    (
        "from",
        "dev-from",
        "cite",
        "intent",
        "to",
        "note",
        "supp",
        "cont",
    )
    + ROUTING_VALUE_FLAGS
    + CONTEXT_LOADING_VALUE_FLAGS
)
ROUTING_BOOLEAN_FLAGS = ("routing-table", "router-row")
CONTEXT_LOADING_BOOLEAN_FLAGS = ("context-loading-path",)
BOOLEAN_FLAGS = (
    (
        "unlock-surface",
        "context-assembly",
    )
    + ROUTING_BOOLEAN_FLAGS
    + CONTEXT_LOADING_BOOLEAN_FLAGS
)
KNOWN_FLAGS = BINDING_FLAGS + ROLE_FLAGS + VALUE_FLAGS + BOOLEAN_FLAGS

_ADDRESS_RE = re.compile(r"^[#^@]?[A-Za-z0-9_./#:^-]+$")
_FLAG_RE = re.compile(rf"(?:^|\s)--({'|'.join(KNOWN_FLAGS)})(?=\s|$)")
_NOTE_TYPE_RE = re.compile(r"^\[([A-Z]{2})\]\s*(.*)$")
_RUNTIME_PACKAGE_RE = re.compile(r"^@<([a-z0-9][a-z0-9._-]*)>/(.+)$")


def _valid_runtime_file_locator(locator: str) -> bool:
    tail = locator
    package = _RUNTIME_PACKAGE_RE.fullmatch(locator)
    if package is not None:
        tail = package.group(2)
    elif locator.startswith("@<"):
        return False
    if not tail or "\\" in tail or "^" in tail or "#" in tail:
        return False
    path = PurePosixPath(tail)
    return not (
        path.is_absolute()
        or path == PurePosixPath(".")
        or ".." in path.parts
        or path.parts[0] in {".skw", ".skillware"}
    )


@dataclass(frozen=True)
class SkwFinding:
    line: int
    message: str


@dataclass(frozen=True)
class SkwNote:
    """A `--note` (documentation) or `--supp` (own touched line) — a typed,
    anchored `Index.Line` carried by an annotation block."""

    flag: str
    type: str | None
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
    loading_deps: tuple[str, ...]
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
    loading_deps: tuple[str, ...]
    decl_span: tuple[int, int]
    body_span: tuple[int, int]
    body: tuple[str, ...]


@dataclass(frozen=True)
class SkwDependency:
    froms: tuple[str, ...]
    dev_froms: tuple[str, ...]
    cites: tuple[str, ...]
    loading_deps: tuple[str, ...]
    unlock_surface: bool
    context_assembly: bool
    heading: str | None
    line: int
    label: str | None
    address: str | None
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwRoutingTable:
    address: str
    line: int
    selection: str
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwRouterRow:
    address: str
    line: int
    table: str
    flags: tuple[str, ...]
    aliases: tuple[str, ...]
    match: str
    defaults: tuple[str, ...]
    destinations: tuple[str, ...]
    loads: tuple[str, ...]
    when: str | None
    then: str | None
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwRoutingView:
    address: str
    line: int
    table: str
    kind: str
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwContextLoadingPath:
    address: str
    line: int
    steps: tuple[str, ...]
    decl_span: tuple[int, int]


@dataclass(frozen=True)
class SkwContextLoadingDependency:
    locator: str
    line: int
    address: str | None


@dataclass(frozen=True)
class SkwContextReachability:
    locator: str
    line: int
    address: str


@dataclass(frozen=True)
class SkwSource:
    lines: tuple[str, ...]
    recipes: tuple[SkwRecipe, ...]
    constructs: tuple[SkwConstruct, ...]
    dependencies: tuple[SkwDependency, ...]
    routing_tables: tuple[SkwRoutingTable, ...]
    router_rows: tuple[SkwRouterRow, ...]
    routing_views: tuple[SkwRoutingView, ...]
    context_loading_paths: tuple[SkwContextLoadingPath, ...]
    context_loading_dependencies: tuple[SkwContextLoadingDependency, ...]
    context_reachabilities: tuple[SkwContextReachability, ...]
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
    lines: tuple[SkwSurfaceLine, ...],
    start: int,
    findings: list[SkwFinding],
) -> tuple[int, str | None, str | None, list[tuple[str, str]]]:
    """Read a ``$kw:`` open line plus contiguous ``--flag`` belonging lines.
    Returns (end_exclusive, address, label, flags). The address is the first
    non-flag token on the open line; ``^label`` addresses also yield a bare
    label for lock-key continuity. Carrier-agnostic: the carrier strips its own
    syntax before this sees machinery content."""
    open_content = lines[start].open_content
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
        flag_content = lines[index].flag_content
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
    text, anchor = split_trailing_address(text)
    text = text.strip()
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
    loading_deps: tuple[str, ...]
    unlock_surface: bool
    context_assembly: bool
    intent: str | None
    notes: list[SkwNote]
    needs_end: bool
    children: list[str] = field(default_factory=list)


def _parse_source(
    surface: SkwSurfaceModel,
) -> SkwSource:
    lines = [line.text for line in surface.lines]
    recipes: list[SkwRecipe] = []
    constructs: list[SkwConstruct] = []
    dependencies: list[SkwDependency] = []
    routing_tables: list[SkwRoutingTable] = []
    router_rows: list[SkwRouterRow] = []
    routing_views: list[SkwRoutingView] = []
    context_loading_paths: list[SkwContextLoadingPath] = []
    context_loading_dependencies: list[SkwContextLoadingDependency] = []
    context_reachabilities: list[SkwContextReachability] = []
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
                    loading_deps=frame.loading_deps,
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
            and (frame.froms or frame.dev_froms or frame.cites or frame.loading_deps)
            and not _has_content(body)
        ):
            dependencies.append(
                SkwDependency(
                    froms=frame.froms,
                    dev_froms=frame.dev_froms,
                    cites=frame.cites,
                    loading_deps=frame.loading_deps,
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
                    loading_deps=frame.loading_deps,
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
    file_point_open = True
    while index < len(lines):
        line = lines[index]
        surface_line = surface.lines[index]
        if surface_line.fence:
            if line.strip():
                file_point_open = False
            in_fence = not in_fence
            fence_line = index + 1
            index += 1
            continue
        if in_fence:
            index += 1
            continue

        boundary = surface_line.boundary_name
        if boundary is not None:
            file_point_open = False
            force_close(index, f"{surface.boundary_label} {boundary!r}")
            heading = boundary
            index += 1
            continue

        close_content = surface_line.close_content
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

        open_content = surface_line.open_content
        if open_content is None:
            flag_content = surface_line.flag_content
            if flag_content is not None:
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"stray flag line outside a declaration: {flag_content.strip()!r}",
                    )
                )
                machinery_spans.append((index, index + 1))
            elif line.strip():
                file_point_open = False
            index += 1
            continue

        declaration_at_file_point = file_point_open
        decl_end, address, label, flags = _read_block(
            surface.lines,
            index,
            findings,
        )

        if address is not None:
            if address in seen_addresses:
                findings.append(SkwFinding(index + 1, f"duplicate address: {address}"))
            seen_addresses.add(address)

        flag_names = [name for name, _ in flags]
        bindings = [name for name in flag_names if name in BINDING_FLAGS]
        routing_table_values = [
            value for name, value in flags if name == "routing-table"
        ]
        router_row_values = [value for name, value in flags if name == "router-row"]
        routing_view_values = [value for name, value in flags if name == "routing-view"]
        context_loading_path_values = [
            value for name, value in flags if name == "context-loading-path"
        ]
        is_routing_table = bool(routing_table_values)
        is_router_row = bool(router_row_values)
        is_routing_view = bool(routing_view_values)
        is_context_loading_path = bool(context_loading_path_values)
        routing_kinds = sum((is_routing_table, is_router_row, is_routing_view))
        declaration_kinds = routing_kinds + int(is_context_loading_path)
        roles = (
            [] if is_router_row else [name for name in flag_names if name in ROLE_FLAGS]
        )
        froms = tuple(value for name, value in flags if name == "from")
        dev_froms = tuple(value for name, value in flags if name == "dev-from")
        cites = tuple(value for name, value in flags if name == "cite")
        loading_deps = tuple(
            value for name, value in flags if name == "loading-dep" and value
        )
        if any(name == "loading-dep" and not value for name, value in flags):
            findings.append(SkwFinding(index + 1, "--loading-dep requires a locator"))
        context_loading_dependencies.extend(
            SkwContextLoadingDependency(
                locator=value,
                line=index + 1,
                address=address,
            )
            for value in loading_deps
        )
        has_reachable_from_flag = any(name == "reachable-from" for name, _ in flags)
        reachable_froms = tuple(
            value for name, value in flags if name == "reachable-from" and value
        )
        if any(name == "reachable-from" and not value for name, value in flags):
            findings.append(
                SkwFinding(index + 1, "--reachable-from requires a runtime file")
            )
        if reachable_froms and address is None:
            findings.append(
                SkwFinding(index + 1, "--reachable-from requires an explicit address")
            )
        if reachable_froms and not declaration_at_file_point:
            findings.append(
                SkwFinding(
                    index + 1,
                    "--reachable-from must be declared at the file point",
                )
            )
        for locator in reachable_froms:
            if not _valid_runtime_file_locator(locator):
                findings.append(
                    SkwFinding(
                        index + 1,
                        f"--reachable-from must name a runtime file: {locator!r}",
                    )
                )
            elif address is not None:
                context_reachabilities.append(
                    SkwContextReachability(
                        locator=locator,
                        line=index + 1,
                        address=address,
                    )
                )
        unlock_surface_values = [
            value for name, value in flags if name == "unlock-surface"
        ]
        unlock_surface = bool(unlock_surface_values)
        context_assembly_values = [
            value for name, value in flags if name == "context-assembly"
        ]
        context_assembly = bool(context_assembly_values)

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
        if declaration_kinds > 1:
            findings.append(
                SkwFinding(
                    index + 1,
                    "a declaration cannot carry several structural declaration kinds",
                )
            )
        if routing_kinds and bindings:
            findings.append(
                SkwFinding(index + 1, "routing annotations cannot carry a binding flag")
            )
        if is_context_loading_path and any(
            name
            not in {
                "context-loading-path",
                "step",
                "loading-dep",
                "reachable-from",
            }
            for name in flag_names
        ):
            findings.append(
                SkwFinding(
                    index + 1,
                    "--context-loading-path may carry only repeatable --step and "
                    "--loading-dep fields",
                )
            )

        role = roles[0] if roles else None
        verb = bindings[0] if bindings else None

        if is_routing_table:
            command = "routing-table"
        elif is_router_row:
            command = "router-row"
        elif is_routing_view:
            command = "routing-view"
        elif is_context_loading_path:
            command = "context-loading-path"
        elif role is not None:
            if not stack or stack[-1].command in ("when", "then"):
                if not stack:
                    findings.append(SkwFinding(index + 1, f"'{role}' outside a router"))
                else:
                    peer_close_rows(index)
            command = role
        elif verb in RECIPE_BINDINGS:
            command = verb
        else:
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
                SkwFinding(index + 1, "--context-assembly requires at least one --from")
            )
        if context_assembly and (
            address is not None or verb is not None or role is not None
        ):
            findings.append(
                SkwFinding(
                    index + 1,
                    "--context-assembly is a self-closing file declaration",
                )
            )

        if is_context_loading_path:
            steps = tuple(value for name, value in flags if name == "step" and value)
            if any(context_loading_path_values):
                findings.append(
                    SkwFinding(index + 1, "--context-loading-path takes no value")
                )
            if address is None:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--context-loading-path requires an explicit address",
                    )
                )
            if not declaration_at_file_point:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--context-loading-path must be declared at the file point",
                    )
                )
            if not steps:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--context-loading-path requires at least one --step",
                    )
                )
            if steps and "SKILL.md" not in steps:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--context-loading-path must contain SKILL.md",
                    )
                )
            if len(steps) != len(set(steps)):
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--context-loading-path cannot repeat a --step",
                    )
                )
            if any(step == ".skw/AGENTS.md" for step in steps):
                findings.append(
                    SkwFinding(
                        index + 1,
                        ".skw/AGENTS.md is builder guidance, not consumer context",
                    )
                )
            if address is not None and steps:
                context_loading_paths.append(
                    SkwContextLoadingPath(
                        address=address,
                        line=index + 1,
                        steps=steps,
                        decl_span=(index, decl_end),
                    )
                )

        if is_routing_table:
            selections = [value for name, value in flags if name == "select"]
            if any(routing_table_values):
                findings.append(SkwFinding(index + 1, "--routing-table takes no value"))
            if address is None:
                findings.append(
                    SkwFinding(
                        index + 1, "--routing-table requires an explicit address"
                    )
                )
            if len(selections) != 1 or selections[0] not in {
                "zero-or-one",
                "one",
                "many",
            }:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--routing-table requires one --select value: "
                        "zero-or-one, one, or many",
                    )
                )
            if address is not None and len(selections) == 1:
                routing_tables.append(
                    SkwRoutingTable(
                        address=address,
                        line=index + 1,
                        selection=selections[0],
                        decl_span=(index, decl_end),
                    )
                )

        if is_router_row:
            table_values = [value for name, value in flags if name == "table"]
            explicit_flags = tuple(value for name, value in flags if name == "flag")
            aliases = tuple(value for name, value in flags if name == "alias")
            matches = [value for name, value in flags if name == "match"]
            defaults = tuple(value for name, value in flags if name == "default")
            destinations = tuple(value for name, value in flags if name == "to")
            loads = tuple(value for name, value in flags if name == "load")
            whens = [value for name, value in flags if name == "when"]
            thens = [value for name, value in flags if name == "then"]
            if any(router_row_values):
                findings.append(SkwFinding(index + 1, "--router-row takes no value"))
            if address is None:
                findings.append(
                    SkwFinding(index + 1, "--router-row requires an explicit address")
                )
            if len(table_values) != 1 or not table_values[0]:
                findings.append(
                    SkwFinding(index + 1, "--router-row requires exactly one --table")
                )
            if len(matches) != 1 or matches[0] not in {
                "explicit",
                "semantic",
                "explicit-or-semantic",
            }:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--router-row requires one --match value: explicit, semantic, "
                        "or explicit-or-semantic",
                    )
                )
            if aliases and not explicit_flags:
                findings.append(
                    SkwFinding(index + 1, "--alias requires at least one --flag")
                )
            if len(whens) > 1:
                findings.append(SkwFinding(index + 1, "--when may appear only once"))
            if len(thens) > 1:
                findings.append(SkwFinding(index + 1, "--then may appear only once"))
            if matches and matches[0] == "explicit" and not explicit_flags:
                findings.append(
                    SkwFinding(index + 1, "explicit router row requires --flag")
                )
            if (
                matches
                and matches[0]
                in {
                    "semantic",
                    "explicit-or-semantic",
                }
                and not any(whens)
            ):
                findings.append(
                    SkwFinding(index + 1, "semantic router row requires --when")
                )
            if matches and matches[0] == "explicit-or-semantic" and not explicit_flags:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "explicit-or-semantic router row requires --flag",
                    )
                )
            if not destinations and not loads and not any(thens):
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--router-row requires --to, --load, or --then",
                    )
                )
            if address is not None and len(table_values) == 1 and len(matches) == 1:
                router_rows.append(
                    SkwRouterRow(
                        address=address,
                        line=index + 1,
                        table=table_values[0],
                        flags=explicit_flags,
                        aliases=aliases,
                        match=matches[0],
                        defaults=defaults,
                        destinations=destinations,
                        loads=loads,
                        when=whens[0] if whens else None,
                        then=thens[0] if thens else None,
                        decl_span=(index, decl_end),
                    )
                )

        if is_routing_view:
            table_values = [value for name, value in flags if name == "table"]
            if address is None:
                findings.append(
                    SkwFinding(index + 1, "--routing-view requires an explicit address")
                )
            if len(routing_view_values) != 1 or routing_view_values[0] not in {
                "calls",
                "modules",
                "full",
            }:
                findings.append(
                    SkwFinding(
                        index + 1,
                        "--routing-view requires one value: calls, modules, or full",
                    )
                )
            if len(table_values) != 1 or not table_values[0]:
                findings.append(
                    SkwFinding(index + 1, "--routing-view requires exactly one --table")
                )
            if (
                address is not None
                and len(routing_view_values) == 1
                and len(table_values) == 1
            ):
                routing_views.append(
                    SkwRoutingView(
                        address=address,
                        line=index + 1,
                        table=table_values[0],
                        kind=routing_view_values[0],
                        decl_span=(index, decl_end),
                    )
                )

        annotation_only = declaration_kinds > 0 or (
            command == "text"
            and (
                bool(froms)
                or bool(dev_froms)
                or bool(cites)
                or bool(loading_deps)
                or has_reachable_from_flag
                or bool(frame_notes)
                or verb == "pointer"
                or unlock_surface
                or context_assembly
            )
        )
        needs_end = command in RECIPE_BINDINGS or (
            command == "text" and not annotation_only
        )

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
            loading_deps=loading_deps,
            unlock_surface=unlock_surface,
            context_assembly=context_assembly,
            intent=" ".join(intent_parts) if intent_parts else None,
            notes=frame_notes,
            needs_end=needs_end,
        )

        machinery_spans.append((index, decl_end))
        if annotation_only:
            emit_frame(frame, decl_end)
        else:
            stack.append(frame)
        index = decl_end

    force_close(len(lines), "EOF")
    table_addresses = {table.address for table in routing_tables}
    route_keys: dict[tuple[str, str], SkwRouterRow] = {}
    for row in router_rows:
        if row.table not in table_addresses:
            findings.append(
                SkwFinding(
                    row.line, f"router row references unknown table: {row.table}"
                )
            )
        for key in (*row.flags, *row.aliases):
            prior = route_keys.setdefault((row.table, key), row)
            if prior is not row:
                findings.append(
                    SkwFinding(
                        row.line,
                        f"duplicate explicit route key {key!r} in table {row.table}; "
                        f"first declared by {prior.address}",
                    )
                )
    for view in routing_views:
        if view.table not in table_addresses:
            findings.append(
                SkwFinding(
                    view.line, f"routing view references unknown table: {view.table}"
                )
            )
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
        routing_tables=tuple(routing_tables),
        router_rows=tuple(router_rows),
        routing_views=tuple(routing_views),
        context_loading_paths=tuple(context_loading_paths),
        context_loading_dependencies=tuple(context_loading_dependencies),
        context_reachabilities=tuple(context_reachabilities),
        notes=tuple(notes),
        machinery_spans=tuple(machinery_spans),
        findings=tuple(findings),
    )


def parse_skw_source(text: str) -> SkwSource:
    """Parse a markdown `.skw.md` source (the skw-skills backend carrier)."""
    from tarav.surfaces.markdown import normalize_markdown

    from .adapters.markdown import adapt_markdown_skw

    return parse_skw_model(adapt_markdown_skw(normalize_markdown(text)))


def parse_skw_code(
    text: str,
    *,
    machinery_lines: frozenset[int] | None = None,
) -> SkwSource:
    """Parse a code source carrying skw machinery in `# $kw:` comments
    (the skw-code backend carrier, carrier B)."""
    from tarav.surfaces.python import normalize_python

    from .adapters.python import adapt_python_skw

    return parse_skw_model(
        adapt_python_skw(
            normalize_python(text),
            machinery_lines=machinery_lines,
        )
    )


def parse_skw_model(surface: SkwSurfaceModel) -> SkwSource:
    """Parse a host-independent Skillware carrier model."""

    return _parse_source(surface)


__all__ = [
    "BINDING_FLAGS",
    "BOOLEAN_FLAGS",
    "KNOWN_FLAGS",
    "RECIPE_BINDINGS",
    "ROLE_FLAGS",
    "ROUTING_BOOLEAN_FLAGS",
    "ROUTING_VALUE_FLAGS",
    "CONTEXT_LOADING_BOOLEAN_FLAGS",
    "CONTEXT_LOADING_VALUE_FLAGS",
    "VALUE_FLAGS",
    "SkwConstruct",
    "SkwContextLoadingDependency",
    "SkwContextLoadingPath",
    "SkwContextReachability",
    "SkwDependency",
    "SkwFinding",
    "SkwNote",
    "SkwRecipe",
    "SkwRouterRow",
    "SkwRoutingTable",
    "SkwRoutingView",
    "SkwSource",
    "parse_skw_code",
    "parse_skw_model",
    "parse_skw_source",
    "recipe_key",
]
