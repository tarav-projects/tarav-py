from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0._core.errors import CliError
from tarav.l0._core.home import initialize_global_layout, load_global_config


def _write(path: Path, cls: str) -> Path:
    path.write_text(json.dumps({"class": cls, "schema_version": 1, "agent": {}}), encoding="utf-8")
    return path


def test_new_homes_are_initialized_with_the_tarav_class(tmp_path: Path) -> None:
    result = initialize_global_layout(home_dir=tmp_path / "home")

    written = json.loads(Path(result["config_path"]).read_text(encoding="utf-8"))
    assert written["class"] == "tarav.global.config"


@pytest.mark.parametrize("cls", ["tarav.global.config", "agentos.global.config"])
def test_current_and_pre_rename_configs_load(tmp_path: Path, cls: str) -> None:
    payload = load_global_config(_write(tmp_path / "config.json", cls))

    assert payload == {"class": cls, "schema_version": 1, "agent": {}}


def test_other_classes_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="tarav.global.config"):
        load_global_config(_write(tmp_path / "config.json", "something.else"))
