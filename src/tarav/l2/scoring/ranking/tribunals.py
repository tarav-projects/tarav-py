"""Generic, closed-packet pairwise scoring within typed tribunals."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from threading import RLock
from typing import Literal

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.checks import Check, CheckPOI, CheckResult

from ..assertions import AssessmentCase, Assertion
from ..model import (
    TRIBUNAL_CASE_TYPE, TRIBUNAL_JUDGMENT_TYPE, TRIBUNAL_PAIR_TYPE,
    ScoringError, canonical_json, new_record, record_reference, validate_record,
)
from ..repository import ScoringRepository
from .score import RankingScore
from .workflow import RANKING_WORKFLOW_SHIP


class PairwiseRankingCase(AssessmentCase):
    """A producer-owned case admitted by one named tribunal Type."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('6022dc2e-9727-433a-bfaa-9b21d95f0564'),
                          name='Tarav.Scoring.PairwiseRankingCase',
                          workflow=RANKING_WORKFLOW_SHIP)

    class RecordInterface(AssessmentCase.RecordInterface):
        tribunal_type_id: str

    class Records(AssessmentCase.Records):
        def parse_record(self, value):
            data = super().parse_record(value)
            TypeShip(data.tribunal_type_id)
            return data

        def record_example(self):
            cls = self._owner
            return cls(
                assertion_ref=Assertion({'type': 'Example.Subject.Reference'}).reference(),
                question='Which case is better supported?',
                presentation='Claim and supplied evidence.',
                tribunal_type_id='00000000-0000-4000-8000-000000000006',
            ).records.to_record()



    @property
    def tribunal_type_id(self) -> str:
        return str(self.records.to_record()['tribunal_type_id'])


class Tribunal(TaravEntity):
    """One identified comparison context per concrete Tribunal class."""
    # tarav.breadcrumb bf84293588c4
    # tarav.breadcrumb 6993f6372ad3
    # tarav.breadcrumb 5a75d5a01ed4

    _instances: dict[type, 'Tribunal'] = {}
    _instance_lock = RLock()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if not isinstance(cls.__dict__.get('_tribunal_id'), classmethod):
            raise TypeError(f'{cls.__name__} must declare a class-local _tribunal_id()')

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('c05e455a-6d3b-4101-9e4e-bf66c38c5610'),
                          name='Tarav.Scoring.Tribunal',
                          workflow=RANKING_WORKFLOW_SHIP)

    @classmethod
    def _tribunal_id(cls) -> Ship:
        return Ship('56ced523-4b67-4a81-a410-f2f0acb83077')

    def __new__(cls):
        with Tribunal._instance_lock:
            if cls not in Tribunal._instances:
                identity = cls._tribunal_id()
                if not isinstance(identity, Ship):
                    raise TypeError('Tribunal identity must be a Ship')
                if str(identity) == str(entity(cls).id):
                    raise ValueError('Tribunal object and class need distinct identities')
                instance = super().__new__(cls)
                TaravEntity.__init__(instance, identity)
                Tribunal._instances[cls] = instance
            return Tribunal._instances[cls]

    def __init__(self):
        pass

    @classmethod
    def _from_record(cls, data):
        if data.id != cls._tribunal_id():
            raise ValueError('Record does not identify this Tribunal')
        return cls()

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return cls().records.to_record()


    def comparison_question(self) -> str:
        raise NotImplementedError

    def instructions(self) -> str:
        return 'Judge only the supplied cases; abstain if their scope is insufficient.'

    def admits(self, case: PairwiseRankingCase) -> bool:
        return case.tribunal_type_id == str(entity(type(self)).id)


class TribunalRegistry:
    """Trusted tribunal Type lookup without a central hard-coded population list."""

    def __init__(self, tribunals: Sequence[Tribunal] = ()) -> None:
        self._tribunals: dict[str, Tribunal] = {}
        for tribunal in tribunals:
            self.register(tribunal)

    def register(self, tribunal: Tribunal) -> None:
        if not isinstance(tribunal, Tribunal):
            raise TypeError('Expected a Tribunal')
        identity = str(entity(type(tribunal)).id)
        if identity in self._tribunals:
            raise ScoringError(f'Tribunal already registered: {identity}')
        self._tribunals[identity] = tribunal

    def resolve(self, identity: str) -> Tribunal:
        try:
            return self._tribunals[identity]
        except KeyError as exc:
            raise ScoringError(f'Unknown tribunal Type: {identity}') from exc


def enroll_case(
    repository: ScoringRepository, case: PairwiseRankingCase,
    *, registry: TribunalRegistry,
) -> dict[str, object]:
    """Retain the exact case packet after its named tribunal admits it."""

    if not isinstance(case, PairwiseRankingCase):
        raise TypeError('Pairwise scoring requires a PairwiseRankingCase')
    tribunal = registry.resolve(case.tribunal_type_id)
    if not tribunal.admits(case):
        raise ScoringError('Tribunal rejected this case')
    packet = case.records.to_record()
    record = new_record(
        TRIBUNAL_CASE_TYPE,
        tribunal_type_id=case.tribunal_type_id,
        assertion_ref=case.assertion_ref,
        case=packet,
    )
    return repository.create(record)


def prepare_pair(
    repository: ScoringRepository, first: Mapping[str, object],
    second: Mapping[str, object], *, registry: TribunalRegistry,
    reverse: bool = False,
) -> tuple[dict[str, object], str]:
    """Freeze one A/B task and its exact prompt from two retained cases."""

    for case_record in (first, second):
        validate_record(case_record)
        if case_record['type'] != TRIBUNAL_CASE_TYPE:
            raise ScoringError('Pair requires retained Tribunal Case Records')
        repository.resolve_reference(record_reference(case_record))
    if first['id'] == second['id']:
        raise ScoringError('Pair requires distinct cases')
    tribunal_id = str(first['tribunal_type_id'])
    if second['tribunal_type_id'] != tribunal_id:
        raise ScoringError('Pair cannot cross tribunals')
    if first['assertion_ref'] == second['assertion_ref']:
        raise ScoringError('Pair requires distinct Assertions')
    tribunal = registry.resolve(tribunal_id)
    a, b = (second, first) if reverse else (first, second)
    prompt = render_pair(tribunal, a, b)
    record = new_record(
        TRIBUNAL_PAIR_TYPE,
        tribunal_type_id=tribunal_id,
        a_case_ref=record_reference(a), b_case_ref=record_reference(b),
        prompt=prompt, prompt_sha256=hashlib.sha256(prompt.encode('utf-8')).hexdigest(),
    )
    return repository.create(record), prompt


def render_pair(
    tribunal: Tribunal, a: Mapping[str, object], b: Mapping[str, object],
) -> str:
    """Generic ranker, tribunal question, then two closed case presentations."""
    # tarav.breadcrumb e9cf546c037a

    question = tribunal.comparison_question().strip()
    instructions = tribunal.instructions().strip()
    if not question or not instructions:
        raise ScoringError('Tribunal needs a question and instructions')
    a_case, b_case = a['case'], b['case']
    return '\n\n'.join((
        '# Pairwise tribunal judgment',
        'Choose A, B, tie, or abstain. Use only the supplied packets. '
        'A relative preference is not a truth verdict.',
        f'Tribunal: {entity(type(tribunal)).name}\nQuestion: {question}\n{instructions}',
        f'## Case A\nQuestion: {a_case["question"]}\n{a_case["presentation"]}',
        f'## Case B\nQuestion: {b_case["question"]}\n{b_case["presentation"]}',
        'Return one outcome (A, B, tie, abstain) with a concise rationale.',
    ))


def submit_judgment(
    repository: ScoringRepository, pair: Mapping[str, object], *,
    outcome: Literal['A', 'B', 'tie', 'abstain'],
    judge: Mapping[str, object], rationale: str,
) -> dict[str, object]:
    """Retain one attributed result; no scorer may expand the frozen packet."""

    validate_record(pair)
    if pair['type'] != TRIBUNAL_PAIR_TYPE:
        raise ScoringError('Judgment requires a Tribunal Pair')
    repository.resolve_reference(record_reference(pair))
    result = new_record(
        TRIBUNAL_JUDGMENT_TYPE,
        tribunal_type_id=pair['tribunal_type_id'],
        pair_ref=record_reference(pair), outcome=outcome,
        judge=dict(judge), rationale=rationale,
    )
    return repository.create(result)


def judge_pair(
    repository: ScoringRepository, pair: Mapping[str, object], *,
    judge: Mapping[str, object],
    evaluate: Callable[[str], Mapping[str, object]],
) -> dict[str, object]:
    """Give a scorer only the frozen prompt, then retain its constrained answer."""

    validate_record(pair)
    if pair['type'] != TRIBUNAL_PAIR_TYPE:
        raise ScoringError('Judgment requires a Tribunal Pair')
    repository.resolve_reference(record_reference(pair))
    answer = evaluate(str(pair['prompt']))
    if not isinstance(answer, Mapping):
        raise ScoringError('Scorer must return an outcome and rationale')
    return submit_judgment(
        repository, pair,
        outcome=answer.get('outcome'),
        rationale=answer.get('rationale'),
        judge=judge,
    )


def tribunal_scores(repository: ScoringRepository, tribunal_type_id: str) -> tuple[RankingScore, ...]:
    """Derived relative support plus sampling, keyed by exact Assertion reference."""
    # tarav.breadcrumb 8d68e5873d28

    cases = [item for item in repository.records(TRIBUNAL_CASE_TYPE)
             if item['tribunal_type_id'] == tribunal_type_id]
    pairs = [item for item in repository.records(TRIBUNAL_PAIR_TYPE)
             if item['tribunal_type_id'] == tribunal_type_id]
    judgments = [item for item in repository.records(TRIBUNAL_JUDGMENT_TYPE)
                 if item['tribunal_type_id'] == tribunal_type_id]
    case_by_id = {str(item['id']): item for item in cases}
    pair_by_id = {str(item['id']): item for item in pairs}
    rows: dict[str, dict] = {}
    for case in cases:
        key = canonical_json(case['assertion_ref'])
        row = rows.setdefault(key, {
            'assertion_ref': case['assertion_ref'], 'case_ids': [],
            'wins': 0, 'losses': 0, 'ties': 0, 'abstentions': 0,
            'comparisons': 0, 'opponents': set(),
        })
        row['case_ids'].append(case['id'])
    for judgment in judgments:
        pair = pair_by_id.get(str(judgment['pair_ref']['id']))
        if pair is None or record_reference(pair) != judgment['pair_ref']:
            raise ScoringError('Judgment references a missing or changed Pair')
        if pair['tribunal_type_id'] != tribunal_type_id:
            raise ScoringError('Judgment tribunal disagrees with its Pair')
        a = case_by_id.get(str(pair['a_case_ref']['id']))
        b = case_by_id.get(str(pair['b_case_ref']['id']))
        if a is None or b is None:
            raise ScoringError('Pair references a missing case')
        if record_reference(a) != pair['a_case_ref'] or record_reference(b) != pair['b_case_ref']:
            raise ScoringError('Pair references a missing or changed case')
        a_key, b_key = canonical_json(a['assertion_ref']), canonical_json(b['assertion_ref'])
        if judgment['outcome'] == 'abstain':
            rows[a_key]['abstentions'] += 1
            rows[b_key]['abstentions'] += 1
            continue
        for key, opponent in ((a_key, b_key), (b_key, a_key)):
            rows[key]['comparisons'] += 1
            rows[key]['opponents'].add(opponent)
        if judgment['outcome'] == 'tie':
            rows[a_key]['ties'] += 1
            rows[b_key]['ties'] += 1
        elif judgment['outcome'] == 'A':
            rows[a_key]['wins'] += 1
            rows[b_key]['losses'] += 1
        else:
            rows[b_key]['wins'] += 1
            rows[a_key]['losses'] += 1
    population = len(rows)
    output = []
    for row in rows.values():
        comparisons = row['comparisons']
        output.append({
            **{key: value for key, value in row.items() if key != 'opponents'},
            'value': (row['wins'] + 0.5 * row['ties']) / comparisons if comparisons else None,
            'opponent_count': len(row['opponents']),
            'possible_opponents': max(0, population - 1),
            'coverage': len(row['opponents']) / (population - 1) if population > 1 else 0.0,
            'tribunal_type_id': tribunal_type_id,
        })
    return tuple(RankingScore(row) for row in sorted(
        output, key=lambda row: canonical_json(row['assertion_ref'])))


class TribunalScorePOI(CheckPOI):
    """Family, never raised: an Assertion's comparative score needs attention."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('ec5a6bc9-b6bd-413d-a713-1325eb7014a5'),
                          name='Tarav.Scoring.TribunalScore.POI',
                          workflow=RANKING_WORKFLOW_SHIP)


class TribunalAssertionUnassessed(TribunalScorePOI):
    """An Assertion has no comparative judgment yet."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('0e3c3a0a-56f7-4efb-ae03-8facbc7475b2'),
                          name='Tarav.Scoring.TribunalScore.POI.Unassessed', workflow=RANKING_WORKFLOW_SHIP)


class TribunalRelativeSupportLow(TribunalScorePOI):
    """An Assertion has weak relative support."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('4dd9d7b0-d25a-44f2-8a9e-8ed0e47a6675'),
                          name='Tarav.Scoring.TribunalScore.POI.RelativeSupportLow', workflow=RANKING_WORKFLOW_SHIP)


class TribunalCoverageSparse(TribunalScorePOI):
    """An Assertion was compared against too few others."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip('98e71505-0939-461b-b388-37c558f97b45'),
                          name='Tarav.Scoring.TribunalScore.POI.CoverageSparse', workflow=RANKING_WORKFLOW_SHIP)


class TribunalScoreCheck(Check):
    """Expose unassessed, sparse, and weak relative support as scoring POIs."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('11dba7b2-38c5-4396-8b94-08e8b862112d'),
                          name='Tarav.Scoring.TribunalScore.Check',
                          workflow=RANKING_WORKFLOW_SHIP)

    def __init__(self, repository: ScoringRepository, tribunal_type_id: str,
                 *, low_support: float = 0.35, sparse_coverage: float = 0.5) -> None:
        super().__init__()
        self.repository = repository
        self.tribunal_type_id = tribunal_type_id
        self.low_support = low_support
        self.sparse_coverage = sparse_coverage

    def _run(self) -> CheckResult:
        rows = tribunal_scores(self.repository, self.tribunal_type_id)
        pois = []
        for row in rows:
            cases = []
            if row['value'] is None:
                cases.append((TribunalAssertionUnassessed, 'No comparative judgment yet'))
            else:
                if row['value'] < self.low_support:
                    cases.append((TribunalRelativeSupportLow, 'Weak relative support'))
                if row['coverage'] < self.sparse_coverage:
                    cases.append((TribunalCoverageSparse, 'Sparse comparison coverage'))
            for case, message in cases:
                pois.append(case(
                    self, message,
                    situation={'tribunal_type_id': self.tribunal_type_id,
                               'assertion_ref': row['assertion_ref'],
                               'comparisons': row['comparisons']},
                    details=row.as_row(),
                ))
        return CheckResult(self, status='completed', pois=pois,
                           data=tuple(row.as_row() for row in rows))


__all__ = [
    'PairwiseRankingCase', 'Tribunal', 'TribunalRegistry', 'TribunalScoreCheck',
    'TribunalScorePOI', 'enroll_case', 'prepare_pair', 'render_pair', 'judge_pair',
    'submit_judgment', 'tribunal_scores',
]
