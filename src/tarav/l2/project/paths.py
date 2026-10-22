"""Project ownership, schema production and Action lifecycle for path maintenance."""
# tarav.breadcrumb 111a9285c967

from tarav.l0.kernel import NamespaceBase, TaravClass, TypeShip, entity
from tarav.l1.checks import Check, CheckResult, CheckSuite, SuiteCheckpoint
from tarav.l1.path_registry import JSONView, PATHS_WORKFLOW_SHIP, PathRegistry
from tarav.l1.path_registry.checks import RegistryCheck


class PathsManager(NamespaceBase):
    @property
    def file(self):
        return self.obj.root / ".tarav/paths.json"

    def views(self):
        """Computed structure only; no persistence or identity maintenance."""
        return tuple(JSONView(entity(cls).id, name, value)
                     for cls in self.obj.types.all()
                     for name, value in cls.view_schemas().items())

    def open(self):
        if not self.file.exists():
            return PathRegistry(self.obj.id)
        registry = self.obj.records.types.load(self.file, expected_type=PathRegistry)
        if registry.project != self.obj.id:
            raise ValueError("PathRegistry belongs to a different Project")
        return registry

    def save(self, registry):
        if registry.project != self.obj.id:
            raise ValueError("PathRegistry belongs to a different Project")
        registry.save(self.file)

    def enroll(self, cls, name):
        if cls not in self.obj.types.all():
            raise ValueError("Type is not selected by this Project")
        view = JSONView(entity(cls).id, name, cls.view_schemas()[name])
        registry = self.open()
        entries = registry.enroll(view)
        self.save(registry)
        return entries

    def suite(self):
        return PathsSuite(self)

    def notebook(self, *, notebook=None):
        """Select the Path Notebook inside this Project's existing Notebook."""
        return self.obj.notebook(notebook=notebook).paths
        # tarav.breadcrumb df94e327bb74


class PathsUnavailable(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("10e273f5-3840-44c1-8683-bf032c326fe2"),
                          name="Tarav.PathRegistry.Unavailable.Check", workflow=PATHS_WORKFLOW_SHIP)

    def __init__(self, reason):
        self.reason = reason

    def _run(self):
        return CheckResult(self, status="incomplete", reason=self.reason)


class PathsSuite(CheckSuite):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("3b61ce60-d144-4775-9024-189683f632a0"),
                          name="Tarav.PathRegistry.Suite", workflow=PATHS_WORKFLOW_SHIP)

    def __init__(self, manager):
        self.manager = manager
        super().__init__(key=str(manager.obj.id), name="Project PathRegistry",
                         checkpoint_types={"registry": (RegistryCheck,)})

    def produce(self):
        if not self.manager.file.exists():
            return
        try:
            registry = self.manager.open()
            # Compute only enrolled Types. Unrelated introspection failures do not
            # prevent maintenance of the Views the Project actually registered.
            owners = {view.typed.owner for view in registry.views}
            views = [JSONView(entity(cls).id, name, value)
                     for cls in self.manager.obj.types.all() if entity(cls).id in owners
                     for name, value in cls.view_schemas().items()]
        except (OSError, ValueError, TypeError, RuntimeError, LookupError) as exc:
            yield PathsUnavailable(str(exc))
            return
        yield RegistryCheck(registry, views)
        yield SuiteCheckpoint("registry")
