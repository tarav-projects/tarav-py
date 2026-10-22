"""Line state references reconstruct bounded authoring context from one Git commit."""

import json
from functools import lru_cache
from pathlib import Path, PurePosixPath

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l0.kernel.current import current_records
from tarav.l1.grounding import SubjectState
from tarav.l1.lines import Block, Line
from tarav.l1.references.git import GitFileReference, git_file, git_text

from .workflow import NOTEBOOK_WORKFLOW_SHIP


@lru_cache(maxsize=2048)
def _record(repository, commit, ship):
    _, content = git_file(repository, commit, f"records/{ship}.json")
    record = json.loads(content)
    if record.get("id") != ship:
        raise ValueError("Historical Notebook filename and Ship disagree")
    return record


class NotebookStateReference(GitFileReference):
    """One Line and its authoring context at an exact Notebook Git commit."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("31af41be-b6ae-4baf-971f-2476a8e179a6"),
                          name="Tarav.Notebook.Reference.State", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, *, notebook, commit, ship):
        root = str(Path(notebook).resolve())
        exact = git_text(root, "rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}")
        super().__init__({"type": entity(type(self)).name, "locator": {
            "repository": root, "commit": exact, "path": f"records/{Ship(str(ship))}.json"}})

    def _bind_record_loader(self, loader):
        self._record_loader = loader

    def locate(self, locator):
        target = super().locate(locator)
        path = PurePosixPath(locator["path"])
        ship = str(Ship(path.stem))
        if path.as_posix() != f"records/{ship}.json":
            raise ValueError("Notebook state must name one Line record")
        repository, commit = locator["repository"], locator["commit"]
        if commit != git_text(repository, "rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}"):
            raise ValueError("Notebook state requires an exact commit, not a moving revision")
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
        return {**target, "state": SubjectState(line.id, entity(type(line)).id,
                                                {"text": line.text, "context": context[::-1]})}

    def ships(self):
        return (*super().ships(), Ship(PurePosixPath(self.locator["path"]).stem))

    class Records(GitFileReference.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "locator": {
                "repository": "/example/notebook", "commit": "0" * 40,
                "path": "records/ba962e69-2835-436f-b5c4-3e77105b6d79.json"}}
