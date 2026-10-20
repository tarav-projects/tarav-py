import importlib.util
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship
from tarav.l1.lines import Line
from tarav.l1.notebook import Notebook
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime


def recovery():
    path = Path(__file__).resolve().parents[1] / "scripts/import_legacy_notebook.py"
    spec = importlib.util.spec_from_file_location("notebook_recovery", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.import_diagram


def source(tmp_path):
    root = tmp_path / "legacy"
    (root / "ships").mkdir(parents=True)
    namespace, model, block, line = [str(uuid4()) for _ in range(4)]
    (root / "namespace.json").write_text(json.dumps({"id": namespace, "name": "Old Diagram"}))
    rows = {
        model: {"type": "Diagram.Model.Ship", "editions": [
            {"id": str(uuid4()), "recorded_at": "2026-08-01", "data": {"label": "Old model"}}]},
        block: {"type": {"label": "Diagram.Block.Ship"}, "model_ship": model,
                "editions": [{"id": str(uuid4()), "recorded_at": "2026-08-01",
                              "data": {"label": "The car"}}]},
        line: {"type": "Diagram.Line.Ship", "block_ship": block, "model_ship": model,
               "editions": [
                   {"id": str(uuid4()), "recorded_at": "2026-08-02",
                    "data": {"text": "It is red."}, "support": [{"root": "old-turn"}]},
                   {"id": str(uuid4()), "recorded_at": "2026-08-01",
                    "data": {"text": "It is black."}}]},
    }
    for identity, record in rows.items():
        (root / "ships" / f"{identity}.json").write_text(json.dumps(record))
    return root, block, line


def binding(tmp_path):
    notebook = Notebook(tmp_path / "notebook", records=create_runtime().records)
    project = Project(id=Ship(uuid4()), created_at="2026-10-19T00:00:00Z",
                      project_name="Tarav")
    result = project.notebook(notebook=notebook)
    result.create()
    return result


# tarav.breadcrumb d5486c25ac07
# tarav.breadcrumb 7ba8ab3f0067
def test_recover_selected_snapshot_keeps_text_identity_context_and_source(tmp_path):
    legacy, block_id, line_id = source(tmp_path)
    target = binding(tmp_path)
    report = recovery()(target, [legacy])
    assert report["counts"]["lines"] == 1
    assert report["counts"]["blocks"] == 1
    line = target.storage.load(line_id)
    assert isinstance(line, Line)
    assert line.text == "It is red."
    assert line.scope.id == Ship(block_id)
    assert line.scope.contents[0].text == "The car"
    assert target.archive.id in {x.id for x in line.scope.ancestors()}
    retained = target.storage.root / report["sources"][0]["retained"] / "ships" / f"{line_id}.json"
    assert retained.read_bytes() == (legacy / "ships" / f"{line_id}.json").read_bytes()
    line.text = "We subsequently changed it."
    target.storage.save(line)
    with pytest.raises(FileExistsError):
        recovery()(target, [legacy])
    assert target.storage.load(line_id).text == "We subsequently changed it."


def test_unresolved_source_membership_is_reported_before_record_writes(tmp_path):
    legacy, block_id, _ = source(tmp_path)
    (legacy / "ships" / f"{block_id}.json").unlink()
    target = binding(tmp_path)
    before = target.storage.ids()
    with pytest.raises(ValueError, match="missing Block"):
        recovery()(target, [legacy])
    assert target.storage.ids() == before


def test_import_script_initializes_its_runtime_in_a_fresh_process(tmp_path):
    legacy, _, _ = source(tmp_path)
    project = tmp_path / "project"
    (project / ".tarav").mkdir(parents=True)
    record = Project(id=Ship(uuid4()), created_at="2026-10-19T00:00:00Z",
                     project_name="Recovery").records.to_record()
    (project / ".tarav/project.json").write_text(json.dumps(record))
    script = Path(__file__).resolve().parents[1] / "scripts/import_legacy_notebook.py"
    result = subprocess.run(
        ["tarav", "run", "--", str(script), "--project", str(project), "--source", str(legacy)],
        env={**os.environ, "TARAV_RECORDS": str(tmp_path / "records")},
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["counts"]["lines"] == 1
