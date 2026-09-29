"""Project harness lifecycle and one real, isolated uv/subprocess integration."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tarav.l0._core.project import initialize_project_layout
from tarav.l0.kernel import entity
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import ProjectWorkflow
from tarav.l1.python_env import RunnerConfigurator
from tarav.l2.project.harness import ProjectHarness, ProjectHarnessError
from tarav.l2.project.runner import (
    ProjectLaunchConfiguration,
    ProjectRunnerConfigurator,
    ProjectRunnerError,
)
from tarav.l3.cli.cli import main
from tarav.l3.project.harness import run


SOURCE = Path(__file__).resolve().parents[1]


def _scaffold(root, **kwargs):
    root.mkdir(parents=True, exist_ok=True)
    return ProjectHarness.scaffold(
        path=root, package="fixture_project", tarav_source=SOURCE, **kwargs
    )


def _snapshot(root):
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _fake_environment(harness):
    harness.interpreter.parent.mkdir(parents=True, exist_ok=True)
    harness.interpreter.write_text("fixture")
    (harness.env / "pyvenv.cfg").write_text("version = 3.12.11\n")


def test_scaffold_discovery_and_reruns_preserve_source_and_identity(
    tmp_path, monkeypatch
):
    def forbidden(*args, **kwargs):
        pytest.fail("Inspection and scaffolding must not launch processes")

    monkeypatch.setattr(subprocess, "run", forbidden)
    root = tmp_path / "project"
    harness = _scaffold(root)
    marker = json.loads(harness.marker.read_text())
    config = harness.configuration()
    assert marker["type"] == {"uuid": config["type_ship"], "label": config["type_name"]}
    assert marker["project_id"] != config["type_ship"]
    assert not harness.env.exists()
    assert "fixture_project" not in sys.modules
    generated = harness.directory / "src" / "fixture_project"
    for source in generated.glob("*.py"):
        compile(source.read_text(), str(source), "exec")
    project_source = generated / "project.py"
    edited = (
        project_source.read_text()
        + "\n    def greeting(self):\n        return 'hello tarav'\n"
    )
    project_source.write_text(edited)
    harness.directory.joinpath(".gitignore").write_text("# keep this\ncache/\n/env/\n")
    before = _snapshot(root)
    harness = _scaffold(root)
    assert _snapshot(root) == before
    assert harness.configuration() == config
    assert json.loads(harness.marker.read_text()) == marker
    assert project_source.read_text() == edited
    (generated / "__main__.py").unlink()
    _scaffold(root)
    assert (generated / "__main__.py").exists()
    assert project_source.read_text() == edited

    child = root / "subdirectory"
    child.mkdir()
    before = _snapshot(root)
    discovered = ProjectHarness.from_path(path=child)
    assert discovered.root == root.resolve()
    assert discovered.inspect()["harness"] == config
    assert _snapshot(root) == before
    nested = _scaffold(child / "nested")
    assert ProjectHarness.from_path(path=nested.directory).root == nested.root
    assert "fixture_project" not in sys.modules


def test_adoption_is_explicit_and_preserves_marker_and_ignore_data(tmp_path):
    root = tmp_path / "existing"
    root.mkdir()
    initialize_project_layout(root)
    marker_path = root / ".tarav/project.json"
    marker = json.loads(marker_path.read_text())
    marker.update(
        {
            "notes": {"keep": "metadata"},
            "type": entity(TaravProject).to_record()["name"],
        }
    )
    marker_path.write_text(json.dumps(marker))
    ignore = root / ".tarav/.gitignore"
    ignore.write_text("# existing rules\ncache/")
    before = _snapshot(root)
    with pytest.raises(ProjectHarnessError, match="explicit adopt"):
        _scaffold(root)
    assert _snapshot(root) == before
    harness = _scaffold(root, adopt=True)
    adopted = json.loads(marker_path.read_text())
    assert adopted["project_id"] == marker["project_id"]
    assert adopted["notes"] == marker["notes"]
    assert adopted["type"]["uuid"] == harness.configuration()["type_ship"]
    assert ignore.read_text() == "# existing rules\ncache/\n/env/\n"
    specialized = tmp_path / "specialized"
    specialized.mkdir()
    initialize_project_layout(specialized)
    path = specialized / ".tarav/project.json"
    document = json.loads(path.read_text())
    document["type"] = "Another.Project"
    path.write_text(json.dumps(document))
    before = _snapshot(specialized)
    with pytest.raises(ProjectHarnessError, match="specialized"):
        _scaffold(specialized, adopt=True)
    assert _snapshot(specialized) == before


def test_declared_product_package_configures_run_and_sync_without_type_dispatch(
    tmp_path, monkeypatch
):
    root = tmp_path / "declared product"
    root.mkdir()
    initialize_project_layout(root)
    marker_path = root / ".tarav/project.json"
    marker = json.loads(marker_path.read_text())
    marker["type"] = {
        "uuid": "3c1313ee-f151-4573-8c91-040a6c69b19e",
        "label": "Product.Project.UnknownToBootstrap",
    }
    marker["harness"] = {
        "manifest": "product-py/pyproject.toml",
        "environment": "product-py/.venv",
    }
    marker_path.write_text(json.dumps(marker))
    manifest = root / "product-py/pyproject.toml"
    manifest.parent.mkdir()
    manifest.write_text('[project]\nname = "product"\nversion = "0.1.0"\n')

    launch = ProjectLaunchConfiguration.from_path(root)
    harness = ProjectHarness.from_path(path=root)
    _fake_environment(harness)
    assert launch.declared is True
    assert launch.manifest == manifest
    assert issubclass(ProjectRunnerConfigurator, RunnerConfigurator)
    assert entity(ProjectRunnerConfigurator).workflow is ProjectWorkflow()
    assert ProjectRunnerConfigurator(launch).configure().interpreter == launch.interpreter
    assert harness.inspect()["harness"] == {
        "manifest": "product-py/pyproject.toml",
        "environment": "product-py/.venv",
        "declared": True,
    }

    calls = []

    def execute(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(subprocess, "run", execute)
    assert (
        main(
            [
                "run",
                "--project",
                str(root),
                "--src",
                "print('configured')",
                "--",
                "literal argument",
            ]
        )
        == 7
    )
    assert calls[-1] == (
        [
            str(launch.interpreter),
            "-c",
            "print('configured')",
            "literal argument",
        ],
        {"cwd": root.resolve(), "check": False},
    )

    monkeypatch.setattr("tarav.l2.project.harness.shutil.which", lambda name: "/fixture/uv")
    harness.sync()
    command, options = calls[-1]
    assert command[1:4] == ["sync", "--project", str(manifest.parent)]
    assert options["env"]["UV_PROJECT_ENVIRONMENT"] == str(launch.environment)


@pytest.mark.parametrize("field", ["manifest", "environment"])
def test_declared_harness_paths_must_remain_inside_project(tmp_path, field):
    root = tmp_path / "project"
    root.mkdir()
    initialize_project_layout(root)
    marker_path = root / ".tarav/project.json"
    marker = json.loads(marker_path.read_text())
    marker["harness"] = {
        "manifest": "product/pyproject.toml",
        "environment": "product/.venv",
    }
    marker["harness"][field] = "../outside"
    marker_path.write_text(json.dumps(marker))

    with pytest.raises(ProjectRunnerError, match="outside"):
        ProjectLaunchConfiguration.from_path(root)


def test_setup_rejects_invalid_inputs_and_conflicting_owned_files(tmp_path):
    root = tmp_path / "new"
    root.mkdir()
    for overrides in (
        {"package": "not-valid"},
        {"class_name": "class"},
        {"class_name": "TypeShip"},
        {"package": "tarav"},
        {"tarav_source": tmp_path / "absent"},
    ):
        arguments = {
            "path": root,
            "package": "fixture_project",
            "tarav_source": SOURCE,
            **overrides,
        }
        with pytest.raises(ProjectHarnessError):
            ProjectHarness.scaffold(**arguments)
        assert list(root.iterdir()) == []
    (root / ".tarav").mkdir()
    manifest = root / ".tarav/pyproject.toml"
    manifest.write_text('[project]\nname = "unrelated"\n')
    before = _snapshot(root)
    with pytest.raises(ProjectHarnessError, match="configuration"):
        _scaffold(root)
    assert _snapshot(root) == before
    manifest.unlink()
    (root / ".tarav/src/fixture_project").mkdir(parents=True)
    with pytest.raises(ProjectHarnessError, match="package source"):
        _scaffold(root)


def test_sync_has_one_explicit_environment_and_failures_preserve_state(
    tmp_path, monkeypatch
):
    import tarav.l2.project.harness as module

    harness = _scaffold(tmp_path / "project with spaces")
    product_env = harness.root / ".venv"
    product_env.mkdir()
    product_env.joinpath("sentinel").write_text("leave product environment alone")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", str(product_env))
    monkeypatch.setenv("VIRTUAL_ENV", str(product_env))
    monkeypatch.setattr(module.shutil, "which", lambda name: "/fixture/uv")
    calls = []

    def synchronize(command, **kwargs):
        calls.append((command, kwargs))
        assert kwargs["env"]["UV_PROJECT_ENVIRONMENT"] == str(harness.env)
        assert "VIRTUAL_ENV" not in kwargs["env"]
        assert command[:4] == [
            "/fixture/uv",
            "sync",
            "--project",
            str(harness.directory),
        ]
        assert kwargs["check"] is True
        _fake_environment(harness)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(module.subprocess, "run", synchronize)
    harness.sync()
    harness.sync()
    assert calls[1][0][-1] == str(harness.interpreter)
    assert (
        product_env.joinpath("sentinel").read_text()
        == "leave product environment alone"
    )
    assert not harness.directory.joinpath(".venv").exists()
    before = _snapshot(harness.root)
    with pytest.raises(ProjectHarnessError, match="cannot be replaced"):
        harness.sync(python="3.14")
    monkeypatch.setattr(module.shutil, "which", lambda name: None)
    with pytest.raises(ProjectHarnessError, match="uv is required"):
        harness.sync()
    monkeypatch.setattr(module.shutil, "which", lambda name: "/fixture/uv")

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(module.subprocess, "run", fail)
    with pytest.raises(ProjectHarnessError, match="sync failed"):
        harness.sync()
    assert _snapshot(harness.root) == before
    (harness.env / "pyvenv.cfg").unlink()
    with pytest.raises(ProjectHarnessError, match="incomplete"):
        harness.sync()
    assert harness.interpreter.exists()


def test_launch_and_cli_keep_arguments_literal_and_forward_exit_status(
    tmp_path, monkeypatch, capsys
):
    root = tmp_path / "project with spaces"
    root.mkdir()
    assert (
        main(
            [
                "project",
                "harness",
                "scaffold",
                "--project",
                str(root),
                "--package",
                "fixture_project",
                "--tarav-source",
                str(SOURCE),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["environment_present"] is False
    harness = ProjectHarness.from_path(path=root)
    with pytest.raises(ProjectHarnessError, match="absent"):
        run(path=root)
    _fake_environment(harness)
    calls = []

    def launch(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 7)

    monkeypatch.setattr(subprocess, "run", launch)
    code = "print('$(touch surprise); `echo injected`')"
    arguments = ["--flag", "with spaces", "$(echo literal); `whoami`"]
    assert (
        main(
            [
                "project",
                "harness",
                "run",
                "--project",
                str(root),
                "--code",
                code,
                "--",
                *arguments,
            ]
        )
        == 7
    )
    command, options = calls[-1]
    assert command[:4] == [str(harness.interpreter), "-I", "-m", "fixture_project"]
    assert "--code=" + code in command
    assert command[-4:] == ["--", *arguments]
    assert options == {"cwd": harness.root, "check": False}
    script = root / "script with spaces.py"
    assert run(path=root, file=script, arguments=arguments) == 7
    assert str(script.resolve()) in calls[-1][0]
    assert main(["project", "harness", "inspect", "--project", str(root)]) == 0
    assert (
        json.loads(capsys.readouterr().out)["harness"]["package"] == "fixture_project"
    )


@pytest.mark.skipif(
    shutil.which("uv") is None, reason="real uv integration requires uv"
)
def test_real_uv_harness_loads_project_and_runs_editable_specialization(
    tmp_path, capfd
):
    root = tmp_path / "project with spaces and $;"
    harness = _scaffold(root)
    project_source = harness.directory / "src/fixture_project/project.py"
    project_source.write_text(
        project_source.read_text()
        + "\n    def greeting(self):\n        return 'hello tarav'\n"
    )
    marker_before = harness.marker.read_bytes()
    host = (sys.prefix, sys.executable)
    harness.sync()
    assert harness.directory.joinpath("uv.lock").is_file()
    assert not harness.directory.joinpath(".venv").exists()
    capfd.readouterr()
    arguments = ["hello world", "$(echo literal); `whoami`"]
    code = "import sys, json; print(json.dumps({'class': type(project).__name__, 'greeting': project.greeting(), 'record': project.to_record(), 'prefix': sys.prefix, 'executable': sys.executable, 'args': sys.argv[1:]}))"
    assert run(path=root, code=code, arguments=arguments) == 0
    result = json.loads(capfd.readouterr().out)
    assert result["class"] == "MyProject"
    assert result["greeting"] == "hello tarav"
    assert result["record"]["project_id"] == json.loads(marker_before)["project_id"]
    assert result["record"]["type"]["uuid"] == harness.configuration()["type_ship"]
    assert result["prefix"] == str(harness.env)
    assert result["executable"] == str(harness.interpreter)
    assert result["args"] == arguments
    sentinel = harness.env / "preserve-on-failed-sync"
    sentinel.write_text("retained environment")
    manifest_before = harness.manifest.read_text()
    harness.manifest.write_text(
        manifest_before.replace(
            'requires-python = ">=3.12"', 'requires-python = ">=99"'
        )
    )
    with pytest.raises(ProjectHarnessError, match="sync failed"):
        harness.sync()
    assert sentinel.read_text() == "retained environment"
    assert harness.interpreter.exists()
    harness.manifest.write_text(manifest_before)
    capfd.readouterr()
    project_source.write_text(
        project_source.read_text().replace("hello tarav", "edited without reinstall")
    )
    script = root / "project probe.py"
    script.write_text("print(project.greeting())\n")
    assert run(path=root, file=script) == 0
    assert capfd.readouterr().out.strip() == "edited without reinstall"
    assert run(path=root, code="raise SystemExit(9)") == 9
    capfd.readouterr()
    assert harness.marker.read_bytes() == marker_before
    document = json.loads(marker_before)
    document["type"] = "Unknown.Project"
    harness.marker.write_text(json.dumps(document))
    unknown_record = harness.marker.read_bytes()
    assert run(path=root) != 0
    assert "UnknownRecordType" in capfd.readouterr().err
    assert harness.marker.read_bytes() == unknown_record
    assert (sys.prefix, sys.executable) == host

    declared_root = tmp_path / "declared product package"
    declared_root.mkdir()
    initialize_project_layout(declared_root)
    declared_marker = declared_root / ".tarav/project.json"
    payload = json.loads(declared_marker.read_text())
    payload["type"] = {
        "uuid": "3c1313ee-f151-4573-8c91-040a6c69b19e",
        "label": "Product.Project.UnknownToBootstrap",
    }
    payload["harness"] = {
        "manifest": "product-py/pyproject.toml",
        "environment": "product-py/.venv",
    }
    declared_marker.write_text(json.dumps(payload))
    package_root = declared_root / "product-py"
    package_root.mkdir()
    package_root.joinpath("pyproject.toml").write_text(
        """[build-system]
requires = ["hatchling>=1.24.0"]
build-backend = "hatchling.build"

[project]
name = "declared-product"
version = "0.1.0"

[tool.hatch.build.targets.wheel]
packages = ["src/declared_product"]
"""
    )
    source = package_root / "src/declared_product"
    source.mkdir(parents=True)
    source.joinpath("__init__.py").write_text("greeting = 'declared package'\n")
    declared = ProjectHarness.from_path(path=declared_root)
    declared.sync()
    capfd.readouterr()
    assert (
        main(
            [
                "run",
                "--project",
                str(declared_root),
                "--src",
                "import declared_product; print(declared_product.greeting)",
            ]
        )
        == 0
    )
    assert capfd.readouterr().out.strip() == "declared package"
