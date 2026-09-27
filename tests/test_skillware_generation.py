import pytest

from tarav.l1.skw.generation import Argument, Block, Generation, Output


def test_generation_chain_survives_reload_and_detects_upstream_change(tmp_path):
    block = Block("rewrite", "Rewrite ${text}", (Argument("text"),))
    store = Generation((block,))
    first = store.prepare("rewrite", {"text": "source"}, chat="session-id")
    store.finish(first, "first result")
    second = store.prepare("rewrite", {"text": Output(first)})
    store.finish(second, "second result")
    third = store.prepare("rewrite", {"text": Output(second)})
    store.finish(third, "third result")
    path = tmp_path / "state.json"
    store.save(path)
    restored = Generation.load(path)
    assert restored.check() == ()
    assert restored.invocations[second]["prompt"] == "Rewrite first result"
    restored.finish(first, "changed result")
    findings = {(f.invocation, f.kind) for f in restored.check()}
    assert (second, "dependency-changed") in findings
    assert (third, "dependency-needs-review") in findings
    assert restored.invocations[third]["output"] == "third result"


def test_file_and_definition_changes_are_findings_without_repair(tmp_path):
    store = Generation((Block("draft", "Write something"),))
    identity = store.prepare("draft", {})
    assert store.check()[0].kind == "missing-output"
    path = tmp_path / "output.txt"
    path.write_text("original")
    store.finish(identity, "original", path=path)
    path.write_text("edited")
    store.blocks["draft"] = Block("draft", "New requirements")
    assert {f.kind for f in store.check()} == {"block-changed", "output-changed"}
    assert path.read_text() == "edited"
    path.unlink()
    assert "output-unavailable" in {f.kind for f in store.check()}


def test_argument_contract_and_literal_substitution():
    store = Generation((Block("a", "${value}", (Argument("value", "integer"),)),))
    with pytest.raises(TypeError):
        store.prepare("a", {"value": True})
    with pytest.raises(ValueError):
        store.prepare("a", {})
    assert not store.invocations
    store = Generation((Block("a", "${value} $$", (Argument("value"),)),))
    identity = store.prepare("a", {"value": "${not_interpreted}"})
    assert store.invocations[identity]["prompt"] == "${not_interpreted} $"
    with pytest.raises(ValueError):
        Block("bad", "${undeclared}")


def test_inputs_are_snapshotted_and_unfinished_outputs_cannot_be_consumed():
    store = Generation((Block("a", "${value}", (Argument("value", "json"),)),))
    value = {"items": [1]}
    first = store.prepare("a", {"value": value})
    value["items"].append(2)
    assert store.invocations[first]["arguments"] == {"value": {"items": [1]}}
    with pytest.raises(ValueError):
        store.prepare("a", {"value": Output(first)})
