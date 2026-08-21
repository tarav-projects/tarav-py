# $kw: --from Index.Line.Record --note [CT] the system never accepts an agent-set flag; every standing is derived or evidenced
# $kw: --from Index.Head.Surface --note [DC] no supersedes field: standing tied to a surface needs no field
# $kw: --from Convergent.Justification --note [DC] placement is held on one reason — its consumer is the Chat.Index writer, designed and deferred rather than absent
# $kw: --from Convergent.Justification --note [DC] an absent line.at edition time stays absent; reading a record never manufactures one
"""`Index.Line.Record` — the object describing one index entry.

Minimally the index is *lines supported by a support set*: annotation plus evidence of
`Touched.Authority`. `Line.Type` declares what to extract; a `Line.Scope` gives the context a
line can only be evaluated in.

Three independent axes run through an entry:

```text
grounding        support links → user turns     immutable; a grounded line stays grounded forever
trace            trace id + predecessor         which *version* of this line is current
index standing   HEAD / TAIL                    whether this *claim* is still current design
```

The governing rule: **no agent-set flags.** Nothing here stores "this is the head" or "this is
reviewed" or "this is demoted". Every standing is derived from structure or carried by
evidence in an immutable surface, so a defect is detectable rather than merely asserted.

The one thing an agent asserts directly is `Equivalence` — that a change preserved semantics —
and it is recorded as a typed claim *precisely because* it cannot be checked.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from dataclasses import dataclass, replace
from enum import StrEnum

from ..gates import GateRef
from ..scope import LineScope, parse_scope

RECORD_SCHEMA = "tarav.index-line-record.v5"
#: `v4` had no place for a support reference's content hash, so a reference could be
#: resolved but never validated. `v5` adds it as an optional member field; `v4` records
#: read unchanged, because absent and none are the same state.
RECORD_SCHEMA_V4 = "tarav.index-line-record.v4"
#: `v3` held one review gate. It could not carry a line the user gated twice under two
#: tokens, and the anchory corpus has such lines, so migrating into it would have dropped
#: evidence the record exists to hold.
RECORD_SCHEMA_V3 = "tarav.index-line-record.v3"
LINE_ID_PREFIX = "ln"
TRACE_ID_PREFIX = "tr"


def new_line_id() -> str:
    """Identify one indexed line."""

    return f"{LINE_ID_PREFIX}_{secrets.token_hex(8)}"


def new_trace_id() -> str:
    """Identify one indexed *semantic*.

    `line.id` points at a particular indexed line; `trace.id` points at a particular indexed
    semantic. Lines carrying the same semantics share a trace.
    """

    return f"{TRACE_ID_PREFIX}_{secrets.token_hex(8)}"


class EquivalenceKind(StrEnum):
    """How a same-trace change claims to have preserved semantics.

    A `RENAME` is mechanically verifiable — token substitution, everything else identical —
    so it can be trusted without a human. A `REPHRASE` is agent judgment and stays visible
    as such.
    """

    RENAME = "rename"
    REPHRASE = "rephrase"


@dataclass(frozen=True, slots=True)
class SupportRef:
    """One member of a `Support.Set` — a reference, never grounding content.

    Grounding data belongs to the user, so the index carries coordinates only.

    ``message_hash`` is the reference's **validation**: the address says where to look, the
    hash proves what was found is what was meant. Without it a check can only establish that
    the coordinate still exists, never that it still says the same thing.

    It is optional because the references this migration carries never had one, and a
    required field would make them unstorable — the mistake `v3`'s single review gate made,
    which `v4` had to widen.
    """

    archive: str
    session_id: str
    message_id: str
    message_hash: str | None = None

    def to_json(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "archive": self.archive,
            "session_id": self.session_id,
            "message_id": self.message_id,
        }
        if self.message_hash:
            # Absent rather than null: a reference that never had a hash and one explicitly
            # recorded as having none are the same state, and writing `null` into 9,768
            # references would assert a distinction the model does not make.
            payload["message_hash"] = self.message_hash
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> SupportRef:
        message_hash = payload.get("message_hash")
        return cls(
            archive=str(payload["archive"]),
            session_id=str(payload["session_id"]),
            message_id=str(payload["message_id"]),
            message_hash=str(message_hash) if message_hash else None,
        )


@dataclass(frozen=True, slots=True)
class PlacementRef:
    """Where a line attaches on a Chat.Index.

    Location, not evidence: the oldest turn containing the line verbatim — agent or user,
    since this is a coordinate rather than authority — falling back to the oldest supporting
    user turn. Stored at landing, never recomputed, so rewording does not move it.

    Nothing computes or reads this yet.
    """


    archive: str
    session_id: str
    turn_id: str

    def to_json(self) -> dict[str, object]:
        return {
            "archive": self.archive,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> PlacementRef:
        return cls(
            archive=str(payload["archive"]),
            session_id=str(payload["session_id"]),
            turn_id=str(payload["turn_id"]),
        )


@dataclass(frozen=True, slots=True)
class Equivalence:
    """The claim that joining a trace preserved semantics.

    Recorded rather than implied by writing a trace id, because it is the single step in the
    whole chain that no machine can verify. Making it an artifact makes it auditable.
    """

    kind: EquivalenceKind
    predecessor: str

    def to_json(self) -> dict[str, object]:
        return {"kind": str(self.kind), "predecessor": self.predecessor}

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> Equivalence:
        return cls(
            kind=EquivalenceKind(str(payload["kind"])),
            predecessor=str(payload["predecessor"]),
        )


@dataclass(frozen=True, slots=True)
class Line:
    """What a reader of the index consumes: `type + body + label`.

    The label is the line's **public id** — it uniquely labels the line for readers. It is not
    the id; the id is internal to the index, and the label may change while the id does not.
    """

    type: str | None
    body: str
    label: str | None = None
    at: str | None = None

    def render(self) -> str:
        prefix = f"- [{self.type}] " if self.type else "- "
        return f"{prefix}{self.body}" + (f" {self.label}" if self.label else "")

    def to_json(self) -> dict[str, object]:
        return {"type": self.type, "body": self.body, "label": self.label, "at": self.at}

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> Line:
        return cls(
            type=payload.get("type") and str(payload["type"]) or None,
            body=str(payload["body"]),
            label=payload.get("label") and str(payload["label"]) or None,
            at=payload.get("at") and str(payload["at"]) or None,
        )


def _gate_tuple(payload: object) -> tuple[GateRef, ...]:
    """Read `links.review` from either schema.

    `v3` wrote one object or null; `v4` writes a list. Both are read, because records on
    disk predate the widening and rewriting them is a migration, not a read.
    """
    if payload is None:
        return ()
    if isinstance(payload, dict):
        return (GateRef.from_json(payload),)
    return tuple(GateRef.from_json(g) for g in payload)


@dataclass(frozen=True, slots=True)
class LineRecord:
    """One index entry: what it says, and how it indexes the authority surface.

    Nothing here states a standing. There is no `head`, no `reviewed`, no `index` side, no
    `supersedes` — every one of those is derived, from the predecessor chain, from a gate's
    presence, or from which surface the line is actually on.

    What remains storable is of three kinds: the line itself, which an agent must generate;
    links into an immutable archive, which are coordinates a machine can follow; and the one
    `Equivalence` claim no machine can check.
    """

    id: str
    trace: str
    scope: LineScope
    line: Line
    support: tuple[SupportRef, ...] = ()
    placement: PlacementRef | None = None
    #: Every gate that evidenced this wording. A tuple rather than one gate: a line can
    #: be gated more than once under distinct tokens, and a single slot would make the
    #: extra evidence unstorable rather than merely unstored.
    review: tuple[GateRef, ...] = ()
    landing: GateRef | None = None
    equivalence: Equivalence | None = None

    @classmethod
    def create(
        cls,
        scope: LineScope | str,
        line_type: str | None,
        body: str,
        *,
        label: str | None = None,
        support: Iterable[SupportRef] = (),
        trace: str | None = None,
    ) -> LineRecord:
        return cls(
            id=new_line_id(),
            trace=trace or new_trace_id(),
            scope=parse_scope(scope) if isinstance(scope, str) else scope,
            line=Line(type=line_type, body=body, label=label),
            support=tuple(support),
        )

    # -- the line --------------------------------------------------------------

    def relabel(self, label: str) -> LineRecord:
        """Change the public label. The id does not move, and this is not a new version."""

        normalized = label if label.startswith("^") else f"^{label}"
        return replace(self, line=replace(self.line, label=normalized))

    def amend(self, line_type: str | None, body: str) -> LineRecord:
        """Fix this line in place. Not a new version; git records it."""

        return replace(
            self, line=Line(type=line_type, body=body, label=self.line.label, at=self.line.at)
        )

    def rescope(self, scope: LineScope | str) -> LineRecord:
        return replace(self, scope=parse_scope(scope) if isinstance(scope, str) else scope)

    # -- the trace -------------------------------------------------------------

    def successor(
        self,
        line_type: str | None,
        body: str,
        *,
        kind: EquivalenceKind = EquivalenceKind.REPHRASE,
        label: str | None = None,
    ) -> LineRecord:
        """A new version of this line: new id, new label, **same trace**.

        The equivalence claim rides along, because asserting sameness is what joining a trace
        actually means. Gates do not: they were opened on a wording, and the successor has to
        earn its own or inherit through the trace.
        """

        return LineRecord(
            id=new_line_id(),
            trace=self.trace,
            scope=self.scope,
            line=Line(type=line_type, body=body, label=label),
            support=self.support,
            equivalence=Equivalence(kind=kind, predecessor=self.id),
        )

    # -- the indexing ----------------------------------------------------------

    @property
    def grounded(self) -> bool:
        return bool(self.support)

    def with_support(self, support: Iterable[SupportRef]) -> LineRecord:
        return replace(self, support=tuple(support))

    def with_placement(self, placement: PlacementRef) -> LineRecord:
        return replace(self, placement=placement)

    def with_review(self, *review: GateRef) -> LineRecord:
        """Attach the gates evidencing that the user read this wording."""

        return replace(self, review=tuple(review))

    def with_landing(self, landing: GateRef) -> LineRecord:
        """Attach the gate evidencing that the user approved landing this to HEAD.

        Same machinery as review, different question. Approving is not reading, and reading
        is not approving, so they are two links that may well cite one user turn.
        """

        return replace(self, landing=landing)

    def to_json(self) -> dict[str, object]:
        return {
            "schema": RECORD_SCHEMA,
            "id": self.id,
            "trace": self.trace,
            "scope": self.scope.address,
            "line": self.line.to_json(),
            "links": {
                "grounding": [s.to_json() for s in self.support],
                "placement": self.placement.to_json() if self.placement else None,
                "review": [g.to_json() for g in self.review],
                "landing": self.landing.to_json() if self.landing else None,
            },
            "equivalence": self.equivalence.to_json() if self.equivalence else None,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> LineRecord:
        links: dict = payload.get("links") or {}  # type: ignore[assignment]
        placement = links.get("placement")
        review = links.get("review")
        landing = links.get("landing")
        equivalence = payload.get("equivalence")
        return cls(
            id=str(payload["id"]),
            trace=str(payload["trace"]),
            scope=parse_scope(str(payload["scope"])),
            line=Line.from_json(payload["line"]),  # type: ignore[arg-type]
            support=tuple(SupportRef.from_json(s) for s in links.get("grounding", [])),
            placement=PlacementRef.from_json(placement) if placement else None,
            review=_gate_tuple(review),
            landing=GateRef.from_json(landing) if landing else None,
            equivalence=Equivalence.from_json(equivalence) if equivalence else None,
        )


__all__ = [
    "LINE_ID_PREFIX",
    "RECORD_SCHEMA",
    "TRACE_ID_PREFIX",
    "Equivalence",
    "EquivalenceKind",
    "Line",
    "LineRecord",
    "PlacementRef",
    "SupportRef",
    "new_line_id",
    "new_trace_id",
]
