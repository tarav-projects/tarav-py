"""Maintained identities for schemas and positions; consumers own their associations."""
# tarav.breadcrumb eb79f527c6b6
# tarav.breadcrumb 11e926e73222

from copy import deepcopy
from uuid import uuid4, uuid5

from pydantic import Field, JsonValue, field_validator
from tarav.l0.label_formats import JSONPointerFormat

from tarav.l0.kernel import (
    Ship, TaravClass, TaravEntity, TaravObject, TaravWorkflow, TypedState,
    TypeShip, WorkflowShip, entity,
)
from tarav.l0._core.persistence import atomic_write_json

PATHS_WORKFLOW_SHIP = WorkflowShip("01a1f680-b529-4a88-a002-bc114a5dc9da")


class PathRegistryWorkflow(TaravWorkflow):
    constitution = "Retain declared identities for JSON paths without inferring semantic continuity."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6261fbe1-3df5-4e1b-8ccd-f6d00b658495"),
                          name="Tarav.Workflow.PathRegistry", workflow=PATHS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return PATHS_WORKFLOW_SHIP


def json_paths(value, path=""):
    """RFC 6901 paths into this exact JSON value, including its root."""
    yield path
    pairs = value.items() if isinstance(value, dict) else enumerate(value) if isinstance(value, list) else ()
    for key, child in pairs:
        token = str(key).replace("~", "~0").replace("/", "~1")
        yield from json_paths(child, path + "/" + token)


class JSONView(TypedState, TaravEntity):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d84fb26f-8740-4bd4-a2a4-ac2c9f1230b8"),
                          name="Tarav.PathRegistry.JSONView", workflow=PATHS_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        owner: TypeShip
        name: str = Field(min_length=1)
        value: JsonValue

    def __init__(self, owner, name, value):
        owner = TypeShip(str(owner))
        super().__init__(Ship(uuid5(owner.uuid, "JSONView:" + name)))
        self.typed = self.records.parse_record({"type": entity(type(self)).name,
            "id": str(self.id), "owner": str(owner), "name": name, "value": deepcopy(value)})

    @classmethod
    def _from_record(cls, loaded):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.typed = loaded.data
        return obj

    @property
    def paths(self):
        return tuple(json_paths(self.typed.value))

    class Records(TaravEntity.Records):
        def record_example(self):
            return JSONView(entity(TaravObject).id, "record", {}).records.to_record()


class PathEntry(TypedState, TaravEntity):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("48ed2177-76fc-4a48-ad3f-2f44941d0840"),
                          name="Tarav.PathRegistry.Path", workflow=PATHS_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        view: Ship
        path: str | None = None
        active: bool = True

        @field_validator("path")
        @classmethod
        def valid_pointer(cls, value):
            # tarav.breadcrumb ff02d5f7d4f9
            if value is not None and not JSONPointerFormat.matches(value):
                raise ValueError("Path must be an RFC 6901 JSON Pointer")
            return value

    def __init__(self, view, path, *, id=None, active=True):
        super().__init__(id or Ship(uuid4()))
        self.typed = self.records.parse_record({"type": entity(type(self)).name,
            "id": str(self.id), "view": str(view), "path": path, "active": active})

    @classmethod
    def _from_record(cls, loaded):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.typed = loaded.data
        return obj

    class Records(TaravEntity.Records):
        def record_example(self):
            return {**super().record_example(), "id": "3909fe5f-f858-4501-ab73-4c90f2767bcc",
                    "view": "2001db37-4dd8-4ba8-a558-b092fa3725b8",
                    "path": "", "active": True}


class PathRegistry(TaravEntity):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("90f52291-606e-4edb-8016-daf41a360f20"),
                          name="Tarav.PathRegistry", workflow=PATHS_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        project: Ship
        views: list[JSONView.RecordInterface]
        entries: list[PathEntry.RecordInterface]

    def __init__(self, project, *, id=None, views=(), entries=()):
        project = Ship(str(project))
        super().__init__(id or Ship(uuid5(project.uuid, "PathRegistry")))
        self.project, self.views, self.entries = project, list(views), list(entries)

    def enroll(self, view):
        """Explicit first enrollment assigns fresh Ships; never updates existing maps."""
        if any(item.id == view.id for item in self.views):
            raise ValueError("View already enrolled; maintain its paths explicitly")
        self.views.append(view)
        created = [PathEntry(view.id, path) for path in view.paths]
        self.entries.extend(created)
        return tuple(created)

    def entry(self, ship):
        matches = [item for item in self.entries if item.id == Ship(str(ship))]
        if len(matches) != 1:
            raise ValueError("Path Ship must identify one entry")
        return matches[0]

    def at(self, view, path):
        """Return all active declarations, exposing ambiguity rather than picking one."""
        return tuple(entry for entry in self.entries
                     if entry.typed.active and entry.typed.view == Ship(str(view)) and entry.typed.path == path)

    def declare(self, ship, path, *, active=True):
        """Maintainer declares continuity by keeping this Ship."""
        entry = self.entry(ship)
        data = {**entry.records.to_record(), "path": path, "active": active}
        entry.typed = entry.records.parse_record(data)

    def add(self, view, path):
        entry = PathEntry(view, path)
        self.entries.append(entry)
        return entry

    def retire(self, ship):
        self.declare(ship, None, active=False)

    def retire_view(self, view):
        """End maintenance of a View, retaining its retired path identities."""
        view = Ship(str(view))
        if not any(item.id == view for item in self.views):
            raise ValueError("View is not enrolled")
        for entry in self.entries:
            if entry.typed.view == view:
                self.retire(entry.id)
        self.views = [item for item in self.views if item.id != view]

    def accept(self, view):
        """Record the accepted schema without changing any path identities."""
        index = next((i for i, old in enumerate(self.views) if old.id == view.id), None)
        if index is None:
            raise ValueError("Enroll the View before accepting a new value")
        self.views[index] = view

    def save(self, path):
        atomic_write_json(path, self.records.to_record())

    @classmethod
    def _from_record(cls, loaded):
        return cls(loaded.data.project, id=loaded.data.id,
            views=[JSONView.records.from_record(value.model_dump(mode="json")) for value in loaded.data.views],
            entries=[PathEntry.records.from_record(value.model_dump(mode="json")) for value in loaded.data.entries])

    def _to_record(self):
        return {**super()._to_record(), "project": str(self.project),
                "views": [v.records.to_record() for v in self.views],
                "entries": [e.records.to_record() for e in self.entries]}

    class Records(TaravEntity.Records):
        def record_example(self):
            return PathRegistry("2ea41fe7-1775-470a-b89f-05b339f2377e").records.to_record()


PATH_REGISTRY_TYPES = (JSONView, PathEntry, PathRegistry)
