from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tarav.kernel import Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.lines.assertions import LineGroundingAssertion
from tarav.lines.workflow import LinesWorkflow
from tarav.runtime import create_runtime
from tarav.scoring import (
    Assertion, GROUNDING_POOL_TYPE, ScoringError, ScoringRepository, ScoringWorkflow,
    create_pool_enrollment, create_scoring_trace,
)
from tarav.scoring.tasks import DEFAULT_ASSERTION_RANKING_REGISTRY, DEFAULT_RANKING_POOL_REGISTRY


class ExtractionAssertion(Assertion):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls,
                          id=TypeShip('ef5b04cf-fb57-43e7-8351-aea6a61b2806'),
                          name='Example.Extraction.Assertion')


def test_assertion_identity_ownership_and_context(tmp_path):
    runtime = create_runtime(archive_root=tmp_path)
    assertion = LineGroundingAssertion.from_record(LineGroundingAssertion.record_example())
    assert isinstance(assertion, Assertion)
    assert entity(Assertion).workflow is ScoringWorkflow()
    assert assertion.workflow is LinesWorkflow()
    assert runtime.records.from_record(assertion.to_record()).id == assertion.id
    assert LineGroundingAssertion.from_reference(assertion.reference()).id == assertion.id
    assert Ship(assertion.subject_ref['edition_id']) in assertion.ships()
    context = runtime.context(assertion)
    assert context.open('subject').to_record()['reference'] == assertion.subject_ref
    assert context.open('evidence').to_record()['reference'] == assertion.subject_ref
    changed = assertion.subject_ref
    changed['edition_id'] = str(uuid4())
    assert LineGroundingAssertion(changed).id != assertion.id
    assert assertion.subject_ref != changed
    record = assertion.to_record()
    record['id'] = str(uuid4())
    with pytest.raises(ValueError, match='identity'):
        LineGroundingAssertion.from_record(record)


def test_custom_assertion_can_use_common_trace_without_line_subject(tmp_path):
    runtime = create_runtime(archive_root=tmp_path, record_types=(ExtractionAssertion,))
    assertion = ExtractionAssertion({'type': 'Example.Extraction.Reference',
                                     'source': 'evidence.json', 'item': 3})
    loaded = runtime.records.from_record(assertion.to_record())
    assert loaded.to_record() == assertion.to_record()
    hinted = ExtractionAssertion({**assertion.subject_ref, 'hints': {'note': 'opaque'}})
    assert hinted.id == assertion.id
    assert hinted.to_record()['subject_ref']['hints'] == {'note': 'opaque'}
    trace = runtime.records.from_record(create_scoring_trace(assertion.reference()))
    assert isinstance(trace, TaravEntity)
    from tarav.scoring.tasks import AssertionRankingRegistry
    registry = AssertionRankingRegistry((ExtractionAssertion,))
    edge = runtime.context(trace).open('assertion_ref')
    assert edge.resolve(assertions=registry).id == assertion.id
    with pytest.raises(TypeError, match='registry'):
        edge.resolve()


def test_enrollment_edges_resolve_typed_objects_and_exact_records(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / 'archive')
    repository = ScoringRepository.initialize(tmp_path / 'scoring')
    pool = repository.create(LineGroundingAssertion.create_pool(
        name='example', pool_type=GROUNDING_POOL_TYPE,
        pool_registry=DEFAULT_RANKING_POOL_REGISTRY))
    assertion = LineGroundingAssertion.from_record(LineGroundingAssertion.record_example())
    enrollment = repository.create(create_pool_enrollment(pool=pool,
                                                         assertion_ref=assertion.reference()))
    obj = runtime.records.from_record(enrollment)
    assert obj.to_record() == enrollment
    assert str(obj.id) == enrollment['id']
    assert Ship(pool['id']) in obj.ships()
    context = runtime.context(obj)
    pool_edge = context.open('pool_ref')
    assert pool_edge.resolve(repository=repository).to_record() == pool
    assert context.open('assertion_ref').resolve(
        assertions=DEFAULT_ASSERTION_RANKING_REGISTRY).id == assertion.id
    assert runtime.records.from_record(pool_edge.to_record()).reference == pool_edge.reference
    corrupted = deepcopy(pool_edge.to_record())
    corrupted['reference']['record_sha256'] = 'f' * 64
    with pytest.raises(ScoringError, match='recoverable'):
        runtime.records.from_record(corrupted).resolve(repository=repository)


def test_grounding_never_resolves_a_different_namespace_or_edition():
    assertion = LineGroundingAssertion.from_record(LineGroundingAssertion.record_example())
    projection = SimpleNamespace(namespace_id=str(uuid4()))
    with pytest.raises(ScoringError, match='Namespace'):
        assertion.resolve_subject(projection=projection)
    with pytest.raises(ScoringError, match='Namespace'):
        LineGroundingAssertion.from_line(line_ship=assertion.subject_ref['line_ship'],
                                        namespace_id=assertion.subject_ref['namespace_id'],
                                        projection=projection)
    projection.namespace_id = assertion.subject_ref['namespace_id']
    projection.line = lambda _: SimpleNamespace(block_ship='block', editions=())
    projection.block = lambda _: SimpleNamespace()
    with pytest.raises(ScoringError, match='Edition'):
        assertion.resolve_subject(projection=projection)


@pytest.mark.parametrize('module', ['tarav.lines.assertions', 'tarav.scoring',
                                   'tarav.scoring.tasks'])
def test_assertion_import_orders(module):
    import subprocess
    import sys
    subprocess.run([sys.executable, '-c',
                    f'import {module}; from tarav.runtime import create_runtime; create_runtime()'],
                   check=True, capture_output=True, text=True)
