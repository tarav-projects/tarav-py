"""Global Project location observations survive moves and expose duplicate IDs."""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from uuid import uuid4

from tarav.l1.project.index import ProjectIndex
from tarav.l1.project.commands import _cmd_project_list


def _project(root: Path, identity: str) -> None:
    marker = root / ".tarav/project.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"class": "agentos.project", "schema_version": 1,
                                  "project_id": identity}) + "\n")


# tarav.breadcrumb 20a0ae09ee0e838a6f0838fa113fcc9916254499815ad1baf33c6a9464c78b9b
def test_move_preserves_old_location_and_recovers_same_identity(tmp_path: Path) -> None:
    identity = str(uuid4())
    old = tmp_path / "old"
    new = tmp_path / "new"
    _project(old, identity)
    index = ProjectIndex(tmp_path / "home/projects.json")
    index.observe(old)
    old.rename(new)
    before = index.list()[0]
    assert before["status"] == "unavailable"
    assert before["locations"][0]["status"] == "missing"

    index.observe(new)
    after = index.list()[0]
    assert after["project_id"] == identity
    assert after["status"] == "present"
    assert {item["status"] for item in after["locations"]} == {"missing", "present"}


def test_live_copy_is_ambiguous_and_replaced_marker_is_not_same_project(tmp_path: Path) -> None:
    identity = str(uuid4())
    first, copy = tmp_path / "first", tmp_path / "copy"
    _project(first, identity)
    _project(copy, identity)
    index = ProjectIndex(tmp_path / "home/projects.json")
    index.observe(first)
    index.observe(copy)
    assert index.list()[0]["status"] == "ambiguous"

    _project(copy, str(uuid4()))
    row = index.list()[0]
    assert row["status"] == "present"
    assert {item["status"] for item in row["locations"]} == {"present", "different-id"}


def test_explicit_root_scan_populates_global_listing(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    identity = str(uuid4())
    _project(tmp_path / "example", identity)
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / "home"))
    assert _cmd_project_list(Namespace(global_index=True, root=tmp_path,
                                       json_output=True)) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["project_id"] == identity
    assert rows[0]["status"] == "present"
