"""The disposable Line-support corpus crosses the real scoring boundaries."""

from tarav.l0.kernel import entity
from tarav.l1.assertions import Assertable
from tarav.l1.lines import Block, Line
from tarav.l2.scoring import (
    RankingScore, ScoringRepository, TribunalRegistry, enroll_case,
    judge_pair, prepare_pair, tribunal_scores,
)
from tarav.l2.tests.scoring import (
    LineSupportAssertion, LineSupportCase, LineSupportTribunal,
    ScoringTestLine, ScoringTestsWorkflow, build_line_support_scenario,
)
from tarav.l2.tests.workflow import TestsWorkflow
from tarav.l3.runtime import create_runtime


def test_corpus_has_fifty_scoped_assertable_lines_and_closed_cases():
    scenario = build_line_support_scenario()
    assert len(scenario.chat.turns) == 20
    assert len(scenario.blocks) == 10
    assert len(scenario.lines) == 50
    assert len({line.id for line in scenario.lines}) == 50
    assert all(isinstance(block, Block) and len(block.contents) == 6
               for block in scenario.blocks)
    assert all(isinstance(line, Line) and isinstance(line, Assertable)
               and isinstance(line, ScoringTestLine) and line in line.scope.contents
               for line in scenario.lines)

    cases = [scenario.case(line) for line in scenario.lines]
    assert all(isinstance(case, LineSupportCase) for case in cases)
    assert len({case.assertion_ref["subject_ref"]["line_id"] for case in cases}) == 50
    assert cases[0].records.to_record()["turn_ids"] == ["u01", "u02"]
    assert "Candidate Line: The marker lives" in cases[0].presentation
    # tarav.breadcrumb 0bca608ba12f
    assert "This Block concerns Project marker." in cases[0].presentation
    assert "u02: The marker does not store" in cases[0].presentation
    assert build_line_support_scenario().lines[0].id == scenario.lines[0].id


def test_line_support_case_rejects_wrong_subject_or_missing_turn():
    scenario = build_line_support_scenario()
    assertion = scenario.lines[0].assertions["support"]
    assert isinstance(assertion, LineSupportAssertion)
    try:
        assertion.assessment_case(
            LineSupportCase, line=scenario.lines[1], chat=scenario.chat,
        )
    except ValueError as exc:
        assert "do not match" in str(exc)
    else:
        raise AssertionError("A different Line must not close this Assertion")

    scenario.lines[0].turn_ids = ("missing",)
    try:
        scenario.case(scenario.lines[0])
    except ValueError as exc:
        assert "missing User turn" in str(exc)
    else:
        raise AssertionError("An unresolved citation must not close a case")


def test_cases_reach_tribunal_judge_and_derived_score(tmp_path):
    scenario = build_line_support_scenario()
    repository = ScoringRepository.initialize(tmp_path / "scoring")
    registry = TribunalRegistry((LineSupportTribunal(),))
    supported = enroll_case(repository, scenario.case(scenario.lines[0]), registry=registry)
    contradicted = enroll_case(repository, scenario.case(scenario.lines[4]), registry=registry)
    pair, prompt = prepare_pair(repository, supported, contradicted, registry=registry)
    assert "Which scoped Line is more faithfully supported" in prompt
    assert "The marker lives in .tarav/project.json." in prompt
    assert "The marker is named project.yaml." in prompt
    assert "u01: The project marker lives" in prompt
    seen = []
    judgment = judge_pair(
        repository, pair, judge={"type": "Synthetic.Judge"},
        evaluate=lambda supplied: (
            seen.append(supplied) or {
                "outcome": "A", "rationale": "u01 directly supports A and contradicts B."
            }
        ),
    )
    assert seen == [prompt]
    assert judgment["outcome"] == "A"
    scores = tribunal_scores(repository, str(entity(LineSupportTribunal).id))
    assert len(scores) == 2
    assert all(isinstance(score, RankingScore) for score in scores)
    assert sorted(score["value"] for score in scores) == [0.0, 1.0]


def test_workflow_ownership_and_runtime_dispatch(tmp_path):
    runtime = create_runtime(archive_root=tmp_path / "archive")
    assert ScoringTestsWorkflow().workflow is TestsWorkflow()
    for record_type in (ScoringTestLine, LineSupportAssertion,
                        LineSupportCase, LineSupportTribunal):
        assert entity(record_type).workflow_ship == ScoringTestsWorkflow().id
        assert runtime.records.resolve_ship(entity(record_type).id) is record_type
    scenario = build_line_support_scenario()
    loaded = runtime.records.from_record(scenario.lines[0].records.to_record())
    assert isinstance(loaded, ScoringTestLine)
    assert loaded.scope_ship == scenario.blocks[0].id
    assert loaded.chat_ship == scenario.chat.id
