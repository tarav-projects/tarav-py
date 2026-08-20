# $kw: --from Typed.Agent.State --note [DC] every standing is derived — from the chain, from a gate, or from which surface the line is on
"""Derived standings.

Nothing in this module reads a flag, because the system never accepts one. Every standing
comes from structure an agent had to *do* something to produce — write a predecessor, open a
gate, put the line on a surface — so a defect shows up as an inconsistency rather than as a
claim nobody can check.

Four standings, on four independent axes:

```text
Trace.HEAD       within a trace     which version of this line is current
Index standing   across surfaces    whether this claim is on a HEAD.Surface
Review standing  per trace          reviewed directly, via the trace, or not at all
Review side      per trace          the agent/user split, derived from review evidence
```

The index axis is the one that changed shape. It used to read a `supersedes` field, which
demoted a whole trace on an agent's say-so. It now reads **where the line actually is**: a
line is in the HEAD if it sits on a declared `HEAD.Surface`. Presence says what is; the
landing gate says what licensed it; the linter reports every mismatch between the two.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from .record.model import LineRecord
from .surfaces import HeadSurfaces, SurfaceLine


class IndexStanding(StrEnum):
    """Whether a claim is current design. Both values are well grounded."""

    #: On a declared `HEAD.Surface` — promoted.
    HEAD = "head"
    #: Recorded, but on no HEAD.Surface. Old design, still grounded.
    TAIL = "tail"


class ReviewStanding(StrEnum):
    #: This exact line carries review evidence.
    DIRECT = "direct"
    #: Another member of its trace does; this line is reviewed by proxy.
    VIA_TRACE = "via_trace"
    NONE = "none"


class ReviewSide(StrEnum):
    """The agent/user split — derived, never stored.

    The user index is *defined* as what the user reviewed, so a stored side would be a
    boolean claiming a human read something. A trace carrying review evidence is on the user
    side; every other trace is agent-maintained end to end, still grounded on `User.Turn`s.
    """

    AGENT = "agent"
    USER = "user"


@dataclass(frozen=True, slots=True)
class Trace:
    """One indexed semantic: the lines that carry it, and its current version."""

    id: str
    members: tuple[LineRecord, ...]

    @property
    def head(self) -> LineRecord | None:
        """The current version — derived from the predecessor chain, never stored.

        A member is superseded within the trace when another member names it as predecessor.
        Exactly one member should be un-succeeded; anything else is a malformed trace, which
        `heads()` exposes rather than hides.
        """

        heads = self.heads()
        return heads[0] if len(heads) == 1 else None

    def heads(self) -> tuple[LineRecord, ...]:
        """Every un-succeeded member. More than one means the trace forked."""

        succeeded = {
            m.equivalence.predecessor for m in self.members if m.equivalence is not None
        }
        return tuple(m for m in self.members if m.id not in succeeded)

    @property
    def malformed(self) -> bool:
        return len(self.heads()) != 1

    @property
    def reviewed(self) -> bool:
        """Review is a property of the trace, so every member is semantically reviewed."""

        return any(m.review is not None for m in self.members)

    @property
    def review_members(self) -> tuple[LineRecord, ...]:
        """The members carrying review evidence — the ones that may never be dropped."""

        return tuple(m for m in self.members if m.review is not None)

    @property
    def landed(self) -> bool:
        """Whether any member carries the gate approving this semantic for the HEAD.

        On the trace, not the line: otherwise every rename would need re-approval, which is
        the problem the trace already solved for review.
        """

        return any(m.landing is not None for m in self.members)

    @property
    def landing_members(self) -> tuple[LineRecord, ...]:
        return tuple(m for m in self.members if m.landing is not None)

    @property
    def side(self) -> ReviewSide:
        return ReviewSide.USER if self.reviewed else ReviewSide.AGENT

    def member(self, line_id: str) -> LineRecord | None:
        return next((m for m in self.members if m.id == line_id), None)


# $kw: --from Index.Line.Record --note [DC] a trace is grouped from the records themselves, never read from a stored chain, so a more auditable structure displaces the agent definition ^c20260819-20u
def build_traces(records: Iterable[LineRecord]) -> dict[str, Trace]:
    grouped: dict[str, list[LineRecord]] = {}
    for record in records:
        grouped.setdefault(record.trace, []).append(record)
    return {
        trace_id: Trace(id=trace_id, members=tuple(members))
        for trace_id, members in grouped.items()
    }


# $kw: --from Index.Head.Surface --note [DF] a line is in the HEAD because it is observed on a HEAD.Surface, which is what promoted means ^c20260819-25u
# --note [CT] the scan replaces a stored surface list, because a value the filesystem already answers cheaply is not a design variable ^d20260819-14u
def lines_on_head_surfaces(
    records: Iterable[LineRecord],
    surface_lines: Mapping[str, Sequence[SurfaceLine]],
    head: HeadSurfaces,
) -> set[str]:
    """The ids of records observed on a declared `HEAD.Surface`.

    Read off a scan of the surfaces rather than a field on the record, because a stored list
    of "surfaces I am on" is a cache of something the filesystem already answers — and a
    cache an agent writes is a value an agent can invent.
    """

    by_label = {r.line.label: r.id for r in records if r.line.label}
    found: set[str] = set()
    for surface, lines in surface_lines.items():
        if not head.contains(surface):
            continue
        for line in lines:
            line_id = by_label.get(line.label or "")
            if line_id is not None:
                found.add(line_id)
    return found


# $kw: --from Index.Head.Surface --note [DC] standing is linked to presence on a surface, so no supersedes field is needed ^c20260819-26u
def index_standing(record: LineRecord, head_lines: set[str]) -> IndexStanding:
    return IndexStanding.HEAD if record.id in head_lines else IndexStanding.TAIL


# $kw: --from Typed.Agent.State --note [CT] review standing is computed from evidence on the record and its trace, because the system will not carry a value which is merely agent-based ^c20260819-15u
def review_standing(record: LineRecord, trace: Trace | None) -> ReviewStanding:
    if record.review is not None:
        return ReviewStanding.DIRECT
    if trace is not None and trace.reviewed:
        return ReviewStanding.VIA_TRACE
    return ReviewStanding.NONE


@dataclass(frozen=True, slots=True)
class Standing:
    """The full derived standing of one entry."""

    record: LineRecord
    index: IndexStanding
    review: ReviewStanding
    side: ReviewSide
    is_trace_head: bool

    @property
    def materializable(self) -> bool:
        """Whether a surface may carry this wording at all.

        Only `Trace.HEAD`. Whether it belongs on a *HEAD* surface is no longer computable
        from the record — that is the landing gate's question, and the editorial act of
        putting the line there is what answers it.
        """

        return self.is_trace_head


def standings(
    records: Iterable[LineRecord], *, head_lines: set[str] | None = None
) -> dict[str, Standing]:
    """Derive every standing in one pass.

    ``head_lines`` comes from a surface scan. With no scan every entry derives TAIL, which is
    the honest reading: nothing was observed on a HEAD.Surface.
    """

    materialized = list(records)
    traces = build_traces(materialized)
    on_head = head_lines or set()

    resolved: dict[str, Standing] = {}
    for record in materialized:
        trace = traces.get(record.trace)
        head = trace.head if trace else None
        resolved[record.id] = Standing(
            record=record,
            index=index_standing(record, on_head),
            review=review_standing(record, trace),
            side=trace.side if trace else ReviewSide.AGENT,
            is_trace_head=head is not None and head.id == record.id,
        )
    return resolved


__all__ = [
    "IndexStanding",
    "ReviewSide",
    "ReviewStanding",
    "Standing",
    "Trace",
    "build_traces",
    "index_standing",
    "lines_on_head_surfaces",
    "review_standing",
    "standings",
]
