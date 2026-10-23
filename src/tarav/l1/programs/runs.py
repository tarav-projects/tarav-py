"""Durable Program execution state in the workflow's external Record partition."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypedState, TypeShip, entity
from tarav.l1.actions import ActionRun

from .actions import ProgramExecutionAction
from .workflow import PROGRAMS_WORKFLOW_SHIP


# tarav.breadcrumb 562b5bedaa8b
class ActiveAction(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: Ship
    action: TypeShip
    token: str = Field(min_length=1)
    source: TypeShip | None = None
    target: TypeShip | None = None


class ProgramRun(TypedState, TaravEntity):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("c34dc8b9-7ad8-4a12-a2d2-67f4787821fb"),
                          name="Tarav.Programs.Run", workflow=PROGRAMS_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
        type: Literal["Tarav.Programs.Run"]
        program: TypeShip
        project: dict[str, JsonValue]
        active: list[ActiveAction]
        phase: Literal["running", "completed"]
        data: dict[str, JsonValue]
        actions: list[dict]
        history: list[dict]
        created_at: str
        updated_at: str

    class Records(TaravEntity.Records):
        def record_example(self):
            from . import TaravProgram

            identity = "4a9af366-b093-4ba0-aedd-6d71a3f2bbd0"
            owner = {"id": "e308d11f-d709-4f23-b8c7-f214e28b3f11", "name": "Example", "root": "/example"}
            action = ActionRun.records.record_example()
            action.update(id=identity, action=str(entity(ProgramExecutionAction).name), project=owner)
            return {"type": str(entity(self._owner).name), "id": identity,
                    "program": str(entity(TaravProgram).id), "project": owner,
                    "active": [], "phase": "completed", "data": {}, "actions": [action],
                    "history": [], "created_at": "2026-10-23T00:00:00Z", "updated_at": "2026-10-23T00:00:00Z"}
