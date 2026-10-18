from typing import Literal, Self

import pytest
from pydantic import BaseModel

from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TaravTypeDeclarationError,
    TypeShip,
    entity,
)
from tarav.l3.runtime import create_runtime


class RuntimeProjection(TaravObject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("8540991c-f4d2-4a8d-868d-03f40cc06c7c"),
            name="Test.RuntimeProjection",
        )

    class RecordInterface(TaravObject.RecordInterface):
        type: Literal["Test.RuntimeProjection"]
        value: int

    def __init__(self, value: int) -> None:
        super().__init__()
        self.value = value

    @classmethod
    def _from_record(cls, record_data: BaseModel) -> Self:
        return cls(record_data.value)

    def _to_record(self) -> dict[str, object]:
        return {"type": entity(type(self)).name, "value": self.value}


def test_registered_runtime_objects_round_trip_their_record_examples() -> None:
    registry = create_runtime().records

    for object_type in registry.record_types:
        example = object_type.records.record_example()
        first = registry.from_record(example)
        encoded = first.records.to_record()
        assert encoded == example, object_type.__name__
        second = registry.from_record(encoded)

        assert type(first) is object_type, object_type.__name__
        assert type(second) is object_type, object_type.__name__
        assert second.records.to_record() == encoded, object_type.__name__


def test_runtime_object_projects_state_without_a_loaded_record() -> None:
    subject = RuntimeProjection(7)

    assert subject._record is None
    assert not hasattr(subject, "record")
    assert not hasattr(subject, "record_data")
    assert subject.records.to_record() == {"type": "Test.RuntimeProjection", "value": 7}


def test_loaded_record_is_input_material_not_the_objects_source_of_truth() -> None:
    supplied = {"type": "Test.RuntimeProjection", "value": 7}
    subject = RuntimeProjection.records.from_record(supplied)

    assert subject._record == supplied
    assert subject._record is not supplied
    subject._record["value"] = 99
    assert subject.value == 7
    assert subject.records.to_record() == supplied


def test_default_projection_is_the_types_minimal_record() -> None:
    class Minimal(TaravObject):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip("327fe3bd-206f-4d56-be52-2b07728982f6"),
                name="Test.Minimal",
            )

    subject = Minimal()

    assert subject._record is None
    assert subject.records.to_record() == {"type": "Test.Minimal"}


def test_tarav_owns_the_public_record_loading_boundary() -> None:
    with pytest.raises(TaravTypeDeclarationError, match="selected Records namespace"):

        class InvalidLoader(TaravObject):
            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(
                    target=cls,
                    id=TypeShip("6128b2f8-6e0a-4579-ac7c-2a66be5ea605"),
                    name="Test.InvalidLoader",
                )

            @classmethod
            def from_record(cls, value):
                return cls()


@pytest.mark.parametrize("name", ("to_record", "validate_record", "record_example"))
def test_record_extensions_must_use_the_selected_namespace(name: str) -> None:
    with pytest.raises(TaravTypeDeclarationError, match="selected Records namespace"):
        type(
            "InvalidRecordExtension",
            (TaravObject,),
            {
                "class_entity": classmethod(
                    lambda cls: TaravClass(
                        target=cls,
                        id=TypeShip("2ac0c5aa-d8fc-4df9-8fa8-9530aab571a4"),
                        name="Test.InvalidRecordExtension",
                    )
                ),
                name: lambda self, value=None: value,
            },
        )


# Types whose Record still reads its state from `_record`. Migrating one means
# removing it here; nothing may be added.
RECORD_STATE_DEBT = frozenset({
    "tarav.l1.archive.references.ArchiveReference",
    "tarav.l1.breadcrumbs.model.Breadcrumb",
    "tarav.l1.breadcrumbs.model.LocatorObservation",
    "tarav.l1.chatlas.normal_model.model.ChatlasNormalModel",
    "tarav.l1.chatlas.normal_model.records.AgentEvent",
    "tarav.l1.chatlas.normal_model.records.AgentLoadedContext",
    "tarav.l1.chatlas.normal_model.records.ChatMessage",
    "tarav.l1.chatlas.normal_model.records.ChatTurn",
    "tarav.l1.chatlas.normal_model.records.UnresolvedEvent",
    "tarav.l1.chatlas.normal_model.records.UserEvent",
    "tarav.l1.chatlas.references.ChatlasTurnReference",
    "tarav.l1.decisions.records.Decision",
    "tarav.l1.git.repository.GitRepository",
    "tarav.l1.references.FileReference",
    "tarav.l1.references.Reference",
    "tarav.l1.references.git.GitCommitMessagePositionReference",
    "tarav.l1.references.git.GitFileReference",
    "tarav.l1.references.positions.FilePositionReference",
    "tarav.l1.references.structured.StructuredFileReference",
    "tarav.l1.skw.annotations.GenerationAnnotation",
    "tarav.l1.skw.annotations.ObjectIndexReference",
    "tarav.l1.skw.code.reading.BlockEntry",
    "tarav.l1.skw.code.reading.ConsultationLink",
    "tarav.l1.skw.code.reading.Contains",
    "tarav.l1.skw.code.reading.EitherDependency",
    "tarav.l1.skw.code.reading.ExpectedLink",
    "tarav.l1.skw.code.reading.FileEntry",
    "tarav.l1.skw.code.reading.IncludesBlock",
    "tarav.l1.skw.code.reading.InlineDependency",
    "tarav.l1.skw.code.reading.ReadingDependency",
    "tarav.l1.skw.code.reading.ReadingLink",
    "tarav.l1.skw.code.reading.ReferenceDependency",
    "tarav.l1.skw.document.SkwBlock",
    "tarav.l1.skw.skills.SkillLink",
    "tarav.l2.blessings.assertions.BlessingAcceptanceCase",
    "tarav.l2.blessings.assertions.BlessingGroundsCase",
    "tarav.l2.breadcrumb_workflows.chatlas_context.model.ChatlasContextAttachment",
    "tarav.l2.git.breadcrumbs.CommitManifest",
    "tarav.l2.lines.assertions.LineGroundingCase",
    "tarav.l2.lines.assertions.LineSupportInventoryCase",
    "tarav.l2.lines.records.BlockEditionRecord",
    "tarav.l2.lines.records.BlockShipRecord",
    "tarav.l2.lines.records.BlockTypeAnnotation",
    "tarav.l2.lines.records.CollectionEditionRecord",
    "tarav.l2.lines.records.CollectionShipRecord",
    "tarav.l2.lines.records.LineAnnotationRecord",
    "tarav.l2.lines.records.LineEditionRecord",
    "tarav.l2.lines.records.LineGateAnnotation",
    "tarav.l2.lines.records.LineShipRecord",
    "tarav.l2.lines.records.LineSupportAnnotation",
    "tarav.l2.lines.records.LineTypeAnnotation",
    "tarav.l2.models.records.ModelEditionRecord",
    "tarav.l2.scoring.assertions.AssessmentCase",
    "tarav.l2.scoring.model.GroundingRankingPoolRecord",
    "tarav.l2.scoring.model.GroundingRankingTaskRecord",
    "tarav.l2.scoring.model.PoolEnrollmentRecord",
    "tarav.l2.scoring.model.RankingResultRecord",
    "tarav.l2.scoring.model.RankingRunRecord",
    "tarav.l2.scoring.model.ScoringEventRecord",
    "tarav.l2.scoring.model.ScoringTraceRecord",
    "tarav.l2.scoring.model.TribunalCaseRecord",
    "tarav.l2.scoring.model.TribunalJudgmentRecord",
    "tarav.l2.scoring.model.TribunalPairRecord",
    "tarav.l2.scoring.ranking.score.RankingScore",
    "tarav.l2.scoring.ranking.tribunals.PairwiseRankingCase",
    "tarav.l2.tests.scoring.LineSupportCase",
    "tarav.l2.unsorted.authorization.CaptureAuthorizationGateRecord",
})


def _reads_state_from_its_record(object_type, registry) -> bool:
    example = object_type.records.record_example()
    subject = registry.from_record(example)
    subject._record = None
    try:
        return subject.records.to_record() != example
    except Exception:
        return True


def test_objects_project_their_state_not_their_loaded_record() -> None:
    # tarav.breadcrumb c3e31a009b49
    registry = create_runtime().records
    debt = {
        f"{object_type.__module__}.{object_type.__qualname__}"
        for object_type in registry.record_types
        if _reads_state_from_its_record(object_type, registry)
    }

    assert debt - RECORD_STATE_DEBT == set(), "new Types read state from _record"
    assert RECORD_STATE_DEBT - debt == set(), "migrated Types: remove them from the list"
