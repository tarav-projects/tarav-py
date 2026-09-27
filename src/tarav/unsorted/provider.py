"""Legacy record registration and namespace navigation; not a workflow."""

from tarav.l0.kernel.space import FilesystemProvider

from tarav.unsorted.storage import DiagramNamespace
from tarav.unsorted.registry import default_diagram_annotation_type_registry, default_diagram_ship_type_registry


DIAGRAM_RECORD_TYPES = (
    *default_diagram_ship_type_registry().record_types,
    *default_diagram_annotation_type_registry(
        include_chatlas_index_types=True
    ).record_types,
)


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
