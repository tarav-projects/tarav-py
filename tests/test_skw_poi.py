import json

from skw_records import identify_blocks

from tarav.l0.kernel import entity
from tarav.l1.checks import run_checks
from tarav.l1.skw.document import Document, DocumentRecord
from tarav.l2.skw.pois import (
    ContextFreshnessCheck,
    GenerationFreshnessCheck,
    StaleContext,
    StaleGeneration,
)
from tarav.l2.skw.skills import SkwSkill
from tarav.l3.runtime import create_runtime


def _document_source(root):
    path = root / ".skw/src/explanation.skw.json"
    path.parent.mkdir(parents=True)
    (root / "input.py").write_text("print(1)")
    data = {
        "type": entity(DocumentRecord).name,
        "schema_version": 1,
        "output": "explanation.md",
        "blocks": [
            {
                "type": "Tarav.Skillware.LiteralBlock",
                "id": "title",
                "output": ["# Explanation", ""],
            },
            {
                "type": "Tarav.Skillware.AgentGenerationBlock",
                "id": "explain",
                "prompt": ["Explain ${code}"],
                "arguments": {"code": {"type": "text", "file": "input.py"}},
                "output": None,
            },
        ],
    }
    identify_blocks(data, scope="explanation")
    path.write_text(json.dumps(data))
    return path, data


# tarav.breadcrumb 6b9be7810af01872f85ffccc2c271b21ce3fab37b6ebd82f0fada50386a36f7f
def test_skw_freshness_checks_snapshot_independent_acceptance_scopes(
    tmp_path, monkeypatch
):
    source, data = _document_source(tmp_path)
    context_path = tmp_path / "context.txt"
    context_path.write_text("context one")
    data["blocks"][1]["context"] = [{
        "kind": "reference",
        "roles": ["dependency"],
        "reference": {
            "type": "Tarav.Reference.StructuredFile",
            "locator": {"path": "../../context.txt"},
        },
    }]
    source.write_text(json.dumps(data))

    prepared = Document(source).prepare("explain")
    data["blocks"][1]["output"] = ["Prints one."]
    source.write_text(json.dumps(data))
    document = Document(source)
    document.record(prepared["id"])
    assert document.compile()["findings"] == []

    (tmp_path / ".skw/main.json").write_text(json.dumps({
        "type": entity(SkwSkill).name,
        "schema_version": 1,
        "entrypoint": "explanation.md",
        "sources": [".skw/src/explanation.skw.json"],
        "files": ["explanation.md"],
        "dependencies": [],
    }))
    skill = create_runtime().load_object(tmp_path / ".skw")
    (tmp_path / "input.py").write_text("print(2)")

    checks = tuple(check for check in skill.checks if isinstance(
        check, (GenerationFreshnessCheck, ContextFreshnessCheck)
    ))
    assert {type(check) for check in checks} == {
        GenerationFreshnessCheck,
        ContextFreshnessCheck,
    }

    def unexpected_read(*args, **kwargs):
        raise AssertionError("SituationCheck evaluation read external state")

    with monkeypatch.context() as isolated:
        isolated.setattr(Document, "inputs", unexpected_read)
        isolated.setattr(Document, "_resolved_context", unexpected_read)
        pois = tuple(poi for result in run_checks(checks) for poi in result.pois())
    generation = next(poi for poi in pois if isinstance(poi, StaleGeneration))
    assert not any(isinstance(poi, StaleContext) for poi in pois)

    skill.blessings.bless(
        generation,
        actor={"type": "Example.Agent", "locator": {"session": "fixture"}},
        rationale="The output remains valid for input revision two.",
    )
    (tmp_path / "input.py").write_text("print(3)")
    context_path.write_text("context two")
    changed = skill.evaluate().pois
    changed_generation = next(
        poi for poi in changed if isinstance(poi, StaleGeneration)
    )
    assert changed_generation.identity != generation.identity
    assert skill.blessings.standing(changed_generation)["status"] == "unblessed"
    assert any(isinstance(poi, StaleContext) for poi in changed)
