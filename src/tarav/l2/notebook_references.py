"""Line state references reconstruct bounded authoring context from one Git commit."""
# tarav.breadcrumb 98fc3b130fdc

import json
from functools import lru_cache
from pathlib import PurePosixPath

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l0.kernel.current import current_records
from tarav.l1.grounding import SubjectState
from tarav.l1.lines import Block, Line
from tarav.l1.archive.references import RepositoryLocator, RepositoryReference
from tarav.l1.references import Reference
from tarav.l1.references.git import git_file
from tarav.l2.git.archive import resolve_repository

from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP


class NotebookStateLocator(RepositoryLocator):
    path: str


@lru_cache(maxsize=2048)
def _record(repository, commit, ship):
    _, content = git_file(repository, commit, f"records/{ship}.json")
    record = json.loads(content)
    if record.get("id") != ship:
        raise ValueError("Historical Notebook filename and Ship disagree")
    return record


class NotebookStateReference(Reference):
    """One Line and its authoring context at an exact Notebook Git commit."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("31af41be-b6ae-4baf-971f-2476a8e179a6"),
                          name="Tarav.Notebook.Reference.State", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(Reference.RecordInterface):
        locator: NotebookStateLocator
        check: None = None

    def __init__(self, record):
        super().__init__()
        self._fields = dict(record)
        self.records.parse_record(self._fields)

    def _bind_record_loader(self, loader):
        self._records = getattr(loader, "__self__", None)
        self._record_loader = loader

    def check_target(self, target, check):
        if check is not None:
            raise ValueError("Notebook state verification is defined by its repository coordinates")
        return True

    def locate(self, locator):
        # This Type is the explicit Git consumer; Archive lookup stays declarative.
        reference = RepositoryReference({"type": entity(RepositoryReference).name,
                                         "locator": locator})
        reference._records = getattr(self, "_records", None)
        resolved = resolve_repository(reference)
        if not resolved.ok:
            raise ValueError(resolved.message)
        target = resolved.target
        path = PurePosixPath(locator["path"])
        ship = str(Ship(path.stem))
        if path.as_posix() != f"records/{ship}.json":
            raise ValueError("Notebook state must name one Line record")
        repository, commit = str(target.repository), target.commit
        loader = getattr(self, "_record_loader", None) or current_records().from_record

        def load(identity):
            return loader(_record(repository, commit, identity))

        line = load(ship)
        if not isinstance(line, Line):
            raise ValueError("Notebook state requires a Line")
        context, seen = [], set()
        identity = str(line.scope_ship)
        while identity:
            if identity in seen:
                raise ValueError("Historical Block ancestry cycle")
            seen.add(identity)
            block = load(identity)
            if not isinstance(block, Block):
                raise ValueError("Historical Line context must be a Block")
            peers = []
            for member_ship in block.content_ships:
                member = load(str(member_ship))
                if isinstance(member, Line) and member.id != line.id:
                    peers.append({"ship": str(member.id), "type": str(entity(type(member)).id),
                                  "text": member.text})
            context.append({"ship": identity, "type": str(entity(type(block)).id), "lines": peers})
            identity = str(block.parent_ship) if block.parent_ship else ""
        return {"repository": repository, "commit": commit, "path": locator["path"],
                "git_oid": target.git_oid, "content": target.content,
                "recovered": target.recovered,
                "state": SubjectState(line.id, entity(type(line)).id,
                                                {"text": line.text, "context": context[::-1]})}

    def ships(self):
        return (*super().ships(), Ship(PurePosixPath(self.locator["path"]).stem))

    class Records(Reference.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "locator": {
                "registry": "/example/registry", "doi": "a" * 64,
                "commit": "0" * 40, "tree": "1" * 40,
                "path": "records/ba962e69-2835-436f-b5c4-3e77105b6d79.json"}}
