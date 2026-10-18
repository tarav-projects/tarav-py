"""Assertion objects carry check semantics; scoring owns evaluation mechanics."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from types import MappingProxyType
from typing import Any
from uuid import UUID, uuid5

from pydantic import model_validator

from tarav.l0.kernel import TypedState
from tarav.l0.kernel import (
    FileRecord, Ship, TaravClass, TaravObject,
    TypeShip, entity,
)
from tarav.l1.assertions import Assertable as Assertable, TaravAssertion
# tarav.breadcrumb 7c3445f11b52
from .identity import SCORING_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


class UnsupportedAssessmentCase(TypeError):
    """This Assertion does not produce the requested case Type."""


class IncompleteCaseScope(ValueError):
    """A supported case cannot yet be closed with the supplied material."""


class AssertionNamespace(Mapping[str, 'Assertion']):
    """An immutable, label-addressed view; list order is not identity."""

    def __init__(self, assertions: Mapping[str, Assertion]) -> None:
        selected = dict(assertions)
        for label, assertion in selected.items():
            if not isinstance(label, str) or not label.strip():
                raise ValueError('Assertion labels must be non-empty strings')
            if not isinstance(assertion, Assertion):
                raise TypeError('Assertion namespace values must be Assertions')
        ids = [str(assertion.id) for assertion in selected.values()]
        if len(ids) != len(set(ids)):
            raise ValueError('An Assertion cannot have two labels in one namespace')
        self._assertions = MappingProxyType(selected)

    def __getitem__(self, label: str) -> Assertion:
        return self._assertions[label]

    def __iter__(self) -> Iterator[str]:
        return iter(self._assertions)

    def __len__(self) -> int:
        return len(self._assertions)

    def by_id(self, identity: Ship | str) -> Assertion:
        matches = [item for item in self._assertions.values() if str(item.id) == str(identity)]
        if not matches:
            raise KeyError(identity)
        return matches[0]


class ScoringDetails(TypedState, FileRecord):
    """Inspectable JSON carried by scoring Context entries."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('5cb94b42-7c0f-4a8d-950e-e9fbc50ecf72'),
                          name='Tarav.Scoring.Details', workflow=SCORING_WORKFLOW_SHIP)


class AssertionReferenceInterface(ScoringDetails.RecordInterface):
    """Common embedded reference shape; its owning type validates the subject."""
    type: str
    subject_ref: dict

    @model_validator(mode='after')
    def assertion_type(self):
        if not self.type.endswith('.Assertion.Reference'):
            raise ValueError('Expected an Assertion.Reference type')
        Assertion.validate_subject(self.subject_ref)
        return self


class AssessmentCase(TypedState, TaravObject):
    """Typed, self-contained scorer input; subtypes own their payload schema."""
    # tarav.breadcrumb fe2d8ede0b40

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('8ef744c9-f239-44bb-a8cb-b3dc26904352'),
            name='Tarav.Scoring.AssessmentCase',
            workflow=SCORING_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        assertion_ref: AssertionReferenceInterface
        question: str
        presentation: str

    def __init__(
        self, *, assertion_ref: Mapping[str, object], question: str,
        presentation: str, **payload: Any,
    ) -> None:
        super().__init__()
        record = {
            'type': entity(type(self)).name,
            'assertion_ref': dict(assertion_ref),
            'question': question,
            'presentation': presentation,
            **payload,
        }
        # The scorer receives a snapshot, even if the producer later edits its inputs.
        self.typed = type(self).records.parse_record(json.loads(json.dumps(record, allow_nan=False)))

    class Records(TaravObject.Records):
        def parse_record(self, value):
            data = super().parse_record(value)
            if not data.question.strip() or not data.presentation.strip():
                raise IncompleteCaseScope('Assessment case needs a question and supplied material')
            return data

        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return cls(
                assertion_ref=Assertion({'type': 'Example.Subject.Reference'}).reference(),
                question='Is this claim supported?',
                presentation='Claim and supplied evidence.',
            ).records.to_record()


    @property
    def assertion_ref(self) -> dict[str, object]:
        return self.records.to_record()['assertion_ref']

    @property
    def presentation(self) -> str:
        return self.records.to_record()['presentation']



class Assertion(TaravAssertion):
    """A typed claim about an exact subject; evaluations are separate objects.

    Subtypes define the subject coordinate and how to obtain/present evidence.
    Identity is derived from the assertion Type Ship and subject reference,
    not from a score, evaluator, or mutable human-readable Type name.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('25a185c0-f0df-4969-9ba0-f4d8cde4df0f'),
                          name='Tarav.Scoring.Assertion', workflow=SCORING_WORKFLOW_SHIP)

    class RecordInterface(TaravAssertion.RecordInterface):
        subject_ref: dict

    def __init__(self, subject_ref):
        # JSON snapshots, not references to mutable caller data.
        subject = self.validate_subject(subject_ref)
        self._subject = json.dumps(subject, sort_keys=True, allow_nan=False)
        super().__init__(self.subject_identity(subject))

    @classmethod
    def validate_subject(cls, subject):
        if not isinstance(subject, dict) or not isinstance(subject.get('type'), str):
            raise ValueError('Assertion requires a typed subject reference')
        if not subject['type']:
            raise ValueError('Assertion subject type must not be empty')
        # Use the ordinary Object JSON contract; do not normalize caller values.
        return ScoringDetails.records.from_record({'value': subject}).records.to_record()['value']

    @classmethod
    def subject_identity(cls, subject):
        coordinate = {key: value for key, value in subject.items() if key != 'hints'}
        key = json.dumps(coordinate, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return Ship(uuid5(UUID(str(entity(cls).id)), key))

    class Records(TaravAssertion.Records):
        def parse_record(self, value):
            cls = self._owner
            data = super().parse_record(value)
            subject = cls.validate_subject(data.subject_ref)
            if data.id != cls.subject_identity(subject):
                raise ValueError('Assertion identity disagrees with its subject')
            return data

        def record_example(self):
            cls = self._owner
            return cls({'type': 'Example.Subject.Reference', 'name': 'example'}).records.to_record()


    @property
    def subject_ref(self):
        return json.loads(self._subject)

    def reference(self):
        """Keep the existing subject-addressed Assertion reference contract."""
        return {'type': entity(type(self)).name + '.Reference',
                'subject_ref': self.subject_ref}

    @classmethod
    def assessment_case_types(cls) -> tuple[type[AssessmentCase], ...]:
        """Case Types this Assertion can close for scoring workflows."""
        return ()

    def assessment_case(self, case_type: type[AssessmentCase], **material: object) -> AssessmentCase:
        """Build a closed case, distinguishing unsupported Types from missing scope."""
        if (
            not isinstance(case_type, type)
            or not issubclass(case_type, AssessmentCase)
            or case_type not in type(self).assessment_case_types()
        ):
            raise UnsupportedAssessmentCase(f'{type(self).__name__} does not produce {case_type!r}')
        case = self._build_assessment_case(case_type, **material)
        if type(case) is not case_type:
            raise TypeError('Assertion returned the wrong AssessmentCase Type')
        if case.assertion_ref != self.reference():
            raise ValueError('Assessment case belongs to another Assertion')
        case.records.to_record()
        return case

    def _build_assessment_case(self, case_type: type[AssessmentCase], **material: object) -> AssessmentCase:
        raise NotImplementedError('Supported case Types require an Assertion producer')

    @classmethod
    def from_reference(cls, reference):
        if reference.get('type') != entity(cls).name + '.Reference':
            raise ValueError('Reference does not identify this Assertion type')
        if set(reference) != {'type', 'subject_ref'}:
            raise ValueError('Unexpected Assertion reference fields')
        return cls(reference['subject_ref'])

    def _to_record(self):
        return {**super()._to_record(), 'subject_ref': self.subject_ref}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.subject_ref)


