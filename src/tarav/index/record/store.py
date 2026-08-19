# $kw: --from Index.Store --note [DC] record and anchory unify into one store; the record carries its own anchor
# $kw: --from Typed.Agent.State --note [DC] one folder per tier: the agent/user split is derived, so a directory cannot name it
"""The index store.

**One store.** Anchory kept a second copy of a fact the record already holds — an anchor and
the id it points at — which meant two stores to keep in step and a whole drift class between
them. The record carries its own anchor, so the join disappears.

The shape is the simplest one that is correct: **one JSON file per line record in a folder.**

One folder per tier. The agent/user split used to be two folders, and that was wrong: the
split is now **derived** from whether a trace carries review evidence, and a folder cannot
name a standing that only the whole trace can decide. Reading the split is a computation over
the records, not a listing of a directory.

Two tiers remain, because the project/user axis is geographic. A project always has a project
index; a user may additionally register a user index — a full index that simply lives outside
the project folder, separating what ships with the project from what stays on this machine.
Reads span both; writes name one.

Anchor allocation lives here too. It is a directory scan plus a max — cheap, because the model's
own premise is that the index is human-paced and low-volume.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..config import Geography, TaravIndexError
from ..scope import LineScope
from .model import LineRecord

#: One sigil across the system. `d` separated the new index's labels from the anchory
#: anchors while the two label spaces were distinct; homogenizing the dossiers onto `c`
#: removed that distinction, so a second sigil would name a difference that is gone.
LABEL_SIGIL = "c"
USER_TAG = "u"
LABEL_RE = re.compile(r"^\^?(?P<sigil>[a-z])(?P<date>\d{8})-(?P<seq>\d+)(?P<tag>[a-z])$")


class RecordStoreError(TaravIndexError):
    """Raised when the store cannot satisfy a request."""


class Tier(str):
    """Where an index physically sits."""

    PROJECT = "project"
    USER = "user"


def normalize_label(label: str) -> str:
    return label if label.startswith("^") else f"^{label}"


def is_label(token: str) -> bool:
    return LABEL_RE.match(token) is not None


@dataclass(frozen=True, slots=True)
class IndexRoot:
    """One physical index: all the entries held at one tier."""

    path: Path
    tier: str

    def record_path(self, line_id: str) -> Path:
        return self.path / f"{line_id}.json"

    def exists(self) -> bool:
        return self.path.exists()

    def read_all(self) -> Iterator[LineRecord]:
        if not self.path.exists():
            return iter(())
        return (
            LineRecord.from_json(json.loads(p.read_text("utf-8")))
            for p in sorted(self.path.glob("*.json"))
        )


class IndexStore:
    """Every index root this project can see, project tier and user tier."""

    def __init__(self, geo: Geography) -> None:
        self._geo = geo

    # -- roots -----------------------------------------------------------------

    @property
    def project_index_dir(self) -> Path:
        return self._geo.project_tier / "index"

    @property
    def user_index_dir(self) -> Path:
        return self._geo.user_tier / "index"

    @property
    def directory(self) -> Path:
        return self.project_index_dir

    def root(self, tier: str = Tier.PROJECT) -> IndexRoot:
        base = self.project_index_dir if tier == Tier.PROJECT else self.user_index_dir
        return IndexRoot(path=base, tier=tier)

    def roots(self) -> list[IndexRoot]:
        """Every root, project tier first — reads span both tiers."""

        return [self.root(tier) for tier in (Tier.PROJECT, Tier.USER)]

    # -- reading ---------------------------------------------------------------

    def all(self, *, tier: str | None = None) -> list[LineRecord]:
        found: list[LineRecord] = []
        for root in self.roots():
            if tier is not None and root.tier != tier:
                continue
            found.extend(root.read_all())
        return found

    def locate(self, line_id: str) -> tuple[LineRecord, IndexRoot] | None:
        for root in self.roots():
            path = root.record_path(line_id)
            if path.exists():
                return LineRecord.from_json(json.loads(path.read_text("utf-8"))), root
        return None

    def get(self, line_id: str) -> LineRecord:
        found = self.locate(line_id)
        if found is None:
            raise RecordStoreError(f"no index entry with id {line_id!r}")
        return found[0]

    def find(self, line_id: str) -> LineRecord | None:
        found = self.locate(line_id)
        return found[0] if found else None

    def by_label(self, label: str) -> LineRecord | None:
        """Resolve a public label to its entry.

        A scan, deliberately: the second store that made this O(1) cost more than it saved.
        """

        normalized = normalize_label(label)
        return next((r for r in self.all() if r.line.label == normalized), None)

    def by_trace(self, trace_id: str) -> list[LineRecord]:
        """Every line carrying one indexed semantic."""

        return [r for r in self.all() if r.trace == trace_id]

    def by_scope(self, scope: LineScope | str) -> list[LineRecord]:
        address = scope if isinstance(scope, str) else scope.address
        return [r for r in self.all() if r.scope.address == address]

    def by_session(self, session_id: str) -> list[LineRecord]:
        return [r for r in self.all() if any(s.session_id == session_id for s in r.support)]

    def count(self) -> int:
        return len(self.all())

    # -- writing ---------------------------------------------------------------

    def put(self, record: LineRecord, *, tier: str = Tier.PROJECT) -> LineRecord:
        """Write an entry into its tier's root.

        If the entry already exists in another root — a tier move — the old file is removed
        so one entry never has two homes.
        """

        target = self.root(tier)
        target.path.mkdir(parents=True, exist_ok=True)

        for root in self.roots():
            if root.path == target.path:
                continue
            stale = root.record_path(record.id)
            if stale.exists():
                stale.unlink()

        target.record_path(record.id).write_text(
            json.dumps(record.to_json(), indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
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

        found = self.locate(line_id)
        if found is None:
            raise RecordStoreError(f"no index entry with id {line_id!r}")
        found[1].record_path(line_id).unlink()

    # -- anchors ---------------------------------------------------------------

    def mint_label(self, record: LineRecord, *, tier: str = Tier.PROJECT) -> LineRecord:
        """Allocate the next public label for today and stamp it on the entry.

        Idempotent: an entry that already carries a label keeps it.
        """

        if record.line.label:
            return record

        today = datetime.now(UTC).strftime("%Y%m%d")
        prefix = f"^{LABEL_SIGIL}{today}-"
        used: list[int] = []
        for existing in self.all():
            label = existing.line.label
            if label and label.startswith(prefix):
                match = LABEL_RE.match(label)
                if match:
                    used.append(int(match.group("seq")))

        labelled = record.relabel(f"{prefix}{max(used, default=-1) + 1}{USER_TAG}")
        return self.put(labelled, tier=tier)


__all__ = [
    "LABEL_RE",
    "LABEL_SIGIL",
    "USER_TAG",
    "IndexRoot",
    "IndexStore",
    "RecordStoreError",
    "Tier",
    "is_label",
    "normalize_label",
]
