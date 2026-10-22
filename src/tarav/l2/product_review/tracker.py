"""Explicit batch maintenance and token-backed completion over existing maps."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from uuid import uuid4

from filelock import FileLock

from tarav.l0.kernel import entity
from tarav.l1.chatlas.normal_model import provide_normal_model, resolve_chat_turn_ref
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.chatlas.turn_snapshots import TurnSnapshotStore
from tarav.l1.git.repository import git_text
from tarav.l1.product_review import (
    Batch, BatchRevision, ReviewCompletion, ProductReviewWorkflow, PRODUCT_REVIEW_SHIP,
)
from tarav.l1.records.registry import RecordMap, RecordRegistry


def now_text():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build(cls, **values):
    return cls.records.from_record({"type": entity(cls).name, **values})


# tarav.breadcrumb 0bd6e4b384e8
class ReviewTracker:
    def __init__(self, mapper, *, root=None, records=None, horizon_days=5):
        if type(horizon_days) is not int or horizon_days < 0:
            raise ValueError("Review horizon days must be a nonnegative integer")
        self.mapper = mapper
        self.horizon_days = horizon_days
        self.repository_id = mapper.repository_id
        self.store = (RecordMap(Path(root), PRODUCT_REVIEW_SHIP, records) if root is not None
                      else RecordRegistry(records=records).for_workflow(ProductReviewWorkflow))

    def create(self):
        self.store.create()
        return self

    def batches(self, *, retired=False):
        if not self.store.marker.exists():
            return ()
        result = []
        for key in self.store.names():
            if key.startswith("batch-"):
                batch = self.store.load(key)
                if not isinstance(batch, Batch):
                    raise ValueError("Batch key has the wrong Record Type")
                if batch.typed.repository_id == self.repository_id and (retired or not batch.typed.retired):
                    result.append(batch)
        return tuple(result)

    def batch(self, identity):
        result = self.store.load("batch-" + identity)
        if not isinstance(result, Batch) or result.typed.id != identity:
            raise ValueError("Batch identity or Type mismatch")
        if result.typed.repository_id != self.repository_id:
            raise ValueError("Batch belongs to another repository")
        return result

    def revision(self, identity):
        result = self.store.load("revision-" + identity)
        if not isinstance(result, BatchRevision) or result.typed.id != identity:
            raise ValueError("Revision identity or Type mismatch")
        if result.typed.repository_id != self.repository_id:
            raise ValueError("Revision belongs to another repository")
        mapping = self.mapper.load(result.typed.map_id)
        chunks = {c.id: c.model_dump() for c in mapping.typed.chunks}
        if (result.typed.commit != mapping.typed.commit
                or any(c.model_dump() != chunks.get(c.id) for c in result.typed.chunks)):
            raise ValueError("Batch revision differs from its pinned committed map")
        return result

    def current(self, batch_id):
        return self.revision(self.batch(batch_id).typed.revisions[-1])

    def select_map(self, *, map_id=None, horizon_days=None, now=None):
        if map_id is not None:
            return self.mapper.load(map_id)
        horizon_days = self.horizon_days if horizon_days is None else horizon_days
        if type(horizon_days) is not int or horizon_days < 0:
            raise ValueError("Review horizon days must be nonnegative")
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=horizon_days)
        history = self.mapper.history()
        if not history:
            raise ValueError("No confirmed Product Map is available")
        # HEAD's ancestry order, not confirmation order, selects the newest eligible commit.
        ancestors = git_text(self.mapper.product.root, "rev-list", "--timestamp", "HEAD").splitlines()
        rank = {line.split()[1]: i for i, line in enumerate(ancestors)}
        dates = {line.split()[1]: int(line.split()[0]) for line in ancestors}
        eligible = [m for identity in history if (m := self.mapper.load(identity)).typed.commit in rank
                    and dates[m.typed.commit] <= cutoff.timestamp()]
        if not eligible:
            raise ValueError("No confirmed Product Map is old enough for the review horizon")
        return min(reversed(eligible), key=lambda m: rank[m.typed.commit])

    def _revision(self, *, batch_id, base, map_id, chunk_ids, title, purpose, actor, reason):
        mapping = self.mapper.load(map_id)
        chunks = {c.id: c for c in mapping.typed.chunks}
        if len(set(chunk_ids)) != len(chunk_ids) or not chunk_ids:
            raise ValueError("Select a nonempty set of unique chunk IDs")
        if not set(chunk_ids) <= chunks.keys():
            raise ValueError("Selected chunk is absent from the pinned map")
        return build(BatchRevision, id=str(uuid4()), batch_id=batch_id,
                     repository_id=self.repository_id, base=base, map_id=map_id,
                     commit=mapping.typed.commit, title=title, purpose=purpose,
                     chunks=[chunks[c].model_dump() for c in sorted(chunk_ids)],
                     created_at=now_text(), actor=actor, reason=reason)

    def create_batch(self, *, map_id, chunk_ids, title, purpose, actor, reason):
        self.store.open()
        identity = str(uuid4())
        revision = self._revision(batch_id=identity, base=None, map_id=map_id, chunk_ids=chunk_ids,
                                  title=title, purpose=purpose, actor=actor, reason=reason)
        batch = build(Batch, id=identity, repository_id=self.repository_id,
                      revisions=[revision.typed.id])
        with FileLock(str(self.store.root) + ".review.lock"):
            self.store.insert("revision-" + revision.typed.id, revision)
            self.store.insert("batch-" + identity, batch)
        return batch

    def revise(self, batch_id, *, base, map_id, chunk_ids, actor, reason, title=None, purpose=None):
        with FileLock(str(self.store.root) + ".review.lock"):
            batch = self.batch(batch_id)
            previous = self.current(batch_id)
            if batch.typed.retired:
                raise ValueError("Cannot revise a retired batch")
            if previous.typed.id != base:
                raise ValueError("Stale batch revision: reload the current revision")
            revision = self._revision(batch_id=batch_id, base=base, map_id=map_id,
                                      chunk_ids=chunk_ids, actor=actor, reason=reason,
                                      title=previous.typed.title if title is None else title,
                                      purpose=previous.typed.purpose if purpose is None else purpose)
            self.store.insert("revision-" + revision.typed.id, revision)
            batch.typed.revisions.append(revision.typed.id)
            self.store.replace("batch-" + batch_id, batch)
        return revision

    def retire(self, batch_id, *, actor, reason):
        with FileLock(str(self.store.root) + ".review.lock"):
            batch = self.batch(batch_id)
            if batch.typed.retired:
                raise ValueError("Batch is already retired")
            data = batch.records.to_record()
            data.update(retired=True, retired_at=now_text(), retired_by=actor, retirement_reason=reason)
            batch = Batch.records.from_record(data)
            self.store.replace("batch-" + batch_id, batch)
        return batch

    def completion(self, revision_id):
        if not self.store.path("completion-" + revision_id).exists():
            return None
        result = self.store.load("completion-" + revision_id)
        if (not isinstance(result, ReviewCompletion) or result.typed.revision_id != revision_id
                or result.typed.repository_id != self.repository_id):
            raise ValueError("Review completion identity or Type mismatch")
        return result

    def presentation(self, revision_id):
        revision = self.revision(revision_id).typed
        lines = ["Product review completion", f"Batch: {revision.batch_id}",
                 f"Revision: {revision.id}", f"Map: {revision.map_id}", f"Commit: {revision.commit}",
                 f"Title: {revision.title}", f"Purpose: {revision.purpose}", "Chunks:"]
        lines.extend(f"- {c.id}: {c.path} bytes [{c.start}, {c.end}) sha256 {c.sha256}" for c in revision.chunks)
        lines.extend(["Review discussion and outcomes captured; follow-up work may remain open.",
                      f"::reviewed review:{revision.id}"])
        return "\n".join(lines)

    # tarav.breadcrumb 442372a29caa
    def complete(self, revision_id, *, presentation, completion, outcomes=()):
        revision = self.revision(revision_id)
        if not all(isinstance(ref, ChatlasTurnReference) for ref in (presentation, completion)):
            raise ValueError("Review evidence must reference exact Chatlas Turns")
        p, u = presentation.turn_result(), completion.turn_result()
        if p["standing"] != "MATCHED" or u["standing"] != "MATCHED":
            raise ValueError("Review evidence is unavailable or amended")
        if p["turn"]["side"] != "agent" or u["turn"]["side"] != "user":
            raise ValueError("Review needs an Agent presentation and a User completion")
        if (presentation.locator["session_identity"] != completion.locator["session_identity"]
                or presentation.order_key(p) >= completion.order_key(u)):
            raise ValueError("User completion must follow presentation in the same session")
        ptext = "\n".join(m["text"] for m in p["messages"])
        utext = "\n".join(m["text"] for m in u["messages"])
        token = "review:" + revision_id
        if (" ".join(self.presentation(revision_id).split()) not in " ".join(ptext.split())
                or re.search(rf"(?m)^\s*::reviewed {re.escape(token)}\s*$", utext) is None):
            raise ValueError("The User must issue the exact presented review-completion token")
        result = build(ReviewCompletion, id=str(uuid4()), revision_id=revision_id,
                       repository_id=self.repository_id, token=token, completed_at=now_text(),
                       presentation=presentation.records.to_record(), completion=completion.records.to_record(),
                       outcomes=[ref.records.to_record() for ref in outcomes])
        with FileLock(str(self.store.root) + ".review.lock"):
            batch = self.batch(revision.typed.batch_id)
            if batch.typed.retired or batch.typed.revisions[-1] != revision_id:
                raise ValueError("Cannot complete a retired or superseded batch revision")
            for reference in (presentation, completion):
                snapshots = TurnSnapshotStore()
                if snapshots.find(reference.locator) is None:
                    model = provide_normal_model(identity_hash=reference.locator["session_identity"])
                    target = resolve_chat_turn_ref(model["turns"], reference.locator)
                    if target["standing"] != "MATCHED":
                        raise ValueError("Exact review evidence cannot be retained")
                    snapshots.retain(model, target["turn"])
            self.store.insert("completion-" + revision_id, result)
        return result

    @staticmethod
    def _state(chunk):
        # A blob changing elsewhere in the file does not change these chunk bytes.
        return chunk.id, chunk.path, chunk.start, chunk.end, chunk.sha256

    def inspect(self, *, map_id=None, horizon_days=None, now=None):
        mapping = self.select_map(map_id=map_id, horizon_days=horizon_days, now=now)
        current = {c.id: c for c in mapping.typed.chunks}
        covered, batches = set(), []
        for batch in self.batches():
            revision = self.current(batch.typed.id)
            changed = [c.id for c in revision.typed.chunks
                       if c.id not in current or self._state(c) != self._state(current[c.id])]
            covered.update(c.id for c in revision.typed.chunks if c.id in current)
            completed = self.completion(revision.typed.id)
            batches.append({"batch_id": batch.typed.id, "revision_id": revision.typed.id,
                            "title": revision.typed.title, "map_id": revision.typed.map_id,
                            "state": "stale" if changed else "reviewed" if completed else "pending",
                            "changed_chunks": changed,
                            "completion": completed.typed.id if completed else None})
        return {"repository_id": self.repository_id, "map_id": mapping.typed.id,
                "commit": mapping.typed.commit, "chunks": len(current),
                "uncovered": sorted(current.keys() - covered), "batches": batches}

    def read(self, revision_id):
        """Expand the exact pinned committed material without reading the worktree."""
        revision = self.revision(revision_id)
        return [{"chunk": c.model_dump(), "content": self.mapper.read_chunk(
            c.id, at=revision.typed.map_id)} for c in revision.typed.chunks]

    def history(self, batch_id):
        return [{"revision": self.revision(identity).records.to_record(),
                 "completion": result.records.to_record() if (result := self.completion(identity)) else None}
                for identity in self.batch(batch_id).typed.revisions]
