"""Retained attachment produced by the Chatlas Context Breadcrumb workflow."""

from typing import Literal

from pydantic import ConfigDict

from tarav.breadcrumbs.model import BreadcrumbId
from tarav.chatlas.references import ChatlasTurnReference
from tarav.kernel import TaravClass, entity
from tarav.kernel import TaravObject, TypeShip
from tarav.breadcrumbs.identity import BREADCRUMBS_WORKFLOW_SHIP


class ChatlasContextAttachment(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('69ffdb4e-0fbc-430e-8480-3533311b2ac7'),
            name='Tarav.Breadcrumb.Attachment.ChatlasContext',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb.Attachment.ChatlasContext"]
        breadcrumb_id: BreadcrumbId
        workflow: Literal["Tarav.Breadcrumbs.ChatlasContext"]
        context: ChatlasTurnReference.RecordInterface

    @classmethod
    def record_example(cls) -> dict[str, object]:
        return {
            "type": entity(cls).name,
            "breadcrumb_id": "0" * 64,
            "workflow": "Tarav.Breadcrumbs.ChatlasContext",
            "context": ChatlasTurnReference.record_example(),
        }


__all__ = ["ChatlasContextAttachment"]
