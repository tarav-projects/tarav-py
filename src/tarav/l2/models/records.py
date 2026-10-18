"""Model Ships and editions; retained identities and schemas are unchanged."""
from __future__ import annotations

from tarav.l0.kernel import Ship, TaravClass, TypeShip
from tarav.l2.unsorted.constants import MODEL_EDITION_TYPE, MODEL_SHIP_TYPE, JsonObject
from tarav.l2.unsorted.records import DiagramAnnotation, TypedAnnotation, TypedShip
from tarav.l2.unsorted.primitives import _edition_id, _edition_payload, _string, _uuid, _validate_editions
from .workflow import MODELS_WORKFLOW_SHIP

class ModelShipRecord(TypedShip):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('990807e6-2348-466e-9c12-dba6673755c1'),
            name=MODEL_SHIP_TYPE,
            workflow=MODELS_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _validate_editions(self.editions, field="Model.Ship.editions")

    def edition_annotations(self) -> tuple[DiagramAnnotation, ...]:
        return tuple(
            DiagramAnnotation(
                _edition_id(edition),
                self.namespace,
                {
                    "type": MODEL_EDITION_TYPE,
                    "model_ship": self.id,
                    **_edition_payload(edition),
                },
            )
            for edition in self.editions
        )


class ModelEditionRecord(TypedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('213b526c-cdd1-4d9b-a39d-650eee709354'),
            name=MODEL_EDITION_TYPE,
            workflow=MODELS_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._fields.get("model_ship"), field="Model.Edition.model_ship")

    @property
    def model_ship(self) -> str:
        return _string(self._fields.get("model_ship"), field="model_ship")

    def model_location(self) -> tuple[str, str]:
        return self.model_ship, "model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return ({"type": "Model.Derived.Support.Assertion"},)

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(ModelEditionRecord, self).ships(),
            Ship(self.model_ship),
        )



