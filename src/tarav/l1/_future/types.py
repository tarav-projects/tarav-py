"""Experimental ownership, object namespace and identified model members."""

from __future__ import annotations

from typing import Literal

from tarav.l0.kernel import (
    NamespaceBase, Ship, TaravClass, TaravEntity, TaravObject, TaravType,
    TypeShip, WorkflowShip,
)
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.context.models import TypePath


FUTURE_WORKFLOW_SHIP = WorkflowShip("a79cbbd8-95d8-45be-b3ed-f3b5cc938c0f")


def class_projection(cls, identity: str, name: str) -> TaravClass:
    return TaravClass(
        target=cls, id=TypeShip(identity), name="Tarav.Future." + name,
        workflow=FUTURE_WORKFLOW_SHIP,
    )


# tarav.context 473c89a0:8944495a171e5499
class _FutureWorkflow(TaravWorkflow):
    """Own the opt-in RDF experiment and its ordinary typed Records."""

    constitution = (
        "Experiment with RDF projections and progressive SPARQL Context "
        "navigation over typed objects, using explicit contributions and "
        "ordinary JSON Records without replacing maintained workflows."
    )

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "d40e7bbc-1137-4220-85e2-874a67f53b4f", "Workflow")

    @classmethod
    def _workflow_id(cls):
        return FUTURE_WORKFLOW_SHIP


class _FutureDescriptor:
    def __get__(self, instance, owner):
        return owner._Future(owner if instance is None else instance)


# tarav.context 473c89a0:b4ad4b3730008174
class FutureType(TaravType):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "24c427f9-496f-4ced-b15a-0c4b15b9b190", "Type")

    class _Future(NamespaceBase):
        def context(self, *, diagram=None, views=()):
            """Create an explorer over the selected experimental Diagram."""
            from .context import ContextExplorer
            from .graph import Diagram

            explorer = ContextExplorer(diagram if diagram is not None else Diagram(), self.obj)
            if views:
                explorer.refine(views=views)
            return explorer

    _future = _FutureDescriptor()


def future(obj):
    """Adapt an existing Type/object without changing its class or identity."""
    if not isinstance(obj, TaravObject) and not (
        isinstance(obj, type) and issubclass(obj, TaravType)
    ):
        raise TypeError("future() requires a Tarav object or Type")
    namespace = obj._Future if isinstance(obj, type) and issubclass(obj, FutureType) else (
        type(obj)._Future if isinstance(obj, FutureType) else FutureType._Future
    )
    return namespace(obj)


class FutureObject(TaravObject, FutureType):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "1393335f-12d5-446e-980d-e3ef89b5dffb", "Object")


class FutureEntity(TaravEntity, FutureType):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, "5fc4f8ac-8c5c-4969-b118-56258ca9ac0c", "Entity")


# tarav.context 473c89a0:a25dc4a4402725c7
class ModelMember(TypePath, FutureType):
    """A stable concept bound to a current path in a represented class."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, "a8a5db68-46c2-44d6-827d-e0e32b37c9c9", "ModelMember")

    class RecordInterface(TypePath.RecordInterface):
        type: Literal["Tarav.Future.ModelMember"]
        owner: TypeShip

    def __init__(self, id: Ship, owner: TypeShip, path: str):
        super().__init__(id, path)
        self.owner = owner

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, record_data.owner, record_data.path)

    def _to_record(self):
        return {**super()._to_record(), "owner": str(self.owner)}

    class Records(TypePath.Records):
        def record_example(self):
            return {
                "type": "Tarav.Future.ModelMember",
                "id": "537ec2b7-c39a-4e7d-9156-177c1f97298e",
                "owner": "1393335f-12d5-446e-980d-e3ef89b5dffb",
                "path": "records",
            }
