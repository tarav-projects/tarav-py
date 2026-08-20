# $kw: --from Index.Store --note [DC] record and anchory unify into one store; the record carries its own anchor
# $kw: --from Typed.Agent.State --note [DC] one depot: the agent/user split is derived, so no directory may name it
"""The index store.

**One store, one depot.** Anchory kept a second copy of a fact the record already holds —
an anchor and the id it points at — which meant two stores to keep in step and a whole
drift class between them. The record carries its own anchor, so the join disappears.

**One tier.** The project/user split is gone. A record's support points at chat evidence in
`~/Documents/chatlas`, which never ships with a project, so a project-tier record would
reach a clone as a dangling reference: storing them user-side does not create that problem,
it stops pretending it is not there. Projects stay distinguishable because `scope.address`
is in the record, which makes it a query rather than a directory.

Storage is a Bloberia depot, keyed by `id`. Not by `label`: a label is the line's *public*
id and may change while the id does not, so keying by it would move a record between shards
on a rename and leave an unlabelled record unstorable. Label lookup is a scan, deliberately
— the second store that made it O(1) cost more than it saved.

Anchor allocation lives here too. It is a scan plus a max — cheap, because the model's own
premise is that the index is human-paced and low-volume.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from filelock import FileLock

from tarav.bloberia.core import TYPE_SHARDS, BloberiaDepot

from ..config import Geography, TaravIndexError
from ..scope import LineScope
from tarav.index_model.label import CITATION_RE, parse_citation

from .model import LineRecord

#: One sigil across the system. `d` separated the new index's labels from the anchory
#: anchors while the two label spaces were distinct; homogenizing the dossiers onto `c`
#: removed that distinction, so a second sigil would name a difference that is gone.
LABEL_SIGIL = "c"
USER_TAG = "u"
#: A label is a *complete* citation: sigil and tag both present. Parsing lives in
#: `index_model.label`; what the store adds is the requirement, not a second grammar.
LABEL_RE = CITATION_RE


class RecordStoreError(TaravIndexError):
    """Raised when the store cannot satisfy a request."""


def normalize_label(label: str) -> str:
    return label if label.startswith("^") else f"^{label}"


def is_label(token: str) -> bool:
    """Whether this token is a well-formed public label.

    Stricter than `is_citation`: an untagged or unprefixed citation still resolves, but the
    store never mints one, so accepting it here would let a partial key be treated as a
    label the store could have produced.
    """

    citation = parse_citation(token)
    return citation is not None and citation.is_complete


class IndexStore:
    """Every index line record, in one depot."""

    def __init__(self, geo: Geography) -> None:
        self._geo = geo
        self._depot = BloberiaDepot(
            geo.index_depot, depot_type=TYPE_SHARDS, key="id", git="."
        )
        self._write_lock = geo.user_root / "locks" / "index-records.lock"

    @property
    def directory(self) -> Path:
        return self._depot.root

    @property
    def depot(self) -> BloberiaDepot:
        return self._depot

    # -- reading ---------------------------------------------------------------

    def iterate(self) -> Iterator[LineRecord]:
        for cargo in self._depot.iterate():
            yield LineRecord.from_json(cargo)

    def all(self) -> list[LineRecord]:
        return list(self.iterate())

    def find(self, line_id: str) -> LineRecord | None:
        cargo = self._depot.first({"id": {"equals": line_id}})
        return LineRecord.from_json(cargo) if cargo is not None else None

    def get(self, line_id: str) -> LineRecord:
        found = self.find(line_id)
        if found is None:
            raise RecordStoreError(f"no index entry with id {line_id!r}")
        return found

    def by_label(self, label: str) -> LineRecord | None:
        normalized = normalize_label(label)
        matches = self._depot.all({"line.label": {"equals": normalized}})
        if len(matches) > 1:
            ids = ", ".join(sorted(str(cargo.get("id")) for cargo in matches))
            raise RecordStoreError(
                f"index label {normalized!r} is ambiguous across records: {ids}"
            )
        return LineRecord.from_json(matches[0]) if matches else None

    def by_trace(self, trace_id: str) -> list[LineRecord]:
        """Every line carrying one indexed semantic."""

        return [
            LineRecord.from_json(c) for c in self._depot.all({"trace": {"equals": trace_id}})
        ]

    def by_scope(self, scope: LineScope | str) -> list[LineRecord]:
        address = scope if isinstance(scope, str) else scope.address
        return [
            LineRecord.from_json(c) for c in self._depot.all({"scope": {"equals": address}})
        ]

    def by_session(self, session_id: str) -> list[LineRecord]:
        """A scan: support is a list, and a path query cannot ask "any member"."""

        return [r for r in self.iterate() if any(s.session_id == session_id for s in r.support)]

    def count(self) -> int:
        return self._depot.count({})

    # -- writing ---------------------------------------------------------------

    def put(self, record: LineRecord) -> LineRecord:
        """Write an entry, replacing its id while preserving public-label uniqueness."""

        self._write_lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self._write_lock):
            return self._put(record)

    def _put(self, record: LineRecord) -> LineRecord:
        """Write under the Index-store lock held by ``put`` or ``mint_label``."""

        if record.line.label:
            record = record.relabel(record.line.label)
            matches = self._depot.all(
                {"line.label": {"equals": record.line.label}}
            )
            conflicts = sorted(
                str(cargo.get("id"))
                for cargo in matches
                if cargo.get("id") != record.id
            )
            if conflicts:
                raise RecordStoreError(
                    f"index label {record.line.label!r} already belongs to "
                    + ", ".join(conflicts)
                )

        query = {"id": {"equals": record.id}}
        if self._depot.count(query):
            self._depot.replace(query, record.to_json())
        else:
            self._depot.insert(record.to_json())
        return record

    def remove(self, line_id: str) -> None:
        """Drop an entry from the semantic model.

        No refusal and no reason. The index is a `WIP.Surface`, and a deletion is already
        recorded — by git, with an author and a message — so a second ledger of agent prose
        about the same deletion would be an invented mechanism carrying an untrusted summary.

        What is conserved is not the bytes but the index's **coverage of the Touched.Data**.
        Losing a grounded line therefore surfaces through `coverage-converges` as a POI whose
        resolution is to read the commit, not through a verdict issued here.
        """

        if not self._depot.delete({"id": {"equals": line_id}}):
            raise RecordStoreError(f"no index entry with id {line_id!r}")

    # -- anchors ---------------------------------------------------------------

    def mint_label(self, record: LineRecord) -> LineRecord:
        """Allocate the next public label for today and stamp it on the entry.

        Idempotent: an entry that already carries a label keeps it.
        """

        if record.line.label:
            return record

        self._write_lock.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(self._write_lock):
            today = datetime.now(UTC).strftime("%Y%m%d")
            prefix = f"^{LABEL_SIGIL}{today}-"
            used: list[int] = []
            for existing in self._depot.all(
                {"line.label": {"contains": prefix.lstrip("^")}}
            ):
                label = (existing.get("line") or {}).get("label")
                if isinstance(label, str) and label.startswith(prefix):
                    citation = parse_citation(label)
                    if citation is not None:
                        used.append(citation.seq)

            return self._put(
                record.relabel(f"{prefix}{max(used, default=-1) + 1}{USER_TAG}")
            )


__all__ = [
    "LABEL_RE",
    "LABEL_SIGIL",
    "USER_TAG",
    "IndexStore",
    "RecordStoreError",
    "is_label",
    "normalize_label",
]
