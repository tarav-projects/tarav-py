# $kw: --from POI.Linter --note [CT] agents edit surfaces with general primitives; the linter checks conformance
# --from Convergent.Justification --note [DC] Check.default_on is held on one reason — a check may ship off when it is expensive or situational, though no catalog row does yet
"""The tarav index linter.

This is where the conformance intelligence lives. Agents edit Markdown and SKW surfaces
directly; the capture path reconciles their grounded lines into records. Afterwards the
linter runs as many checks as it can and reports POIs.

Shaped after `tarav index linter`: a **check catalog** with selectors (`--check`, `--skip`,
`--list-checks`), two tiers, and per-check default state. Growing the system means adding a
row here, not adding a command.

- `structural` — the surface could not be read; later checks cannot run meaningfully.
- `reportable` — a finding that accumulates.

The bar every retained line must reach is **typed** and **User.Touched grounded**. A line
below the bar is work not yet done, not an error to reject; the Index is a `WIP.Surface`, so
divergence is a signal to work and the linter never says which side is right.

A POI can be accepted with `bless` — the acceptance is recorded per finding, so silencing one
known case never weakens the check for every other.

Three rules govern how checks are written here, and they all point the same way.

**`DUMB.CODE.IS.BETTER`.** A check saves the agent computable operations; it never does the
semantic work. Rules may overdetect, because an agent is on the other side and a false
positive is code successfully handing something up the ladder. Asking an agent to find the
error instead costs a semantic evaluation of *everything* — establishing that something is
fine is as expensive as finding it broken — and still loses the cross-item relations a check
computes in one pass.

**No semantic value in the signal.** A finding names the computation and reports the values
it compared. It does not describe what that means. Agents double-check from first principles,
and they can only do that from operands rather than from a sentence about the operands.

**The code is the documentation.** A prose description of a check is a stored copy of a
computable fact with nothing asserting it still holds — `Untyped.Agent.State` about the
checker. So a finding carries `file:line`, the docstring says *why* the constraint exists,
the body says *what* is computed, and nothing says what is computed twice. That makes
readability of a check body a contract rather than a preference.
"""

from __future__ import annotations

import json
import subprocess
from time import perf_counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from tarav.index_model.nodes import BlockHeading, MetaLine
from tarav.index_model.parser import parse_depot

from .chatlas import ARCHIVE_NAME as CHAT_ARCHIVE, ChatError, load_session
from .config import Geography, TaravIndexError
from .gates import GateCheck, GateRef, GateVerdict, verify_gate
from .record.model import EquivalenceKind, LineRecord, SupportRef
from .record.store import IndexStore
from .scope import resolve_scope_surface
from .standing import (
    Standing,
    Trace,
    build_traces,
    lines_on_head_surfaces,
    standings,
)
from .surfaces import (
    Homes,
    SurfaceLine,
    discover_surfaces,
    load_homes,
    read_surface,
    resolve_surface_path,
    scope_home,
)
from .verdict import Evaluator, GateResult, Status


class Tier(StrEnum):
    STRUCTURAL = "structural"
    REPORTABLE = "reportable"


class LintError(TaravIndexError):
    """Raised when the lint run itself cannot proceed."""


@dataclass(frozen=True, slots=True)
class Finding:
    """One typed signal of a well-declared computation.

    Signals attention; prescribes no remedy; carries no reading of what it means. `operands`
    holds the values the check compared, so the agent re-derives the semantics from the
    evidence instead of from a sentence about the evidence.

    `source` is the pointer that replaces a description — computed from the check function,
    never written down, because a stored pointer would be the same defect one level up.
    """

    poi_class: str
    subject: str
    operands: dict[str, str] = field(default_factory=dict)
    status: Status = Status.FAILED
    evaluator: Evaluator = Evaluator.CODE
    surface: str | None = None
    tier: Tier = Tier.REPORTABLE
    source: str | None = None

    @property
    def identity(self) -> str:
        """Stable id for blessing.

        Over the class, subject and surface only. Operands may change as the values drift
        without the finding becoming a different one — otherwise a blessing would evaporate
        the moment the thing it accepted moved slightly.
        """

        canonical = json.dumps(
            [self.poi_class, self.subject, self.surface or ""],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def render(self) -> str:
        where = f"  [{self.surface}]" if self.surface else ""
        operands = "  ".join(f"{k}={v!r}" for k, v in self.operands.items())
        return f"{self.poi_class}  {self.subject}  {operands}{where}"

    @property
    def blocked(self) -> bool:
        return self.status is Status.BLOCKED


@dataclass(slots=True)
class LintContext:
    """Everything the checks read, resolved once per run."""

    geo: Geography
    root: Path
    store: IndexStore
    homes: Homes = field(default_factory=Homes)
    records: list[LineRecord] = field(default_factory=list)
    standing: dict[str, Standing] = field(default_factory=dict)
    surface_lines: dict[str, list[SurfaceLine]] = field(default_factory=dict)
    head_lines: set[str] = field(default_factory=set)
    subjects: frozenset[str] | None = None
    """The record ids under examination, or `None` for the whole corpus.

    It narrows what is *examined*, never what is *known*: `records`, `by_label`, `traces`
    and `standing` stay whole, because a check that must consult a record's trace siblings
    or its label neighbours is not asking about the selection. Narrowing the context
    instead would make a targeted run quietly answer a different question than a full one.
    """

    def selected_records(self) -> list[LineRecord]:
        """The records this run is examining, one at a time.

        Which iterator a check body uses is also how its scope is declared -- see
        `Check.record_scoped`. A check that reads `records` is consulting context; a check
        that iterates this is examining subjects, and is the kind a point lookup can run.
        """

        if self.subjects is None:
            return self.records
        return [record for record in self.records if record.id in self.subjects]

    def is_selected(self, record_id: str) -> bool:
        """Whether this record is under examination.

        For the checks that reach records sideways -- through a surface line's label or a
        trace's members -- where iterating the selection directly would mean not walking
        the structure the check is about.
        """

        return self.subjects is None or record_id in self.subjects

    def head_surface_lines(self) -> Iterator[tuple[str, SurfaceLine]]:
        """Lines sitting on the structurally discovered live surface cut."""

        for surface, lines in self.surface_lines.items():
            for line in lines:
                yield surface, line

    def by_label(self) -> dict[str, LineRecord]:
        return {r.line.label: r for r in self.records if r.line.label}

    def traces(self):
        return build_traces(self.records)

    def all_surface_lines(self) -> Iterator[tuple[str, SurfaceLine]]:
        for surface, lines in self.surface_lines.items():
            for line in lines:
                yield surface, line


def _reaches_selected_records(fn: CheckFn, seen: frozenset[str] = frozenset()) -> bool:
    """Whether `fn`, or a module-local function it calls, iterates the selected records.

    Static and local: it walks names this module defines, so it cannot be fooled into
    following something imported, and `seen` keeps a mutually recursive pair terminating.
    """

    code = getattr(fn, "__code__", None)
    if code is None:  # a class or builtin reached through a call name
        return False
    names = code.co_names
    if "selected_records" in names or "is_selected" in names:
        return True
    here = globals()
    for name in names:
        if name in seen:
            continue
        candidate = here.get(name)
        if callable(candidate) and getattr(candidate, "__module__", None) == __name__:
            if _reaches_selected_records(candidate, seen | {name}):
                return True
    return False


def _referenced_poi_classes(
    fn: CheckFn, seen: frozenset[str] = frozenset()
) -> frozenset[str]:
    """POI class identities named by a check and its module-local helpers."""

    code = getattr(fn, "__code__", None)
    if code is None:
        return frozenset()
    found = {
        value
        for value in code.co_consts
        if isinstance(value, str) and value.startswith("Index.Linter/")
    }
    here = globals()
    for name in code.co_names:
        if name in seen:
            continue
        candidate = here.get(name)
        if callable(candidate) and getattr(candidate, "__module__", None) == __name__:
            found.update(
                _referenced_poi_classes(candidate, seen | {name})  # type: ignore[arg-type]
            )
    return frozenset(found)


CheckFn = Callable[[LintContext], list[Finding]]
GateFn = Callable[[LintContext], GateResult]


@dataclass(frozen=True, slots=True)
class Check:
    """One conformance check.

    There is no ``title``. A prose description of what a check computes is a stored copy of a
    computable fact with nothing asserting it still holds — so the description is the
    implementation, and `source` points at it.

    ``resolutions`` survive precisely because they are *not* derivable from the body: the
    code computes that something fired, never what may legitimately be done about it. A POI
    prescribes no remedy, so these are alternatives to choose between case by case.
    """

    name: str
    tier: Tier
    run: CheckFn
    default_on: bool = True
    resolutions: tuple[str, ...] = ()
    gate: GateFn | None = None
    dev: bool = False
    """Whether this check runs only under `tarav index linter dev`.

    A dev check is an ordinary check on ordinary machinery -- same signature,
    same findings, same verdict. All `dev` changes is *when it is selected*.
    It exists to make a chain runnable before its evidence can exist: a gate
    check that accepts an agent turn as the gate key, so the capture path can
    be exercised without a real user in the loop.
    """
    replaces: str | None = None
    """The check this one stands in for while the dev lane is running.

    A dev check that merely *added* a finding would leave its strict counterpart
    failing, and the run could never go green. Naming the counterpart drops it
    for the duration, so the dev lane reports one verdict per constraint rather
    than two contradictory ones.
    """

    @property
    def record_scoped(self) -> bool:
        """Whether this check examines records one at a time.

        Read off the body rather than stored beside it: a check declares its scope by
        iterating `selected_records()`, and a second declaration in the catalog would be a
        copy of that fact with nothing keeping the two honest. A check that only reads
        `records` for context, or that walks surfaces, traces, or the depot, is not
        answerable for one record and is not offered to a targeted run.

        Followed through module-local helpers, because `gate-verifies` and its dev
        counterpart are two-line wrappers over one shared body -- and reading only the
        wrapper called both of them corpus-scoped, which silently dropped every
        `Gate.Evidence.Invalid` finding from targeted runs against the live corpus.
        """

        return _reaches_selected_records(self.run)

    def can_run(self, ctx: LintContext) -> GateResult:
        """`GateResult`: a precondition the check cannot supply for itself."""

        return self.gate(ctx) if self.gate else GateResult.ok()

    @property
    def poi_classes(self) -> frozenset[str]:
        """Class identities derived from the executable check, never a second registry."""

        return _referenced_poi_classes(self.run)

    @property
    def source(self) -> str:
        """`file:line` of the check body — computed, never written down."""

        code = self.run.__code__
        return f"{Path(code.co_filename).name}:{code.co_firstlineno}"

    @property
    def why(self) -> str:
        """The docstring, which says why the constraint exists. The body says what."""

        return (self.run.__doc__ or "").strip()


# -- checks -------------------------------------------------------------------
# Each returns findings; none mutates anything.


# $kw: Index.Linter/Support.LegacyCoordinate --from POI.Linter
def _support_legacy_coordinate_finding(
    record: LineRecord, ref: SupportRef
) -> Finding:
    return Finding(
        "Index.Linter/Support.LegacyCoordinate",
        record.id,
        {"archive": ref.archive, "coordinate": ref.message_id},
        status=Status.BLOCKED,
    )


# $kw: Index.Linter/Support.Unreachable --from POI.Linter
def _support_unreachable_finding(record: LineRecord, ref: SupportRef) -> Finding:
    return Finding(
        "Index.Linter/Support.Unreachable",
        record.id,
        {"archive": ref.archive, "session": ref.session_id},
        status=Status.BLOCKED,
    )


# $kw: Index.Linter/Support.Mismatch --from POI.Linter
def _support_mismatch_finding(record: LineRecord, ref: SupportRef) -> Finding:
    return Finding(
        "Index.Linter/Support.Mismatch",
        record.id,
        {"message": ref.message_id, "session": ref.session_id},
    )


# $kw: Index.Linter/Support.NotTouched --from POI.Linter
def _support_not_touched_finding(
    record: LineRecord, ref: SupportRef, *, side: str
) -> Finding:
    return Finding(
        "Index.Linter/Support.NotTouched",
        record.id,
        {"message": ref.message_id, "side": side},
    )


# $kw: Index.Linter/Trace.Forked --from POI.Linter
def _trace_forked_finding(trace: Trace) -> Finding:
    heads = trace.heads()
    return Finding(
        "Index.Linter/Trace.Forked",
        trace.id,
        {"heads": str(len(heads)), "ids": " ".join(member.id for member in heads)},
    )


# $kw: Index.Linter/Trace.Cycle --from POI.Linter
def _trace_cycle_finding(trace: Trace) -> Finding:
    return Finding(
        "Index.Linter/Trace.Cycle",
        trace.id,
        {"members": str(len(trace.members)), "heads": "0"},
    )


# $kw: Index.Linter/Equivalence.PredecessorMissing --from POI.Linter
def _equivalence_predecessor_missing_finding(record: LineRecord) -> Finding:
    assert record.equivalence is not None
    return Finding(
        "Index.Linter/Equivalence.PredecessorMissing",
        record.id,
        {"predecessor": record.equivalence.predecessor},
    )


# $kw: Index.Linter/Equivalence.TraceMismatch --from POI.Linter
def _equivalence_trace_mismatch_finding(
    record: LineRecord, predecessor: LineRecord
) -> Finding:
    return Finding(
        "Index.Linter/Equivalence.TraceMismatch",
        record.id,
        {"trace": record.trace, "predecessor_trace": predecessor.trace},
    )


# $kw: Index.Linter/Gate.Evidence.Invalid --from POI.Linter
def _gate_evidence_invalid_finding(
    record: LineRecord, kind: str, gate: GateRef, check: GateCheck
) -> Finding:
    return Finding(
        "Index.Linter/Gate.Evidence.Invalid",
        record.id,
        {"gate": kind, "reason": check.detail, "token": gate.token},
    )


# $kw: Index.Linter/Gate.Evidence.Unavailable --from POI.Linter
def _gate_evidence_unavailable_finding(
    record: LineRecord, kind: str, gate: GateRef, check: GateCheck
) -> Finding:
    return Finding(
        "Index.Linter/Gate.Evidence.Unavailable",
        record.id,
        {
            "gate": kind,
            "archive": gate.archive,
            "session": gate.session_id,
            "reason": check.detail,
        },
        status=Status.BLOCKED,
    )


# $kw: Index.Linter/Blessing.Unevidenced --from POI.Linter
def _blessing_unevidenced_finding(
    finding: Finding, *, check_name: str, source: str
) -> Finding:
    return Finding(
        "Index.Linter/Blessing.Unevidenced",
        finding.identity,
        {"check": check_name, "gate": "invalid"},
        source=source,
    )


# $kw: Index.Linter/Surface.Unreadable --from POI.Linter
def _check_surfaces_readable(ctx: LintContext) -> list[Finding]:
    """Nothing downstream means anything if the surface did not parse, so this runs first."""

    findings: list[Finding] = []
    for surface in discover_surfaces(ctx.geo, ctx.root):
        path = resolve_surface_path(surface, ctx.root)
        try:
            ctx.surface_lines[surface] = read_surface(path, surface)
        except (OSError, ValueError) as exc:
            findings.append(
                Finding(
                    "Index.Linter/Surface.Unreadable",
                    surface,
                    {"error": str(exc)},
                    surface=surface,
                    tier=Tier.STRUCTURAL,
                )
            )
    return findings


# $kw: Index.Linter/Alias.HasBlock --from POI.Linter
def _check_alias_has_no_block(ctx: LintContext) -> list[Finding]:
    """An alias resolves to its canonical block; a second block creates two definitions."""

    findings: list[Finding] = []
    routers = sorted(ctx.root.rglob("000-INDEX.md"))
    for router in routers:
        depot = router.parent
        if any(part.startswith(".") for part in depot.relative_to(ctx.root).parts):
            continue

        documents = list(parse_depot(depot).documents)

        blocks: dict[str, list[tuple[Path, int]]] = {}
        aliases: list[tuple[str, str, Path, int]] = []
        for document in documents:
            if document.path is None:
                continue
            for node in document.nodes:
                if isinstance(node, BlockHeading):
                    name = str(node.parsed.get("path", "")).strip()
                    if name:
                        blocks.setdefault(name, []).append((document.path, node.start_line))
                elif isinstance(node, MetaLine) and node.src.strip().startswith("- aliases:"):
                    canonical = str(node.parsed.get("block_path", "")).strip()
                    for span in node.spans:
                        if span.kind == "concept_cite":
                            alias = str(span.parsed.get("value", "")).strip()
                            if alias and alias != canonical:
                                aliases.append(
                                    (canonical, alias, document.path, node.start_line)
                                )

        for canonical, alias, declaration_path, declaration_line in aliases:
            for block_path, block_line in blocks.get(alias, []):
                surface = str(block_path.relative_to(ctx.root))
                findings.append(
                    Finding(
                        "Index.Linter/Alias.HasBlock",
                        alias,
                        {
                            "canonical": canonical,
                            "declaration": (
                                f"{declaration_path.relative_to(ctx.root)}:{declaration_line}"
                            ),
                            "alias_block": f"{surface}:{block_line}",
                        },
                        surface=surface,
                    )
                )
    return findings


# $kw: Index.Linter/Record.Unreadable --from POI.Linter
def _check_records_loadable(ctx: LintContext) -> list[Finding]:
    """The records are the states being estimated; unreadable, there is nothing to estimate."""

    try:
        ctx.records = list(ctx.store.all())
        ctx.head_lines = lines_on_head_surfaces(ctx.records, ctx.surface_lines)
        ctx.standing = standings(ctx.records, head_lines=ctx.head_lines)
    except (OSError, ValueError, KeyError) as exc:
        return [
            Finding(
                "Index.Linter/Record.Unreadable",
                str(ctx.store.directory),
                {"error": str(exc)},
                tier=Tier.STRUCTURAL,
            )
        ]
    return []


# $kw: Index.Linter/Line.Untyped --from POI.Linter
def _check_line_typed(ctx: LintContext) -> list[Finding]:
    """Without the type there is no type, so nothing else about the line can be checked."""

    return [
        Finding(
            "Index.Linter/Line.Untyped",
            f"{line.scope.label}:{line.lineno}",
            {"body": line.body},
            surface=surface,
        )
        for surface, line in ctx.all_surface_lines()
        if not line.typed
    ]


# $kw: Index.Linter/Line.Unanchored --from POI.Linter
def _check_line_anchored(ctx: LintContext) -> list[Finding]:
    """The label is the line's public id; without it nothing can point at this line."""

    return [
        Finding(
            "Index.Linter/Line.Unanchored",
            f"{line.scope.label}:{line.lineno}",
            {"body": line.body},
            surface=surface,
        )
        for surface, line in ctx.all_surface_lines()
        if line.label is None
    ]


# $kw: Index.Linter/Line.Unrecorded --from POI.Linter
def _check_anchor_has_record(ctx: LintContext) -> list[Finding]:
    """A surface line with no record indexes nothing — it is text that looks indexed."""

    by_label = ctx.by_label()
    return [
        Finding(
            "Index.Linter/Line.Unrecorded",
            line.label,
            {"body": line.body},
            surface=surface,
        )
        for surface, line in ctx.all_surface_lines()
        if line.label is not None and line.label not in by_label
    ]


# $kw: Index.Linter/Anchor.Collision --from POI.Linter
# --note [DF] `Index.Linter/Anchor.Collision` is emitted when one anchor occurs on more than one distinct line projection (`Line.Type + Index.Line.Body`) ^c20260802-240u
# --note [CT] evaluation compares occurrence projections while excluding trailing `Index.Line.Anchor` tokens ^c20260802-241u
# --note [CT] repeated occurrences of one line projection may carry the same anchor without creating a collision ^c20260802-242u
# --note [CT] the instance identifies the anchor, each distinct projection, and every observed location ^c20260802-243u
# --note [DC] resolution restores one agreed line projection for the anchor across its retained occurrences ^c20260802-244u
# --note [FR] the maintainer may correct or remove stale occurrences, coordinate their amendment and refresh the attachment assertion, or assign independent anchors when occurrences represent different line relationships ^c20260802-245u
# --note [CT] an independently anchored projection has an independently validated relationship dossier; equivalent support members may be reused only when they support that projection ^c20260802-246u
# --note [DC] the class is not blessable while occurrence disagreement makes anchor-based line selection ambiguous ^c20260802-247u
# --note [RJ] `Anchory.Linter/Anchor.Duplicate` concerns duplicate registry keys rather than disagreement among Index occurrences ^c20260802-248u
def _check_anchor_collision(ctx: LintContext) -> list[Finding]:
    """One label must name one line, or a pointer stops resolving to one thing."""

    seen: dict[str, tuple[str, str | None, str]] = {}
    findings: list[Finding] = []
    for surface, line in ctx.all_surface_lines():
        label = line.label
        if label is None:
            continue
        previous = seen.get(label)
        projection = (line.line_type, line.body)
        if previous is not None and previous[1:] != projection:
            findings.append(
                Finding(
                    "Index.Linter/Anchor.Collision",
                    label,
                    {
                        "here": line.body,
                        "here_type": str(line.line_type),
                        "there": previous[2],
                        "there_type": str(previous[1]),
                        "other_surface": previous[0],
                    },
                    surface=surface,
                )
            )
        else:
            seen[label] = (surface, line.line_type, line.body)
    return findings


# $kw: Index.Linter/Line.Drift --from POI.Linter
def _check_line_drift(ctx: LintContext) -> list[Finding]:
    """Neither side is presumed right — which one is wrong is the work, not the check's call."""

    by_label = ctx.by_label()
    findings: list[Finding] = []
    for surface, line in ctx.all_surface_lines():
        record = by_label.get(line.label or "")
        if record is None or not ctx.is_selected(record.id):
            continue
        if line.body != record.line.body or line.line_type != record.line.type:
            findings.append(
                Finding(
                    "Index.Linter/Line.Drift",
                    record.id,
                    {
                        "surface": line.body,
                        "record": record.line.body,
                        "surface_type": str(line.line_type),
                        "record_type": str(record.line.type),
                    },
                    surface=surface,
                )
            )
    return findings


# $kw: --from Index.WIP.Surface --note [CT] an ungrounded line is work not yet done rather than a violation, because the index is a WIP.Surface ^c20260818-19u
# $kw: Index.Linter/Line.Ungrounded --from POI.Linter
def _check_record_grounded(ctx: LintContext) -> list[Finding]:
    """The bar. An ungrounded entry carries `Index.Presumption`, which is debt, not error."""

    return [
        Finding("Index.Linter/Line.Ungrounded", record.id, {"support": "0"})
        for record in ctx.selected_records()
        if not record.support
    ]


class _SessionCache:
    """One archive read per session. Plumbing, kept out of the checks that use it.

    The failure is remembered as well as the success. A cache that only remembered
    successes would re-attempt every unavailable session once per record, which is the
    expensive case rather than the cheap one.
    """

    def __init__(self, geo: Geography) -> None:
        self._geo = geo
        self._seen: dict[str, object | ChatError] = {}

    def _resolve(self, session_id: str) -> object | ChatError:
        if session_id not in self._seen:
            try:
                self._seen[session_id] = load_session(self._geo, session_id)
            except ChatError as exc:
                self._seen[session_id] = exc
        return self._seen[session_id]

    def get(self, session_id: str):
        """The session, or `None` when the archive cannot supply it."""

        resolved = self._resolve(session_id)
        return None if isinstance(resolved, ChatError) else resolved

    def load(self, _geo: Geography, session_id: str):
        """`load_session`'s signature, so it can stand in for it.

        The original error is re-raised rather than a fresh one: `verify_gate` puts the
        detail into its UNAVAILABLE verdict, and a cached read must not degrade that to a
        vaguer reason than an uncached one would give.
        """

        resolved = self._resolve(session_id)
        if isinstance(resolved, ChatError):
            raise resolved
        return resolved


def _check_support_resolves(ctx: LintContext) -> list[Finding]:
    """Support is the fundamental variable this system is least able to validate.

    These assertions reach the *existence* and *qualification* of the cited turns. Whether
    those turns actually support the claim is semantic, and belongs to a higher tier — so a
    green result here must never be read as grounding being verified.

    An absent archive reports `unknown`. It is user-scoped, so absence is normal, but normal
    is not the same as checked.
    """

    findings: list[Finding] = []
    archive = _SessionCache(ctx.geo)
    for record in ctx.selected_records():
        for ref in record.support:
            if ref.archive != CHAT_ARCHIVE:
                # A coordinate this archive cannot address is not a mismatch. 5,755 refs
                # carry Chatlas1 turn ids -- `turn-r1326`, or a provider uuid -- which
                # Chatlas2 addresses by digest and cannot look up at all. Calling that
                # `Support.Mismatch` asserted the evidence had changed; it has not been
                # read. Reported as its own unverifiable state so the migration backlog is
                # legible instead of hiding inside 38% of the corpus's findings.
                findings.append(_support_legacy_coordinate_finding(record, ref))
                continue
            session = archive.get(ref.session_id)
            if session is None:
                findings.append(_support_unreachable_finding(record, ref))
                continue
            message = session.message(ref.message_id)
            if message is None:
                findings.append(_support_mismatch_finding(record, ref))
            elif not message.carries_touch:
                findings.append(
                    _support_not_touched_finding(record, ref, side=message.side)
                )
    return findings


# $kw: Index.Linter/Review.SupportUnseen --from POI.Linter
def _check_review_covers_support(ctx: LintContext) -> list[Finding]:
    """Review is the only validation support-selection ever gets, so it should have seen it.

    The gate proves the user saw the *wording*. If the agent turn never showed which turns
    the line claims as evidence, the user approved a sentence, not a grounding.

    Deliberately coarse: it looks for the support address as a substring. Overdetects on a
    turn that cited support some other way, which is the correct direction to be wrong in.
    """

    findings: list[Finding] = []
    # The whole corpus's gates name 22 distinct sessions. Asking the archive per record
    # instead of per session is the same read 76 times over, which is what made a full run
    # cost tens of minutes.
    archive = _SessionCache(ctx.geo)
    for record in ctx.selected_records():
        if not record.review or not record.support:
            continue
        gate = record.review[0]
        session = archive.get(gate.session_id)
        if session is None:
            findings.append(
                Finding(
                    "Index.Linter/Review.SupportUnseen",
                    record.id,
                    {"session": gate.session_id},
                    status=Status.BLOCKED,
                )
            )
            continue
        turn = session.message(gate.agent_turn_id)
        if turn is None:
            continue
        missing = [r.message_id for r in record.support if r.message_id not in turn.text]
        if missing:
            findings.append(
                Finding(
                    "Index.Linter/Review.SupportUnseen",
                    record.id,
                    {"unshown": ",".join(m[:16] for m in missing)},
                )
            )
    return findings


# $kw: Index.Linter/Record.Unplaced --from POI.Linter
def _check_record_placed(ctx: LintContext) -> list[Finding]:
    """An entry on no surface is invisible to every reader of the index.

    Two entries are exempt. One whose home carries no `Index.Notes` at all -- the serialized
    side is the whole of that home, so there is nothing to be missing from. And one that has
    been superseded within its trace: a revision *replaces* the predecessor's wording on the
    surface, so a superseded member is absent by construction, and reporting it would make
    every revision leave a permanent finding behind.

    Being off the surface is still readable: the successor is what `materialization-standing`
    holds to the surface, and the trace is what carries the history.
    """

    superseded = {
        member.equivalence.predecessor
        for trace in ctx.traces().values()
        for member in trace.members
        if member.equivalence is not None
    }
    on_surface = {line.label for _, line in ctx.all_surface_lines() if line.label}
    findings: list[Finding] = []
    for record in ctx.selected_records():
        label = record.line.label
        if not label or label in on_surface or record.id in superseded:
            continue
        home = scope_home(record.scope, ctx.root)
        if home is not None and not ctx.homes.carries_notes(home):
            continue
        findings.append(
            Finding("Index.Linter/Record.Unplaced", record.id, {"label": label})
        )
    return findings


# $kw: Index.Linter/Record.Untyped --from POI.Linter
def _check_record_typed(ctx: LintContext) -> list[Finding]:
    """Same bar as the surface line, applied to the record that claims to index it."""

    return [
        Finding("Index.Linter/Record.Untyped", record.id, {"body": record.line.body})
        for record in ctx.selected_records()
        if record.line.type is None
    ]


# $kw: Index.Linter/Record.LabelCollision --from POI.Linter
def _check_record_label_unique(ctx: LintContext) -> list[Finding]:
    """A public selector that resolves to several records selects nothing reliably."""

    ids_by_label: dict[str, list[str]] = {}
    for record in ctx.selected_records():
        if record.line.label:
            ids_by_label.setdefault(record.line.label, []).append(record.id)
    return [
        Finding(
            "Index.Linter/Record.LabelCollision",
            label,
            {"ids": " ".join(sorted(ids))},
        )
        for label, ids in sorted(ids_by_label.items())
        if len(ids) > 1
    ]


# $kw: Index.Linter/Record.Unscoped --from POI.Linter
def _check_record_scoped(ctx: LintContext) -> list[Finding]:
    """A line is an orthogonal part of something larger; unscoped, it evaluates to nothing."""

    return [
        Finding("Index.Linter/Record.Unscoped", record.id, {"scope": ""})
        for record in ctx.selected_records()
        if not record.scope.address
    ]


# $kw: Index.Linter/Scope.Unresolved --from POI.Linter
def _check_scope_resolves(ctx: LintContext) -> list[Finding]:
    """One address space, two kinds — and both must reach something that exists.

    Addressability is what lets documentation be pointers rather than descriptions, so an
    address that resolves to nothing is worse than a missing one.
    """

    findings: list[Finding] = []
    for record in ctx.selected_records():
        path = resolve_scope_surface(record.scope, ctx.root)
        if path is None or not path.exists():
            findings.append(
                Finding(
                    "Index.Linter/Scope.Unresolved",
                    record.id,
                    {"scope": record.scope.address, "kind": str(record.scope.kind)},
                )
            )
    return findings


# $kw: Index.Linter/Reviewed.Cite.Closure --from POI.Linter
# --note [DF] emitted when a reviewed Index line cites a real block that remains in the unreviewed agendix
# --note [CT] the existing policy requires promoting the target into the reviewed Index or dropping the citation
# --note [RJ] this migration does not choose or perform either repair
def _check_review_closure(ctx: LintContext) -> list[Finding]:
    """`Reviewed.Cite.Closure`: reviewed standing may not rest on nothing touched.

    The agent/user split is derived from review evidence, so the closure rule bites here —
    a reviewed trace carrying an ungrounded member is the reviewed side depending on the
    unreviewed one.
    """

    findings: list[Finding] = []
    for trace in ctx.traces().values():
        if not trace.reviewed:
            continue
        for member in trace.members:
            if member.support or not ctx.is_selected(member.id):
                continue
            findings.append(
                Finding(
                    "Index.Linter/Reviewed.Cite.Closure",
                    member.id,
                    {"trace": trace.id, "support": "0"},
                )
            )
    return findings


# $kw: Index.Linter/Scope.KindMismatch --from POI.Linter
def _check_annotation_scope_kind(ctx: LintContext) -> list[Finding]:
    """A line's host decides its scope kind, so a disagreement means one of them moved."""

    findings: list[Finding] = []
    by_label = ctx.by_label()
    for surface, line in ctx.all_surface_lines():
        record = by_label.get(line.label or "")
        if record is None or not ctx.is_selected(record.id):
            continue
        if line.scope.kind is not record.scope.kind:
            findings.append(
                Finding(
                    "Index.Linter/Scope.KindMismatch",
                    record.id,
                    {"surface": str(line.scope.kind), "record": str(record.scope.kind)},
                    surface=surface,
                )
            )
    return findings


# $kw: Index.Linter/Line.Type.Unknown --from POI.Linter
def _check_line_type_known(ctx: LintContext) -> list[Finding]:
    """An unrecognized type selects no assertions, so the line is untyped in practice."""

    known = {"DF", "DC", "CT", "RJ", "PR", "FR", "EX", "IMPL", "IS"}
    return [
        Finding(
            "Index.Linter/Line.Type.Unknown",
            f"{line.scope.label}:{line.lineno}",
            {"type": str(line.line_type), "known": " ".join(sorted(known))},
            surface=surface,
        )
        for surface, line in ctx.all_surface_lines()
        if line.line_type is not None and line.line_type not in known
    ]


def _check_trace_wellformed(ctx: LintContext) -> list[Finding]:
    """`Trace.HEAD` is derived, so a malformed chain surfaces instead of picking a winner."""

    findings: list[Finding] = []
    for trace in ctx.traces().values():
        heads = trace.heads()
        if len(heads) > 1:
            findings.append(_trace_forked_finding(trace))
        elif not heads:
            findings.append(_trace_cycle_finding(trace))
    return findings


def _check_equivalence_predecessor(ctx: LintContext) -> list[Finding]:
    """The chain is what derives `Trace.HEAD`, so a broken link breaks the derivation."""

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.selected_records():
        if record.equivalence is None:
            continue
        predecessor = by_id.get(record.equivalence.predecessor)
        if predecessor is None:
            findings.append(_equivalence_predecessor_missing_finding(record))
        elif predecessor.trace != record.trace:
            findings.append(
                _equivalence_trace_mismatch_finding(record, predecessor)
            )
    return findings


# $kw: --from Typed.Agent.State --note [DC] the rephrase claim is agent-generated, so it sits beside a cheap inlined assertion that makes talking harder than being right ^c20260819-19u
# $kw: Index.Linter/Equivalence.SupportChanged --from POI.Linter
def _check_equivalence_support_invariant(ctx: LintContext) -> list[Finding]:
    """If the new wording needed new evidence, it is not the same claim.

    One of the few cheap assertions guarding the review economy, which a same-trace change
    can otherwise walk straight into.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.selected_records():
        if record.equivalence is None:
            continue
        predecessor = by_id.get(record.equivalence.predecessor)
        if predecessor is None:
            continue
        if set(record.support) != set(predecessor.support):
            findings.append(
                Finding(
                    "Index.Linter/Equivalence.SupportChanged",
                    record.id,
                    {
                        "support": str(len(record.support)),
                        "predecessor_support": str(len(predecessor.support)),
                    },
                )
            )
    return findings


# $kw: Index.Linter/Equivalence.NotARename --from POI.Linter
def _check_rename_verifiable(ctx: LintContext) -> list[Finding]:
    """`rename` is the typed form of the equivalence claim, so it must survive its own test.

    Coarse on purpose — word count only. A rename that changes shape is caught; a clever one
    that does not is left to the agent, which is the right division of labour.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.selected_records():
        equivalence = record.equivalence
        if equivalence is None or equivalence.kind is not EquivalenceKind.RENAME:
            continue
        predecessor = by_id.get(equivalence.predecessor)
        if predecessor is None:
            continue
        before = predecessor.line.body.split()
        after = record.line.body.split()
        if len(before) != len(after):
            findings.append(
                Finding(
                    "Index.Linter/Equivalence.NotARename",
                    record.id,
                    {"before_words": str(len(before)), "after_words": str(len(after))},
                )
            )
    return findings


# $kw: Index.Linter/Review.ViaRephrase --from POI.Linter
def _check_rephrase_in_review_chain(ctx: LintContext) -> list[Finding]:
    """A `rephrase` is `Untyped.Agent.State` on the path that grants reviewed standing.

    `rename` and `rephrase` are the typed and untyped forms of one claim. Reviewed standing
    reached only through renames is mechanically verified end to end; reached through a
    rephrase it rests on an assertion nothing checks. Both currently print as `via_trace`,
    and a reader should be able to tell them apart.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.selected_records():
        if record.review:
            continue
        trace = ctx.traces().get(record.trace)
        if trace is None or not trace.reviewed:
            continue
        cursor, hops = record, 0
        while cursor.equivalence is not None and hops < 64:
            if cursor.equivalence.kind is EquivalenceKind.REPHRASE:
                findings.append(
                    Finding(
                        "Index.Linter/Review.ViaRephrase",
                        record.id,
                        {"trace": trace.id, "claimed_at": cursor.id},
                        evaluator=Evaluator.AGENT,
                    )
                )
                break
            cursor = by_id.get(cursor.equivalence.predecessor) or cursor
            hops += 1
    return findings


# $kw: Index.Linter/Review.EvidenceLost --from POI.Linter
def _check_review_evidence_retained(ctx: LintContext) -> list[Finding]:
    """The reviewed member is the review's only verifiable evidence; lose it and the claim
    survives while its proof does not."""

    findings: list[Finding] = []
    for trace in ctx.traces().values():
        if not trace.reviewed:
            continue
        for member in trace.review_members:
            if not member.review:
                continue
            if not member.line.body.strip():
                findings.append(
                    Finding(
                        "Index.Linter/Review.EvidenceLost",
                        trace.id,
                        {"member": member.id, "body": ""},
                    )
                )
    return findings


def _gate_findings(ctx: LintContext, *, require_touch: bool) -> list[Finding]:
    """Shared body of `gate-verifies` and its dev counterpart.

    One traversal for both links, because review and landing are the same mechanism.
    `require_touch` is the single axis the two callers differ on.
    """

    findings: list[Finding] = []
    archive = _SessionCache(ctx.geo)
    for record in ctx.selected_records():
        gates = [("review", g) for g in record.review]
        if record.landing is not None:
            gates.append(("landing", record.landing))
        for kind, gate in gates:
            check = verify_gate(
                ctx.geo,
                gate,
                record.line.body,
                require_touch=require_touch,
                load=archive.load,
            )
            if check.verdict is GateVerdict.INVALID:
                findings.append(
                    _gate_evidence_invalid_finding(record, kind, gate, check)
                )
            elif check.verdict is GateVerdict.UNAVAILABLE:
                findings.append(
                    _gate_evidence_unavailable_finding(record, kind, gate, check)
                )
    return findings


# $kw: --from Index.Head.Surface --note [DF] the approval turn is the gate, and approval there also means moving the line to the HEAD ^c20260819-16u
# $kw: Index.Linter/Landing.Unevidenced --from POI.Linter
def _check_landing_evidenced(ctx: LintContext) -> list[Finding]:
    """Presence says what is; the gate says what licensed it.

    Presence without a gate is a promotion an agent granted on its own authority.
    """

    traces = ctx.traces()
    findings: list[Finding] = []
    for record in ctx.selected_records():
        if record.id not in ctx.head_lines:
            continue
        trace = traces.get(record.trace)
        if trace is not None and trace.landed:
            continue
        findings.append(
            Finding(
                "Index.Linter/Landing.Unevidenced",
                record.id,
                {"trace": record.trace, "landing_gate": "none"},
            )
        )
    return findings


# $kw: Index.Linter/Landing.Unhonored --from POI.Linter
def _check_landing_honored(ctx: LintContext) -> list[Finding]:
    """The gate outlives the surface edit, which is what makes a silent demotion visible.

    Demotion itself stays ungated — it is a diff anyone can read — but it stops being silent.
    """

    findings: list[Finding] = []
    for trace in ctx.traces().values():
        if not trace.landed:
            continue
        if any(m.id in ctx.head_lines for m in trace.members):
            continue
        findings.append(
            Finding(
                "Index.Linter/Landing.Unhonored",
                trace.id,
                {"members": str(len(trace.members)), "on_head_surface": "0"},
            )
        )
    return findings


# $kw: Index.Linter/Materialization.Standing --from POI.Linter
def _check_materialization_standing(ctx: LintContext) -> list[Finding]:
    """The older wording should have left when its successor arrived."""

    findings: list[Finding] = []
    for record in ctx.selected_records():
        standing = ctx.standing.get(record.id)
        if standing is None or standing.materializable:
            continue
        if record.id in ctx.head_lines:
            findings.append(
                Finding(
                    "Index.Linter/Materialization.Standing",
                    record.id,
                    {"trace": record.trace, "is_trace_head": "false"},
                )
            )
    return findings


def _grounded_coverage(records: Iterable[LineRecord]) -> set[tuple[str, str, str]]:
    """The Touched.Data currently covered by grounded lines."""

    return {
        (ref.archive, ref.session_id, ref.message_id)
        for record in records
        for ref in record.support
    }


def _coverage_at_git_head(geo: Geography) -> set[tuple[str, str, str]] | None:
    """Grounded coverage as of the last commit, or ``None`` when git cannot say.

    Degrades to silence rather than failing: an untracked project is a normal state, not a
    defect.
    """

    index_dir = geo.index_depot
    if not index_dir.exists():
        return None

    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=index_dir, capture_output=True, text=True, check=False,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return None

    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=index_dir, capture_output=True, text=True, check=False,
    )
    if toplevel.returncode != 0:
        return None
    root = Path(toplevel.stdout.strip())

    try:
        relative = index_dir.resolve().relative_to(root.resolve())
    except ValueError:
        return None

    listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", "HEAD", "--", str(relative)],
        cwd=root, capture_output=True, text=True, check=False,
    )
    if listing.returncode != 0:
        return None

    coverage: set[tuple[str, str, str]] = set()
    for name in listing.stdout.splitlines():
        if not name.endswith(".json") or name.endswith("meta.json"):
            continue
        blob = subprocess.run(
            ["git", "show", f"HEAD:{name}"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if blob.returncode != 0:
            continue
        try:
            payload = json.loads(blob.stdout)
        except ValueError:
            continue
        # A depot file holds one record or a shard of many, and which is the depot's
        # private business. Reading both keeps this check indifferent to the topology,
        # which is the property the store went to some trouble to keep.
        for candidate in _records_in(payload):
            coverage |= _grounded_coverage([candidate])
    return coverage


def _records_in(payload: object) -> list[LineRecord]:
    if not isinstance(payload, dict):
        return []
    try:
        return [LineRecord.from_json(payload)]
    except (ValueError, KeyError, TypeError):
        pass
    found = []
    for value in payload.values():
        if isinstance(value, dict):
            try:
                found.append(LineRecord.from_json(value))
            except (ValueError, KeyError, TypeError):
                continue
    return found


# $kw: --from Index.Removal --note [CT] deleted lines are tracked on git and not by the index, so what is conserved is coverage rather than a removals ledger ^c20260819-23u
# $kw: Index.Linter/Coverage.Shrank --from POI.Linter
def _check_coverage_converges(ctx: LintContext) -> list[Finding]:
    """The bytes of the index are free to move; its coverage of the Touched.Data is not.

    There is no excuse mechanism. An index-side ledger of *why* a line went would be agent
    prose about a deletion git already records with an author and a message.

    An untracked project reports `unknown`, not clean: nothing was compared.
    """

    previous = _coverage_at_git_head(ctx.geo)
    if previous is None:
        return []

    lost = previous - _grounded_coverage(ctx.records)
    return [
        Finding(
            "Index.Linter/Coverage.Shrank",
            f"{session}:{message[:16]}",
            {"archive": archive, "session": session, "message": message},
        )
        for archive, session, message in sorted(lost)
    ]


def _gate_git_available(ctx: LintContext) -> GateResult:
    if _coverage_at_git_head(ctx.geo) is None:
        return GateResult.blocked("the index depot is not tracked by git")
    return GateResult.ok()


#: The catalog. Growing the system means adding a row here.
def _check_gate_verifies(ctx: LintContext) -> list[Finding]:
    """The gate is the only reason any assertion about a line is state, so this is the check
    that makes the rest of the model mean something.

    One check for both links, because review and landing are the same mechanism. An absent
    archive reports `unknown`: it is user-scoped, so absence is the normal case elsewhere,
    but a gate nobody could check is not a gate that held.
    """

    return _gate_findings(ctx, require_touch=True)


def _check_gate_verifies_dev(ctx: LintContext) -> list[Finding]:
    """`gate-verifies` with the `User.Touch` requirement dropped, and nothing else.

    Both turns must still exist, both must still carry the token, and the line must still
    appear verbatim in the agent turn. What this permits is a gate opened by a turn that is
    not a qualifying user turn — which is the one thing a test cannot manufacture honestly,
    and the reason a `dev` run is stamped as such wherever its verdict is printed.
    """

    return _gate_findings(ctx, require_touch=False)


# $kw: Index.Linter/Class.Review --from POI.Linter --note [CT] Every Tarav linter POI.Class requires an individual semantic review; corpus counts prove execution, not correctness. ^c20260821-6u
CHECK_REGISTRY: tuple[Check, ...] = (
    Check(
        "surfaces-readable", Tier.STRUCTURAL, _check_surfaces_readable,
        resolutions=(
            "repair the surface so it parses",
            "remove it from discovery, if it is not an index surface",
        ),
    ),
    Check(
        "alias-has-no-block", Tier.REPORTABLE, _check_alias_has_no_block,
        resolutions=(
            "merge the alias block into its canonical concept block",
            "remove the alias declaration, if the second concept is genuinely distinct",
        ),
    ),
    Check(
        "records-loadable", Tier.STRUCTURAL, _check_records_loadable,
        resolutions=(
            "repair the malformed entry",
            "restore it from git, if the damage is recent",
        ),
    ),
    Check(
        "line-typed", Tier.REPORTABLE, _check_line_typed, resolutions=(
        "type it — the Line.Type declares what to extract from the Touched.Data",
        "delete it — an untyped line asserts nothing classifiable",
    )),
    Check(
        "line-type-known", Tier.REPORTABLE, _check_line_type_known, resolutions=(
        "correct the code to a known Line.Type",
        "propose the new code, if the vocabulary is genuinely short",
    )),
    Check(
        "line-anchored", Tier.REPORTABLE, _check_line_anchored, resolutions=(
        "mint a label so readers can resolve the line",
        "delete it — the line is scratch",
    )),
    Check(
        "anchor-has-record", Tier.REPORTABLE, _check_anchor_has_record, resolutions=(
        "write the record — the line exists but the index does not know it",
        "remove the surface line, if it was a draft",
    )),
    Check(
        "anchor-collision", Tier.REPORTABLE, _check_anchor_collision, resolutions=(
        "relabel one of them — a label identifies exactly one line",
        "merge them, if they are the same line duplicated",
    )),
    Check(
        "line-drift", Tier.REPORTABLE, _check_line_drift, resolutions=(
        "adopt the surface wording into the record",
        "rewrite the surface from the record",
        "leave it — the divergence may be work in progress",
    )),
    Check(
        "record-typed", Tier.REPORTABLE, _check_record_typed, resolutions=(
        "type the entry",
        "delete it while it is still ungrounded",
    )),
    Check(
        "record-label-unique", Tier.REPORTABLE, _check_record_label_unique, resolutions=(
        "relabel one record so the public selector is unambiguous",
        "merge the records, if they are duplicate editions of one line",
    )),
    Check(
        "record-scoped", Tier.REPORTABLE, _check_record_scoped, resolutions=(
        "give it a scope — a line only means something inside one",
    )),
    Check(
        "record-grounded", Tier.REPORTABLE, _check_record_grounded, resolutions=(
        "ground it — find the support that was always there",
        "delete it — it was scratch, and nothing is lost",
        "keep it — useful orientation carrying Index.Presumption; grounding stays debt",
    )),
    Check(
        "support-resolves", Tier.REPORTABLE, _check_support_resolves, resolutions=(
        "fetch the archive it names",
        "re-ground the line against evidence that still resolves",
        "record the mis-grounding, if the support never supported the claim",
    )),
    Check(
        "record-placed", Tier.REPORTABLE, _check_record_placed, resolutions=(
        "materialize it on a surface",
        "leave it record-only, if no surface needs it yet",
    )),
    Check(
        "scope-resolves", Tier.REPORTABLE, _check_scope_resolves, resolutions=(
        "create the surface the scope names",
        "rescope the line to a surface that exists",
    )),
    Check(
        "scope-kind", Tier.REPORTABLE, _check_annotation_scope_kind, resolutions=(
        "correct whichever side names the wrong hosting kind",
    )),
    Check(
        "review-closure", Tier.REPORTABLE, _check_review_closure, resolutions=(
        "ground the user entry in its own right",
        "move it to the agent index until it is reviewed",
    )),
    Check(
        "trace-wellformed", Tier.REPORTABLE, _check_trace_wellformed, resolutions=(
        "pick one successor — a fork means two claims, so split the trace",
        "break the cycle by correcting a predecessor",
    )),
    Check(
        "equivalence-predecessor", Tier.REPORTABLE, _check_equivalence_predecessor, resolutions=(
        "point at a predecessor that exists in the same trace",
        "start a new trace, if this is a different claim",
    )),
    Check(
        "equivalence-support", Tier.REPORTABLE, _check_equivalence_support_invariant, resolutions=(
        "start a new trace — new evidence means a new claim",
        "restore the support, if the change really was cosmetic",
    )),
    Check(
        "equivalence-rename", Tier.REPORTABLE, _check_rename_verifiable, resolutions=(
        "downgrade the claim to a rephrase",
        "start a new trace, if the meaning moved",
    )),
    Check(
        "review-covers-support", Tier.REPORTABLE, _check_review_covers_support, resolutions=(
        "show the support in the review turn and re-open the gate",
        "accept it — the user saw the evidence some other way this check cannot read",
        "drop the review claim if the grounding was never actually reviewed",
    )),
    Check(
        "review-via-rephrase", Tier.REPORTABLE, _check_rephrase_in_review_chain, resolutions=(
        "review the current wording directly, replacing the untyped claim with evidence",
        "re-make the change as a rename, if it really was one",
        "accept it — the rephrase holds, and now the reader can see that it was assumed",
    )),
    Check(
        "review-evidence", Tier.REPORTABLE, _check_review_evidence_retained, resolutions=(
        "restore the reviewed member — it is the review\u2019s only evidence",
    )),
    Check(
        "gate-verifies", Tier.REPORTABLE, _check_gate_verifies, resolutions=(
        "correct the turns the gate names",
        "drop the gate — it cannot be verified, so it asserts nothing",
        "re-open the gate; a real approval leaves a real turn",
    )),
    Check(
        "gate-verifies-dev", Tier.REPORTABLE, _check_gate_verifies_dev,
        dev=True, replaces="gate-verifies", resolutions=(
        "correct the turns the gate names",
        "re-run without `dev` once a real user turn exists",
    )),
    Check(
        "landing-evidenced", Tier.REPORTABLE, _check_landing_evidenced, resolutions=(
        "record the landing gate for the approval turn that licensed it",
        "take the line off the live Index surface until it is approved",
        "move provisional wording to a non-Index work surface",
    )),
    Check(
        "landing-honored", Tier.REPORTABLE, _check_landing_honored, resolutions=(
        "land the approved line onto a live Index surface",
        "accept the demotion — the gate records that it was once current design",
        "read the diff that removed it, if the demotion was not intended",
    )),
    Check(
        "materialization-standing", Tier.REPORTABLE, _check_materialization_standing, resolutions=(
        "remove the superseded wording from the surface",
        "reconsider the successor, if the older wording is the one that should stand",
    )),
    Check(
        "coverage-converges", Tier.REPORTABLE, _check_coverage_converges,
        gate=_gate_git_available,
        resolutions=(
            "restore the line — its coverage was real and is now missing",
            "read the commit that removed it; git is the deletion record",
            "accept the loss — the support never supported the claim",
        ),
    ),
)

# $kw: --from Index.WIP.Surface --note [DF] the bar checks are the ones reporting work not yet done, as against an inconsistency between two things
BAR_CHECKS = frozenset({"line-typed", "record-typed", "record-grounded", "scope-resolves"})


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One check's own verdict — `passed | failed | blocked`, per check."""

    name: str
    status: Status
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LintReport:
    """An estimate, not a defect list.

    `clean` is a claim about *errors*, and it is not the same claim as *verified*. A report
    with no failures and eighteen blocked checks is a very different epistemic position from
    one with no failures and everything checked, so the two are counted separately and
    printed separately.
    """

    findings: tuple[Finding, ...]
    blocked: tuple[Finding, ...]
    blessed: tuple[Finding, ...]
    results: tuple[CheckResult, ...]
    records_loaded: int
    records_checked: int
    surface_files_loaded: int
    surface_lines_checked: int
    elapsed_ms: float
    project_id: str | None = None
    project_root: str | None = None
    dev: tuple[str, ...] = ()
    """Names of the dev checks this run used, empty for an ordinary run.

    A dev run is not a verdict about the project; it is a verdict about the
    machinery. Carrying the names on the report means every printer and every
    caller has to decide what to do about them, rather than a boolean nobody
    reads.
    """

    @property
    def is_dev(self) -> bool:
        return bool(self.dev)

    @property
    def checks_run(self) -> tuple[str, ...]:
        return tuple(r.name for r in self.results)

    @property
    def clean(self) -> bool:
        """No errors. Says nothing about how much was checked — read `verified` for that."""

        return not self.findings

    @property
    def verified(self) -> bool:
        """No errors *and* nothing blocked."""

        return not self.findings and not self.blocked and not self.blocked_checks

    @property
    def blocked_checks(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status is Status.BLOCKED)

    def by_class(self) -> dict[str, list[Finding]]:
        """Grouped by check — a concentration here reads as the system having drifted."""

        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.poi_class, []).append(finding)
        return grouped

    def by_subject(self) -> dict[str, list[Finding]]:
        """Grouped by state — a concentration here reads as one `Bad.State`.

        The linter groups and stops. Which of the two readings applies is semantic, and that
        is the agent's work.
        """

        grouped: dict[str, list[Finding]] = {}
        for finding in self.findings:
            grouped.setdefault(finding.subject, []).append(finding)
        return grouped

    def summary(self) -> str:
        passed = sum(1 for r in self.results if r.status is Status.PASSED)
        failed = sum(1 for r in self.results if r.status is Status.FAILED)
        return (
            f"{len(self.results)} check(s): {passed} passed, {failed} failed, "
            f"{len(self.blocked_checks)} blocked   "
            f"{len(self.findings)} error(s), {len(self.blocked)} unverifiable"
        )


def _blessings_path(geo: Geography) -> Path:
    return geo.project_tier / "blessed.json"


def read_blessings(geo: Geography) -> dict[str, GateRef]:
    """The accepted POIs and the gate each one rests on."""

    path = _blessings_path(geo)
    if not path.exists():
        return {}
    payload = json.loads(path.read_text("utf-8"))
    return {
        identity: GateRef.from_json(gate) for identity, gate in payload.items()
    }


def bless(geo: Geography, identity: str, gate: GateRef) -> None:
    """Accept one exact POI, on the user's evidence.

    A blessing is the one piece of state whose *purpose* is to stop the checker, so it is the
    last place an unevidenced agent value could survive — an agent silencing its own findings
    with a file it writes itself. It needs a gate for the same reason everything else does.

    Silencing one known case still never weakens the check for any other.
    """

    blessings = read_blessings(geo)
    blessings[identity] = gate
    path = _blessings_path(geo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {k: v.to_json() for k, v in sorted(blessings.items())},
            indent=1,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _blessing_holds(geo: Geography, gate: GateRef) -> bool:
    """Only verified user evidence may silence a finding."""

    return verify_gate(geo, gate).verdict is GateVerdict.VERIFIED


def select_checks(
    check: list[str] | None = None,
    skip: list[str] | None = None,
    *,
    dev: bool = False,
    targeted: bool = False,
) -> list[Check]:
    """The checks this run will execute.

    Outside the dev lane a `dev` check is never selected, not even by name: a
    relaxed check that can be summoned into an ordinary run is a relaxed check
    that will eventually be summoned by accident. Inside it, each dev check
    displaces the one it `replaces`, so a constraint is reported once.
    """

    names = {c.name for c in CHECK_REGISTRY}
    for requested in (check or []) + (skip or []):
        if requested not in names:
            raise LintError(f"unknown check: {requested!r}")

    displaced = {
        entry.replaces for entry in CHECK_REGISTRY if dev and entry.dev and entry.replaces
    }
    selected = []
    for entry in CHECK_REGISTRY:
        if entry.dev and not dev:
            continue
        if targeted and not entry.record_scoped and entry.tier is not Tier.STRUCTURAL:
            # Not a filter applied afterwards: a corpus check has no per-record answer to
            # give, so asking it about one record and discarding the rest would be running
            # the whole linter to throw most of it away.
            #
            # The structural tier stays regardless, because it is what establishes the
            # context: it reads the surfaces and loads the records. Dropping it leaves a
            # targeted run examining an empty corpus and reporting it clean, which is the
            # failure mode this whole selection has to avoid.
            continue
        if entry.name in displaced:
            continue
        enabled = entry.name in check if check else entry.default_on
        if skip and entry.name in skip:
            enabled = False
        if enabled:
            selected.append(entry)
    return selected


# $kw: --from State.Estimation --note [DF] a state is minimally a value plus an err or unknown estimate, an Agent.State is dangerous because verification cost varies, so the report counts blocked apart from failed ^c20260819-17u
# --from Dumb.Code --note [DF] the catalog is a Fishing.Net: cheap tests run over all items, converting expensive semantic attention into cheap mechanical attention
# --note [CT] Execution metadata reports elapsed time and loaded surface-file, surface-line, record, and check counts. ^c20260820-15u
def lint(
    geo: Geography,
    *,
    project_root: Path | None = None,
    check: list[str] | None = None,
    skip: list[str] | None = None,
    dev: bool = False,
    subjects: Iterable[str] | None = None,
) -> LintReport:
    """Run the selected checks and report what each one found — including what it could not.

    ``subjects`` narrows the run to those record ids: only checks answerable for a single
    record run, and they examine only those records. The corpus is still loaded, because a
    record's standing depends on its trace siblings and a corpus this size loads in about a
    tenth of a second; what a targeted run avoids is the per-record archive reads, which is
    where the time actually goes.
    """

    started_at = perf_counter()
    root = project_root or geo.project_root
    ctx = LintContext(
        geo=geo,
        root=root,
        store=IndexStore(geo),
        homes=load_homes(geo),
        subjects=None if subjects is None else frozenset(subjects),
    )

    selected = select_checks(check, skip, dev=dev, targeted=subjects is not None)
    blessings = read_blessings(geo)
    findings: list[Finding] = []
    blocked: list[Finding] = []
    blessed: list[Finding] = []
    results: list[CheckResult] = []

    for entry in selected:
        allowed = entry.can_run(ctx)
        if not allowed.allowed:
            results.append(CheckResult(entry.name, Status.BLOCKED, allowed.reason))
            continue

        produced = [
            replace(finding, source=entry.source) for finding in entry.run(ctx)
        ]
        errors: list[Finding] = []

        for finding in produced:
            if finding.blocked:
                blocked.append(finding)
                continue
            gate = blessings.get(finding.identity)
            if gate is None:
                errors.append(finding)
            elif _blessing_holds(geo, gate):
                blessed.append(finding)
            else:
                errors.append(finding)
                errors.append(
                    _blessing_unevidenced_finding(
                        finding,
                        check_name=entry.name,
                        source=entry.source,
                    )
                )

        findings.extend(errors)
        results.append(
            CheckResult(entry.name, Status.FAILED if errors else Status.PASSED)
        )

        if entry.tier is Tier.STRUCTURAL and produced:
            # A surface that will not parse makes later findings noise, not signal.
            break

    return LintReport(
        findings=tuple(findings),
        blocked=tuple(blocked),
        blessed=tuple(blessed),
        results=tuple(results),
        records_loaded=len(ctx.records),
        records_checked=len(ctx.selected_records()),
        surface_files_loaded=len(ctx.surface_lines),
        surface_lines_checked=sum(len(v) for v in ctx.surface_lines.values()),
        elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
        project_id=geo.project_id,
        project_root=str(root.resolve()),
        dev=tuple(e.name for e in selected if e.dev),
    )


__all__ = [
    "BAR_CHECKS",
    "CHECK_REGISTRY",
    "Check",
    "CheckResult",
    "Finding",
    "LintError",
    "LintReport",
    "Tier",
    "bless",
    "lint",
    "read_blessings",
    "select_checks",
]
