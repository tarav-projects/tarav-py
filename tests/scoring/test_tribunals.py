"""Cross-workflow pairwise scoring against closed, retained case packets."""

from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l2.scoring import (
    Assertion, PairwiseRankingCase, ScoringError, ScoringRepository,
    RankingScore, RankingWorkflow, Score, ScoringWorkflow, Tribunal,
    TribunalRegistry, TribunalScoreCheck, enroll_case, prepare_pair,
    judge_pair, submit_judgment, tribunal_scores,
)
from tarav.l2.scoring.model import (
    TRIBUNAL_PAIR_TYPE, TribunalCaseRecord, TribunalPairRecord, TribunalJudgmentRecord,
    new_record, record_reference,
)
from tarav.l3.runtime import create_runtime


def test_ranking_workflow_and_tribunal_have_distinct_class_and_object_identities(tmp_path):
    # tarav.breadcrumb a9435c4bc997322c773e21e48e34e069347b23475f3ad82d5d5801c80d5f7410
    assert issubclass(RankingWorkflow, ScoringWorkflow)
    assert RankingWorkflow().workflow is ScoringWorkflow()
    assert EvidenceTribunal() is EvidenceTribunal()
    assert StyleTribunal() is StyleTribunal()
    assert EvidenceTribunal() is not StyleTribunal()
    assert EvidenceTribunal().id != entity(EvidenceTribunal).id
    assert EvidenceTribunal().id != StyleTribunal().id
    assert EvidenceTribunal.records.from_record(EvidenceTribunal().records.to_record()) is EvidenceTribunal()
    runtime = create_runtime(archive_root=tmp_path, record_types=(EvidenceTribunal,))
    assert runtime.records.from_record(EvidenceTribunal().records.to_record()) is EvidenceTribunal()


def test_ranking_score_is_typed_but_derived(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(),))
    enroll_case(repository, _case(EvidenceCase, claim='Only', material='Quote'),
                registry=registry)
    score, = tribunal_scores(repository, str(entity(EvidenceTribunal).id))
    assert isinstance(score, RankingScore)
    assert isinstance(score, Score)
    assert score['value'] is None
    assert score.as_row() == dict(score)
    detached_ref = score['assertion_ref']
    detached_ref['type'] = 'Changed.Reference'
    assert score['assertion_ref'] != detached_ref
    runtime = create_runtime(archive_root=tmp_path / 'archive')
    assert runtime.records.from_record(score.records.to_record()).records.to_record() == score.records.to_record()


class EvidenceTribunal(Tribunal):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('46da1f8a-5c3c-4554-9285-1dc1115fa421'),
                          name='Example.Evidence.Tribunal')

    @classmethod
    def _tribunal_id(cls):
        return Ship('122ec8df-6147-45c6-8c35-47c9370b2fd6')

    def comparison_question(self):
        return 'Which claim has stronger source support?'


class StyleTribunal(Tribunal):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('d35553d7-07cb-42ca-8f92-97521de036a7'),
                          name='Example.Style.Tribunal')

    @classmethod
    def _tribunal_id(cls):
        return Ship('c8aa8db1-d391-403b-9df5-bebcdfe10ac3')

    def comparison_question(self):
        return 'Which phrasing is clearer?'


class EvidenceCase(PairwiseRankingCase):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('8834e1cf-d679-450f-a6e2-6c6eeef0128a'),
                          name='Example.Evidence.AssessmentCase')

    class RecordInterface(PairwiseRankingCase.RecordInterface):
        source_quote: str


class StyleCase(PairwiseRankingCase):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('3b354df3-b61f-43e4-a0eb-637330da4d87'),
                          name='Example.Style.AssessmentCase')

    class RecordInterface(PairwiseRankingCase.RecordInterface):
        style_note: str


class ExampleAssertion(Assertion):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip('7e0d8c8e-eace-419d-844e-89e89f2141cf'),
                          name='Example.Claims.Assertion')

    @classmethod
    def assessment_case_types(cls):
        return (EvidenceCase, StyleCase)

    def _build_assessment_case(self, case_type, *, claim, material):
        if case_type is EvidenceCase:
            return EvidenceCase(
                assertion_ref=self.reference(),
                tribunal_type_id=str(entity(EvidenceTribunal).id),
                question='Is this claim source-supported?',
                presentation=f'{claim}\nSource: {material}', source_quote=material,
            )
        return StyleCase(
            assertion_ref=self.reference(),
            tribunal_type_id=str(entity(StyleTribunal).id),
            question='Is this phrasing clear?',
            presentation=f'{claim}\nStyle note: {material}', style_note=material,
        )


def _assertion():
    return ExampleAssertion({'type': 'Example.Claim.Reference', 'id': str(uuid4())})


def _case(case_type, *, claim, material):
    return _assertion().assessment_case(case_type, claim=claim, material=material)


def test_two_tribunals_share_ranker_but_not_population(tmp_path):
    # tarav.breadcrumb 62350a7fa04268d941d05b6266c573c608af1754b451ef04d6bbc91dbf5e1188
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(), StyleTribunal()))
    first = enroll_case(repository, _case(EvidenceCase, claim='Claim one', material='Source A'),
                        registry=registry)
    second = enroll_case(repository, _case(EvidenceCase, claim='Claim two', material='Source B'),
                         registry=registry)
    style = enroll_case(repository, _case(StyleCase, claim='Clear wording', material='Short'),
                        registry=registry)
    second_style = enroll_case(repository,
                               _case(StyleCase, claim='Obscure wording', material='Too long'),
                               registry=registry)
    with pytest.raises(ScoringError, match='cross tribunals'):
        prepare_pair(repository, first, style, registry=registry)
    pair, prompt = prepare_pair(repository, first, second, registry=registry)
    assert 'Which claim has stronger source support?' in prompt
    assert 'Claim one' in prompt and 'Claim two' in prompt
    assert 'Source A' in prompt and 'Source B' in prompt
    assert 'Which phrasing is clearer?' not in prompt
    _, style_prompt = prepare_pair(repository, style, second_style, registry=registry)
    assert 'Which phrasing is clearer?' in style_prompt
    assert 'Style note: Short' in style_prompt
    assert 'Which claim has stronger source support?' not in style_prompt
    assert pair['prompt'] == prompt
    assert repository.open().resolve_reference(pair['a_case_ref']) == first
    assert repository.open().resolve_reference(pair['b_case_ref']) == second
    judgment = submit_judgment(repository, pair, outcome='A',
                               judge={'type': 'Example.Agent', 'name': 'judge-1'},
                               rationale='A has a direct quoted source.')
    assert repository.open().resolve_reference(judgment['pair_ref']) == pair
    with pytest.raises(ScoringError, match='already has a Judgment'):
        submit_judgment(repository, pair, outcome='B',
                        judge={'type': 'Example.Agent'}, rationale='Contradictory result')
    rows = tribunal_scores(repository.open(), str(entity(EvidenceTribunal).id))
    assert [row['value'] for row in rows] == [0.0, 1.0] or [row['value'] for row in rows] == [1.0, 0.0]
    assert all(row['comparisons'] == 1 and row['coverage'] == 1.0 for row in rows)
    assert all(row['possible_opponents'] == 1 for row in rows)
    style_rows = tribunal_scores(repository, str(entity(StyleTribunal).id))
    assert len(style_rows) == 2 and all(row['value'] is None for row in style_rows)
    assert all(row['comparisons'] == 0 for row in style_rows)


def test_abstention_keeps_cases_unscored_and_pois_visible(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(),))
    cases = [enroll_case(repository, _case(EvidenceCase, claim=f'Claim {i}', material=f'S{i}'),
                         registry=registry) for i in range(3)]
    pair, _ = prepare_pair(repository, cases[0], cases[1], registry=registry, reverse=True)
    submit_judgment(repository, pair, outcome='abstain',
                    judge={'type': 'Example.Agent'}, rationale='Packets are insufficient.')
    tribunal_id = str(entity(EvidenceTribunal).id)
    rows = tribunal_scores(repository, tribunal_id)
    assert len(rows) == 3
    assert all(row['value'] is None for row in rows)
    assert sorted(row['abstentions'] for row in rows) == [0, 1, 1]
    result = TribunalScoreCheck(repository, tribunal_id).run()
    assert result.status == 'completed'
    assert len(result.pois()) == 3
    assert all(type(poi).__name__ == 'TribunalAssertionUnassessed' for poi in result.pois())


def test_pair_record_rejects_changed_or_outside_case(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(),))
    first = enroll_case(repository, _case(EvidenceCase, claim='A', material='S'),
                        registry=registry)
    second = enroll_case(repository, _case(EvidenceCase, claim='B', material='T'),
                         registry=registry)
    with pytest.raises(ScoringError, match='not retained'):
        prepare_pair(repository, {**first, 'id': str(uuid4())}, second, registry=registry)
    with pytest.raises(ScoringError, match='distinct'):
        prepare_pair(repository, first, first, registry=registry)
    valid_pair, _ = prepare_pair(repository, first, second, registry=registry)
    with pytest.raises(ScoringError, match='immutable'):
        repository.save({**first, 'case': {**first['case'], 'presentation': 'Edited packet'}})
    wrong_tribunal_pair = new_record(
        TRIBUNAL_PAIR_TYPE,
        tribunal_type_id=str(entity(StyleTribunal).id),
        a_case_ref=record_reference(first), b_case_ref=record_reference(second),
        prompt=valid_pair['prompt'], prompt_sha256=valid_pair['prompt_sha256'],
    )
    with pytest.raises(ScoringError, match='one tribunal'):
        repository.create(wrong_tribunal_pair)


def test_scorer_gets_only_prompt_and_sparse_weak_signals(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(),))
    cases = [enroll_case(repository, _case(EvidenceCase, claim=f'Claim {i}', material=f'S{i}'),
                         registry=registry) for i in range(3)]
    pair, prompt = prepare_pair(repository, cases[0], cases[1], registry=registry)
    seen = []
    judgment = judge_pair(
        repository, pair, judge={'type': 'Example.Agent'},
        evaluate=lambda supplied: (seen.append(supplied)
                                   or {'outcome': 'A', 'rationale': 'A has stronger support.'}),
    )
    assert seen == [prompt]
    assert judgment['outcome'] == 'A'
    tribunal_id = str(entity(EvidenceTribunal).id)
    rows = tribunal_scores(repository, tribunal_id)
    assert sorted(row['value'] for row in rows if row['value'] is not None) == [0.0, 1.0]
    assert sorted(row['coverage'] for row in rows) == [0.0, 0.5, 0.5]
    result = TribunalScoreCheck(repository, tribunal_id, sparse_coverage=0.75).run()
    cases = [type(poi).__name__ for poi in result.pois()]
    assert cases.count('TribunalAssertionUnassessed') == 1
    assert cases.count('TribunalCoverageSparse') == 2
    assert cases.count('TribunalRelativeSupportLow') == 1


def test_tie_is_half_relative_support(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((EvidenceTribunal(),))
    a = enroll_case(repository, _case(EvidenceCase, claim='A', material='S'), registry=registry)
    b = enroll_case(repository, _case(EvidenceCase, claim='B', material='T'), registry=registry)
    pair, _ = prepare_pair(repository, a, b, registry=registry)
    submit_judgment(repository, pair, outcome='tie', judge={'type': 'Example.Agent'},
                    rationale='Evidence is equally strong.')
    assert [row['value'] for row in tribunal_scores(repository, str(entity(EvidenceTribunal).id))] == [0.5, 0.5]


def test_one_case_has_no_invented_score(tmp_path):
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    registry = TribunalRegistry((StyleTribunal(),))
    enroll_case(repository, _case(StyleCase, claim='Only one', material='Clear'),
                registry=registry)
    rows = tribunal_scores(repository, str(entity(StyleTribunal).id))
    assert len(rows) == 1
    assert rows[0]['value'] is None and rows[0]['possible_opponents'] == 0


def test_tribunal_records_use_the_installed_scoring_registry(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / 'archive')
    for record_type in (TribunalCaseRecord, TribunalPairRecord, TribunalJudgmentRecord):
        assert runtime.records.resolve_ship(entity(record_type).id) is record_type
        example = record_type.records.record_example()
        assert runtime.records.from_record(example).records.to_record() == example
