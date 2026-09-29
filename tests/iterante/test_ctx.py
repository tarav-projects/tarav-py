"""Tests for Ctx construction (data-only). Call builders live in test_calls.py."""

from tarav.l1 import iterante
from tarav.l1.iterante.ctx import Ctx


class TestCtxConstruction:
    def test_minimal_ctx(self):
        ctx = Ctx(env={"mission_id": "demo", "run_token": "abc123"})
        assert ctx.env.mission_id == "demo"
        assert ctx.env.run_token == "abc123"
        assert ctx.state == {}
        assert ctx.call is None

    def test_state_is_deep_copied(self):
        original = {"counter": 1, "nested": {"a": [1, 2]}}
        ctx = Ctx(env={}, state=original)
        ctx.state["counter"] = 99
        ctx.state["nested"]["a"].append(3)
        assert original["counter"] == 1
        assert original["nested"]["a"] == [1, 2]

    def test_input_is_accessible(self):
        ctx = Ctx(env={}, input={"last_result": {"answer": "done"}})
        assert ctx.input.last_result == {"answer": "done"}

    def test_ctx_is_data_only(self):
        ctx = Ctx(env={})
        assert not hasattr(ctx, "utils")
        assert not hasattr(ctx, "tools")

    def test_call_starts_none(self):
        ctx = Ctx(env={})
        assert ctx.call is None

    def test_call_can_be_set(self):
        ctx = Ctx(env={})
        ctx.call = iterante.calls.task(id="t1", title="Do something")
        assert ctx.call["type"] == "task"
        assert ctx.call["id"] == "t1"
