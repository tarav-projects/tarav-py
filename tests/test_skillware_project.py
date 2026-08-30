from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.skillware.build import (
    SkillwareError,
    build_skill,
    check_skill,
    expand_file,
    load_skillware,
    resolve_build_root,
)
from tarav.skillware.commands import (
    _cmd_skillware_build,
    _cmd_skillware_check,
    _cmd_skillware_status,
    register_skillware_commands,
)
from _skillware_helpers import _write_skill


def _write_project(root: Path) -> Path:
    """A project containing one built Skillware package."""
    (root / ".skw").mkdir(parents=True)
    (root / ".skw" / "skw.json").write_text(json.dumps({}), encoding="utf-8")
    pkg_a_src = root / "packages" / "pkgA" / ".skw" / "src"
    pkg_a_src.mkdir(parents=True)
    (pkg_a_src / "mod.skw.md").write_text(
        "# mod\n\nPackage content.\n",
        encoding="utf-8",
    )
    build_skill(root / "packages" / "pkgA")  # a real package is built
    return root


def test_project_check_discovers_built_packages(tmp_path: Path) -> None:
    from tarav.skillware.build import check_project

    proj = _write_project(tmp_path)

    report = check_project(proj)
    assert report.poi_count == 0
    assert any("pkgA" in str(pkg) for pkg, _ in report.packages)


def test_project_check_honors_exclude(tmp_path: Path) -> None:
    from tarav.skillware.build import check_project, discover_packages

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
    from tarav.skillware.build import parse_skw_config

    good = tmp_path / "skw.json"
    good.write_text(
        json.dumps(
            {
                "id": "tarav-pkg",
                "projects": ["../sib"],
                "depots": ["../pkg"],
                "mystery": 1,
            }
        ),
        encoding="utf-8",
    )
    config = parse_skw_config(good)
    assert config.id == "tarav-pkg"
    assert config.projects == ("../sib",)
    assert any("mystery" in w for w in config.warnings)
    assert any("depots" in w for w in config.warnings)

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"projects": "not-a-list"}), encoding="utf-8")
    with pytest.raises(SkillwareError):
        parse_skw_config(bad)

    invalid_id = tmp_path / "invalid-id.json"
    invalid_id.write_text(json.dumps({"id": "Tarav Pkg"}), encoding="utf-8")
    with pytest.raises(SkillwareError, match="package id"):
        parse_skw_config(invalid_id)


def test_skw_config_parses_strict_edition_history_policy(tmp_path: Path) -> None:
    from tarav.skillware.build import parse_skw_config

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


def test_skw_config_parses_typed_code_surfaces(tmp_path: Path) -> None:
    from tarav.skillware.build import CodeSurfaceConfig, parse_skw_config

    config_path = tmp_path / "skw.json"
    config_path.write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {
                        "language": "python",
                        "include": ["src/**/*.py"],
                        "exclude": ["src/**/_generated.py"],
                        "allow_points": ["file", "class", "function"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert parse_skw_config(config_path).code_surfaces == (
        CodeSurfaceConfig(
            language="python",
            include=("src/**/*.py",),
            exclude=("src/**/_generated.py",),
            allow_points=("file", "class", "function"),
        ),
    )


@pytest.mark.parametrize(
    "surface",
    [
        {},
        {"language": "python"},
        {"language": "python", "include": []},
        {"language": "python", "include": "src/*.py"},
        {"language": "python", "include": ["../outside.py"]},
        {"language": "python", "include": ["src/*.py"], "exclude": "x.py"},
        {"language": "python", "include": ["src/*.py"], "unknown": True},
    ],
)
def test_skw_config_rejects_invalid_code_surface(
    tmp_path: Path,
    surface: object,
) -> None:
    from tarav.skillware.build import parse_skw_config

    config_path = tmp_path / "skw.json"
    config_path.write_text(
        json.dumps({"code_surfaces": [surface]}),
        encoding="utf-8",
    )

    with pytest.raises(SkillwareError, match="code_surfaces"):
        parse_skw_config(config_path)


def test_expand_code_surfaces_is_deterministic_and_strict(tmp_path: Path) -> None:
    from tarav.skillware.build import CodeSurfaceConfig, expand_code_surfaces

    (tmp_path / "src" / "nested").mkdir(parents=True)
    for relative in ("src/a.py", "src/nested/b.py", "src/nested/_generated.py"):
        (tmp_path / relative).write_text("x = 1\n", encoding="utf-8")

    targets = expand_code_surfaces(
        tmp_path,
        (
            CodeSurfaceConfig(
                language="python",
                include=("src/**/*.py",),
                exclude=("src/**/_generated.py",),
            ),
        ),
    )
    assert [(target.language, target.path) for target in targets] == [
        ("python", (tmp_path / "src/a.py").resolve()),
        ("python", (tmp_path / "src/nested/b.py").resolve()),
    ]

    with pytest.raises(SkillwareError, match="matched no files"):
        expand_code_surfaces(
            tmp_path,
            (
                CodeSurfaceConfig(
                    language="python",
                    include=("missing/**/*.py",),
                ),
            ),
        )


def test_expand_code_surfaces_deduplicates_one_selector_but_rejects_two_owners(
    tmp_path: Path,
) -> None:
    from tarav.skillware.build import CodeSurfaceConfig, expand_code_surfaces

    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    one = CodeSurfaceConfig(
        language="python",
        include=("src/*.py", "src/a.py"),
    )
    assert len(expand_code_surfaces(tmp_path, (one,))) == 1

    with pytest.raises(SkillwareError, match="selected more than once"):
        expand_code_surfaces(
            tmp_path,
            (
                CodeSurfaceConfig(language="python", include=("src/*.py",)),
                CodeSurfaceConfig(language="python", include=("src/a.py",)),
            ),
        )

    with pytest.raises(SkillwareError, match="unsupported.*language"):
        expand_code_surfaces(
            tmp_path,
            (
                CodeSurfaceConfig(
                    language="javascript",
                    include=("src/*.js",),
                ),
            ),
        )


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
    from tarav.skillware.build import parse_skw_config

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
    from tarav.skillware.build import (
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
    from tarav.skillware.build import find_project_root

    (tmp_path / ".tarav").mkdir()
    (tmp_path / ".tarav" / "project.json").write_text("{}", encoding="utf-8")
    deep = tmp_path / "skills" / "pkg" / ".skw"
    deep.mkdir(parents=True)
    assert find_project_root(deep) == tmp_path.resolve()
    assert find_project_root(tmp_path / "nowhere") == tmp_path.resolve()


def test_skw_is_the_only_build_home(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    loaded = load_skillware(skill)

    assert loaded.build_root == skill / ".skw"
    assert loaded.src_root == skill / ".skw" / "src"

    old_layout = tmp_path / "old-layout"
    (old_layout / ".skillware" / "src").mkdir(parents=True)
    assert resolve_build_root(old_layout) == old_layout / ".skw"


def test_skw_is_the_only_skillware_verb() -> None:
    parser = argparse.ArgumentParser(prog="tarav")
    subparsers = parser.add_subparsers(dest="command")
    register_skillware_commands(subparsers)

    args = parser.parse_args(["skw", "check", "--skill", "some/path"])
    assert args.handler is _cmd_skillware_check
    assert args.skill == "some/path"

    with pytest.raises(SystemExit):
        parser.parse_args(["skillware", "check", "--skill", "some/path"])


def test_project_bless_accepts_exact_poi_without_skill() -> None:
    parser = argparse.ArgumentParser(prog="tarav")
    subparsers = parser.add_subparsers(dest="command")
    register_skillware_commands(subparsers)

    args = parser.parse_args(["skw", "bless", "--poi", "deadbeef"])
    assert args.skill is None
    assert args.poi == "deadbeef"

    with pytest.raises(SystemExit):
        parser.parse_args(["skw", "build"])


def test_project_check_reports_configured_code_surface_domain(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / ".tarav").mkdir()
    (tmp_path / ".tarav" / "project.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".skw").mkdir()
    (tmp_path / ".skw" / "skw.json").write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {"language": "python", "include": ["src/**/*.py"]}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "mod.py").write_text(
        "# ordinary\nx = 1\n",
        encoding="utf-8",
    )
    parser = argparse.ArgumentParser(prog="tarav")
    register_skillware_commands(parser.add_subparsers(dest="command"))
    monkeypatch.chdir(tmp_path)

    args = parser.parse_args(["skw", "check", "--json"])
    assert args.handler(args) == 1
    payload = json.loads(capsys.readouterr().out)
    code = payload["domain"]["code_surfaces"]
    assert code["targets"] == [{"language": "python", "path": "src/mod.py"}]
    assert len(code["poi_ids"]) == 2
    assert payload["summary"]["code_files"] == 1

    comment = next(
        poi
        for poi in payload["pois"]
        if poi["evidence"]["kind"] == "non-skw-annotation"
    )
    bless_args = parser.parse_args(
        ["skw", "bless", "--poi", comment["instance_id"], "--json"]
    )
    assert bless_args.handler(bless_args) == 0
    capsys.readouterr()

    assert args.handler(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert [poi["evidence"]["kind"] for poi in payload["pois"]] == [
        "missing-header"
    ]


def test_check_payload_uses_skw_command_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    _cmd_skillware_build(argparse.Namespace(skill=str(skill), json=True))
    capsys.readouterr()
    _cmd_skillware_check(argparse.Namespace(skill=str(skill), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["domain"]["command"] == "tarav skw check"


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


def test_cli_build_refuses_and_reports_a_hand_edited_target(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    _cmd_skillware_build(argparse.Namespace(skill=str(skill), json=True))
    capsys.readouterr()
    target = skill / "references" / "mod.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nrogue\n", encoding="utf-8"
    )

    args = argparse.Namespace(skill=str(skill), json=True, discard_hand_edits=[])
    assert _cmd_skillware_build(args) == 1
    payload = json.loads(capsys.readouterr().out)
    assert [r["target"] for r in payload["refusals"]] == ["references/mod.md"]
    assert payload["refusals"][0]["src"] == "references/mod.skw.md"
    assert (
        payload["refusals"][0]["target_sha256"]
        != payload["refusals"][0]["lock_sha256"]
    )

    # the text form names the target, its src, and the escape
    text_args = argparse.Namespace(
        skill=str(skill), json=False, discard_hand_edits=[]
    )
    assert _cmd_skillware_build(text_args) == 1
    out = capsys.readouterr().out
    assert "references/mod.md has changes not present in its source" in out
    assert "src/references/mod.skw.md" in out
    assert "--discard-hand-edits references/mod.md" in out

    discard = argparse.Namespace(
        skill=str(skill), json=True, discard_hand_edits=["references/mod.md"]
    )
    assert _cmd_skillware_build(discard) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["refusals"] == []
    assert "rogue" not in target.read_text(encoding="utf-8")


def test_build_stamps_agents_md(tmp_path: Path) -> None:
    from tarav.skillware.build import AGENTS_MD_TEXT

    skill = _write_skill(tmp_path)
    build_skill(skill)
    agents = skill / ".skw" / "AGENTS.md"
    assert agents.is_file()
    assert agents.read_text(encoding="utf-8") == AGENTS_MD_TEXT
    assert "tarav skw build" in AGENTS_MD_TEXT
    assert "tarav-skillware" in AGENTS_MD_TEXT


def test_build_overwrites_hand_edited_agents_md(tmp_path: Path) -> None:
    from tarav.skillware.build import AGENTS_MD_TEXT

    skill = _write_skill(tmp_path)
    build_skill(skill)
    agents = skill / ".skw" / "AGENTS.md"
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
