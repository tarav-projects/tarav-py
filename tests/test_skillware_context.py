from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

from tarav.skillware.build import SkillwareError, build_skill
from tarav.skillware.commands import _cmd_skillware_context
from tarav.skillware.context import audit_context, project_context


def _write_context_skill(
    root: Path,
    *,
    paths: str = "> $kw: ^direct --context-loading-path --step SKILL.md\n",
    load_target: str = "references/capture.md",
    agents: bool = False,
    dependencies: str = "",
) -> Path:
    skill = root / "skill"
    src = skill / ".skw" / "src"
    (src / "references").mkdir(parents=True)
    (skill / ".skw" / "skw.json").write_text("{}\n", encoding="utf-8")
    (src / "SKILL.skw.md").write_text(
        "# Skill\n\n"
        "> $kw: ^run-contract\n"
        "Runtime contract.\n"
        "> $kw. end\n\n"
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^capture --router-row --table ^driver --flag --capture "
        f"--match explicit --load {load_target}\n",
        encoding="utf-8",
    )
    (src / "references" / "capture.skw.md").write_text(
        f"{paths}{dependencies}\n# Capture\n\nCapture body.\n",
        encoding="utf-8",
    )
    if agents:
        (skill / "AGENTS.md").write_text("# Local agent context\n", encoding="utf-8")
    build_skill(skill)
    return skill


def _write_graph_skill(
    root: Path,
    package_id: str,
    *,
    deps: dict[str, Path] | None = None,
    loads: tuple[str, ...] = (),
    reachable_from: str | None = None,
) -> Path:
    skill = root / package_id
    src = skill / ".skw" / "src"
    src.mkdir(parents=True)
    config = {
        "id": package_id,
        "deps": {
            dep_id: os.path.relpath(dep_root, skill)
            for dep_id, dep_root in (deps or {}).items()
        },
    }
    (skill / ".skw" / "skw.json").write_text(
        json.dumps(config), encoding="utf-8"
    )
    reachability = (
        "> $kw: ^root-reachability "
        f"--reachable-from {reachable_from}\n\n"
        if reachable_from
        else ""
    )
    rows = "".join(
        (
            f"> $kw: ^route-{index} --router-row --table ^driver\n"
            "> --match semantic\n"
            f"> --load {target}\n"
            f"> --when load route {index}\n"
        )
        for index, target in enumerate(loads, start=1)
    )
    table = (
        "> $kw: ^driver --routing-table --select many\n" + rows if rows else ""
    )
    (src / "SKILL.skw.md").write_text(
        reachability + f"# {package_id}\n\n" + table,
        encoding="utf-8",
    )
    build_skill(skill)
    return skill


def test_project_context_resolves_direct_routing_path(tmp_path: Path) -> None:
    skill = _write_context_skill(tmp_path)

    report = project_context(skill, "references/capture.md")

    assert report.target == "references/capture.md"
    assert len(report.paths) == 1
    path = report.paths[0]
    assert path.address == "^direct"
    assert [step.path for step in path.steps] == [
        "SKILL.md",
        "references/capture.md",
    ]
    assert path.steps[0].edge.kind == "skill-loading-root"
    assert path.steps[1].edge.kind == "routing-table"
    assert path.steps[1].edge.provenance == ("SKILL.md^capture",)
    assert path.projected_context.index("# Skill") < path.projected_context.index(
        "# Capture"
    )


def test_project_context_supports_local_agents_and_multiple_paths(
    tmp_path: Path,
) -> None:
    skill = _write_context_skill(
        tmp_path,
        paths=(
            "> $kw: ^direct --context-loading-path --step SKILL.md\n"
            "> $kw: ^with-agents --context-loading-path\n"
            "> --step AGENTS.md\n"
            "> --step SKILL.md\n"
        ),
        agents=True,
    )

    report = project_context(skill, "references/capture.md")

    assert [path.address for path in report.paths] == ["^direct", "^with-agents"]
    with_agents = report.paths[1]
    assert [step.path for step in with_agents.steps] == [
        "AGENTS.md",
        "SKILL.md",
        "references/capture.md",
    ]
    assert [step.edge.kind for step in with_agents.steps] == [
        "local-agents-root",
        "skill-loading",
        "routing-table",
    ]
    assert report.paths[0].projected_context != with_agents.projected_context


def test_project_context_validates_addressed_loading_dependencies(
    tmp_path: Path,
) -> None:
    skill = _write_context_skill(
        tmp_path,
        dependencies=(
            "> $kw: ^runtime-requirements\n> --loading-dep SKILL.skw.md^run-contract\n"
        ),
    )

    report = project_context(skill, "references/capture.md")

    dependency = report.paths[0].dependencies[0]
    assert dependency.locator == "SKILL.skw.md^run-contract"
    assert dependency.provider == "SKILL.md"
    assert dependency.satisfied_at == 1
    assert dependency.status == "satisfied"


def test_project_context_rejects_dependency_not_materialized_in_provider(
    tmp_path: Path,
) -> None:
    skill = _write_context_skill(
        tmp_path,
        dependencies=(
            "> $kw: ^runtime-requirements\n> --loading-dep SKILL.skw.md^run-contract\n"
        ),
    )
    (skill / "SKILL.md").write_text("# Skill without contract\n", encoding="utf-8")

    with pytest.raises(SkillwareError, match="not materialized"):
        project_context(skill, "references/capture.md")


def test_project_context_rejects_dependency_from_target_or_later_step(
    tmp_path: Path,
) -> None:
    skill = _write_context_skill(
        tmp_path,
        dependencies=(
            "> $kw: ^local-contract\n"
            "Local contract.\n"
            "> $kw. end\n\n"
            "> $kw: ^runtime-requirements\n"
            "> --loading-dep references/capture.skw.md^local-contract\n"
        ),
    )

    with pytest.raises(SkillwareError, match="must occur earlier"):
        project_context(skill, "references/capture.md")


@pytest.mark.parametrize(
    ("paths", "load_target", "message"),
    [
        ("", "references/capture.md", "declares no Context.Loading.Path"),
        (
            "> $kw: ^missing --context-loading-path --step missing.md --step SKILL.md\n",
            "references/capture.md",
            "loading step does not exist",
        ),
        (
            "> $kw: ^unrealized --context-loading-path --step SKILL.md\n",
            "references/other.md",
            "has no Routing.Table --load edge",
        ),
    ],
)
def test_project_context_fails_closed(
    tmp_path: Path,
    paths: str,
    load_target: str,
    message: str,
) -> None:
    skill = _write_context_skill(tmp_path, paths=paths, load_target=load_target)
    with pytest.raises(SkillwareError, match=message):
        project_context(skill, "references/capture.md")


def test_context_command_emits_machine_projection(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_context_skill(tmp_path)
    args = argparse.Namespace(
        skill=str(skill),
        target="references/capture.md",
        json=True,
    )

    assert _cmd_skillware_context(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "tarav skw context"
    assert payload["target"] == "references/capture.md"
    assert payload["paths"][0]["steps"][1]["edge"]["kind"] == "routing-table"
    assert payload["paths"][0]["dependencies"] == []
    assert "Capture body." in payload["paths"][0]["projected_context"]


def test_project_context_resolves_direct_cross_package_reachability(
    tmp_path: Path,
) -> None:
    child = _write_graph_skill(
        tmp_path,
        "child-skill",
        reachable_from="@<root-skill>/SKILL.md",
    )
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps={"child-skill": child},
        loads=("@<child-skill>/SKILL.md",),
    )

    report = project_context(root, "@<child-skill>/SKILL.md")

    assert report.target == "@<child-skill>/SKILL.md"
    path = report.paths[0]
    assert path.address == "^root-reachability"
    assert [step.path for step in path.steps] == [
        "@<root-skill>/SKILL.md",
        "@<child-skill>/SKILL.md",
    ]
    assert path.steps[1].edge.kind == "routing-table"
    assert path.steps[1].edge.provenance == (
        "@<root-skill>/SKILL.md^route-1",
    )


def test_context_audit_resolves_transitive_cross_package_path(tmp_path: Path) -> None:
    leaf = _write_graph_skill(
        tmp_path,
        "leaf-skill",
        reachable_from="@<root-skill>/SKILL.md",
    )
    middle = _write_graph_skill(
        tmp_path,
        "middle-skill",
        deps={"leaf-skill": leaf},
        loads=("@<leaf-skill>/SKILL.md",),
    )
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps={"middle-skill": middle},
        loads=("@<middle-skill>/SKILL.md",),
    )

    audit = audit_context(root)

    assert [report.target for report in audit.targets] == [
        "@<leaf-skill>/SKILL.md"
    ]
    assert [step.path for step in audit.targets[0].paths[0].steps] == [
        "@<root-skill>/SKILL.md",
        "@<middle-skill>/SKILL.md",
        "@<leaf-skill>/SKILL.md",
    ]


def test_context_graph_accepts_typed_load_to_unmanaged_skill(tmp_path: Path) -> None:
    external = tmp_path / "external-skill"
    external.mkdir()
    (external / "SKILL.md").write_text("# External\n", encoding="utf-8")
    child = _write_graph_skill(
        tmp_path,
        "child-skill",
        reachable_from="@<root-skill>/SKILL.md",
    )
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps={"child-skill": child, "external-skill": external},
        loads=("@<child-skill>/SKILL.md", "@<external-skill>/SKILL.md"),
    )

    audit = audit_context(root)

    assert audit.targets[0].target == "@<child-skill>/SKILL.md"


def test_context_graph_requires_loader_to_register_cross_package_target(
    tmp_path: Path,
) -> None:
    leaf = _write_graph_skill(tmp_path, "leaf-skill")
    middle = _write_graph_skill(
        tmp_path,
        "middle-skill",
        loads=("@<leaf-skill>/SKILL.md",),
    )
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps={"middle-skill": middle, "leaf-skill": leaf},
        loads=("@<middle-skill>/SKILL.md",),
    )

    with pytest.raises(SkillwareError, match="not registered by"):
        audit_context(root)


@pytest.mark.parametrize(
    ("setup", "message"),
    [
        ("unknown-package", "unknown runtime package"),
        ("missing-file", "runtime load target does not exist"),
        ("unreachable", "no loading path"),
        ("identity-mismatch", "registry key"),
    ],
)
def test_context_graph_fails_closed(
    tmp_path: Path, setup: str, message: str
) -> None:
    child = _write_graph_skill(
        tmp_path,
        "child-skill",
        reachable_from="@<root-skill>/SKILL.md",
    )
    deps = {"child-skill": child}
    loads: tuple[str, ...] = ("@<child-skill>/SKILL.md",)
    if setup == "unknown-package":
        loads = ("@<missing-skill>/SKILL.md",)
    elif setup == "missing-file":
        loads = ("@<child-skill>/missing.md",)
    elif setup == "unreachable":
        loads = ()
    elif setup == "identity-mismatch":
        deps = {"wrong-id": child}
        loads = ("@<wrong-id>/SKILL.md",)
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps=deps,
        loads=loads,
    )

    with pytest.raises(SkillwareError, match=message):
        audit_context(root)


def test_context_command_audits_all_reachability_without_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    child = _write_graph_skill(
        tmp_path,
        "child-skill",
        reachable_from="@<root-skill>/SKILL.md",
    )
    root = _write_graph_skill(
        tmp_path,
        "root-skill",
        deps={"child-skill": child},
        loads=("@<child-skill>/SKILL.md",),
    )
    args = argparse.Namespace(skill=str(root), target=None, json=True)

    assert _cmd_skillware_context(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"] == {"target_count": 1, "requirement_count": 1}
    assert payload["targets"][0]["target"] == "@<child-skill>/SKILL.md"
