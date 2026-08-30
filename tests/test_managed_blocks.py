from __future__ import annotations

import json
from pathlib import Path

from tarav.wayfinder import (
    WayfinderReferenceRoot,
    WayfinderRegistry,
    WayfinderResolutionPOI,
    WayfinderResolutionResult,
    managed_block_reference,
    parse_reference,
)
from tarav.skillware.managed_blocks import create_managed_wayfinder


def _write_project(root: Path, source: str) -> tuple[str, Path]:
    project_id = "00000000-0000-4000-8000-000000000533"
    (root / ".tarav").mkdir(parents=True)
    (root / ".tarav" / "project.json").write_text(
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": project_id,
                "created_at": "2026-08-20T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    (root / ".skw").mkdir()
    (root / ".skw" / "skw.json").write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {
                        "language": "python",
                        "include": ["src/**/*.py"],
                        "allow_points": ["file", "class", "function"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    target = root / "src" / "checks.py"
    target.parent.mkdir(parents=True)
    target.write_text(source, encoding="utf-8")
    return project_id, target


def _registry(tmp_path: Path, project_id: str, root: Path) -> WayfinderRegistry:
    registry = WayfinderRegistry(tmp_path / "registry.json")
    registry.register(
        WayfinderReferenceRoot(type="agentos.project", id=project_id), root
    )
    return registry


def test_managed_block_reference_round_trips_block_sugar() -> None:
    reference = managed_block_reference("project-533", "Index.Linter/Example")

    assert reference.type == "managed.block"
    assert reference.root.type == "agentos.project"
    assert parse_reference("block://project-533/Index.Linter/Example") == reference


def test_code_hosted_block_resolves_statically_and_survives_symbol_rename(
    tmp_path: Path,
) -> None:
    source = """# $kw: --from Design.Root

# $kw: Index.Linter/Example --from Index.Record --cite Fix.Guide
# --note [DF] the example check has canonical local guidance ^c20260820-2u
def old_name() -> None:
    raise RuntimeError('discovery must not import this module')
"""
    project_id, target = _write_project(tmp_path / "project", source)
    registry = _registry(tmp_path, project_id, tmp_path / "project")
    reference = managed_block_reference(project_id, "Index.Linter/Example")

    first = create_managed_wayfinder(registry).resolve(reference)

    assert isinstance(first, WayfinderResolutionResult)
    assert first.target["block_path"] == "Index.Linter/Example"
    assert first.target["host"] == {"kind": "function", "name": "old_name"}
    assert first.target["relationships"] == [
        {"kind": "from", "address": "Index.Record"},
        {"kind": "cite", "address": "Fix.Guide"},
    ]
    assert "canonical local guidance" in first.target["content"]

    target.write_text(source.replace("old_name", "new_name"), encoding="utf-8")
    renamed = create_managed_wayfinder(registry).resolve(reference)

    assert isinstance(renamed, WayfinderResolutionResult)
    assert renamed.reference == reference
    assert renamed.target["host"] == {"kind": "function", "name": "new_name"}


def test_duplicate_code_hosted_block_identity_is_ambiguous(tmp_path: Path) -> None:
    source = """# $kw: --from Design.Root

# $kw: Duplicate.Block --note [DF] first ^c20260820-2u
def first() -> None:
    pass

# $kw: Duplicate.Block --note [DF] second ^c20260820-2u
def second() -> None:
    pass
"""
    project_id, _ = _write_project(tmp_path / "project", source)
    registry = _registry(tmp_path, project_id, tmp_path / "project")

    result = create_managed_wayfinder(registry).resolve(
        managed_block_reference(project_id, "Duplicate.Block")
    )

    assert isinstance(result, WayfinderResolutionPOI)
    assert result.kind == "ambiguous"
    assert len(result.candidates) == 2
