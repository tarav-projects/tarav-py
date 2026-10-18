"""tarav.l2.unsorted.authorization: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.l2.unsorted.constants import CAPTURE_AUTHORIZATION_GATE_TYPE
from tarav.l2.unsorted.contracts import ChatlasTurnReferenceInterface
from tarav.l2.lines.references import DiagramArgumentReferenceInterface
from tarav.l2.unsorted.primitives import DiagramModelError
from tarav.l0.kernel import Ship
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l2.unsorted.records import TypedAnnotation
from tarav.l2.unsorted.identity import UNSORTED_WORKFLOW_SHIP
from tarav.l2.unsorted.primitives import _array
from tarav.l2.unsorted.primitives import _string
from tarav.l2.unsorted.primitives import _uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.unsorted.constants import JsonObject

class CaptureAuthorizationGateRecord(TypedAnnotation):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('f3701ea7-cb6c-494f-b3e5-1d38370abde0'),
            name=CAPTURE_AUTHORIZATION_GATE_TYPE,
            workflow=UNSORTED_WORKFLOW_SHIP,
        )

    def _validate_record(self) -> None:
        self._require_record_type()
        _uuid(self._fields.get("model_ship"), field="Capture.Authorization.model_ship")
        _string(self._fields.get("token"), field="Capture.Authorization.token")
        _string(self._fields.get("workflow"), field="Capture.Authorization.workflow")
        ChatlasTurnReferenceInterface.model_validate(self._fields.get("permission_turn"))
        operations = tuple(
            _string(item, field="Capture.Authorization.operations[]")
            for item in _array(
                self._fields.get("operations", []),
                field="Capture.Authorization.operations",
            )
        )
        if not operations:
            raise DiagramModelError(
                "Capture.Authorization.operations must not be empty"
            )
        scopes = tuple(
            DiagramArgumentReferenceInterface.model_validate(item)
            for item in _array(
                self._fields.get("target_scope", []),
                field="Capture.Authorization.target_scope",
            )
        )
        if not scopes:
            raise DiagramModelError(
                "Capture.Authorization.target_scope must not be empty"
            )

    @property
    def model_ship(self) -> str:
        return _uuid(self._fields.get("model_ship"), field="model_ship")

    @property
    def token(self) -> str:
        return _string(self._fields.get("token"), field="token")

    @property
    def workflow(self) -> str:
        return _string(self._fields.get("workflow"), field="workflow")

    @property
    def permission_turn(self) -> ChatlasTurnReferenceInterface:
        return ChatlasTurnReferenceInterface.model_validate(
            self._fields.get("permission_turn")
        )

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(
            _string(item, field="operations[]")
            for item in _array(self._fields.get("operations", []), field="operations")
        )

    @property
    def target_scope(self) -> tuple[DiagramArgumentReferenceInterface, ...]:
        return tuple(
            DiagramArgumentReferenceInterface.model_validate(item)
            for item in _array(
                self._fields.get("target_scope", []), field="target_scope"
            )
        )

    def ships(self) -> tuple[Ship, ...]:
        return (
            *super(CaptureAuthorizationGateRecord, self).ships(),
            Ship(self.model_ship),
            *(
                Ship(reference.id)
                for reference in self.target_scope
                if reference.kind == "ship"
            ),
        )

    def model_location(self) -> tuple[str, str]:
        return self.model_ship, "model_ship"

    def type_assertions(self) -> tuple[JsonObject, ...]:
        return tuple(
            {"type": kind}
            for kind in (
                "Capture.Authorization.Permission.Role.Assertion",
                "Capture.Authorization.Token.Assertion",
                "Capture.Authorization.Scope.Assertion",
            )
        )
