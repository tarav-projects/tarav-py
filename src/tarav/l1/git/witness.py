"""The witness of tarav-change IDs, kept outside the repositories it watches.

`.tarav/changes` is append-only, but a history rewrite can cut it, and the
repository then shows nothing. The witness remembers, per Project and
branch, which IDs the branch had at its last commit, so the next commit or
check can tell that some are gone. It is machine-local and best effort: it
finds nothing new, it only notices a loss.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from pydantic import ConfigDict

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TaravObject, TypeShip, entity

from .workflow import GIT_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord

WITNESS_ENV_VAR = "TARAV_GIT_CHANGES_ROOT"


# tarav.breadcrumb 709971905b10
# tarav.breadcrumb 46dd1f5a78f3
class ChangeWitness(TaravObject):
    """The tarav-change IDs one branch of one Project had at its last commit."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3d8f1a64-b27c-4e90-a5d3-71c6e9b04f28"),
                          name="Tarav.Git.Change.Witness", workflow=GIT_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Git.Change.Witness"]
        project: str
        branch: str
        changes: list[str]
        at: str

    def __init__(self, *, project: str, branch: str, changes: list[str], at: str) -> None:
        super().__init__()
        self.project, self.branch, self.changes, self.at = project, branch, list(changes), at

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(project=loaded.data.project, branch=loaded.data.branch,
                   changes=loaded.data.changes, at=loaded.data.at)

    def _to_record(self):
        return {"type": entity(type(self)).name, "project": self.project, "branch": self.branch,
                "changes": list(self.changes), "at": self.at}

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "project": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
                    "branch": "main", "changes": ["63736466-86f6-4d42-b164-8e7c56502a20"],
                    "at": "2026-10-16T00:00:00+00:00"}


# tarav.breadcrumb 38a87f208df1
class ChangeOverrule(TaravEntity):
    """A commit that went through although IDs the witness held were gone."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9b4e2c71-6f08-4d35-8a1e-c5d7f3b92e60"),
                          name="Tarav.Git.Change.Overrule", workflow=GIT_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Git.Change.Overrule"]
        project: str
        branch: str
        commit: str
        missing: list[str]
        at: str

    def __init__(self, id: Ship, *, project: str, branch: str, commit: str, missing: list[str],
                 at: str) -> None:
        super().__init__(id)
        self.project, self.branch, self.commit = project, branch, commit
        self.missing, self.at = list(missing), at

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.id, project=loaded.data.project, branch=loaded.data.branch,
                   commit=loaded.data.commit, missing=loaded.data.missing, at=loaded.data.at)

    def _to_record(self):
        return {**super()._to_record(), "project": self.project, "branch": self.branch,
                "commit": self.commit, "missing": list(self.missing), "at": self.at}

    class Records(TaravEntity.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "id": "4c0b6e1d-93a2-4f57-b8d1-2e6a9f0c7b35",
                    "project": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94", "branch": "main",
                    "commit": "0c6a7501c6caace13e15a00add8d0995d52ff1e6",
                    "missing": ["63736466-86f6-4d42-b164-8e7c56502a20"],
                    "at": "2026-10-16T00:00:00+00:00"}


class ChangeWitnesses:
    """The witness depot: one witness per Project and branch, and the overrules."""

    def __init__(self, root: Path | str | None = None) -> None:
        override = os.environ.get(WITNESS_ENV_VAR)
        chosen = root if root is not None else override or default_tarav_data_root() / "git-changes"
        self.root = Path(chosen).expanduser().resolve()

    def _branch_path(self, project: str, branch: str) -> Path:
        return self.root / project / "branches" / f"{quote(branch, safe='')}.json"

    def get(self, project: str, branch: str) -> ChangeWitness | None:
        path = self._branch_path(project, branch)
        if not path.is_file():
            return None
        return ChangeWitness.records.from_record(json.loads(path.read_text(encoding="utf-8")))

    def put(self, witness: ChangeWitness) -> None:
        path = self._branch_path(witness.project, witness.branch)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_json(path, witness.records.to_record(), ensure_ascii=False)

    def add_overrule(self, overrule: ChangeOverrule) -> None:
        folder = self.root / overrule.project / "overrules"
        folder.mkdir(parents=True, exist_ok=True)
        text = json.dumps(overrule.records.to_record(), ensure_ascii=False, indent=2) + "\n"
        with (folder / f"{overrule.id}.json").open("x", encoding="utf-8") as handle:
            handle.write(text)

    def overrules(self, project: str) -> list[ChangeOverrule]:
        folder = self.root / project / "overrules"
        paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
        return [ChangeOverrule.records.from_record(json.loads(path.read_text(encoding="utf-8")))
                for path in paths]


GIT_WITNESS_RECORD_TYPES = (ChangeWitness, ChangeOverrule)

__all__ = ["ChangeOverrule", "ChangeWitness", "ChangeWitnesses", "GIT_WITNESS_RECORD_TYPES",
           "WITNESS_ENV_VAR"]
