"""Explicit proposal/confirmation over endpoint Git states and standard Records."""

from collections import defaultdict
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from filelock import FileLock

from tarav.l0.kernel import LoadedRecord, TaravClass, TaravObject, TypeShip
from tarav.l1.git.repository import git_bytes
from tarav.l1.records.registry import RecordMap, RecordRegistry

from .alignment import chunk, partition, reconcile_file
from .git import CommittedProduct
from .model import (ContinuityDecision, MappingProposal, MappingTrack, ProductMap,
                    SkippedSurface, build)
from .workflow import PRODUCT_MAPPING_SHIP, ProductMappingWorkflow


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# tarav.breadcrumb f4c958be0f29
class ProductMapper(TaravObject):
    """One repository's maintained mapping stream, with no semantic parser."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8c7c18a6-e6e8-4900-9c6e-aa199ecbf878"),
                          name="Tarav.ProductMapping.Mapper", workflow=PRODUCT_MAPPING_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        repository: str
        repository_id: str
        root: str

    def __init__(self, repository, repository_id, *, root=None, records=None):
        super().__init__()
        if not isinstance(repository_id, str) or not repository_id.strip():
            raise ValueError("An explicit repository identity is required")
        self.repository = Path(repository).expanduser().resolve()
        self._product = None
        self.repository_id = repository_id
        self.store = (RecordMap(Path(root), PRODUCT_MAPPING_SHIP, records) if root is not None
                      else RecordRegistry(records=records).for_workflow(ProductMappingWorkflow))
        self.track_key = "track-" + sha256(repository_id.encode()).hexdigest()

    def _to_record(self):
        return {**super()._to_record(), "repository": str(self.repository),
                "repository_id": self.repository_id, "root": str(self.store.root)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.repository, loaded.data.repository_id, root=loaded.data.root)

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "repository": "/example/product",
                    "repository_id": "example-repository", "root": "/example/maps"}

    @property
    def product(self):
        if self._product is None:
            self._product = CommittedProduct(self.repository)
        return self._product

    def track(self):
        if not self.store.marker.exists():
            return None
        if not self.store.path(self.track_key).exists():
            return None
        obj = self.store.load(self.track_key)
        if not isinstance(obj, MappingTrack) or obj.typed.repository_id != self.repository_id:
            raise ValueError("Mapping track identity or Type mismatch")
        return obj

    def create(self, *, target_bytes=4096, boundary_bytes=256, include=None, exclude=None):
        data = build(MappingTrack, repository_id=self.repository_id, target_bytes=target_bytes,
                     boundary_bytes=boundary_bytes, include=["*"] if include is None else include,
                     exclude=[] if exclude is None else exclude, maps=[], issued_ids=[])
        self.store.create()
        self.store.insert(self.track_key, data)
        return self

    def load(self, identity):
        obj = self.store.load(identity)
        if not isinstance(obj, ProductMap) or obj.typed.id != identity:
            raise ValueError("Map identity or Type mismatch")
        if obj.typed.repository_id != self.repository_id:
            raise ValueError("Map belongs to another repository")
        return obj

    def latest(self):
        track = self.track()
        return self.load(track.typed.maps[-1]) if track and track.typed.maps else None

    def inventory(self, commit, track=None):
        data = (track or self.track()).typed
        selected = {path: surface for path, surface in self.product.inventory(commit).items()
                    if any(fnmatchcase(path, pattern) for pattern in data.include)
                    and not any(fnmatchcase(path, pattern) for pattern in data.exclude)}
        regular = {p: s for p, s in selected.items() if s.mode in {"100644", "100755"}}
        skipped = [SkippedSurface(path=p, mode=s.mode, oid=s.oid)
                   for p, s in selected.items() if p not in regular]
        return regular, skipped

    def _renames(self, before, after):
        raw = git_bytes(self.product.root, "diff", "--no-ext-diff", "--no-textconv",
                        "--name-status", "-z", "-M", before, after)
        fields = iter(raw.split(b"\0"))
        result = {}
        for status in fields:
            if not status:
                continue
            path = next(fields).decode("utf-8", errors="surrogateescape")
            if status.startswith((b"R", b"C")):
                destination = next(fields).decode("utf-8", errors="surrogateescape")
                if status.startswith(b"R"):
                    result[path] = destination
        return result

    def propose(self, target="HEAD"):
        track = self.track()
        if track is None:
            raise ValueError("Create an explicit mapping track before proposing")
        commit = self.product.exact(target)
        regular, skipped = self.inventory(commit, track)
        previous = self.latest()
        old_files = defaultdict(list)
        if previous:
            for item in previous.typed.chunks:
                old_files[item.path].append(item)
        renames = self._renames(previous.typed.commit, commit) if previous else {}
        # Only a unique disappeared blob can propose continuity into a new file.
        missing_by_blob = defaultdict(list)
        for path, items in old_files.items():
            if path not in regular:
                missing_by_blob[items[0].blob].append(path)
        destinations = defaultdict(list)
        for path, surface in regular.items():
            if path not in old_files:
                destinations[surface.oid].append(path)
        for oid, paths in missing_by_blob.items():
            if len(paths) == 1 and len(destinations[oid]) == 1:
                renames.setdefault(paths[0], destinations[oid][0])
        sources = {new: old for old, new in renames.items() if old not in regular}
        chunks = []
        with self.product.batch():
            for path, surface in sorted(regular.items()):
                content = self.product.blob(surface.oid)
                old = old_files.get(path) or old_files.get(sources.get(path))
                if old:
                    chunks.extend(reconcile_file(old, path, surface.oid,
                                                 self.product.blob(old[0].blob), content))
                else:
                    chunks.extend(chunk(path, surface.oid, content, a, b)
                                  for a, b in partition(content, track.typed.target_bytes,
                                                        track.typed.boundary_bytes))
        return build(MappingProposal, repository_id=self.repository_id,
                     base=previous.typed.id if previous else None, commit=commit,
                     tree=self.product.tree(commit), chunks=chunks, skipped=skipped)

    def changes(self, proposal):
        """Return exact changed states, without interpreting identity continuity."""
        previous = self.load(proposal.typed.base) if proposal.typed.base else None
        old = {item.id: item for item in previous.typed.chunks} if previous else {}
        new = {item.id: item for item in proposal.typed.chunks}
        result = []
        for identity in sorted(old.keys() | new.keys()):
            a, b = old.get(identity), new.get(identity)
            if a == b:
                continue
            kind = ("new" if a is None else "retired" if b is None else
                    "moved" if a.sha256 == b.sha256 else "edited")
            result.append({"id": identity, "kind": kind,
                           "before": a.model_dump() if a else None,
                           "after": b.model_dump() if b else None})
        return result

    def audit(self, candidate):
        """Verify exact inventory, fingerprints and full nonoverlapping byte coverage."""
        data = candidate.typed
        if data.repository_id != self.repository_id:
            raise ValueError("Map repository identity mismatch")
        if self.product.tree(data.commit) != data.tree:
            raise ValueError("Map tree does not match its commit")
        regular, skipped = self.inventory(data.commit)
        if sorted((s.path, s.mode, s.oid) for s in skipped) != sorted(
                (s.path, s.mode, s.oid) for s in data.skipped):
            raise ValueError("Skipped surface inventory mismatch")
        grouped = defaultdict(list)
        identities = set()
        for item in data.chunks:
            if item.id in identities:
                raise ValueError("Duplicate chunk identity")
            identities.add(item.id)
            grouped[item.path].append(item)
        if grouped.keys() != regular.keys():
            raise ValueError("Map does not cover exactly the selected regular files")
        total = 0
        with self.product.batch():
            for path, surface in regular.items():
                content = self.product.blob(surface.oid)
                position = 0
                items = sorted(grouped[path], key=lambda c: c.start)
                for item in items:
                    if (item.blob != surface.oid or item.start != position or
                            item.end < item.start or item.end > len(content) or
                            (item.start == item.end and (content or len(items) != 1))):
                        raise ValueError(f"Invalid chunk range, gap, overlap or blob in {path}")
                    if sha256(content[item.start:item.end]).hexdigest() != item.sha256:
                        raise ValueError(f"Chunk fingerprint mismatch in {path}")
                    position = item.end
                if position != len(content):
                    raise ValueError(f"Uncovered bytes in {path}")
                total += len(content)
        return {"files": len(regular), "chunks": len(data.chunks), "bytes": total,
                "skipped": len(skipped), "commit": data.commit}

    # tarav.breadcrumb 0d81a252b4d8
    def confirm(self, proposal, *, decisions, actor, reason):
        if not isinstance(proposal, MappingProposal):
            raise TypeError("Confirmation requires a MappingProposal")
        decisions = [d if isinstance(d, ContinuityDecision) else
                     ContinuityDecision.model_validate(d) for d in decisions]
        # Separate lock serializes the multi-Record transition without nesting store locks.
        with FileLock(str(self.store.root) + ".mapping.lock"):
            track = self.track()
            if track is None:
                raise ValueError("Mapping track is not initialized")
            expected = track.typed.maps[-1] if track.typed.maps else None
            if proposal.typed.base != expected:
                raise ValueError("Stale proposal: mapping stream has advanced")
            self.audit(proposal)
            changes = self.changes(proposal)
            old = {change["id"] for change in changes if change["before"] is not None}
            new = {change["id"] for change in changes if change["after"] is not None}
            seen_old, seen_new = set(), set()
            for decision in decisions:
                a, b = set(decision.source_ids), set(decision.target_ids)
                if (not a and not b or len(a) != len(decision.source_ids)
                        or len(b) != len(decision.target_ids) or a & seen_old or b & seen_new
                        or not a <= old or not b <= new):
                    raise ValueError("Invalid, duplicate or unrelated continuity decision")
                if (a & new) - b or (b & old) - a:
                    raise ValueError("Retained IDs must occur on both sides of the same decision")
                seen_old.update(a)
                seen_new.update(b)
            if seen_old != old or seen_new != new:
                raise ValueError("Every changed, new or retired chunk needs an explicit decision")
            previous = self.latest()
            previous_ids = {c.id for c in previous.typed.chunks} if previous else set()
            new_ids = {c.id for c in proposal.typed.chunks} - previous_ids
            if new_ids & set(track.typed.issued_ids):
                raise ValueError("A retired chunk ID cannot be reused")
            result = build(ProductMap, **{k: v for k, v in proposal.records.to_record().items()
                                         if k != "type"}, id=str(uuid4()),
                           confirmed_at=utc_now(), actor=actor, reason=reason,
                           decisions=[d.model_dump() for d in decisions])
            self.store.insert(result.typed.id, result)
            track.typed.maps.append(result.typed.id)
            track.typed.issued_ids.extend(sorted(new_ids))
            self.store.replace(self.track_key, track)
        return result

    def history(self):
        track = self.track()
        return tuple(track.typed.maps) if track else ()

    def locate(self, chunk_id, *, at=None):
        """Locate an ID in the latest or explicitly pinned map, never another revision."""
        selected = self.load(at) if at else self.latest()
        if selected:
            for item in selected.typed.chunks:
                if item.id == chunk_id:
                    return item
        raise ValueError(f"Chunk is absent from the selected map: {chunk_id}")

    def read_chunk(self, chunk_id, *, at=None):
        """Return exact committed bytes; an explicit map ID pins the content state."""
        selected = self.locate(chunk_id, at=at)
        content = self.product.blob(selected.blob)[selected.start:selected.end]
        if (len(content) != selected.end - selected.start or
                sha256(content).hexdigest() != selected.sha256):
            raise ValueError("Chunk bytes do not match the recorded state")
        return content

    def chunk_history(self, chunk_id):
        """Expand recorded versions and creation/continuity/retirement decisions."""
        result = []
        for identity in self.history():
            mapping = self.load(identity).typed
            chunk = next((c for c in mapping.chunks if c.id == chunk_id), None)
            decisions = [d.model_dump() for d in mapping.decisions
                         if chunk_id in d.source_ids or chunk_id in d.target_ids]
            if chunk is not None or decisions:
                result.append({"map": identity, "commit": mapping.commit,
                               "chunk": chunk.model_dump() if chunk is not None else None,
                               "decisions": decisions})
        return result
