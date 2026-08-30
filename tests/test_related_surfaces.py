from __future__ import annotations

import json
from pathlib import Path

from tarav.skillware.related_surfaces import RelatedSurfaceResolver
from tarav.wayfinder import Wayfinder, WayfinderReferenceRoot, WayfinderRegistry
from tarav.skillware.managed_blocks import resolve_managed_block_reference
from tarav.wayfinder.model import managed_block_reference



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


def test_related_surfaces_are_lazy_bounded_cycle_safe_and_keep_diagnostics(
    tmp_path: Path,
) -> None:
    project_id, _ = _write_project(
        tmp_path / "project",
        """# $kw: --from Design.Root

# $kw: Check.Root --cite Guide.One --cite Missing
# --note [DF] local root guidance ^c20260820-5u
def check() -> None:
    pass

# $kw: Guide.One --note [DF] related guidance ^c20260820-5u
def guide() -> None:
    pass
""",
    )
    registry = WayfinderRegistry(tmp_path / "registry.json")
    registry.register(
        WayfinderReferenceRoot(type="agentos.project", id=project_id),
        tmp_path / "project",
    )
    wayfinder = Wayfinder(
        registry,
        resolvers=(resolve_managed_block_reference,),
    )
    resolver = RelatedSurfaceResolver(wayfinder)
    root = managed_block_reference(project_id, "Check.Root")

    root_only = resolver.resolve(root, projection="root")
    direct = resolver.resolve(root, projection="direct")
    reachable = resolver.resolve(root, projection="reachable", max_depth=4)

    assert [node.reference.address for node in root_only.nodes] == ["Check.Root"]
    assert [node.reference.address for node in direct.nodes] == [
        "Check.Root",
        "Guide.One",
    ]
    assert direct.diagnostics[0].reference.address == "Missing"
    assert reachable.nodes == direct.nodes
    assert reachable.diagnostics == direct.diagnostics


def test_related_surfaces_rejects_unbounded_or_unknown_projection(
    tmp_path: Path,
) -> None:
    resolver = RelatedSurfaceResolver(Wayfinder(WayfinderRegistry(tmp_path / "r")))

    try:
        resolver.resolve(
            managed_block_reference("demo", "Root"),
            projection="reachable",
            max_depth=0,
        )
    except ValueError as exc:
        assert "max_depth" in str(exc)
    else:
        raise AssertionError("expected bounded traversal validation")
