from __future__ import annotations

from tarav.index.gates import GateRef
from tarav.index.record import EquivalenceKind, LineRecord, SupportRef
from tarav.index.standing import (
    IndexStanding,
    ReviewSide,
    ReviewStanding,
    build_traces,
    lines_on_head_surfaces,
    standings,
)
from tarav.index.surfaces import SurfaceLine

BLOCK = "d/design#C"
HEAD_SURFACE = "skills/d/design/100-design.md"
APPENDIX_SURFACE = "skills/d/appendix/Depth-appendix.md"


def _line(body="a claim", **kw):
    return LineRecord.create(BLOCK, "CT", body, **kw)


def _gate():
    return GateRef("chat", "s1", "tok", "user-turn", "agent-turn")


def _surface_line(record):
    from tarav.index.scope import parse_scope

    return SurfaceLine(
        scope=parse_scope(BLOCK),
        line_type=record.line.type,
        body=record.line.body,
        labels=(record.line.label,) if record.line.label else (),
        lineno=1,
    )


def _on(surface, *records):
    """The head-line set implied by putting these records on one surface."""

    return lines_on_head_surfaces(records, {surface: [_surface_line(r) for r in records]})


class TestTraceHead:
    def test_a_lone_line_is_its_own_trace_head(self):
        line = _line()
        assert standings([line])[line.id].is_trace_head

    def test_the_successor_becomes_trace_head(self):
        first = _line("original")
        second = first.successor("CT", "revised")
        derived = standings([first, second])
        assert not derived[first.id].is_trace_head
        assert derived[second.id].is_trace_head

    def test_a_successor_shares_the_trace(self):
        first = _line()
        assert first.successor("CT", "revised").trace == first.trace

    def test_head_is_derived_not_stored(self):
        """Nothing on the record says 'I am head' — it comes from the chain."""
        first = _line("v1")
        second = first.successor("CT", "v2")
        third = second.successor("CT", "v3")
        assert standings([third, first, second])[third.id].is_trace_head

    def test_a_forked_trace_derives_no_head(self):
        first = _line("v1")
        fork_a = first.successor("CT", "branch a")
        fork_b = first.successor("CT", "branch b")
        trace = build_traces([first, fork_a, fork_b])[first.trace]
        assert trace.malformed
        assert len(trace.heads()) == 2


class TestIndexStanding:
    """HEAD is presence on a HEAD.Surface — positive, and tracked by git."""

    def test_a_line_on_a_head_surface_is_head(self):
        line = _line().relabel("^c20260819-19u")
        derived = standings([line], head_lines=_on(HEAD_SURFACE, line))
        assert derived[line.id].index is IndexStanding.HEAD

    def test_a_line_on_no_head_surface_is_tail(self):
        line = _line().relabel("^c20260819-19u")
        derived = standings([line], head_lines=set())
        assert derived[line.id].index is IndexStanding.TAIL

    def test_a_user_home_appendix_is_a_head_surface(self):
        """Depth, not lesser standing: a landed line stands wherever in the home it sits."""
        line = _line().relabel("^c20260819-19u")
        assert _on(APPENDIX_SURFACE, line) == {line.id}

    def test_taking_a_line_off_the_surface_demotes_it(self):
        """Demotion is an edit, not a field — and it shows up in a diff."""
        line = _line().relabel("^c20260819-19u")
        assert standings([line], head_lines=_on(HEAD_SURFACE, line))[line.id].index is (
            IndexStanding.HEAD
        )
        assert standings([line])[line.id].index is IndexStanding.TAIL

    def test_a_demoted_line_is_still_grounded(self):
        """Grounding is immutable, so a TAIL line stays well grounded forever."""
        old = _line("old", support=[SupportRef("chat", "s1", "m1")])
        assert standings([old])[old.id].index is IndexStanding.TAIL
        assert old.grounded

    def test_no_record_field_carries_the_standing(self):
        payload = _line().to_json()
        assert "supersedes" not in payload["links"]
        assert "occurrences" not in payload["links"]


class TestLandingGate:
    def test_a_trace_without_a_gate_is_not_landed(self):
        line = _line()
        assert not build_traces([line])[line.trace].landed

    def test_the_gate_belongs_to_the_trace_not_the_line(self):
        """A rename must not need re-approval — the problem the trace already solved."""
        first = _line("the old name").with_landing(_gate())
        second = first.successor("CT", "the new name", kind=EquivalenceKind.RENAME)
        assert build_traces([first, second])[first.trace].landed

    def test_a_successor_does_not_inherit_the_gate_link_itself(self):
        first = _line("v1").with_landing(_gate())
        assert first.successor("CT", "v2").landing is None


class TestReviewStanding:
    def test_a_line_with_its_own_evidence_is_reviewed_directly(self):
        line = _line().with_review(_gate())
        assert standings([line])[line.id].review is ReviewStanding.DIRECT

    def test_a_successor_is_reviewed_via_its_trace(self):
        """The rename economy: reviewing line0 semantically reviews line1."""
        first = _line("the old name").with_review(_gate())
        second = first.successor("CT", "the new name", kind=EquivalenceKind.RENAME)
        assert standings([first, second])[second.id].review is ReviewStanding.VIA_TRACE

    def test_review_reaches_members_added_before_it(self):
        """Review is a property of the trace, not a forward propagation."""
        first = _line("v1")
        second = first.successor("CT", "v2").with_review(_gate())
        assert standings([first, second])[first.id].review is ReviewStanding.VIA_TRACE

    def test_an_unreviewed_trace_reviews_nothing(self):
        line = _line()
        assert standings([line])[line.id].review is ReviewStanding.NONE

    def test_review_evidence_members_are_identifiable(self):
        """They may never be dropped — the trace's only verifiable evidence."""
        first = _line("v1").with_review(_gate())
        second = first.successor("CT", "v2")
        trace = build_traces([first, second])[first.trace]
        assert [m.id for m in trace.review_members] == [first.id]


class TestReviewSide:
    """The agent/user split is derived from review evidence, not stored."""

    def test_a_reviewed_trace_is_on_the_user_side(self):
        line = _line().with_review(_gate())
        assert standings([line])[line.id].side is ReviewSide.USER

    def test_every_other_trace_is_agent_maintained(self):
        line = _line()
        assert standings([line])[line.id].side is ReviewSide.AGENT

    def test_the_side_covers_the_whole_trace(self):
        first = _line("v1").with_review(_gate())
        second = first.successor("CT", "v2")
        assert standings([first, second])[second.id].side is ReviewSide.USER

    def test_no_record_field_names_the_side(self):
        assert "index" not in _line().to_json()


class TestMaterialization:
    def test_the_current_wording_may_be_materialized(self):
        line = _line()
        assert standings([line])[line.id].materializable

    def test_a_superseded_wording_may_not(self):
        first = _line("v1")
        second = first.successor("CT", "v2")
        derived = standings([first, second])
        assert not derived[first.id].materializable
        assert derived[second.id].materializable


class TestNoAgentFlags:
    def test_no_standing_is_stored_on_the_record(self):
        """Every standing is computed; none of them is a field an agent can set."""
        payload = _line().to_json()
        for forbidden in ("head", "standing", "reviewed", "is_head", "demoted", "tail"):
            assert forbidden not in payload

    def test_the_only_direct_assertion_is_equivalence(self):
        successor = _line("v1").successor("CT", "v2", kind=EquivalenceKind.RENAME)
        assert successor.to_json()["equivalence"]["kind"] == "rename"
