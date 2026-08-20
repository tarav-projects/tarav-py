# $kw: --from POI.Linter --note [CT] agents edit surfaces with general primitives; the linter checks conformance
# $kw: --from Convergent.Justification --note [DC] Check.default_on is held on one reason — a check may ship off when it is expensive or situational, though no catalog row does yet
"""The tarav index linter.

This is where the intelligence lives. Agents edit the markdown surfaces directly with
ordinary file primitives — there is no landing API, no capture pipeline, no adopt command.
Afterwards the linter runs as many checks as it can and reports POIs.

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
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import sha256
from pathlib import Path

from .chatlas import ChatError, load_session
from .config import Geography, TaravIndexError
from .gates import GateRef, GateVerdict, verify_gate
from .record.model import EquivalenceKind, LineRecord
from .record.store import IndexStore
from .scope import resolve_scope_surface
from .standing import (
    Standing,
    build_traces,
    lines_on_head_surfaces,
    standings,
)
from .surfaces import (
    HeadSurfaces,
    Homes,
    SurfaceLine,
    discover_surfaces,
    load_head_surfaces,
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
    head: HeadSurfaces = field(default_factory=HeadSurfaces)
    homes: Homes = field(default_factory=Homes)
    records: list[LineRecord] = field(default_factory=list)
    standing: dict[str, Standing] = field(default_factory=dict)
    surface_lines: dict[str, list[SurfaceLine]] = field(default_factory=dict)
    head_lines: set[str] = field(default_factory=set)

    def head_surface_lines(self) -> Iterator[tuple[str, SurfaceLine]]:
        """Only the lines sitting on a declared `HEAD.Surface`."""

        for surface, lines in self.surface_lines.items():
            if not self.head.contains(surface):
                continue
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

    def can_run(self, ctx: LintContext) -> GateResult:
        """`GateResult`: a precondition the check cannot supply for itself."""

        return self.gate(ctx) if self.gate else GateResult.ok()

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


def _check_records_loadable(ctx: LintContext) -> list[Finding]:
    """The records are the states being estimated; unreadable, there is nothing to estimate."""

    try:
        ctx.records = list(ctx.store.all())
        ctx.head_lines = lines_on_head_surfaces(ctx.records, ctx.surface_lines, ctx.head)
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


def _check_anchor_collision(ctx: LintContext) -> list[Finding]:
    """One label must name one line, or a pointer stops resolving to one thing."""

    seen: dict[str, tuple[str, str]] = {}
    findings: list[Finding] = []
    for surface, line in ctx.all_surface_lines():
        label = line.label
        if label is None:
            continue
        previous = seen.get(label)
        if previous is not None and previous[1] != line.body:
            findings.append(
                Finding(
                    "Index.Linter/Anchor.Collision",
                    label,
                    {
                        "here": line.body,
                        "there": previous[1],
                        "other_surface": previous[0],
                    },
                    surface=surface,
                )
            )
        else:
            seen[label] = (surface, line.body)
    return findings


def _check_line_drift(ctx: LintContext) -> list[Finding]:
    """Neither side is presumed right — which one is wrong is the work, not the check's call."""

    by_label = ctx.by_label()
    findings: list[Finding] = []
    for surface, line in ctx.all_surface_lines():
        record = by_label.get(line.label or "")
        if record is None:
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
def _check_record_grounded(ctx: LintContext) -> list[Finding]:
    """The bar. An ungrounded entry carries `Index.Presumption`, which is debt, not error."""

    return [
        Finding("Index.Linter/Line.Ungrounded", record.id, {"support": "0"})
        for record in ctx.records
        if not record.support
    ]


class _SessionCache:
    """One archive read per session. Plumbing, kept out of the checks that use it."""

    def __init__(self, geo: Geography) -> None:
        self._geo = geo
        self._seen: dict[str, object | None] = {}

    def get(self, session_id: str):
        if session_id not in self._seen:
            try:
                self._seen[session_id] = load_session(self._geo, session_id)
            except ChatError:
                self._seen[session_id] = None
        return self._seen[session_id]


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
    for record in ctx.records:
        for ref in record.support:
            session = archive.get(ref.session_id)
            if session is None:
                findings.append(
                    Finding(
                        "Index.Linter/Support.Unreachable",
                        record.id,
                        {"archive": ref.archive, "session": ref.session_id},
                        status=Status.BLOCKED,
                    )
                )
                continue
            message = session.message(ref.message_id)
            if message is None:
                findings.append(
                    Finding(
                        "Index.Linter/Support.Mismatch",
                        record.id,
                        {"message": ref.message_id, "session": ref.session_id},
                    )
                )
            elif not message.carries_touch:
                findings.append(
                    Finding(
                        "Index.Linter/Support.NotTouched",
                        record.id,
                        {"message": ref.message_id, "side": message.side},
                    )
                )
    return findings


def _check_review_covers_support(ctx: LintContext) -> list[Finding]:
    """Review is the only validation support-selection ever gets, so it should have seen it.

    The gate proves the user saw the *wording*. If the agent turn never showed which turns
    the line claims as evidence, the user approved a sentence, not a grounding.

    Deliberately coarse: it looks for the support address as a substring. Overdetects on a
    turn that cited support some other way, which is the correct direction to be wrong in.
    """

    findings: list[Finding] = []
    for record in ctx.records:
        if record.review is None or not record.support:
            continue
        try:
            session = load_session(ctx.geo, record.review.session_id)
        except ChatError:
            findings.append(
                Finding(
                    "Index.Linter/Review.SupportUnseen",
                    record.id,
                    {"session": record.review.session_id},
                    status=Status.BLOCKED,
                )
            )
            continue
        turn = session.message(record.review.agent_turn_id)
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
    for record in ctx.records:
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


def _check_record_typed(ctx: LintContext) -> list[Finding]:
    """Same bar as the surface line, applied to the record that claims to index it."""

    return [
        Finding("Index.Linter/Record.Untyped", record.id, {"body": record.line.body})
        for record in ctx.records
        if record.line.type is None
    ]


def _check_record_scoped(ctx: LintContext) -> list[Finding]:
    """A line is an orthogonal part of something larger; unscoped, it evaluates to nothing."""

    return [
        Finding("Index.Linter/Record.Unscoped", record.id, {"scope": ""})
        for record in ctx.records
        if not record.scope.address
    ]


def _check_scope_resolves(ctx: LintContext) -> list[Finding]:
    """One address space, two kinds — and both must reach something that exists.

    Addressability is what lets documentation be pointers rather than descriptions, so an
    address that resolves to nothing is worse than a missing one.
    """

    findings: list[Finding] = []
    for record in ctx.records:
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
            if member.support:
                continue
            findings.append(
                Finding(
                    "Index.Linter/Reviewed.Cite.Closure",
                    member.id,
                    {"trace": trace.id, "support": "0"},
                )
            )
    return findings


def _check_annotation_scope_kind(ctx: LintContext) -> list[Finding]:
    """A line's host decides its scope kind, so a disagreement means one of them moved."""

    findings: list[Finding] = []
    by_label = ctx.by_label()
    for surface, line in ctx.all_surface_lines():
        record = by_label.get(line.label or "")
        if record is None:
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
            findings.append(
                Finding(
                    "Index.Linter/Trace.Forked",
                    trace.id,
                    {"heads": str(len(heads)), "ids": " ".join(m.id for m in heads)},
                )
            )
        elif not heads:
            findings.append(
                Finding(
                    "Index.Linter/Trace.Cycle",
                    trace.id,
                    {"members": str(len(trace.members)), "heads": "0"},
                )
            )
    return findings


def _check_equivalence_predecessor(ctx: LintContext) -> list[Finding]:
    """The chain is what derives `Trace.HEAD`, so a broken link breaks the derivation."""

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.records:
        if record.equivalence is None:
            continue
        predecessor = by_id.get(record.equivalence.predecessor)
        if predecessor is None:
            findings.append(
                Finding(
                    "Index.Linter/Equivalence.PredecessorMissing",
                    record.id,
                    {"predecessor": record.equivalence.predecessor},
                )
            )
        elif predecessor.trace != record.trace:
            findings.append(
                Finding(
                    "Index.Linter/Equivalence.TraceMismatch",
                    record.id,
                    {"trace": record.trace, "predecessor_trace": predecessor.trace},
                )
            )
    return findings


# $kw: --from Typed.Agent.State --note [DC] the rephrase claim is agent-generated, so it sits beside a cheap inlined assertion that makes talking harder than being right ^c20260819-19u
def _check_equivalence_support_invariant(ctx: LintContext) -> list[Finding]:
    """If the new wording needed new evidence, it is not the same claim.

    One of the few cheap assertions guarding the review economy, which a same-trace change
    can otherwise walk straight into.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.records:
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


def _check_rename_verifiable(ctx: LintContext) -> list[Finding]:
    """`rename` is the typed form of the equivalence claim, so it must survive its own test.

    Coarse on purpose — word count only. A rename that changes shape is caught; a clever one
    that does not is left to the agent, which is the right division of labour.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.records:
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


def _check_rephrase_in_review_chain(ctx: LintContext) -> list[Finding]:
    """A `rephrase` is `Untyped.Agent.State` on the path that grants reviewed standing.

    `rename` and `rephrase` are the typed and untyped forms of one claim. Reviewed standing
    reached only through renames is mechanically verified end to end; reached through a
    rephrase it rests on an assertion nothing checks. Both currently print as `via_trace`,
    and a reader should be able to tell them apart.
    """

    by_id = {r.id: r for r in ctx.records}
    findings: list[Finding] = []
    for record in ctx.records:
        if record.review is not None:
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


def _check_review_evidence_retained(ctx: LintContext) -> list[Finding]:
    """The reviewed member is the review's only verifiable evidence; lose it and the claim
    survives while its proof does not."""

    findings: list[Finding] = []
    for trace in ctx.traces().values():
        if not trace.reviewed:
            continue
        for member in trace.review_members:
            if member.review is None:
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
    for record in ctx.records:
        for kind, gate in (("review", record.review), ("landing", record.landing)):
            if gate is None:
                continue
            check = verify_gate(
                ctx.geo, gate, record.line.body, require_touch=require_touch
            )
            if check.verdict is GateVerdict.CONTRADICTED:
                findings.append(
                    Finding(
                        "Index.Linter/Gate.Contradicted",
                        record.id,
                        {"gate": kind, "reason": check.detail, "token": gate.token},
                    )
                )
            elif check.verdict is GateVerdict.UNVERIFIABLE:
                findings.append(
                    Finding(
                        "Index.Linter/Gate.Unverifiable",
                        record.id,
                        {"gate": kind, "session": gate.session_id},
                        status=Status.BLOCKED,
                    )
                )
    return findings


# $kw: --from Index.Head.Surface --note [DF] the approval turn is the gate, and approval there also means moving the line to the HEAD ^c20260819-16u
def _check_landing_evidenced(ctx: LintContext) -> list[Finding]:
    """Presence says what is; the gate says what licensed it.

    Presence without a gate is a promotion an agent granted on its own authority.
    """

    traces = ctx.traces()
    findings: list[Finding] = []
    for record in ctx.records:
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


def _check_materialization_standing(ctx: LintContext) -> list[Finding]:
    """The older wording should have left when its successor arrived."""

    findings: list[Finding] = []
    for record in ctx.records:
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

    index_dir = geo.index_dir
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
        if not name.endswith(".json"):
            continue
        blob = subprocess.run(
            ["git", "show", f"HEAD:{name}"],
            cwd=root, capture_output=True, text=True, check=False,
        )
        if blob.returncode != 0:
            continue
        try:
            payload = json.loads(blob.stdout)
            record = LineRecord.from_json(payload)
        except (ValueError, KeyError):
            continue
        coverage |= _grounded_coverage([record])
    return coverage


# $kw: --from Index.Removal --note [CT] deleted lines are tracked on git and not by the index, so what is conserved is coverage rather than a removals ledger ^c20260819-23u
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
        return GateResult.blocked("the project index is not tracked by git")
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


CATALOG: tuple[Check, ...] = (
    Check(
        "surfaces-readable", Tier.STRUCTURAL, _check_surfaces_readable,
        resolutions=(
            "repair the surface so it parses",
            "remove it from discovery, if it is not an index surface",
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
        "take the line off the HEAD.Surface until it is approved",
        "narrow the HEAD.Surface declaration, if this surface is not current design",
    )),
    Check(
        "landing-honored", Tier.REPORTABLE, _check_landing_honored, resolutions=(
        "land the approved line onto a HEAD.Surface",
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
    records_checked: int
    surface_lines_checked: int
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
    """A blessing degrades like review: absent archive silences, contradiction revokes."""

    return verify_gate(geo, gate).verdict is not GateVerdict.CONTRADICTED


def select_checks(
    check: list[str] | None = None,
    skip: list[str] | None = None,
    *,
    dev: bool = False,
) -> list[Check]:
    """The checks this run will execute.

    Outside the dev lane a `dev` check is never selected, not even by name: a
    relaxed check that can be summoned into an ordinary run is a relaxed check
    that will eventually be summoned by accident. Inside it, each dev check
    displaces the one it `replaces`, so a constraint is reported once.
    """

    names = {c.name for c in CATALOG}
    for requested in (check or []) + (skip or []):
        if requested not in names:
            raise LintError(f"unknown check: {requested!r}")

    displaced = {
        entry.replaces for entry in CATALOG if dev and entry.dev and entry.replaces
    }
    selected = []
    for entry in CATALOG:
        if entry.dev and not dev:
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
def lint(
    geo: Geography,
    *,
    project_root: Path | None = None,
    check: list[str] | None = None,
    skip: list[str] | None = None,
    dev: bool = False,
) -> LintReport:
    """Run the selected checks and report what each one found — including what it could not."""

    root = project_root or geo.project_root
    ctx = LintContext(
        geo=geo,
        root=root,
        store=IndexStore(geo),
        head=load_head_surfaces(geo),
        homes=load_homes(geo),
    )

    selected = select_checks(check, skip, dev=dev)
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
                    Finding(
                        "Index.Linter/Blessing.Unevidenced",
                        finding.identity,
                        {"check": entry.name, "gate": "contradicted"},
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
        records_checked=len(ctx.records),
        surface_lines_checked=sum(len(v) for v in ctx.surface_lines.values()),
        dev=tuple(e.name for e in selected if e.dev),
    )


__all__ = [
    "BAR_CHECKS",
    "CATALOG",
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
