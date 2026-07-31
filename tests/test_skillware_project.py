from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos.skillware.build import (
    SkillwareError,
    build_skill,
    check_skill,
    expand_file,
    load_skillware,
)
from agentos.skillware.commands import (
    _cmd_skillware_build,
    _cmd_skillware_check,
    _cmd_skillware_status,
    register_skillware_commands,
)
from _skillware_helpers import (
    _write_skill,
)


def _write_project(root: Path) -> Path:
    """A project with the marker, a shared depot, a project config pointing at
    it, and one package (pkgA) that declares a dependency on a shared block."""
    (root / ".agentos").mkdir(parents=True)
    (root / ".agentos" / "project.json").write_text("{}", encoding="utf-8")
    depot = root / "shared-depot"
    (depot / "design").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text(
        "- `design/100-design.md` — Shared.Block\n", encoding="utf-8"
    )
    (depot / "design" / "100-design.md").write_text(
        "## Shared.Block\n\n- shared across packages\n", encoding="utf-8"
    )
    (root / ".skw").mkdir()
    (root / ".skw" / "skw.json").write_text(
        json.dumps({"depots": ["shared-depot"]}), encoding="utf-8"
    )
    pkg_a_src = root / "packages" / "pkgA" / ".skw" / "src"
    pkg_a_src.mkdir(parents=True)
    (pkg_a_src / "mod.skw.md").write_text(
        "# mod\n\n> $kw: --from Shared.Block\n\nUses `Shared.Block`.\n",
        encoding="utf-8",
    )
    build_skill(root / "packages" / "pkgA")  # a real package is built
    return root


def test_project_check_catches_cross_package_dangling(tmp_path: Path) -> None:
    """The project-scope payoff: a rename in the shared depot breaks pkgA's
    declared dependency, caught by `check_project` without targeting pkgA."""
    from agentos.skillware.build import check_project

    proj = _write_project(tmp_path)
    depot_chapter = proj / "shared-depot" / "design" / "100-design.md"

    # GREEN: the shared block resolves via the cascaded project depot.
    report = check_project(proj)
    assert report.poi_count == 0
    assert any("pkgA" in str(pkg) for pkg, _ in report.packages)

    # RED: rename the shared block without an alias — pkgA's --from dangles.
    depot_chapter.write_text(
        depot_chapter.read_text(encoding="utf-8").replace(
            "## Shared.Block", "## Renamed.Block"
        ),
        encoding="utf-8",
    )
    report = check_project(proj)
    dangling = [
        (pkg, poi)
        for pkg, pr in report.packages
        for poi in pr.pois
        if poi.kind == "dangling-dependency"
    ]
    assert len(dangling) == 1
    pkg, poi = dangling[0]
    assert "pkgA" in str(pkg) and poi.key == "Shared.Block"


def test_project_check_honors_exclude(tmp_path: Path) -> None:
    from agentos.skillware.build import check_project, discover_packages

    proj = _write_project(tmp_path)
    # a second package
    pkg_b_src = proj / "packages" / "pkgB" / ".skw" / "src"
    pkg_b_src.mkdir(parents=True)
    (pkg_b_src / "mod.skw.md").write_text("# b\n\nplain.\n", encoding="utf-8")

    assert any("pkgB" in str(p) for p in discover_packages(proj))

    (proj / ".skw" / "skw.json").write_text(
        json.dumps({"depots": ["shared-depot"], "exclude": ["packages/pkgB"]}),
        encoding="utf-8",
    )
    assert not any("pkgB" in str(p) for p in discover_packages(proj))
    report = check_project(proj)
    assert not any("pkgB" in str(pkg) for pkg, _ in report.packages)


def test_skw_config_parse_warns_unknown_keys_and_rejects_bad_types(
    tmp_path: Path,
) -> None:
    from agentos.skillware.build import parse_skw_config

    good = tmp_path / "skw.json"
    good.write_text(
        json.dumps({"depots": ["../pkg"], "projects": ["../sib"], "mystery": 1}),
        encoding="utf-8",
    )
    config = parse_skw_config(good)
    assert config.depots == ("../pkg",)
    assert config.projects == ("../sib",)
    assert any("mystery" in w for w in config.warnings)

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"depots": "not-a-list"}), encoding="utf-8")
    with pytest.raises(SkillwareError):
        parse_skw_config(bad)


def test_skw_config_parses_strict_edition_history_policy(tmp_path: Path) -> None:
    from agentos.skillware.build import parse_skw_config

    config_path = tmp_path / "skw.json"
    config_path.write_text(
        json.dumps(
            {
                "edition_history": {
                    "targets": ["src/**/*.py", "tools/*.py"],
                    "exclude": ["src/**/__init__.py"],
                    "depot": ".state/history",
                }
            }
        ),
        encoding="utf-8",
    )

    policy = parse_skw_config(config_path).edition_history
    assert policy is not None
    assert policy.targets == ("src/**/*.py", "tools/*.py")
    assert policy.exclude == ("src/**/__init__.py",)
    assert policy.depot == ".state/history"


@pytest.mark.parametrize(
    "policy",
    [
        {},
        {"targets": []},
        {"targets": "src/*.py"},
        {"targets": ["../outside.py"]},
        {"targets": ["src/*.py"], "unknown": True},
        {"targets": ["src/*.py"], "exclude": "tests/*.py"},
        {"targets": ["src/*.py"], "depot": 7},
    ],
)
def test_skw_config_rejects_invalid_edition_history_policy(
    tmp_path: Path,
    policy: object,
) -> None:
    from agentos.skillware.build import parse_skw_config

    config_path = tmp_path / "skw.json"
    config_path.write_text(
        json.dumps({"edition_history": policy}),
        encoding="utf-8",
    )

    with pytest.raises(SkillwareError, match="edition_history"):
        parse_skw_config(config_path)


def test_expand_edition_history_targets_is_deterministic(
    tmp_path: Path,
) -> None:
    from agentos.skillware.build import (
        EditionHistoryConfig,
        expand_edition_history_targets,
    )

    (tmp_path / "src" / "nested").mkdir(parents=True)
    for relative in (
        "src/a.py",
        "src/nested/b.py",
        "src/nested/__init__.py",
        "src/readme.md",
    ):
        path = tmp_path / relative
        path.write_text(relative, encoding="utf-8")
    policy = EditionHistoryConfig(
        targets=("src/**/*.py",),
        exclude=("src/**/__init__.py",),
    )

    assert expand_edition_history_targets(tmp_path, policy) == (
        (tmp_path / "src/a.py").resolve(),
        (tmp_path / "src/nested/b.py").resolve(),
    )

    with pytest.raises(SkillwareError, match="matched no files"):
        expand_edition_history_targets(
            tmp_path,
            EditionHistoryConfig(targets=("missing/**/*.py",)),
        )


def test_find_project_root_walks_to_marker(tmp_path: Path) -> None:
    from agentos.skillware.build import find_project_root

    (tmp_path / ".agentos").mkdir()
    (tmp_path / ".agentos" / "project.json").write_text("{}", encoding="utf-8")
    deep = tmp_path / "skills" / "pkg" / ".skw"
    deep.mkdir(parents=True)
    assert find_project_root(deep) == tmp_path.resolve()
    assert find_project_root(tmp_path / "nowhere") == tmp_path.resolve()


def test_cascade_extends_package_depots_across_repos(tmp_path: Path) -> None:
    """A package's own depots are extended by project-scope depots, including
    a sibling project's depots reached via `projects`."""
    from agentos.skillware.build import load_skillware, resolve_project_depots

    # sibling repo with its own project-level depot
    sib = tmp_path / "sib"
    (sib / ".skw").mkdir(parents=True)
    (sib / "depot" / "design").mkdir(parents=True)
    (sib / "depot" / "000-INDEX.md").write_text(
        "- `design/100-design.md` — Sib.Concept\n", encoding="utf-8"
    )
    (sib / "depot" / "design" / "100-design.md").write_text(
        "## Sib.Concept\n\n- from the sibling repo\n", encoding="utf-8"
    )
    (sib / ".skw" / "skw.json").write_text(
        json.dumps({"depots": ["depot"]}), encoding="utf-8"
    )

    # project with a package and a project-scope config pointing at the sibling
    proj = tmp_path / "proj"
    skill = _write_skill(proj)  # legacy .skillware/ package with its own ../depot
    (proj / ".agentos").mkdir(parents=True)
    (proj / ".agentos" / "project.json").write_text("{}", encoding="utf-8")
    (proj / ".skw").mkdir()
    (proj / ".skw" / "skw.json").write_text(
        json.dumps({"projects": ["../sib"]}), encoding="utf-8"
    )

    project_depots = tuple(resolve_project_depots(proj))
    assert any(d.name == "depot" and "sib" in str(d) for d in project_depots)

    sw = load_skillware(skill, extra_depots=project_depots)
    # the package keeps its own depot AND gains the sibling's
    assert any("sib" in str(d) for d in sw.depots)
    assert any(str(d).endswith("proj/depot") for d in sw.depots)


def test_build_dir_prefers_skw_with_skillware_fallback(tmp_path: Path) -> None:
    """`.skw/` is the current build home; `.skillware/` still loads during the
    deprecation window; when both exist, `.skw/` wins."""
    skill = _write_skill(tmp_path)  # writes a legacy .skillware/ package

    # Fallback: a legacy .skillware/ package still loads.
    legacy = load_skillware(skill)
    assert legacy.build_root.name == ".skillware"

    # Current: rename to .skw/ and it loads as the preferred home.
    (skill / ".skillware").rename(skill / ".skw")
    current = load_skillware(skill)
    assert current.build_root.name == ".skw"

    # Both present: .skw/ takes precedence.
    (skill / ".skillware").mkdir()
    (skill / ".skillware" / "src").mkdir()
    assert load_skillware(skill).build_root.name == ".skw"


def test_skw_verb_with_skillware_alias() -> None:
    """The verb is `agentos skw`; `skillware` stays as a deprecation alias."""
    parser = argparse.ArgumentParser(prog="agentos")
    subparsers = parser.add_subparsers(dest="command")
    register_skillware_commands(subparsers)

    for verb in ("skw", "skillware"):
        args = parser.parse_args([verb, "check", "--skill", "some/path"])
        assert args.handler is _cmd_skillware_check
        assert args.skill == "some/path"


def test_check_payload_uses_skw_command_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    _cmd_skillware_build(argparse.Namespace(skill=str(skill), json=True))
    capsys.readouterr()
    _cmd_skillware_check(argparse.Namespace(skill=str(skill), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"]["command"] == "agentos skw check"


def test_cli_build_check_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    args = argparse.Namespace(skill=str(skill), json=True)

    assert _cmd_skillware_build(args) == 0
    build_payload = json.loads(capsys.readouterr().out)
    assert {entry["action"] for entry in build_payload["entries"]} == {"built"}

    assert _cmd_skillware_check(args) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["summary"]["poi_count"] == 0
    assert check_payload["pois"] == []

    target = skill / "references" / "mod.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nrogue\n", encoding="utf-8"
    )
    assert _cmd_skillware_check(args) == 1
    check_payload = json.loads(capsys.readouterr().out)
    statuses = {
        entry["target"]: entry["status"] for entry in check_payload["domain"]["entries"]
    }
    assert statuses["references/mod.md"] == "hand-edited"

    assert _cmd_skillware_status(args) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["lock_present"] is True
    mod = next(
        f for f in status_payload["files"] if f["src"] == "references/mod.skw.md"
    )
    assert mod["recipes"] == {"copy": 2, "derived": 1}

    with pytest.raises(CliError):
        _cmd_skillware_build(
            argparse.Namespace(skill=str(tmp_path / "nope"), json=True)
        )


def test_build_stamps_agents_md(tmp_path: Path) -> None:
    from agentos.skillware.build import AGENTS_MD_TEXT

    skill = _write_skill(tmp_path)
    build_skill(skill)
    agents = skill / ".skillware" / "AGENTS.md"
    assert agents.is_file()
    assert agents.read_text(encoding="utf-8") == AGENTS_MD_TEXT
    assert "agentos skw build" in AGENTS_MD_TEXT
    assert "agentos-skillware" in AGENTS_MD_TEXT


def test_build_overwrites_hand_edited_agents_md(tmp_path: Path) -> None:
    from agentos.skillware.build import AGENTS_MD_TEXT

    skill = _write_skill(tmp_path)
    build_skill(skill)
    agents = skill / ".skillware" / "AGENTS.md"
    agents.write_text("# my local notes\n", encoding="utf-8")
    build_skill(skill)
    assert agents.read_text(encoding="utf-8") == AGENTS_MD_TEXT


_PRODUCER_TEMPLATE = """# template

## Body

- canonical line one
- canonical line two
"""


def _write_pkg_pair(root: Path, *, dep_path: str, from_locator: str) -> Path:
    """A producer package holding a copyable region, and a consumer that pulls
    it through the named `deps` registry. Returns the consumer root."""
    producer = root / "producer"
    psrc = producer / ".skw" / "src" / "references"
    psrc.mkdir(parents=True)
    (psrc / "template.skw.md").write_text(_PRODUCER_TEMPLATE, encoding="utf-8")
    (producer / ".skw" / "skw.json").write_text(json.dumps({}), encoding="utf-8")

    consumer = root / "consumer"
    csrc = consumer / ".skw" / "src" / "references"
    csrc.mkdir(parents=True)
    (csrc / "copy.skw.md").write_text(
        f"# copy\n\n> $kw: #body --copy --from {from_locator}\n\n> $kw. end\n",
        encoding="utf-8",
    )
    (consumer / ".skw" / "skw.json").write_text(
        json.dumps({"deps": {"producer": dep_path}}), encoding="utf-8"
    )
    return consumer


def test_cross_package_dep_resolves_through_registry(tmp_path: Path) -> None:
    consumer = _write_pkg_pair(
        tmp_path,
        dep_path="../producer",
        from_locator="@<producer>/references/template.skw.md#Body",
    )
    expansion = expand_file(load_skillware(consumer), Path("references/copy.skw.md"))
    assert not expansion.findings
    fresh = "\n".join(expansion.fresh_lines)
    assert "- canonical line one" in fresh
    assert "- canonical line two" in fresh
    # the lock records the LOGICAL id, not a filesystem path
    assert list(expansion.dep_hashes["copy"]) == [
        "@<producer>/references/template.skw.md#Body"
    ]


def test_cross_package_dep_layout_independent(tmp_path: Path) -> None:
    """Moving the producer and pointing skw.json at the new location keeps the
    dependency resolving with an unchanged logical key."""
    consumer = _write_pkg_pair(
        tmp_path,
        dep_path="../producer",
        from_locator="@<producer>/references/template.skw.md#Body",
    )
    build_skill(consumer)
    assert not check_skill(consumer).pois

    (tmp_path / "packages").mkdir()
    (tmp_path / "producer").rename(tmp_path / "packages" / "producer")
    (consumer / ".skw" / "skw.json").write_text(
        json.dumps({"deps": {"producer": "../packages/producer"}}), encoding="utf-8"
    )
    assert not check_skill(consumer).pois


def test_raw_path_escape_is_rejected(tmp_path: Path) -> None:
    """The CT: a --from may not climb out of the package with `..`; it must go
    through a registered dependency id."""
    consumer = _write_pkg_pair(
        tmp_path,
        dep_path="../producer",
        from_locator="../../../producer/.skw/src/references/template.skw.md#Body",
    )
    expansion = expand_file(load_skillware(consumer), Path("references/copy.skw.md"))
    messages = " | ".join(f.message for f in expansion.findings)
    assert "registered dependency id" in messages


def test_unknown_dep_id_is_unresolvable(tmp_path: Path) -> None:
    consumer = _write_pkg_pair(
        tmp_path,
        dep_path="../producer",
        from_locator="@<ghost>/references/template.skw.md#Body",
    )
    expansion = expand_file(load_skillware(consumer), Path("references/copy.skw.md"))
    messages = " | ".join(f.message for f in expansion.findings)
    assert "unknown dependency id <ghost>" in messages
