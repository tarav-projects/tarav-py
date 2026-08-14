from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.skillware.build import (
    SkillwareError,
    bless_pois_by_kind,
    bless_skill,
    build_skill,
    check_skill,
    unlock_requirements,
)
from tarav.skillware.commands import _cmd_skillware_bless, _cmd_skillware_check
from tarav.skillware.model import parse_skw_source


def test_unlock_surface_annotation_parses_as_typed_dependency() -> None:
    source = parse_skw_source(
        "> $kw: ^bless-context --unlock-surface\n> --from .skw/unlock-tokens.json\n"
    )

    assert not source.findings
    assert len(source.dependencies) == 1
    dependency = source.dependencies[0]
    assert dependency.address == "^bless-context"
    assert dependency.froms == (".skw/unlock-tokens.json",)
    assert dependency.unlock_surface is True


def test_unlock_surface_annotation_requires_address_single_from_and_no_value() -> None:
    cases = (
        (
            "> $kw: --unlock-surface --from .skw/unlock-tokens.json\n",
            "explicit address",
        ),
        (
            "> $kw: ^context --unlock-surface\n",
            "exactly one --from",
        ),
        (
            "> $kw: ^context --unlock-surface yes --from .skw/unlock-tokens.json\n",
            "takes no value",
        ),
        (
            "> $kw: ^context --derived --unlock-surface "
            "--from .skw/unlock-tokens.json\nbody\n> $kw. end\n",
            "cannot carry a binding or router role",
        ),
    )

    for text, expected in cases:
        source = parse_skw_source(text)
        assert any(expected in finding.message for finding in source.findings)


def _write_unlock_packages(tmp_path: Path) -> tuple[Path, Path]:
    provider = tmp_path / "context-provider"
    provider_src = provider / ".skw" / "src" / "references"
    provider_src.mkdir(parents=True)
    (provider_src / "check.skw.md").write_text(
        "# Check\n\n"
        "> $kw: ^bless-context --unlock-surface\n"
        "> --from .skw/unlock-tokens.json\n\n"
        "Read the whole blessing context.\n",
        encoding="utf-8",
    )
    (provider_src / "policy.skw.md").write_text(
        "# Policy\n\n"
        "> $kw: ^policy-context --unlock-surface\n"
        "> --from .skw/unlock-tokens.json\n\n"
        "Read the whole policy context.\n",
        encoding="utf-8",
    )
    (provider / ".skw" / "unlock-tokens.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "tokens": [
                    {
                        "token": "skw-unlock:9f4c2a7d8e31",
                        "surface": "references/check.skw.md^bless-context",
                        "unlocks": ["derived-stale"],
                    },
                    {
                        "token": "skw-unlock:a1384bc95d20",
                        "surface": "references/policy.skw.md^policy-context",
                        "unlocks": ["derived-stale", "dangling-dependency"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    target = tmp_path / "poi-target"
    target_src = target / ".skw" / "src"
    target_src.mkdir(parents=True)
    (target_src / "SKILL.skw.md").write_text("# Target\n", encoding="utf-8")
    (target / ".skw" / "skw.json").write_text(
        json.dumps(
            {"unlock_registries": ["../context-provider/.skw/unlock-tokens.json"]}
        ),
        encoding="utf-8",
    )
    return provider, target


def test_registry_resolves_multiple_requirements_for_one_poi_kind(
    tmp_path: Path,
) -> None:
    provider, target = _write_unlock_packages(tmp_path)

    requirements = unlock_requirements(target, "derived-stale")

    assert [requirement.token for requirement in requirements] == [
        "skw-unlock:9f4c2a7d8e31",
        "skw-unlock:a1384bc95d20",
    ]
    assert [requirement.surface for requirement in requirements] == [
        "references/check.skw.md^bless-context",
        "references/policy.skw.md^policy-context",
    ]
    assert all(
        requirement.registry == provider / ".skw" / "unlock-tokens.json"
        for requirement in requirements
    )
    assert unlock_requirements(target, "undeclared-dependency") == ()


def test_registry_rejects_duplicate_surface(tmp_path: Path) -> None:
    provider, target = _write_unlock_packages(tmp_path)
    registry = provider / ".skw" / "unlock-tokens.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["tokens"][1]["surface"] = payload["tokens"][0]["surface"]
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SkillwareError, match="duplicate unlock surface"):
        unlock_requirements(target, "derived-stale")


def test_registry_rejects_description_field(tmp_path: Path) -> None:
    provider, target = _write_unlock_packages(tmp_path)
    registry = provider / ".skw" / "unlock-tokens.json"
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["tokens"][0]["description"] = "not part of schema v1"
    registry.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(SkillwareError, match="exactly token, surface, and unlocks"):
        unlock_requirements(target, "derived-stale")


def test_registry_requires_machine_checkable_surface_annotation(
    tmp_path: Path,
) -> None:
    provider, target = _write_unlock_packages(tmp_path)
    source = provider / ".skw" / "src" / "references" / "check.skw.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace(" --unlock-surface", ""),
        encoding="utf-8",
    )

    with pytest.raises(SkillwareError, match="not marked --unlock-surface"):
        unlock_requirements(target, "derived-stale")


def _raise_derived_stale(target: Path):
    src = target / ".skw" / "src" / "references"
    src.mkdir(parents=True, exist_ok=True)
    (src / "lib.skw.md").write_text(
        "# Library\n\n## Context\n\n- version one\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# Module\n\n"
        "## Derived\n\n"
        "> $kw: --derived --from references/lib.skw.md#Context\n\n"
        "- deliberate derived text\n\n"
        "> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(target)
    library = src / "lib.skw.md"
    library.write_text(
        library.read_text(encoding="utf-8").replace("version one", "version two"),
        encoding="utf-8",
    )
    build_skill(target)
    return next(poi for poi in check_skill(target).pois if poi.kind == "derived-stale")


def test_bless_requires_every_registered_unlock_without_mutating_lock(
    tmp_path: Path,
) -> None:
    _, target = _write_unlock_packages(tmp_path)
    poi = _raise_derived_stale(target)
    lock_path = target / ".skw" / "lock.json"
    lock_before = lock_path.read_text(encoding="utf-8")

    with pytest.raises(SkillwareError) as missing:
        bless_skill(target, poi.poi_hash)
    assert "references/check.skw.md^bless-context" in str(missing.value)
    assert "references/policy.skw.md^policy-context" in str(missing.value)
    assert lock_path.read_text(encoding="utf-8") == lock_before

    with pytest.raises(SkillwareError, match="policy-context"):
        bless_skill(
            target,
            poi.poi_hash,
            unlocks=("skw-unlock:9f4c2a7d8e31",),
        )
    assert lock_path.read_text(encoding="utf-8") == lock_before

    record = bless_skill(
        target,
        poi.poi_hash,
        unlocks=(
            "skw-unlock:9f4c2a7d8e31",
            "skw-unlock:a1384bc95d20",
        ),
    )
    assert record.key == "Derived"
    assert not any(item.kind == "derived-stale" for item in check_skill(target).pois)


def test_bulk_bless_uses_the_same_unlock_gate(tmp_path: Path) -> None:
    _, target = _write_unlock_packages(tmp_path)
    _raise_derived_stale(target)

    with pytest.raises(SkillwareError, match="requires unlock token"):
        bless_pois_by_kind(target, "derived-stale")

    blessed = bless_pois_by_kind(
        target,
        "derived-stale",
        unlocks=(
            "skw-unlock:9f4c2a7d8e31",
            "skw-unlock:a1384bc95d20",
        ),
    )
    assert len(blessed) == 1


def test_cli_check_reports_context_without_disclosing_tokens(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, target = _write_unlock_packages(tmp_path)
    _raise_derived_stale(target)

    exit_code = _cmd_skillware_check(
        argparse.Namespace(
            skill=str(target),
            json=True,
            list_checks=False,
            check=(),
            skip=(),
        )
    )
    payload = json.loads(capsys.readouterr().out)
    poi = next(
        item for item in payload["pois"] if item["evidence"]["kind"] == "derived-stale"
    )

    assert exit_code == 1
    assert payload["domain"]["unlock_requirements"]["derived-stale"] == [
        {
            "surface": "references/check.skw.md^bless-context",
            "registry": str(
                (
                    tmp_path / "context-provider" / ".skw" / "unlock-tokens.json"
                ).resolve()
            ),
        },
        {
            "surface": "references/policy.skw.md^policy-context",
            "registry": str(
                (
                    tmp_path / "context-provider" / ".skw" / "unlock-tokens.json"
                ).resolve()
            ),
        },
    ]
    assert poi["instance_id"]
    assert "skw-unlock:" not in json.dumps(payload)


def test_cli_bless_accepts_repeatable_unlock_receipts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, target = _write_unlock_packages(tmp_path)
    poi = _raise_derived_stale(target)

    with pytest.raises(CliError, match="requires unlock token"):
        _cmd_skillware_bless(
            argparse.Namespace(
                skill=str(target),
                poi=poi.poi_hash,
                kind=None,
                all=False,
                unlock=[],
                json=True,
            )
        )

    assert (
        _cmd_skillware_bless(
            argparse.Namespace(
                skill=str(target),
                poi=poi.poi_hash,
                kind=None,
                all=False,
                unlock=[
                    "skw-unlock:9f4c2a7d8e31",
                    "skw-unlock:a1384bc95d20",
                ],
                json=True,
            )
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["blessed"]["key"] == "Derived"


def test_cli_bulk_bless_forwards_unlock_receipts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, target = _write_unlock_packages(tmp_path)
    _raise_derived_stale(target)

    assert (
        _cmd_skillware_bless(
            argparse.Namespace(
                skill=str(target),
                poi=None,
                kind="derived-stale",
                all=True,
                unlock=[
                    "skw-unlock:9f4c2a7d8e31",
                    "skw-unlock:a1384bc95d20",
                ],
                json=True,
            )
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["blessed"] == 1
