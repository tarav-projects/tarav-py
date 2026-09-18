"""Diagram registers its existing semantic interpreters with the library."""

from tarav.harness.workflows import Workflow
from tarav.navigation import FilesystemProvider

from . import (
    DiagramNamespace,
    default_diagram_annotation_type_registry,
    default_diagram_ship_type_registry,
)


class DiagramWorkflow(Workflow):
    name = "diagram"
    record_types = (
        *default_diagram_ship_type_registry().record_types,
        *default_diagram_annotation_type_registry(
            include_chatlas_index_types=True
        ).record_types,
    )

    def provider(self, root, records):
        return DiagramProvider(DiagramNamespace.open(root), records)


class DiagramProvider(FilesystemProvider):
    """Preserve Namespace/address bindings while exposing ordinary navigation."""

    def __init__(self, namespace: DiagramNamespace, records) -> None:
        self.namespace = namespace
        super().__init__(namespace.root, records)

    def load(self, address: str):
        path = self.path(address)
        relative = path.relative_to(self.root)
        if len(relative.parts) == 2 and path.suffix == ".json":
            if relative.parts[0] == "ships":
                return self.namespace.ship(path.stem).specialize()
            if relative.parts[0] == "annotations":
                return self.namespace.annotation(path.stem).specialize()
        return super().load(address)
