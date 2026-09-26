"""Diagram registers its existing semantic interpreters with the library."""

from tarav.kernel import TaravClass
from tarav.kernel import TypeShip
from tarav.kernel.workflows import TaravWorkflow
from tarav.diagram.identity import DIAGRAM_WORKFLOW_SHIP
from tarav.kernel.space import FilesystemProvider

from . import (
    DiagramNamespace,
    default_diagram_annotation_type_registry,
    default_diagram_ship_type_registry,
)


DIAGRAM_RECORD_TYPES = (
    *default_diagram_ship_type_registry().record_types,
    *default_diagram_annotation_type_registry(
        include_chatlas_index_types=True
    ).record_types,
)


class DiagramWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('5c2f77b6-8994-4fa9-a330-966beb13bec1'),
            name='Tarav.Workflow.Diagram',
            workflow=DIAGRAM_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return DIAGRAM_WORKFLOW_SHIP
    workflow_name = "diagram"
    constitution = "Retain explicit semantic records, relationships, and claims about subjects."

    @classmethod
    def provider(cls, root, records):
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
