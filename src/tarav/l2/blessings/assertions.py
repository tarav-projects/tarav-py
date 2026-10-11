"""Blessing-owned Assertions and read-only navigation into scorer-owned results."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from uuid import UUID

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.actions.blessing import Blessing
from tarav.l1.blessings.workflow import BLESSINGS_WORKFLOW_SHIP
from tarav.l2.scoring import (
    Assertion, AssertionNamespace, AssessmentCase, IncompleteCaseScope,
    PairwiseRankingCase, Tribunal, tribunal_scores,
)
from tarav.l2.scoring.model import TRIBUNAL_CASE_TYPE, canonical_json
from tarav.l2.scoring.repository import ScoringRepository


class BlessingAcceptanceTribunal(Tribunal):
    """Compare how well supplied grounds justify accepting continuing POIs."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('ee70eef8-4256-467f-acef-e63431156e13'),
            name='Tarav.Blessings.Acceptance.Tribunal',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def _tribunal_id(cls):
        return Ship('ddf43a66-b162-419a-984c-c2b235f9a27e')

    def comparison_question(self) -> str:
        return 'Which blessing better justifies leaving its continuing POI without immediate action?'

    def instructions(self) -> str:
        return ('Judge the supplied POI snapshots, rationales, and source passages only. '
                'Absence of support is visible weakness, not a reason to invent evidence.')


class BlessingAcceptanceCase(PairwiseRankingCase):
    """Closed packet about accepting one exact blessing and POI situation."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('a4860f0f-8b63-46c5-86f2-83045440b5d0'),
            name='Tarav.Blessings.Acceptance.AssessmentCase',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    class RecordInterface(PairwiseRankingCase.RecordInterface):
        blessing_id: str
        poi: dict
        actor: dict | None
        rationale: str
        support: list[dict]
        source_passages: list[dict]

    class Records(PairwiseRankingCase.Records):
        def record_example(self):
            cls = self._owner
            blessing = Blessing.records.from_record(Blessing.records.record_example())
            return BlessingAcceptanceAssertion.from_blessing(blessing).assessment_case(
                cls, blessing=blessing,
            ).records.to_record()



class BlessingGroundsCase(AssessmentCase):
    """Closed question about whether offered source passages support a rationale."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('7b5f1c63-c809-475d-b67d-c147c12d5e2b'),
            name='Tarav.Blessings.Grounds.AssessmentCase',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    class RecordInterface(AssessmentCase.RecordInterface):
        blessing_id: str
        rationale: str
        support: list[dict]
        source_passages: list[dict]

    class Records(AssessmentCase.Records):
        def record_example(self):
            cls = self._owner
            record = Blessing.records.record_example()
            support = {'type': 'Example.Source.Reference', 'locator': {'path': 'example.txt'}}
            record['support'] = [support]
            blessing = Blessing.records.from_record(record)
            return BlessingGroundsAssertion.from_blessing(blessing).assessment_case(
                cls, blessing=blessing,
                source_passages=[{'reference': support, 'text': 'Example passage.'}],
            ).records.to_record()



# tarav.breadcrumb 91366f34b009b85172f86bd59fab0a34e84658851653c39b331340e0a314e17f
class _BlessingAssertion(Assertion):
    """A claim tied to one Blessing, the closing record of a POI's action, and its POI situation."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('b9a44e9a-d6cc-4f05-adb2-4e5fbc64df67'),
            name='Tarav.Blessings.Assertion',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_subject(cls, subject):
        value = super().validate_subject(subject)
        if value.get('type') != 'Tarav.Blessings.Blessing.Reference':
            raise ValueError('Blessing Assertion requires a Blessing reference')
        try:
            UUID(str(value['blessing_id']))
            TypeShip(value['poi_class_id'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError('Blessing Assertion requires blessing and POI identities') from exc
        if not isinstance(value.get('poi_id'), str) or not value['poi_id']:
            raise ValueError('Blessing Assertion requires an exact POI identity')
        if not isinstance(value.get('poi_situation'), dict):
            raise ValueError('Blessing Assertion requires the retained situation')
        return value

    class Records(Assertion.Records):
        def record_example(self):
            cls = self._owner
            blessing = Blessing.records.from_record(Blessing.records.record_example())
            return cls.from_blessing(blessing).records.to_record()


    @classmethod
    def from_blessing(cls, blessing: Blessing):
        if not isinstance(blessing, Blessing):
            raise TypeError('Expected a Blessing')
        record = blessing.records.to_record()
        poi = record['poi']
        return cls({
            'type': 'Tarav.Blessings.Blessing.Reference',
            'blessing_id': str(blessing.id),
            'blessing_type': record['type'],
            'poi_class_id': poi['class_id'],
            'poi_id': poi['id'],
            'poi_situation': poi['situation'],
        })

    def _blessing_record(self, blessing: Blessing) -> dict:
        if not isinstance(blessing, Blessing):
            raise IncompleteCaseScope('Blessing case needs the Blessing')
        if type(self).from_blessing(blessing).id != self.id:
            raise ValueError('Blessing case belongs to another blessing or POI situation')
        return blessing.records.to_record()


class BlessingAcceptanceAssertion(_BlessingAssertion):
    """This continuing POI situation is acceptable without immediate action."""
    # tarav.breadcrumb 70cabc230c3391b8429af97593b2e3cfd05d5ad01a111afef1fe526b4b87a5fb

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('808ac08f-0fd2-4b2f-b0ec-521286f79a4a'),
            name='Tarav.Blessings.Acceptance.Assertion',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def assessment_case_types(cls):
        return (BlessingAcceptanceCase,)

    def _build_assessment_case(self, case_type, *, blessing=None, source_passages=()):
        record = self._blessing_record(blessing)
        passages = _closed_passages(record['support'], source_passages)
        presentation = '\n'.join((
            'Acceptance claim: this still-detected POI needs no immediate action.',
            f'POI: {json.dumps(record["poi"], sort_keys=True, ensure_ascii=False)}',
            f'Actor: {json.dumps(record["actor"], sort_keys=True, ensure_ascii=False)}',
            f'Rationale: {record["reason"]}',
            'Offered support: ' + (
                json.dumps(passages, sort_keys=True, ensure_ascii=False)
                if passages else '(none supplied)'
            ),
        ))
        return BlessingAcceptanceCase(
            assertion_ref=self.reference(),
            tribunal_type_id=str(entity(BlessingAcceptanceTribunal).id),
            question='How justified is accepting this POI without immediate action?',
            presentation=presentation,
            blessing_id=str(blessing.id), poi=record['poi'], actor=record['actor'],
            rationale=record['reason'], support=record['support'],
            source_passages=passages,
        )


class BlessingGroundsAssertion(_BlessingAssertion):
    """The offered source passages substantiate this blessing's rationale."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('455f4acd-5d7d-4e90-8da2-0e76b9784bc7'),
            name='Tarav.Blessings.Grounds.Assertion',
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    @classmethod
    def assessment_case_types(cls):
        return (BlessingGroundsCase,)

    def _build_assessment_case(self, case_type, *, blessing=None, source_passages=()):
        record = self._blessing_record(blessing)
        if not record['support']:
            raise IncompleteCaseScope('Grounds case needs at least one offered support reference')
        passages = _closed_passages(record['support'], source_passages)
        return BlessingGroundsCase(
            assertion_ref=self.reference(),
            question='Do the supplied source passages substantiate this rationale?',
            presentation='\n'.join((
                f'Rationale: {record["reason"]}',
                json.dumps(passages, sort_keys=True, ensure_ascii=False),
            )),
            blessing_id=str(blessing.id), rationale=record['reason'],
            support=record['support'], source_passages=passages,
        )


def _closed_passages(support: Sequence[dict], passages: Sequence[dict]) -> list[dict]:
    # tarav.breadcrumb 421710242c9af1b4ae681feb0078c080b6b3dfef6767804fc27e6d67a712eeeb
    values = list(passages)
    expected = Counter(canonical_json(item) for item in support)
    seen = Counter()
    for passage in values:
        if not isinstance(passage, dict) or not isinstance(passage.get('reference'), dict):
            raise IncompleteCaseScope('Every source passage needs its exact support reference')
        if not isinstance(passage.get('text'), str) or not passage['text'].strip():
            raise IncompleteCaseScope('Every source passage needs nonempty text')
        seen[canonical_json(passage['reference'])] += 1
    if seen != expected:
        raise IncompleteCaseScope('Resolve every offered support reference to one passage')
    return values


def assertions_for_blessing(blessing: Blessing) -> AssertionNamespace:
    """Expose stable labels without turning an optional factual ground into fact."""

    assertions = {'main': BlessingAcceptanceAssertion.from_blessing(blessing)}
    if blessing.records.to_record()['support']:
        assertions['grounds'] = BlessingGroundsAssertion.from_blessing(blessing)
    return AssertionNamespace(assertions)


def score_vector_for_blessing(
    blessing: Blessing, repository: ScoringRepository,
) -> dict[str, dict]:
    """Read named assessments from scorer storage."""
    # tarav.breadcrumb 899cfa53b02f35e7a436d35d3b60f2b1e544ddbd150d682d41901b7985474eca

    if not isinstance(repository, ScoringRepository):
        raise TypeError('Expected a ScoringRepository')
    cases = repository.records(TRIBUNAL_CASE_TYPE)
    vector = {}
    for label, assertion in assertions_for_blessing(blessing).items():
        reference = assertion.reference()
        tribunal_ids = sorted({
            str(case['tribunal_type_id']) for case in cases
            if case['assertion_ref'] == reference
        })
        entries = []
        for tribunal_id in tribunal_ids:
            entries.extend(
                row.as_row() for row in tribunal_scores(repository, tribunal_id)
                if row['assertion_ref'] == reference
            )
        status = ('unassessed' if not entries else
                  'unscored' if all(row['value'] is None for row in entries) else 'scored')
        vector[label] = {
            'assertion_ref': reference,
            'status': status,
            'assessments': entries,
        }
    return vector
