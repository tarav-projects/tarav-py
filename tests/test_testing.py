from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from agentos._core.project import (
    find_agentos_project_root,
    load_global_config,
    load_project_config,
    load_project_marker,
)
from agentos.agent.config import load_agent_configs
from agentos.testing import AgentosTestEnvironment, write_raw_json


def test_environment_builds_loader_valid_agentos_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_global_config(
        agent={"providers": {"codex": {"cli_command": ["codex"]}}},
    )
    environment.write_profile(
        "codex-work",
        provider="codex",
        home=str(tmp_path / "codex-home"),
    )
    project_root = tmp_path / "project"
    project_root.mkdir()
    marker_path = environment.write_project_marker(
        project_root,
        project_name="Testing project",
    )
    config_path = environment.write_project_config(
        project_root,
        skills={"routing": {"sources": {}, "profiles": {}}},
    )

    assert environment.environment_variables() == {
        "HOME": str(environment.home),
        "AGENTOS_HOME": str(environment.agentos_home),
    }
    assert (
        load_global_config(environment.agentos_home / "config.json")["class"]
        == "agentos.global.config"
    )
    assert load_agent_configs()[0].instance_id == "codex-work"
    assert load_project_marker(marker_path)["project_name"] == "Testing project"
    assert load_project_config(config_path)["class"] == "agentos.project.config"
    (project_root / "nested").mkdir()
    assert find_agentos_project_root(project_root / "nested") == project_root


def test_raw_json_is_explicit_malformed_state_escape_hatch(tmp_path: Path) -> None:
    path = write_raw_json(tmp_path / "invalid.json", {"schema_version": "invalid"})

    assert json.loads(path.read_text(encoding="utf-8")) == {"schema_version": "invalid"}


def test_valid_builders_reject_reserved_fields_and_unsafe_profile_ids(
    tmp_path: Path,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)

    with pytest.raises(ValueError, match="reserved"):
        environment.write_global_config(**{"class": "wrong"})
    with pytest.raises(ValueError, match="filename"):
        environment.write_profile("../escape", provider="codex")


def test_agentos_testing_import_does_not_import_pytest() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import agentos.testing; assert 'pytest' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
