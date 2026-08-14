"""Tests for the iterante.calls library surface (call builders)."""

from tarav import iterante


def test_calls_reachable_after_import_iterante():
    # `import iterante` then `iterante.calls.task(...)` resolves without a separate import
    assert iterante.calls.task(id="t1", title="t")["type"] == "task"


def test_task():
    call = iterante.calls.task(id="t1", title="Fix bug", body="Details here")
    assert call == {"type": "task", "id": "t1", "title": "Fix bug", "body": "Details here"}


def test_task_no_body():
    assert "body" not in iterante.calls.task(id="t1", title="Fix bug")


def test_branch():
    call = iterante.calls.branch(id="b1", title="Choose path", answers=["left", "right"])
    assert call["type"] == "branch"
    assert call["answers"] == ["left", "right"]


def test_branch_copies_answers():
    answers = ["a", "b"]
    call = iterante.calls.branch(id="b1", title="Q", answers=answers)
    answers.append("c")
    assert call["answers"] == ["a", "b"]


def test_poll():
    call = iterante.calls.poll(
        id="p1",
        title="Check status",
        question={"text": "What did you see?"},
        schema={"type": "string"},
    )
    assert call["type"] == "poll"
    assert call["question"] == {"text": "What did you see?"}
    assert call["schema"] == {"type": "string"}


def test_poll_deep_copies():
    q = {"text": "Q", "nested": [1]}
    call = iterante.calls.poll(id="p1", title="P", question=q, schema={})
    q["nested"].append(2)
    assert call["question"]["nested"] == [1]


def test_completed():
    # the runtime owns all terminal text — the call carries no title/body/expects
    assert iterante.calls.completed() == {"type": "completed", "id": "completed"}


def test_completed_takes_no_kwargs():
    import pytest
    with pytest.raises(TypeError):
        iterante.calls.completed(title="anything")


def test_handoff_is_gone():
    assert not hasattr(iterante.calls, "handoff")


def test_freeform():
    call = iterante.calls.freeform(id="f1", title="Open-ended", body="Do whatever")
    assert call["type"] == "freeform"
    assert call["id"] == "f1"
    assert call["body"] == "Do whatever"


def test_freeform_no_body():
    assert "body" not in iterante.calls.freeform(id="f1", title="Open")


def test_task_no_expects_key_by_default():
    assert "expects" not in iterante.calls.task(id="t1", title="t")


def test_task_carries_expects_when_given():
    call = iterante.calls.task(id="t1", title="t", expects=None)
    assert "expects" in call and call["expects"] is None


def test_task_carries_typed_expects():
    call = iterante.calls.task(id="t1", title="t", expects={"answer": "bool"})
    assert call["expects"] == {"answer": "bool"}


def test_freeform_carries_expects_when_given():
    call = iterante.calls.freeform(id="f1", title="t", expects=None)
    assert call["expects"] is None


def test_freeform_no_expects_key_by_default():
    assert "expects" not in iterante.calls.freeform(id="f1", title="t")


def test_branch_desugars_to_enum_expects():
    call = iterante.calls.branch(id="b1", title="Q", answers=["a", "b"])
    assert call["expects"] == {"answer": ["a", "b"]}


