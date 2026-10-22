"""Read-only comparison of computed JSON and maintained path declarations."""
# tarav.breadcrumb 912492046509

from collections import Counter

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult
from . import PATHS_WORKFLOW_SHIP


class SchemaChanged(CheckPOI):
    """A computed View differs from the Project's accepted structure."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9e89c3e8-9208-480d-92cf-858080c93865"),
                          name="Tarav.PathRegistry.SchemaChanged", workflow=PATHS_WORKFLOW_SHIP)


class PathMissing(CheckPOI):
    """An active Path declares a position absent from its computed View."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4a4df9ea-c2cc-4107-8d2b-72ca9995b008"),
                          name="Tarav.PathRegistry.PathMissing", workflow=PATHS_WORKFLOW_SHIP)


class PathUnregistered(CheckPOI):
    """A computed JSON position has no active Path identity."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("53733722-1cab-4e53-8fc4-2b62116e36de"),
                          name="Tarav.PathRegistry.PathUnregistered", workflow=PATHS_WORKFLOW_SHIP)


class PathUndeclared(CheckPOI):
    """An active Path identity has no declared JSON position."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("6845285d-c879-46c9-bfea-71ba27be9bb1"),
                          name="Tarav.PathRegistry.PathUndeclared", workflow=PATHS_WORKFLOW_SHIP)


class DuplicatePath(CheckPOI):
    """Several active Path identities declare the same View position."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4b48d247-d76e-4cbd-a26e-5c2416cfb9ab"),
                          name="Tarav.PathRegistry.DuplicatePath", workflow=PATHS_WORKFLOW_SHIP)


class IdentityConflict(CheckPOI):
    """The registry contains repeated identities requiring explicit maintenance."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("380c382a-9754-498b-a549-a68a9f834f2d"),
                          name="Tarav.PathRegistry.IdentityConflict", workflow=PATHS_WORKFLOW_SHIP)


class ViewMissing(CheckPOI):
    """A maintained View is unavailable or an active Path names an unenrolled View."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d24f497a-7782-4fa3-8b05-bfc298e75329"),
                          name="Tarav.PathRegistry.ViewMissing", workflow=PATHS_WORKFLOW_SHIP)


class RegistryCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8981136e-fdd6-4fbf-a733-5f1f4ac20587"),
                          name="Tarav.PathRegistry.Check", workflow=PATHS_WORKFLOW_SHIP)

    def __init__(self, registry, computed):
        self.registry, self.computed = registry, computed

    def _run(self):
        registry = self.registry
        findings = []

        def report(cls, message, **coordinates):
            findings.append(cls(self, message, situation={"registry": str(registry.id), **coordinates}))

        for kind, values in (("view", registry.views), ("entry", registry.entries)):
            for ship, count in Counter(str(v.id) for v in values).items():
                if count > 1:
                    report(IdentityConflict, f"Repeated {kind} Ship {ship}", identity=ship)
        saved = {view.id: view for view in registry.views}
        current = {view.id: view for view in self.computed}
        for entry in registry.entries:
            if entry.typed.active and entry.typed.view not in saved:
                report(ViewMissing, "Active path names an unenrolled View", entry=str(entry.id))
        for view in saved.values():
            new = current.get(view.id)
            if new is None:
                report(ViewMissing, f"View {view.typed.name} is no longer provided by this Project", view=str(view.id))
                continue
            if new.typed.value != view.typed.value:
                report(SchemaChanged, f"View {view.typed.name} changed since acceptance", view=str(view.id))
            paths = set(new.paths)
            entries = [e for e in registry.entries if e.typed.view == view.id and e.typed.active]
            declared = Counter(e.typed.path for e in entries if e.typed.path is not None)
            for entry in entries:
                path = entry.typed.path
                if path is None:
                    report(PathUndeclared, "Active Path Ship has no declared path", entry=str(entry.id))
                elif path not in paths:
                    report(PathMissing, f"Declared path {path!r} is absent", entry=str(entry.id))
            for path, count in declared.items():
                if count > 1:
                    report(DuplicatePath, f"Several active Ships declare {path!r}", view=str(view.id), path=path)
            for path in sorted(paths - declared.keys()):
                report(PathUnregistered, f"Computed path {path!r} has no active Ship", view=str(view.id), path=path)
        return CheckResult(self, status="completed", pois=findings)


PATH_CHECK_TYPES = (SchemaChanged, PathMissing, PathUnregistered, PathUndeclared,
                    DuplicatePath, IdentityConflict, ViewMissing, RegistryCheck)
