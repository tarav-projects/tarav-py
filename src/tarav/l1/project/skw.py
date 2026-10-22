"""Project binding for Skillware document operations."""

from tarav.l0.kernel import NamespaceBase
from tarav.l1.skw.document import DEFAULT_DEPOT, project_document


# tarav.breadcrumb bf3c78decf2f
class SkwManager(NamespaceBase):
    """Select Skillware sources in this Project; reads never compile or provision."""

    @property
    def depot(self):
        return self.obj.root / DEFAULT_DEPOT

    def document(self, source, *, registry=None):
        return project_document(source, project=self.obj.root,
                                depot=self.depot.relative_to(self.obj.root),
                                registry=registry if registry is not None else self.obj.records.types)


__all__ = ["SkwManager"]
