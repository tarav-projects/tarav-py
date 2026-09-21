"""Retained attachment produced by the Chatlas Context Breadcrumb workflow."""

from typing import Literal

from pydantic import ConfigDict

from tarav.breadcrumbs.model import BreadcrumbId
from tarav.chatlas.references import ChatlasTurnReference
from tarav.harness import TaravObject, TypeShip


class ChatlasContextAttachment(TaravObject):
    type_ship = TypeShip("69ffdb4e-0fbc-430e-8480-3533311b2ac7")
    type_name = "Tarav.Breadcrumb.Attachment.ChatlasContext"

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb.Attachment.ChatlasContext"]
        breadcrumb_id: BreadcrumbId
        workflow: Literal["Tarav.Breadcrumbs.ChatlasContext"]
        context: ChatlasTurnReference.RecordInterface

    @classmethod
    def json_example(cls) -> dict[str, object]:
        return {
            "type": cls.type_name,
            "breadcrumb_id": "0" * 64,
            "workflow": "Tarav.Breadcrumbs.ChatlasContext",
            "context": ChatlasTurnReference.json_example(),
        }


__all__ = ["ChatlasContextAttachment"]
