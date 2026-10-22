"""Exact chunk states and attributed continuity decisions, independent of review."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tarav.l0.kernel import TaravClass, TaravObject, TypedState, TypeShip

from .workflow import PRODUCT_MAPPING_SHIP

Identity = Annotated[str, Field(min_length=1)]
Oid = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class MappingData(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


# tarav.breadcrumb c0da0c687830
class Chunk(MappingData):
    id: str
    path: str
    blob: Oid
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    sha256: Digest

    @field_validator("id")
    @classmethod
    def uuid_id(cls, value):
        if str(UUID(value)) != value:
            raise ValueError("Chunk IDs must be canonical UUIDs")
        return value


class SkippedSurface(MappingData):
    path: str
    mode: str
    oid: Oid


# tarav.breadcrumb 572b99bdb538
class ContinuityDecision(MappingData):
    """An attributed transition relates old IDs to new IDs; empty sides create/retire."""

    source_ids: list[str]
    target_ids: list[str]
    reason: str = Field(min_length=1, pattern=r"\S")


class MappingProposal(TypedState, TaravObject):
    """Editable candidates. This is never itself a confirmed map."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4de2dcb1-5675-4e8e-ad9f-a15268ec2089"),
                          name="Tarav.ProductMapping.Proposal", workflow=PRODUCT_MAPPING_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.ProductMapping.Proposal"]
        repository_id: Identity
        base: str | None
        commit: Oid
        tree: Oid
        chunks: list[Chunk]
        skipped: list[SkippedSurface]

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "repository_id": "example-repository",
                    "base": None, "commit": "0" * 40, "tree": "0" * 40,
                    "chunks": [], "skipped": []}


class ProductMap(TypedState, TaravObject):
    """An immutable confirmed map of one committed state."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("dd4e0552-2cfe-413d-a9da-bae9b213087c"),
                          name="Tarav.ProductMapping.Map", workflow=PRODUCT_MAPPING_SHIP)

    class RecordInterface(MappingProposal.RecordInterface):
        type: Literal["Tarav.ProductMapping.Map"]
        id: str
        confirmed_at: str
        actor: str = Field(min_length=1, pattern=r"\S")
        reason: str = Field(min_length=1, pattern=r"\S")
        decisions: list[ContinuityDecision]

    class Records(TaravObject.Records):
        def record_example(self):
            from tarav.l0.kernel import entity

            return {**MappingProposal.records.record_example(), "type": entity(self._owner).name,
                    "id": "18ce30ea-ff0e-494f-a0cf-7cf079d7870e",
                    "confirmed_at": "1970-01-01T00:00:00Z", "actor": "example-agent",
                    "reason": "Schema example only; no mapping claim", "decisions": []}


class MappingTrack(TypedState, TaravObject):
    """The explicit scope and ordered confirmed checkpoints of one mapping stream."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("4edcfb7c-c4c7-4a73-aa26-283b1899e581"),
                          name="Tarav.ProductMapping.Track", workflow=PRODUCT_MAPPING_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.ProductMapping.Track"]
        repository_id: Identity
        target_bytes: int = Field(default=4096, gt=0)
        boundary_bytes: int = Field(default=256, ge=0)
        include: list[str] = Field(default_factory=lambda: ["*"])
        exclude: list[str] = Field(default_factory=list)
        maps: list[str] = Field(default_factory=list)
        issued_ids: list[str] = Field(default_factory=list)

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "repository_id": "example-repository"}


def build(cls, **values):
    """Construct state through the public Record loader, retaining no parallel dict."""
    from tarav.l0.kernel import entity

    return cls.records.from_record({"type": entity(cls).name, **values})


PRODUCT_MAPPING_RECORD_TYPES = (MappingProposal, ProductMap, MappingTrack)
