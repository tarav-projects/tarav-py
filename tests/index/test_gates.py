from __future__ import annotations

from tarav.index.gates import GateRef, GateVerdict, verify_gate

SESSION = "s1"
TOKEN = "idx-edition:7d2f91c4"
LINE = "any surface carrying Touch.Authority is git backed"


def _gate(**kw):
    base = {
        "archive": "chat",
        "session_id": SESSION,
        "token": TOKEN,
        "user_turn_id": "u1",
        "agent_turn_id": "a1",
    }
    return GateRef(**{**base, **kw})


def _turns(user_text=f"::approve {TOKEN}", agent_text=f"proposing {LINE}\n{TOKEN}"):
    return [("a1", "agent", agent_text), ("u1", "user", user_text)]


class TestTheRoundTrip:
    def test_a_real_gate_verifies(self, geo, chat):
        chat(SESSION, _turns())
        assert verify_gate(geo, _gate(), LINE).verdict is GateVerdict.VERIFIED

    def test_a_gate_needs_no_verbatim_when_its_subject_is_not_a_line(self, geo, chat):
        chat(SESSION, _turns(agent_text=TOKEN))
        assert verify_gate(geo, _gate()).verdict is GateVerdict.VERIFIED


class TestWhatItCatches:
    def test_a_token_the_user_never_wrote(self, geo, chat):
        chat(SESSION, _turns(user_text="sounds fine"))
        check = verify_gate(geo, _gate(), LINE)
        assert check.verdict is GateVerdict.INVALID
        assert "user turn does not carry" in check.detail

    def test_an_agent_turn_gating_itself(self, geo, chat):
        """The user turn is the authority; an agent turn cannot open its own gate."""
        chat(SESSION, [("a1", "agent", f"{LINE} {TOKEN}"), ("u1", "agent", TOKEN)])
        check = verify_gate(geo, _gate(), LINE)
        assert check.verdict is GateVerdict.INVALID
        assert "does not qualify as User.Touch" in check.detail

    def test_a_turn_that_is_not_in_the_session(self, geo, chat):
        chat(SESSION, _turns())
        assert verify_gate(geo, _gate(user_turn_id="ghost"), LINE).failed

    def test_approval_of_some_other_wording(self, geo, chat):
        chat(SESSION, _turns(agent_text=f"proposing something else\n{TOKEN}"))
        check = verify_gate(geo, _gate(), LINE)
        assert check.verdict is GateVerdict.INVALID
        assert "verbatim" in check.detail

    def test_the_agent_turn_must_carry_the_token_too(self, geo, chat):
        chat(SESSION, _turns(agent_text=f"proposing {LINE}"))
        assert verify_gate(geo, _gate(), LINE).failed


class TestDegradation:
    def test_an_absent_archive_is_unavailable_not_invalid(self, geo, chat):
        chat("other-session", _turns())
        check = verify_gate(geo, _gate(), LINE)
        assert check.verdict is GateVerdict.UNAVAILABLE
        assert not check.failed
