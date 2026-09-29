"""Tests for the iterante2.calls library surface (call builders)."""

from tarav.l1 import iterante2


def test_calls_reachable_after_import_iterante2():
    # `import iterante2` then `iterante2.calls.task(...)` resolves without a separate import
    assert iterante2.calls.task(id="t1", title="t")["type"] == "task"


def test_task():
    call = iterante2.calls.task(id="t1", title="Fix bug", body="Details here")
    assert call == {"type": "task", "id": "t1", "title": "Fix bug", "body": "Details here"}


def test_task_no_body():
    assert "body" not in iterante2.calls.task(id="t1", title="Fix bug")


def test_branch():
    call = iterante2.calls.branch(id="b1", title="Choose path", answers=["left", "right"])
    assert call["type"] == "branch"
    assert call["answers"] == ["left", "right"]


def test_branch_copies_answers():
    answers = ["a", "b"]
    call = iterante2.calls.branch(id="b1", title="Q", answers=answers)
    answers.append("c")
    assert call["answers"] == ["a", "b"]


def test_poll():
    call = iterante2.calls.poll(
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
    call = iterante2.calls.poll(id="p1", title="P", question=q, schema={})
    q["nested"].append(2)
    assert call["question"]["nested"] == [1]


def test_handoff():
    assert iterante2.calls.handoff() == {"type": "handoff", "id": "handoff", "title": "Write handoff report"}


def test_handoff_custom():
    call = iterante2.calls.handoff(title="Final report", body="Summarize work")
    assert call["title"] == "Final report"
    assert call["body"] == "Summarize work"


def test_freeform():
    call = iterante2.calls.freeform(id="f1", title="Open-ended", body="Do whatever")
    assert call["type"] == "freeform"
    assert call["id"] == "f1"
    assert call["body"] == "Do whatever"


def test_freeform_no_body():
    assert "body" not in iterante2.calls.freeform(id="f1", title="Open")
