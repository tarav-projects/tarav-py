"""Stable batches, immutable revisions and separate review-completion evidence."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tarav.l0.kernel import TaravClass, TaravObject, TypedState, TypeShip
from tarav.l1.references import Reference

from .workflow import PRODUCT_REVIEW_SHIP

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Identity = Annotated[str, Field(pattern=r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$")]
Oid = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]


class ChunkState(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    id: Identity
    path: str
    blob: Oid
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Batch(TypedState, TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("43d90f9c-2367-4ac8-b803-b5fb3e73e086"),
                          name="Tarav.ProductReview.Batch", workflow=PRODUCT_REVIEW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.ProductReview.Batch"]
        id: Identity
        repository_id: Text
        revisions: list[Identity] = Field(min_length=1)
        retired: bool = False
        retired_at: str | None = None
        retired_by: Text | None = None
        retirement_reason: Text | None = None

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "id": "0" * 8 + "-0000-0000-0000-000000000001",
                    "repository_id": "example-product", "revisions": ["00000000-0000-0000-0000-000000000002"]}


# tarav.breadcrumb c910032d8541
class BatchRevision(TypedState, TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("ed536b2b-6fda-47cb-94a0-e05d022aa794"),
                          name="Tarav.ProductReview.BatchRevision", workflow=PRODUCT_REVIEW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.ProductReview.BatchRevision"]
        id: Identity
        batch_id: Identity
        repository_id: Text
        base: Identity | None
        map_id: Identity
        commit: Oid
        title: Text
        purpose: Text
        chunks: list[ChunkState] = Field(min_length=1)
        created_at: str
        actor: Text
        reason: Text

        @model_validator(mode="after")
        def unique_chunks(self):
            if len({c.id for c in self.chunks}) != len(self.chunks):
                raise ValueError("A batch revision cannot repeat a chunk ID")
            return self

    class Records(TaravObject.Records):
        def record_example(self):
            return {**super().record_example(), "id": "00000000-0000-0000-0000-000000000002",
                    "batch_id": "00000000-0000-0000-0000-000000000001", "repository_id": "example-product",
                    "base": None, "map_id": "00000000-0000-0000-0000-000000000003", "commit": "0" * 40,
                    "title": "Example", "purpose": "Example only", "chunks": [{
                        "id": "00000000-0000-0000-0000-000000000004", "path": "example.txt",
                        "blob": "0" * 40, "start": 0, "end": 1, "sha256": "0" * 64}],
                    "created_at": "1970-01-01T00:00:00Z", "actor": "example-agent", "reason": "Example only"}


# tarav.breadcrumb 4a45fda6fe39
class ReviewCompletion(TypedState, TaravObject):
    """The review happened; follow-up work may remain open."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("d2fe41a5-1adb-4d10-9330-91701579d203"),
                          name="Tarav.ProductReview.Completion", workflow=PRODUCT_REVIEW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.ProductReview.Completion"]
        id: Identity
        revision_id: Identity
        repository_id: Text
        token: Text
        completed_at: str
        presentation: Reference.RecordInterface
        completion: Reference.RecordInterface
        outcomes: list[Reference.RecordInterface] = Field(default_factory=list)

        @model_validator(mode="after")
        def token_names_revision(self):
            if self.token != "review:" + self.revision_id:
                raise ValueError("Completion token must name its exact batch revision")
            return self

    class Records(TaravObject.Records):
        def record_example(self):
            ref = {"type": "Tarav.Chatlas.Reference.Turn", "locator": {
                "session_identity": "0" * 64, "turn_address": "0" * 64, "turn_hash": "0" * 64}}
            return {**super().record_example(), "id": "00000000-0000-0000-0000-000000000005",
                    "revision_id": "00000000-0000-0000-0000-000000000002", "repository_id": "example-product",
                    "token": "review:00000000-0000-0000-0000-000000000002", "completed_at": "1970-01-01T00:00:00Z",
                    "presentation": ref, "completion": ref, "outcomes": []}


PRODUCT_REVIEW_RECORD_TYPES = (Batch, BatchRevision, ReviewCompletion)
