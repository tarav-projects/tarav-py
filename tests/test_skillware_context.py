from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos.skillware.build import SkillwareError, build_skill
from agentos.skillware.commands import _cmd_skillware_context
from agentos.skillware.context import project_context


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
    assert payload["command"] == "agentos skw context"
    assert payload["target"] == "references/capture.md"
    assert payload["paths"][0]["steps"][1]["edge"]["kind"] == "routing-table"
    assert payload["paths"][0]["dependencies"] == []
    assert "Capture body." in payload["paths"][0]["projected_context"]
