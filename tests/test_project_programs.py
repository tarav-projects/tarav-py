"""Trusted Project harness loading and token-contextualized Project status."""

import json
import os
from pathlib import Path
import site
import subprocess
import sys
from uuid import uuid4

import pytest

from tarav.l0.kernel import Ship
from tarav.l2.project import Project


@pytest.fixture
def cli(tmp_path, monkeypatch):
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    root = tmp_path / "project"
    (root / ".tarav").mkdir(parents=True)
    source = root / "src"
    source.mkdir()
    environment = root / ".tarav/env"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)],
                   check=True, capture_output=True, timeout=30)
    packages = environment / f"lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages"
    (packages / "test_dependencies.pth").write_text(
        f"import site; site.addsitedir({site.getsitepackages()[0]!r})\n{source}\n")
    (source / "program_project_fixture.py").write_text('''from pathlib import Path
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import CheckSuite, CheckResult, CheckPOI, SituationCheck
from tarav.l1.programs import State, StateAction, TaravProgram, Transition
from tarav.l1.programs.workflow import PROGRAMS_WORKFLOW_SHIP
from tarav.l2.project import Project
from tarav.l3.runtime import get_runtime

def identity(cls, number, name):
    return TaravClass(target=cls, id=TypeShip(f"00000000-0000-0000-0000-{number:012d}"),
                      name="Harness.Programs." + name, workflow=PROGRAMS_WORKFLOW_SHIP)

class Ready(State):
    @classmethod
    def class_entity(cls): return identity(cls, 9001, "Ready")

class TextCheck(SituationCheck):
    @classmethod
    def class_entity(cls): return identity(cls, 9002, "Text.Check")
    def __init__(self, run):
        super().__init__(situation={"run": str(run.id)})
        self.path = Path(run.typed.project["root"]) / "product.txt"
    def _run(self):
        if (self.path.parent / "unavailable").exists():
            return CheckResult(self, status="incomplete", reason="Product unavailable")
        return CheckResult(self, status="completed", pois=[] if self.path.exists()
                           and self.path.read_text() == "written" else
                           [self.poi(CheckPOI, message="Product must contain written")])

class Written(State):
    @classmethod
    def class_entity(cls): return identity(cls, 9003, "Written")
    class Checks(State.Checks):
        def suite(self): return CheckSuite([TextCheck(self.obj.run)])

class Write(StateAction):
    State = Written
    prompt = "Write the product."
    @classmethod
    def class_entity(cls): return identity(cls, 9004, "Write")

class Reset(StateAction):
    State = Ready
    @classmethod
    def class_entity(cls): return identity(cls, 9005, "Reset")

class FixtureProgram(TaravProgram):
    initial = Ready
    graph = (Transition(Ready, Write), Transition(Written, Reset))
    @classmethod
    def class_entity(cls): return identity(cls, 9006, "Example")

class FixtureProject(Project):
    @classmethod
    def class_entity(cls): return identity(cls, 9007, "Project")
    class Checks(Project.Checks):
        def suite(self): return self.obj.programs.suite()

get_runtime().records.register(FixtureProgram)
''')
    project = Project(id=Ship(uuid4()), created_at="2026-10-23T00:00:00Z", project_name="Programs Test")
    marker = project.records.to_record()
    marker["type"] = {"uuid": "00000000-0000-0000-0000-000000009007", "label": "Harness.Programs.Project"}
    marker["harness"] = {"environment": ".tarav/env", "type": "program_project_fixture:FixtureProject"}
    (root / ".tarav/project.json").write_text(json.dumps(marker))
    command = str(Path(sys.executable).with_name("tarav"))

    def invoke(*args, code=0):
        result = subprocess.run([command, *args, "--project", str(root), "--json"],
                                capture_output=True, text=True, timeout=45, env=os.environ.copy())
        assert result.returncode == code, result.stderr + result.stdout
        return json.loads(result.stdout) if result.stdout else result.stderr

    invoke.root = root
    return invoke


# tarav.breadcrumb bb679137f263
# tarav.breadcrumb b04ba5a64e3b
def test_real_harness_program_and_contextual_status_lifecycle(cli):
    # The definition exists only inside the Project's chosen environment.
    probe = subprocess.run([sys.executable, "-c", "import program_project_fixture"],
                           capture_output=True, text=True, timeout=30)
    assert probe.returncode != 0 and "No module named" in probe.stderr
    listing = cli("program", "list")
    assert listing["programs"] == [{"id": "00000000-0000-0000-0000-000000009006",
                                    "name": "Harness.Programs.Example"}]
    assert listing["runs"] == []
    frame = cli("program", "start", "--program", "Harness.Programs.Example")
    cli("program", "choose", "--token", frame["token"], "--action", "Harness.Programs.Write")
    failed = cli("program", "step", "--token", frame["token"], code=1)
    assert not failed["advanced"] and failed["token"] == frame["token"]
    (cli.root / "product.txt").write_text("written")
    reached = cli("program", "step", "--token", frame["token"])
    assert reached["advanced"] and reached["token"] != frame["token"]
    assert cli("program", "resume", "--run", frame["run"])["token"] == reached["token"]
    assert "Stale" in cli("program", "status", "--token", frame["token"], code=2)
    assert cli("program", "status", "--token", reached["token"])["coherent"]
    # Parent run remains open; completed StateAction is retained in the registry.
    status = cli("status", "--program-token", reached["token"], code=1)
    assert status["open"] == 1
    (cli.root / "product.txt").write_text("drift")
    drift = cli("status", "--program-token", reached["token"], code=1)
    assert drift["actions"]["opened"] == 1 and drift["open"] == 2
    (cli.root / "unavailable").touch()
    incomplete = cli("status", "--program-token", reached["token"], code=1)
    assert incomplete["open"] == 2 and incomplete["actions"]["gone"] == 0
    assert any(item["status"] == "incomplete" for item in incomplete["checks"]["unfinished"])
    (cli.root / "unavailable").unlink()
    # No token, or a different run's token, cannot close this run's drift action.
    assert cli("status", code=1)["open"] == 2
    other = cli("program", "start", "--program", "Harness.Programs.Example")
    assert cli("status", "--program-token", other["token"], code=1)["open"] == 3
    (cli.root / "product.txt").write_text("written")
    restored = cli("status", "--program-token", reached["token"], code=1)
    assert restored["actions"]["gone"] == 1 and restored["open"] == 2
    retained = cli("program", "show", "--run", reached["run"])
    assert retained["token"] == reached["token"] and retained["arrival"] == 1
    assert cli("program", "recover", "--run", reached["run"])["token"] == reached["token"]


def test_cli_rejects_arbitrary_class_paths_and_invalid_inputs(cli, tmp_path):
    assert "owned by this Project" in cli("program", "start", "--program", "os:system", code=2)
    data = tmp_path / "invalid.json"
    data.write_text("null")
    assert "JSON object" in cli("program", "start", "--program", "Harness.Programs.Example",
                                "--data", str(data), code=2)
    data.write_text("{broken")
    assert "error:" in cli("program", "start", "--program", "Harness.Programs.Example",
                            "--data", str(data), code=2)
    assert "token" in cli("program", "status", "--token", "invalid", code=2)
    assert cli("program", "list")["runs"] == []
