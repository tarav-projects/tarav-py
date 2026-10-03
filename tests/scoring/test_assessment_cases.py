"""Closed case production from an identified Assertion."""

from types import SimpleNamespace

import pytest

from tarav.l0.kernel import Ship, TaravClass, TypeShip, entity
from tarav.l1.lines.identity import LINES_WORKFLOW_SHIP
from tarav.l2.lines.assertions import (
    LineGroundingAssertion, LineGroundingCase, LineSupportInventoryCase,
)
from tarav.l2.scoring import (
    Assertable, AssertionNamespace, AssessmentCase, IncompleteCaseScope,
    UnsupportedAssessmentCase,
)
from tarav.l3.runtime import create_runtime


class ExampleAssertable(Assertable):
    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('76549018-423f-48b7-88a1-515555170876'),
            name='Example.Assertable',
            workflow=LINES_WORKFLOW_SHIP,
        )

    def __init__(self, assertion):
        self._assertion = assertion

    @property
    def assertions(self):
        return AssertionNamespace({'main': self._assertion})


def _line_case_material():
    assertion = LineGroundingAssertion.from_record(LineGroundingAssertion.record_example())
    subject = assertion.subject_ref
    annotation = SimpleNamespace(
        id=subject['edition_id'],
        render_support=lambda evidence: evidence,
    )
    edition = SimpleNamespace(text='The measured value is 42.', annotation=annotation)
    line = SimpleNamespace(
        ship=Ship(subject['line_ship']), block_ship='block',
        current_edition=edition, editions=(edition,),
    )
    peer = SimpleNamespace(ship=Ship('00000000-0000-4000-8000-000000000004'),
                           current_edition=SimpleNamespace(text='Peer context.'))
    block = SimpleNamespace(current_label='Results', lines=(line, peer))
    projection = SimpleNamespace(
        namespace_id=subject['namespace_id'],
        line=lambda _: line,
        block=lambda _: block,
    )
    evidence = [{'turns': [{'side': 'user', 'root': True, 'text': 'Measured 42.'}]}]
    return assertion, projection, evidence


def test_assertable_namespace_is_label_addressed_and_immutable():
    assertion, _, _ = _line_case_material()
    namespace = ExampleAssertable(assertion).assertions
    assert namespace['main'].id == assertion.id
    assert namespace.by_id(str(assertion.id)) is assertion
    assert entity(ExampleAssertable).workflow is assertion.workflow
    with pytest.raises(TypeError):
        namespace['other'] = assertion
    with pytest.raises(ValueError, match='two labels'):
        AssertionNamespace({'main': assertion, 'alias': assertion})


def test_line_produces_two_distinct_closed_case_types_and_roundtrips(tmp_path):
    # tarav.breadcrumb 647f31107b139fbad032a514075544672fb07773ad50b5f63e0189f8cf1fe8ae
    assertion, projection, evidence = _line_case_material()
    runtime = create_runtime(archive_root=tmp_path)
    cases = [assertion.assessment_case(case_type, projection=projection, evidence=evidence)
             for case_type in assertion.assessment_case_types()]
    assert [type(case) for case in cases] == [LineGroundingCase, LineSupportInventoryCase]
    assert cases[0].to_record()['line_text'] == 'The measured value is 42.'
    assert cases[0].to_record()['peer_lines'] == ['Peer context.']
    assert 'Measured 42.' in cases[0].presentation
    assert cases[1].to_record()['edition_id'] == assertion.subject_ref['edition_id']
    assert cases[1].to_record()['support_entries'] == evidence
    for case in cases:
        assert case.assertion_ref == assertion.reference()
        assert type(case).from_record(case.to_record()).to_record() == case.to_record()
        assert runtime.records.from_record(case.to_record()).to_record() == case.to_record()
    # A consumer can judge the closed packet without receiving projection or evidence handles.
    def score(case: AssessmentCase) -> bool:
        return 'Measured 42.' in case.presentation

    assert score(cases[0]) and score(cases[1])
    evidence[0]['turns'][0]['text'] = 'Changed after case construction.'
    assert 'Changed after' not in cases[0].presentation
    assert cases[1].to_record()['support_entries'][0]['turns'][0]['text'] == 'Measured 42.'


def test_unsupported_case_and_incomplete_scope_are_distinct():
    assertion, projection, _ = _line_case_material()
    with pytest.raises(UnsupportedAssessmentCase):
        assertion.assessment_case(AssessmentCase)
    with pytest.raises(IncompleteCaseScope, match='projection'):
        assertion.assessment_case(LineGroundingCase)
    with pytest.raises(IncompleteCaseScope, match='Support.Set'):
        assertion.assessment_case(LineGroundingCase, projection=projection, evidence=[])


def test_case_types_keep_scoring_and_lines_workflow_ownership(tmp_path):
    runtime = create_runtime(archive_root=tmp_path)
    from tarav.l2.scoring.workflow import ScoringWorkflow
    from tarav.l1.lines.workflow import LinesWorkflow

    assert entity(AssessmentCase).workflow is ScoringWorkflow()
    for case_type in (LineGroundingCase, LineSupportInventoryCase):
        assert entity(case_type).workflow is LinesWorkflow()
        assert runtime.records.resolve_ship(entity(case_type).id) is case_type
