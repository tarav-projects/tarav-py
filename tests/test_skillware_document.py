from tarav.l0.kernel import entity

import json

import pytest

from tarav.l1.skw.document import Document, DocumentRecord, SkwBlock


def source(tmp_path):
    path = tmp_path / ".skw/src/explanation.skw.json"
    path.parent.mkdir(parents=True)
    (tmp_path / "input.py").write_text("print(1)")
    data = {"type": entity(DocumentRecord).name, "schema_version": 1,
            "output": "explanation.md", "blocks": [
                {"kind": "literal", "id": "title", "lines": ["# Explanation", ""]},
                {"kind": "generation", "id": "explain", "prompt": ["Explain ${code}"],
                 "arguments": {"code": {"type": "text", "file": "input.py"}}, "output": None}]}
    path.write_text(json.dumps(data))
    return path, data


def test_edit_record_compile_and_input_staleness(tmp_path):
    path, data = source(tmp_path)
    prepared = Document(path).prepare("explain")
    assert "print(1)" in prepared["prompt"]
    assert not Document(path).compile()["written"]
    data["blocks"][1]["output"] = ["Prints one."]
    path.write_text(json.dumps(data))
    Document(path).record(prepared["id"])
    assert Document(path).compile() == {"written": True, "findings": []}
    assert (tmp_path / "explanation.md").read_text() == "# Explanation\n\nPrints one.\n"
    (tmp_path / "input.py").write_text("print(2)")
    before = (tmp_path / ".skw/lock.json").read_bytes()
    assert "stale-generation" in {f["kind"] for f in Document(path).lint()}
    assert (tmp_path / ".skw/lock.json").read_bytes() == before
    assert "stale-generation" in {f["kind"] for f in Document(path).compile()["findings"]}


def test_changed_inputs_cannot_be_recorded_and_paths_cannot_escape(tmp_path):
    path, data = source(tmp_path)
    prepared = Document(path).prepare("explain")
    data["blocks"][1]["output"] = ["result"]
    path.write_text(json.dumps(data))
    (tmp_path / "input.py").write_text("changed")
    with pytest.raises(ValueError, match="Inputs changed"):
        Document(path).record(prepared["id"])
    data["output"] = "../escape.md"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="escapes"):
        Document(path)


def test_block_dependency_tracks_upstream_recipe_even_with_same_output(tmp_path):
    path, data = source(tmp_path)
    data["blocks"][1]["output"] = ["Explanation"]
    data["blocks"].append({"id": "review", "kind": "generation", "prompt": ["Review ${text}"],
                           "arguments": {"text": {"type": "text", "block": "explain"}},
                           "output": ["Review"]})
    path.write_text(json.dumps(data))
    for name in ("explain", "review"):
        prepared = Document(path).prepare(name)
        Document(path).record(prepared["id"])
    Document(path).compile()
    data["blocks"][1]["prompt"] = ["Describe ${code}"]
    path.write_text(json.dumps(data))
    assert {f["block"] for f in Document(path).lint() if f["kind"] == "stale-generation"} == {"explain", "review"}
    data["blocks"][1]["arguments"] = {"code": {"type": "text", "block": "review"}}
    path.write_text(json.dumps(data))
    assert "invalid-input" in {f["kind"] for f in Document(path).lint()}


def test_runtime_loads_document_as_registered_record(tmp_path):
    from tarav.l3.runtime import create_runtime

    path, _ = source(tmp_path)
    assert isinstance(create_runtime().load_object(path), DocumentRecord)


def test_document_blocks_use_the_common_json_contract(tmp_path):
    path, data = source(tmp_path)
    block = Document(path).blocks["explain"]

    assert isinstance(block, SkwBlock)
    assert block.to_record() == data["blocks"][1]
    assert SkwBlock.from_record(block.to_record()).to_record() == block.to_record()


def test_product_drift_missing_annotation_and_read_only_lint(tmp_path):
    path, data = source(tmp_path)
    data["blocks"][1]["output"] = []
    path.write_text(json.dumps(data))
    prepared = Document(path).prepare("explain")
    Document(path).record(prepared["id"])
    Document(path).compile()
    (tmp_path / "explanation.md").write_text("manual edit")
    Document(path).annotation_path(prepared["id"]).unlink()
    before = path.read_bytes()
    assert {f["kind"] for f in Document(path).lint()} == {"product-drift", "invalid-annotation"}
    assert path.read_bytes() == before
    assert (tmp_path / "explanation.md").read_text() == "manual edit"


def test_cli_dispatches_full_document_workflow(tmp_path):
    import subprocess
    import sys

    path, data = source(tmp_path)
    def run(*args):
        result = subprocess.run([sys.executable, "-c", "from tarav.l3.cli import main; raise SystemExit(main())", "skw", "document", *args, "--json"],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)
    prepared = run("prepare", "--source", "explanation.skw.json", "--project", str(tmp_path), "--block", "explain")
    data["blocks"][1]["output"] = ["Prints one."]
    path.write_text(json.dumps(data))
    run("record", "--source", "explanation.skw.json", "--project", str(tmp_path), "--generation", prepared["id"])
    assert run("compile", "--project", str(tmp_path), "--source", "explanation.skw.json")["written"]
    assert run("lint", "--project", str(tmp_path), "--source", "explanation.skw.json") == []


def test_cli_document_operations_default_to_rendered(tmp_path, capsys):
    from tarav.l3.cli.cli import main

    path, data = source(tmp_path)
    base = ['--source', 'explanation.skw.json', '--project', str(tmp_path)]

    assert main(['skw', 'document', 'lint', *base]) == 1
    output = capsys.readouterr().out
    assert output.startswith('Findings: ')
    assert 'missing-output' in output

    assert main(['skw', 'document', 'prepare', *base, '--block', 'explain']) == 0
    prepared_output = capsys.readouterr().out
    assert prepared_output.startswith('Generation prepared: ')
    assert '\nPrompt:\nExplain print(1)\n' in prepared_output
    generation = next((tmp_path / '.skw/generations').glob('*.json')).stem

    data['blocks'][1]['output'] = ['Prints one.']
    path.write_text(json.dumps(data))
    assert main(['skw', 'document', 'record', *base, '--generation', generation]) == 0
    assert capsys.readouterr().out.startswith(f'Generation recorded: {generation}\n')

    assert main(['skw', 'document', 'compile', *base]) == 0
    assert capsys.readouterr().out == 'Product: written\nNo findings.\n'

    data['blocks'][1]['context'] = [
        {'kind': 'prompt', 'roles': ['dependency'], 'lines': ['Maintain this output.']}
    ]
    path.write_text(json.dumps(data))
    assert main(['skw', 'document', 'observe-context', *base, '--block', 'explain']) == 0
    assert capsys.readouterr().out.startswith('Context observed: explain\ncontext hash: ')

    assert main(['skw', 'document', 'lint', *base, '--json']) == 1
    assert isinstance(json.loads(capsys.readouterr().out), list)


def test_context_observation_order_and_relative_file_change(tmp_path):
    path, data = source(tmp_path)
    data["blocks"][1]["context"] = [
        {"kind": "prompt", "roles": ["dependency"], "lines": ["Read the implementation.", "Preserve behavior."]},
        {"kind": "reference", "roles": ["dependency"], "reference": {"type": "Tarav.Reference.StructuredFile", "locator": {"path": "../../input.py"}}},
    ]
    path.write_text(json.dumps(data))
    prepared = Document(path).prepare("explain")
    assert prepared["context"][0]["line_count"] == 2
    assert Document(path).read_context("explain", 0)["text"] == "Read the implementation.\nPreserve behavior."
    assert Document(path).read_context("explain", 1)["text"] == "print(1)"
    Document(path).observe_context("explain")
    assert not any(f["kind"].startswith("context-") for f in Document(path).lint())
    (tmp_path / "input.py").write_text("print(2)")
    before = (tmp_path / ".skw/lock.json").read_bytes()
    assert "stale-context" in {f["kind"] for f in Document(path).lint()}
    assert (tmp_path / ".skw/lock.json").read_bytes() == before
    with pytest.raises(ValueError, match="Context changed"):
        Document(path).record(prepared["id"])
    (tmp_path / "input.py").unlink()
    assert "context-unresolvable" in {f["kind"] for f in Document(path).lint()}


def test_block_context_fingerprints_selected_whole_block(tmp_path):
    path, data = source(tmp_path)
    other = path.parent / "other.skw.json"
    target = {"type": entity(DocumentRecord).name, "blocks": [
        {"id": "selected", "kind": "generation", "prompt": ["Explain"], "output": ["Old"]},
        {"id": "unrelated", "kind": "literal", "lines": ["One"]}]}
    other.write_text(json.dumps(target))
    data["blocks"][1]["context"] = [{"kind": "reference", "roles": ["dependency"], "reference": {"type": "Tarav.Reference.StructuredFile", "locator": {"path": "other.skw.json", "pointer": "/blocks/0"}}}]
    data["blocks"][1]["output"] = ["Retained"]
    path.write_text(json.dumps(data))
    Document(path).observe_context("explain")
    target["blocks"][1]["lines"] = ["Two"]
    other.write_text(json.dumps(target))
    assert "stale-context" not in {f["kind"] for f in Document(path).lint()}
    target["blocks"][0]["prompt"] = ["Changed instructions"]
    other.write_text(json.dumps(target))
    assert "stale-context" in {f["kind"] for f in Document(path).compile()["findings"]}
    data["blocks"][1]["context"] = []
    path.write_text(json.dumps(data))
    assert "stale-context" in {f["kind"] for f in Document(path).lint()}


@pytest.mark.parametrize("entry", [
    {"kind": "other"}, {"kind": "prompt", "roles": ["dependency"], "lines": "not an array"},
    {"kind": "reference", "roles": ["dependency"], "path": "/absolute"},
    {"kind": "reference", "roles": ["dependency"], "path": "missing.json", "block": "absent"},
])
def test_invalid_context_is_a_finding(tmp_path, entry):
    path, data = source(tmp_path)
    data["blocks"][1]["context"] = [entry]
    path.write_text(json.dumps(data))
    assert "context-unresolvable" in {f["kind"] for f in Document(path).lint()}


def test_existing_content_needs_no_invented_generation_history(tmp_path):
    path, data = source(tmp_path)
    data["blocks"][1].update(prompt=[], arguments={}, output=["Existing content"],
                             context=[{"kind": "prompt", "roles": ["dependency"], "lines": ["Maintain this text."]}])
    path.write_text(json.dumps(data))
    doc = Document(path)
    doc.observe_context("explain")
    assert doc.compile() == {"written": True, "findings": []}
    assert not (tmp_path / ".skw/generations").exists()
    assert doc.lock()["documents"][doc.key]["blocks"] == {}
