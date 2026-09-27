"""Assertion objects carry check semantics; scoring owns evaluation mechanics."""

import json
from uuid import UUID, uuid5

from pydantic import model_validator

from tarav.kernel import FileRecord, Ship, TaravClass, TaravEntity, TypeShip, entity
from .identity import SCORING_WORKFLOW_SHIP


class ScoringDetails(FileRecord):
    """Inspectable JSON carried by scoring Context entries."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('5cb94b42-7c0f-4a8d-950e-e9fbc50ecf72'),
                          name='Tarav.Scoring.Details', workflow=SCORING_WORKFLOW_SHIP)


class Assertion(TaravEntity):
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

    class RecordInterface(TaravEntity.RecordInterface):
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
        return ScoringDetails.from_record({'value': subject}).to_record()['value']

    @classmethod
    def subject_identity(cls, subject):
        coordinate = {key: value for key, value in subject.items() if key != 'hints'}
        key = json.dumps(coordinate, sort_keys=True, separators=(',', ':'), allow_nan=False)
        return Ship(uuid5(UUID(str(entity(cls).id)), key))

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        subject = cls.validate_subject(data.subject_ref)
        if data.id != cls.subject_identity(subject):
            raise ValueError('Assertion identity disagrees with its subject')
        return data

    @property
    def subject_ref(self):
        return json.loads(self._subject)

    def reference(self):
        """Keep the existing subject-addressed Assertion reference contract."""
        return {'type': entity(type(self)).name + '.Reference',
                'subject_ref': self.subject_ref}

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
    def _from_record(cls, data):
        return cls(data.subject_ref)

    @classmethod
    def record_example(cls):
        return cls({'type': 'Example.Subject.Reference', 'name': 'example'}).to_record()

    def obj_context(self, builder):
        builder.add('subject', opener=lambda: ScoringDetails.from_record(
            {'type': entity(ScoringDetails).name, 'reference': self.subject_ref}))


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
