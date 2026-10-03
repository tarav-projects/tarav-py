"""Blessing Assertions navigate scorer-owned results without hiding POIs."""

from copy import deepcopy
from uuid import uuid4

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.blessings import BlessablePOI, BlessingRecord, BlessingStore
from tarav.l1.checks import Check, CheckPOI, CheckResult
from tarav.l1.poi import fingerprint
from tarav.l2.blessings import (
    BlessingAcceptanceAssertion, BlessingAcceptanceCase,
    BlessingAcceptanceTribunal, BlessingGroundsCase,
)
from tarav.l2.scoring import (
    Assertable, IncompleteCaseScope, ScoringRepository, TribunalRegistry,
    enroll_case, prepare_pair, submit_judgment,
)
from tarav.l3.runtime import create_runtime


class ExampleCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('8ddeaa9c-b4a2-442c-b1b4-3938aad7af4e'),
                          name='Example.Blessing.Check')

    def _run(self):
        return CheckResult(self, status='completed', pois=(
            ExamplePOI(self, 'review', 'Review this situation',
                       situation={'path': 'example.md', 'edition': 1}),
        ))


class ExamplePOI(CheckPOI, BlessablePOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('0c839e6f-ea86-464e-85a8-1456beaeb78a'),
                          name='Example.Blessing.POI')


def _blessing(*, support=()):
    record = deepcopy(BlessingRecord.record_example())
    record['id'] = str(uuid4())
    record['rationale'] = 'The unusual formatting is faithful to the source.'
    record['support'] = list(support)
    return BlessingRecord.from_record(record)


def test_blessing_is_assertable_and_main_case_has_exact_poi_context(tmp_path):
    runtime = create_runtime(archive_root=tmp_path)
    blessing = _blessing()
    assert isinstance(blessing, Assertable)
    assert tuple(blessing.assertions) == ('main',)
    assertion = blessing.assertions['main']
    assert isinstance(assertion, BlessingAcceptanceAssertion)
    assert runtime.records.from_record(blessing.to_record()).assertions['main'].id == assertion.id
    case = assertion.assessment_case(BlessingAcceptanceCase, blessing=blessing)
    record = case.to_record()
    assert record['poi'] == blessing.to_record()['poi']
    assert record['actor'] == blessing.to_record()['actor']
    assert record['rationale'] == blessing.to_record()['rationale']
    assert '(none supplied)' in record['presentation']
    assert runtime.records.from_record(record).to_record() == record
    assert blessing.score_vector(ScoringRepository.initialize(tmp_path / 'scoring'))['main']['status'] == 'unassessed'


def test_optional_grounds_require_resolved_passage_and_do_not_fake_evidence(tmp_path):
    create_runtime(archive_root=tmp_path / 'archive')
    reference = {'type': 'Example.Source.Reference', 'locator': {'path': 'source.txt'}}
    blessing = _blessing(support=(reference,))
    assert tuple(blessing.assertions) == ('main', 'grounds')
    with pytest.raises(IncompleteCaseScope, match='every offered support'):
        blessing.assertions['main'].assessment_case(BlessingAcceptanceCase, blessing=blessing)
    with pytest.raises(IncompleteCaseScope, match='every offered support'):
        blessing.assertions['grounds'].assessment_case(BlessingGroundsCase, blessing=blessing)
    passages = [{'reference': reference, 'text': 'The publisher uses this formatting.'}]
    main_case = blessing.assertions['main'].assessment_case(
        BlessingAcceptanceCase, blessing=blessing, source_passages=passages,
    )
    grounds_case = blessing.assertions['grounds'].assessment_case(
        BlessingGroundsCase, blessing=blessing, source_passages=passages,
    )
    assert main_case.to_record()['source_passages'] == passages
    assert grounds_case.to_record()['source_passages'] == passages
    passages[0]['text'] = 'Later mutation'
    assert main_case.to_record()['source_passages'][0]['text'] != 'Later mutation'


def test_distinct_blessings_keep_identity_and_score_view_reads_tribunal(tmp_path):
    # tarav.breadcrumb 40fb7f57dc70ff6a251bc53eb76c7df45b2e0c64f6eb7eec6c0c8455cb849ac1
    create_runtime(archive_root=tmp_path / 'archive')
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((BlessingAcceptanceTribunal(),))
    first, second = _blessing(), _blessing()
    assert first.to_record()['poi']['id'] == second.to_record()['poi']['id']
    assert first.assertions['main'].id != second.assertions['main'].id
    cases = [enroll_case(
        repository,
        blessing.assertions['main'].assessment_case(
            BlessingAcceptanceCase, blessing=blessing,
        ),
        registry=registry,
    ) for blessing in (first, second)]
    assert first.score_vector(repository)['main']['status'] == 'unscored'
    pair, prompt = prepare_pair(repository, cases[0], cases[1], registry=registry)
    assert 'Which blessing better justifies' in prompt
    submit_judgment(repository, pair, outcome='A',
                    judge={'type': 'Example.Agent'}, rationale='First is better supported.')
    first_score = first.score_vector(repository)['main']
    second_score = second.score_vector(repository)['main']
    assert first_score['status'] == second_score['status'] == 'scored'
    assert first_score['assessments'][0]['value'] == 1.0
    assert second_score['assessments'][0]['value'] == 0.0
    assert 'score' not in first.to_record()


def test_case_rejects_a_changed_poi_situation_under_same_blessing_id(tmp_path):
    create_runtime(archive_root=tmp_path)
    blessing = _blessing()
    assertion = blessing.assertions['main']
    changed = deepcopy(blessing.to_record())
    changed['poi']['situation'] = {'example': 'different situation'}
    changed['poi']['id'] = fingerprint([
        changed['poi']['class_id'], changed['poi']['situation'],
    ])
    changed_blessing = BlessingRecord.from_record(changed)
    assert changed_blessing.assertions['main'].id != assertion.id
    with pytest.raises(ValueError, match='another blessing or POI situation'):
        assertion.assessment_case(BlessingAcceptanceCase, blessing=changed_blessing)


def test_old_standing_and_detection_remain_visible_after_blessing(tmp_path):
    create_runtime(archive_root=tmp_path / 'archive')
    check = ExampleCheck()
    first_result = check.run()
    poi = first_result.pois()[0]
    store = BlessingStore(tmp_path / 'blessings')
    record = store.bless(poi, actor={'type': 'Example.Actor', 'locator': {'name': 'agent'}},
                         rationale='Reviewed against source')
    assert store.standing(poi)['status'] == 'blessed'
    assert check.run().pois()[0].identity == poi.identity
    loaded = store.load(record['id'])
    assert isinstance(loaded, Assertable)
    assert loaded.assertions['main'].subject_ref['poi_id'] == poi.identity
    legacy = store.assess(record['id'], actor={'type': 'Example.Actor', 'locator': {'name': 'agent'}},
                          assertion='acceptance-justified', score=0.2,
                          rationale='Weak prior review')
    assert store.standing(poi)['scores'][0]['id'] == legacy['id']
    assert loaded.score_vector(ScoringRepository.initialize(tmp_path / 'scoring'))['main']['status'] == 'unassessed'
    assert entity(type(loaded)).name == 'Tarav.Blessings.Record'
