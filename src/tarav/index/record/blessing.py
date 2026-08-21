# $kw: --from Index.Line.Record --from Semantic.Assertion --note [DC] a blessing is an Agent.Claim carrying its own support set, not a user gate ^c20260821-35u
# --note [CT] the record makes the agent's judgment auditable later; it never makes it checkable now ^c20260821-36u
"""`Blessing.Record` — an agent's claim that one `POI.Instance` is acceptable.

A blessing is the one thing allowed to stop a checker, so it is the last place an unevidenced
agent value could survive. What licenses it is not a user's approval token but the same thing
that licenses every other index line: **a free `Index.Line` plus a `User.Touched` support set**.

```text
poi        the POI instance this accepts
line       the agent's one-line explanation of why -- free, hosted by no surface
support    the user turns the agent claims license that explanation
```

Two things follow from that shape.

**No validity flag.** Whether a blessing silences its POI is derived from whether its support
resolves and qualifies, exactly as a `LineRecord` derives `head` rather than storing it. An
agent cannot write down that its own blessing is good.

**No scope.** The explanation is a *free* line: freeness is a property of the host, not a field,
so there is no scope to leave empty and no `ScopeKind` naming a POI instance. A surface check
asking "is this line placed?" is never offered this depot, because placement is not a question
this host answers.

What the support set is *not* is a proof of relevance. Nothing mechanical can establish that
these turns license this application — that is the `Semantic.Assertion` the record exists to
make auditable later, and it is true of every support set in the system, not only a blessing's.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterable
from dataclasses import dataclass, replace

from filelock import FileLock

from tarav.bloberia.core import TYPE_SHARDS, BloberiaDepot

from ..config import Geography, TaravIndexError
from .model import Line, SupportRef

BLESSING_SCHEMA = "tarav.index-blessing-record.v1"
BLESSING_ID_PREFIX = "bl"


def new_blessing_id() -> str:
    return f"{BLESSING_ID_PREFIX}_{secrets.token_hex(8)}"


class BlessingStoreError(TaravIndexError):
    """Raised when the blessing store cannot satisfy a request."""


@dataclass(frozen=True, slots=True)
class BlessingRecord:
    """One accepted POI, and the claim that accepts it."""

    id: str
    poi: str
    line: Line
    support: tuple[SupportRef, ...] = ()

    @classmethod
    def create(
        cls,
        poi: str,
        line_type: str | None,
        body: str,
        *,
        support: Iterable[SupportRef] = (),
    ) -> BlessingRecord:
        return cls(
            id=new_blessing_id(),
            poi=poi,
            line=Line(type=line_type, body=body),
            support=tuple(support),
        )

    def amend(self, line_type: str | None, body: str) -> BlessingRecord:
        """Correct the claim in place. Not a new blessing; git records the change."""

        return replace(self, line=Line(type=line_type, body=body))

    @property
    def grounded(self) -> bool:
        """Carries support at all. Whether that support *holds* is a separate walk."""

        return bool(self.support)

    def to_json(self) -> dict[str, object]:
        return {
            "schema": BLESSING_SCHEMA,
            "id": self.id,
            "poi": self.poi,
            "line": self.line.to_json(),
            "support": [ref.to_json() for ref in self.support],
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> BlessingRecord:
        support = payload.get("support") or []
        if not isinstance(support, list):
            raise BlessingStoreError(f"malformed support on blessing {payload.get('id')!r}")
        return cls(
            id=str(payload["id"]),
            poi=str(payload["poi"]),
            line=Line.from_json(payload["line"]),  # type: ignore[arg-type]
            support=tuple(SupportRef.from_json(ref) for ref in support),
        )


class BlessingStore:
    """Every blessing, in one depot beside the records.

    Its own depot rather than a discriminator inside the record depot: a shared one would put
    blessings in front of every check that iterates records, turning host-bound applicability
    into a filter each of those checks would have to remember to apply.
    """

    def __init__(self, geo: Geography) -> None:
        self._geo = geo
        self._depot = BloberiaDepot(
            geo.blessing_depot, depot_type=TYPE_SHARDS, key="id", git="."
        )
        self._write_lock = geo.user_root / "locks" / "index-blessings.lock"

    @property
    def directory(self):
        return self._depot.root

    def all(self) -> list[BlessingRecord]:
        return [BlessingRecord.from_json(cargo) for cargo in self._depot.iterate()]

    def find(self, blessing_id: str) -> BlessingRecord | None:
        cargo = self._depot.first({"id": {"equals": blessing_id}})
        return BlessingRecord.from_json(cargo) if cargo is not None else None

    def get(self, blessing_id: str) -> BlessingRecord:
        found = self.find(blessing_id)
        if found is None:
            raise BlessingStoreError(f"no blessing with id {blessing_id!r}")
        return found

    def by_poi(self, poi: str) -> list[BlessingRecord]:
        return [
            BlessingRecord.from_json(cargo)
            for cargo in self._depot.all({"poi": {"equals": poi}})
        ]

    def put(self, record: BlessingRecord) -> BlessingRecord:
        self._write_lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self._write_lock):
            query = {"id": {"equals": record.id}}
            if self._depot.count(query):
                self._depot.replace(query, record.to_json())
            else:
                self._depot.insert(record.to_json())
        return record

    def remove(self, blessing_id: str) -> None:
        if not self._depot.delete({"id": {"equals": blessing_id}}):
            raise BlessingStoreError(f"no blessing with id {blessing_id!r}")


__all__ = [
    "BLESSING_SCHEMA",
    "BlessingRecord",
    "BlessingStore",
    "BlessingStoreError",
    "new_blessing_id",
]
