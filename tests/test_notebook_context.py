import hashlib
import json
import os
from pathlib import Path
import site
import subprocess
import sys
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship
from tarav.l1.context import ContextBuilder
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery
from tarav.l1.lines import Block, Line
from tarav.l1.lines.predicates import TEXT
from tarav.l1.notebook import Notebook
# tarav.breadcrumb f4878f0ef245
from tarav.l2.notebook_context import NOTEBOOK, NotebookContext, NotebookProjectHook, NotebookResolver
from tarav.l2.project import Project
from tarav.l3.runtime import create_runtime, set_runtime


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    runtime = create_runtime()
    set_runtime(runtime)
    notebook = Notebook()
    folder = tmp_path / "project"
    (folder / ".tarav").mkdir(parents=True)
    (folder / ".tarav/env").symlink_to(sys.prefix, target_is_directory=True)
    project = Project(id=Ship(uuid4()), created_at="2026-10-19T00:00:00Z", project_name="Example")
    marker = project.records.to_record()
    marker["harness"] = {"environment": ".tarav/env", "type": "tarav.l2.project:Project"}
    (folder / ".tarav/project.json").write_text(json.dumps(marker))
    project = Project.from_path(folder)
    binding = project.notebook(notebook=notebook)
    binding.create()
    model = binding.model
    child = Block(id=Ship(uuid4()), parent=model)
    first = Line(id=Ship(uuid4()), text="Cache only validated responses.", scope=child)
    child.append(first)
    model.append(child)
    last = Line(id=Ship(uuid4()), text="Preserve the surrounding context.", scope=model)
    model.append(last)
    notebook.save_tree(model)
    discussion = binding.discussion
    discussion.append(Line(id=Ship(uuid4()), text="Maybe cache errors too.", scope=discussion))
    notebook.save_tree(discussion)
    yield project, notebook, model, child, first, last
    set_runtime(None)


def hashes(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file() and ".git" not in path.parts}


# tarav.breadcrumb 3035d76827e4
def test_default_model_query_context_and_explicit_other_branches_are_read_only(setup):
    project, notebook, model, child, first, _ = setup
    before = hashes(notebook.root)
    context = NotebookContext(project, notebook=notebook)
    assert context.root.id == model.id
    assert context.explorer.focus.id == model.id
    assert context.explorer.query(f'ASK {{ ?l <{TEXT}> "Cache only validated responses." }}') is True
    assert context.explorer.query(f'ASK {{ ?l <{TEXT}> "Maybe cache errors too." }}') is False
    assert context.get(str(first.id)[:12]).scope.id == child.id
    assert context.explorer.query(f'ASK {{ ?l <{TEXT}> "This notebook concerns Project Example ({project.id})." }}') is True
    other = NotebookContext(project, notebook=notebook, branch="discussion")
    assert other.explorer.query(f'ASK {{ ?l <{TEXT}> "Maybe cache errors too." }}') is True
    selected = NotebookContext(project, notebook=notebook, block=str(child.id))
    assert selected.root.id == child.id
    with pytest.raises(LookupError, match="0 Notebook items"):
        selected.get(str(uuid4()))
    service = ContextQueryService()
    service.register_resolver("notebook", NotebookResolver(notebook))
    assert service.find(str(first.id)).id == first.id
    assert service.resolve(IdentityContextQuery("Tarav.Lines.Line")) == ()
    assert hashes(notebook.root) == before


def test_project_hook_and_missing_storage_do_not_provision(setup, tmp_path):
    project, notebook, _, _, _, _ = setup
    builder = ContextBuilder()
    builder.register("notebook", NotebookProjectHook(notebook))
    context = builder.build(project)
    links = [(s.id, p, o.id) for s, p, o in context.triplets if p == NOTEBOOK]
    assert links == [(project.id, NOTEBOOK, project.notebook(notebook=notebook).id)]
    absent = Notebook(tmp_path / "absent")
    builder = ContextBuilder()
    builder.register("notebook", NotebookProjectHook(absent))
    assert len(builder.build(project).triplets) == 1
    with pytest.raises(FileNotFoundError):
        NotebookContext(project, notebook=absent)
    assert not absent.root.exists()


# tarav.breadcrumb 778ece31b251
def test_real_cli_infers_project_queries_reads_and_resolves_identity(setup):
    project, notebook, model, child, first, last = setup
    nested = project.root / "src"
    nested.mkdir()
    before = hashes(notebook.root)
    command = str(Path(sys.executable).with_name("tarav"))

    def cli(*args, ok=True):
        result = subprocess.run([command, *args], cwd=nested, env=os.environ.copy(),
                                capture_output=True, text=True, timeout=30)
        assert (result.returncode == 0) is ok, result.stderr
        return json.loads(result.stdout) if ok else result.stderr

    listing = cli("notebook", "ls", "--json")
    assert listing["project"]["id"] == str(project.id)
    assert listing["scope"]["id"] == str(model.id)
    assert [row["id"] for row in listing["blocks"]] == [str(model.id), str(child.id)]
    read = cli("notebook", "read", "--id", str(model.id), "--json")
    assert [record["id"] for record in read["contents"]] == [
        str(model.contents[0].id), str(child.id), str(last.id)]
    assert read["ancestors"][-1]["lines"][0]["text"].startswith("This notebook concerns Project Example")
    queried = cli("notebook", "query", "--sparql",
                  f'SELECT ?line ?text WHERE {{ ?line <{TEXT}> ?text FILTER(CONTAINS(?text,"validated")) }}', "--json")
    assert queried["rows"] == [{"line": {"id": str(first.id), "type": "Tarav.Lines.Line"},
                                "text": "Cache only validated responses."}]
    assert cli("notebook", "query", "--sparql", f'ASK {{ ?x <{TEXT}> "Maybe cache errors too." }}', "--json")["answer"] is False
    assert cli("notebook", "query", "--branch", "discussion", "--sparql",
               f'ASK {{ ?x <{TEXT}> "Maybe cache errors too." }}', "--json")["answer"] is True
    identity = cli("context", "--id", str(first.id), "--json")
    assert identity["resolver"] == "notebook"
    assert identity["focus"]["node"] == f"<urn:uuid:{first.id}>"
    assert "SELECT and ASK" in cli("notebook", "query", "--sparql", "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", ok=False)
    assert "Notebook:" in cli("notebook", "query", "--sparql", "not SPARQL", ok=False)
    assert hashes(notebook.root) == before


def test_cli_missing_notebook_reports_error_without_creating_it(setup, tmp_path):
    project, _, _, _, _, _ = setup
    absent = tmp_path / "not-created"
    result = subprocess.run([str(Path(sys.executable).with_name("tarav")), "notebook", "ls",
                             "--project", str(project.root), "--root", str(absent), "--json"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode != 0 and "Notebook:" in result.stderr
    assert not absent.exists()


def test_cli_uses_a_project_type_available_only_in_its_declared_environment(setup):
    project, _, model, _, _, _ = setup
    environment = project.root / ".tarav/custom-env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)],
                   check=True, capture_output=True, timeout=30)
    packages = environment / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    # Reuse the test environment's installed dependencies while keeping this
    # fixture's Project Type visible only inside its own harness interpreter.
    (packages / "test_dependencies.pth").write_text(
        f"import site; site.addsitedir({site.getsitepackages()[0]!r})\n")
    module = packages / "notebook_project_fixture.py"
    module.write_text('''from tarav.l2.project import Project
from tarav.l0.kernel import TaravClass, TypeShip
class HarnessProject(Project):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("eac933dc-74e8-44e3-a6dd-d39e603a56fb"),
                          name="Test.Notebook.HarnessProject")
''')
    marker = project.root / ".tarav/project.json"
    data = json.loads(marker.read_text())
    data["type"] = {"uuid": "eac933dc-74e8-44e3-a6dd-d39e603a56fb", "label": "Test.Notebook.HarnessProject"}
    data.pop("class_id", None)
    data["harness"] = {"environment": ".tarav/custom-env", "type": "notebook_project_fixture:HarnessProject"}
    marker.write_text(json.dumps(data))
    probe = subprocess.run([sys.executable, "-c",
                            "import tarav_bypass; from tarav.l3.runtime import get_runtime; "
                            "get_runtime(); from tarav.l1.project import TaravProject; "
                            f"TaravProject.load_project(path={str(project.root)!r})"],
                           capture_output=True, text=True, timeout=30)
    assert probe.returncode != 0 and "No module named 'notebook_project_fixture'" in probe.stderr
    result = subprocess.run([str(Path(sys.executable).with_name("tarav")), "notebook", "ls",
                             "--project", str(project.root), "--json"],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["project"]["type"] == "Test.Notebook.HarnessProject"
    assert report["scope"]["id"] == str(model.id)
