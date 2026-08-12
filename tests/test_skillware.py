from __future__ import annotations

import argparse
import hashlib
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
    _cmd_skillware_check,
    _cmd_skillware_status,
)
from _skillware_helpers import (
    DEPOT_ALIAS_CHAPTER,
    MOD_COMPILED,
    _entry,
    _write_skill,
)


def test_expand_compiles_and_refreshes_copies(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    assert "\n".join(expansion.fresh_lines) + "\n" == MOD_COMPILED
    # src refresh keeps machinery but replaces stale copy bodies
    refreshed = "\n".join(expansion.src_refresh_lines)
    assert "- alpha one" in refreshed
    assert "- stale copy" not in refreshed
    assert "> $kw: --copy" in refreshed
    assert "- derived solution" in refreshed  # derived bodies never touched


def test_expand_records_dep_hashes(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    derived_deps = expansion.dep_hashes["Derived"]
    assert set(derived_deps) == {"references/lib.skw.md#Alpha", "Concept.One"}
    assert all(isinstance(value, str) for value in derived_deps.values())


def test_locator_findings(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "## A\n\n> $kw: --copy --from references/missing.skw.md#X\n\n- body\n\n> $kw. end\n"
        "\n## B\n\n> $kw: --copy --from references/lib.skw.md#Nope\n\n- body\n\n> $kw. end\n"
        "\n## C\n\n> $kw: --copy --from Concept.Missing\n\n- body\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    messages = " | ".join(finding.message for finding in expansion.findings)
    assert "missing.skw.md" in messages
    assert "Nope" in messages
    assert "Concept.Missing" in messages


def test_cycle_detection(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "a.skw.md").write_text(
        "## A\n\n> $kw: --copy --from references/b.skw.md#B\n\n- x\n\n> $kw. end\n",
        encoding="utf-8",
    )
    (src / "b.skw.md").write_text(
        "## B\n\n> $kw: --copy --from references/a.skw.md#A\n\n- x\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/a.skw.md"))
    assert any("cycle" in finding.message for finding in expansion.findings)


def test_load_skillware_requires_src(tmp_path: Path) -> None:
    with pytest.raises(SkillwareError):
        load_skillware(tmp_path / "nope")


def test_extract_mentions_from_backticked_dotted_names() -> None:
    from agentos.skillware.build import extract_mentions

    text = (
        "Uses `Index.Ontology`, `Turn.Type::Project.Index.Gate`, "
        "`file.md`, `lower.Case`, and `Single`."
    )
    assert extract_mentions(text) == {
        "Index.Ontology",
        "Turn.Type::Project.Index.Gate",
    }


def test_resolve_mentions_keeps_only_depot_resolving_names(tmp_path: Path) -> None:
    from agentos.skillware.build import resolve_mentions

    skill = _write_skill(tmp_path)
    skillware = load_skillware(skill)
    assert resolve_mentions(skillware, {"Concept.One", "Concept.Missing"}) == {
        "Concept.One"
    }


def test_dotted_name_locator_resolves_meta_aliases(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    depot_file = tmp_path / "depot" / "design" / "100-design.md"
    depot_file.write_text(DEPOT_ALIAS_CHAPTER, encoding="utf-8")
    skillware = load_skillware(skill)

    canonical = expand_file(skillware, Path("references/mod.skw.md"))
    assert not canonical.findings

    alias_lines, alias_detail = __import__(
        "agentos.skillware.build", fromlist=["_resolve_locator"]
    )._resolve_locator(
        skillware, "Concept.Alias", stack=(Path("references/mod.skw.md"),)
    )
    canonical_lines, canonical_detail = __import__(
        "agentos.skillware.build", fromlist=["_resolve_locator"]
    )._resolve_locator(skillware, "Concept.One", stack=(Path("references/mod.skw.md"),))
    collision_lines, collision_detail = __import__(
        "agentos.skillware.build", fromlist=["_resolve_locator"]
    )._resolve_locator(
        skillware, "Concept.Taken", stack=(Path("references/mod.skw.md"),)
    )

    assert (
        alias_detail is None and canonical_detail is None and collision_detail is None
    )
    assert alias_lines == canonical_lines == ["- canonical line"]
    assert collision_lines == ["- taken canonical line"]


def test_build_then_check_ok(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    report = build_skill(skill)
    assert not report.findings
    assert {(str(e.target), e.action) for e in report.entries} == {
        ("references/base.md", "built"),
        ("references/lib.md", "built"),
        ("references/mod.md", "built"),
    }
    assert (skill / "references" / "mod.md").read_text(encoding="utf-8") == MOD_COMPILED
    compiled = (skill / "references" / "mod.md").read_text(encoding="utf-8")
    assert "$kw" not in compiled
    # src refreshed: stale copy body replaced in the src file
    src_text = (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(
        encoding="utf-8"
    )
    assert "- stale copy" not in src_text

    second = build_skill(skill)
    assert all(entry.action == "unchanged" for entry in second.entries)

    check = check_skill(skill)
    assert not check.pois
    assert all(entry.status == "ok" for entry in check.entries)


def test_check_never_built_and_hand_edited(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    check = check_skill(skill)
    assert all(entry.status == "never-built" for entry in check.entries)
    assert check.pois

    build_skill(skill)
    target = skill / "references" / "mod.md"
    target.write_text(
        target.read_text(encoding="utf-8") + "\nrogue edit\n", encoding="utf-8"
    )
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "hand-edited"


def test_check_stale_build_on_src_edit(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        src.read_text(encoding="utf-8").replace(
            "Intro prose.", "Intro prose, revised."
        ),
        encoding="utf-8",
    )
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "stale-build"


def test_copy_drift_and_derived_stale_on_dep_edit(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two revised"),
        encoding="utf-8",
    )

    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert "Copied" in entry.copy_drift
    assert "Derived" in entry.derived_stale

    # rebuild repairs the copy but must NOT silently bless the stale derived body
    build_skill(skill)
    assert "- alpha two revised" in (skill / "references" / "mod.md").read_text(
        encoding="utf-8"
    )
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert not entry.copy_drift
    assert "Derived" in entry.derived_stale

    # the agent re-derives (edits the derived body in src) and rebuilds: flag clears
    mod = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    mod.write_text(
        mod.read_text(encoding="utf-8").replace(
            "- derived solution", "- derived solution v2"
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not check.pois
    assert _entry(check, "references/mod.md").derived_stale == ()


def test_dependency_sync_pois_and_hashes(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    depot = tmp_path / "depot" / "design" / "100-design.md"
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Concept.Two\n\n- concept two\n",
        encoding="utf-8",
    )
    src.write_text(
        "# mod\n\n"
        "Mentions `Concept.Two` without declaring it.\n\n"
        "> $kw: --from Concept.Missing\n\n"
        "## Copy\n\n> $kw: --copy --from Concept.One\n\n- stale\n\n> $kw. end\n",
        encoding="utf-8",
    )

    check = check_skill(skill)
    kinds = {(poi.kind, poi.key) for poi in check.pois}
    assert ("undeclared-dependency", "Concept.Two") in kinds
    # Concept.Missing is declared but does not resolve — it is dangling, not
    # unhonored (unhonored means declared-and-resolving but unmentioned).
    assert ("dangling-dependency", "Concept.Missing") in kinds
    assert not any(
        poi.kind == "unhonored-dependency" and poi.key == "Concept.Missing"
        for poi in check.pois
    )
    assert not any(
        poi.kind == "unhonored-dependency" and poi.key == "Concept.One"
        for poi in check.pois
    )

    first = next(p for p in check.pois if p.kind == "undeclared-dependency")
    second = next(
        p for p in check_skill(skill).pois if p.kind == "undeclared-dependency"
    )
    assert first.poi_hash == second.poi_hash

    src.write_text(
        src.read_text(encoding="utf-8").replace("Concept.Two", "Concept.Three"),
        encoding="utf-8",
    )
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Concept.Three\n\n- concept three\n",
        encoding="utf-8",
    )
    changed = next(
        p for p in check_skill(skill).pois if p.kind == "undeclared-dependency"
    )
    assert changed.poi_hash != first.poi_hash


def test_dependency_roles_resolve_and_citations_must_be_visible(
    tmp_path: Path,
) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "> $kw: --dev-from references/missing.skw.md\n"
        "> --cite Concept.One\n\n"
        "No visible citation.\n",
        encoding="utf-8",
    )

    check = check_skill(skill)
    assert any(
        poi.kind == "unresolvable" and "dev-from" in poi.detail for poi in check.pois
    )

    context = skill / ".skillware" / "src" / "references" / "context.skw.md"
    context.write_text("# context\n\nAll builder context.\n", encoding="utf-8")
    src.write_text(
        "# mod\n\n"
        "> $kw: --dev-from references/context.skw.md\n"
        "> --cite Concept.One\n\n"
        "No visible citation.\n",
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert any(
        poi.kind == "uncited-dependency" and poi.key == "Concept.One"
        for poi in check.pois
    )

    src.write_text(
        src.read_text(encoding="utf-8").replace(
            "No visible citation.", "Uses `Concept.One` explicitly."
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    assert not any(poi.kind == "uncited-dependency" for poi in check_skill(skill).pois)


def test_dev_from_participates_in_derived_staleness(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    context = skill / ".skillware" / "src" / "references" / "context.skw.md"
    context.write_text("# context\n\nContext v1.\n", encoding="utf-8")
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "## Derived\n\n"
        "> $kw: --derived --from Concept.One\n"
        "> --dev-from references/context.skw.md\n\n"
        "- derived solution\n\n"
        "> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(skill)
    assert not any(poi.kind == "derived-stale" for poi in check_skill(skill).pois)

    context.write_text("# context\n\nContext v2.\n", encoding="utf-8")
    assert any(
        poi.kind == "derived-stale" and poi.key == "Derived"
        for poi in check_skill(skill).pois
    )


def test_context_assembly_bypass_requires_companion_dev_from(
    tmp_path: Path,
) -> None:
    skill = _write_skill(tmp_path)
    context = skill / ".skillware" / "src" / "references" / "context.skw.md"
    context.write_text(
        "> $kw: --context-assembly --from Concept.One\n\n"
        "# Context\n\n"
        "Curates `Concept.One` for builders.\n",
        encoding="utf-8",
    )
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n> $kw: --cite Concept.One\n\nUses `Concept.One` explicitly.\n",
        encoding="utf-8",
    )
    build_skill(skill)

    bypass = [
        poi for poi in check_skill(skill).pois if poi.kind == "context-assembly-bypass"
    ]
    assert len(bypass) == 1
    assert bypass[0].key == "Concept.One"
    assert "is covered by" in bypass[0].detail
    assert "claimed by" not in bypass[0].detail
    assert "references/context.skw.md" in bypass[0].detail

    from agentos.skillware.build import bless_skill

    bless_skill(skill, bypass[0].poi_hash)
    assert not any(
        poi.kind == "context-assembly-bypass" for poi in check_skill(skill).pois
    )

    src.write_text(
        src.read_text(encoding="utf-8").replace(
            "> $kw: --cite Concept.One",
            "> $kw: --cite Concept.One\n> --dev-from references/context.skw.md",
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    assert not any(
        poi.kind == "context-assembly-bypass" for poi in check_skill(skill).pois
    )


def test_malformed_note_pois(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "## Good\n\n> $kw: #good --note [DF] a grounded note ^c20260721-2\n\nprose\n\n"
        "## No Type\n\n> $kw: #nt --note a note without a type ^c20260721-2\n\nprose\n\n"
        "## No Anchor\n\n> $kw: #na --note [CT] a note without an anchor\n\nprose\n\n"
        "## Supp No Anchor\n\n> $kw: #sna --supp own line no anchor\n\nprose\n",
        encoding="utf-8",
    )
    build_skill(skill)
    keys = {(p.kind, p.key) for p in check_skill(skill).pois}
    assert ("malformed-note", "#nt") in keys
    assert ("malformed-note", "#na") in keys
    assert ("malformed-note", "#sna") in keys
    assert ("malformed-note", "#good") not in keys


def test_alias_mentions_remain_literal_dependency_sync_pois(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    depot_file = tmp_path / "depot" / "design" / "100-design.md"
    depot_file.write_text(DEPOT_ALIAS_CHAPTER, encoding="utf-8")
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n> $kw: --from Concept.One\n\nMentions `Concept.Alias`.\n",
        encoding="utf-8",
    )

    check = check_skill(skill)
    kinds = {(poi.kind, poi.key) for poi in check.pois}
    assert ("undeclared-dependency", "Concept.Alias") in kinds
    assert ("unhonored-dependency", "Concept.One") in kinds

    first = next(p for p in check.pois if p.kind == "undeclared-dependency")
    second = next(
        p for p in check_skill(skill).pois if p.kind == "undeclared-dependency"
    )
    assert first.poi_hash == second.poi_hash

    from agentos.skillware.build import bless_skill

    bless_skill(skill, first.poi_hash)
    assert not any(
        p.kind == "undeclared-dependency" and p.key == "Concept.Alias"
        for p in check_skill(skill).pois
    )

    depot_file.write_text(
        depot_file.read_text(encoding="utf-8").replace(
            "- canonical line", "- canonical line v2"
        ),
        encoding="utf-8",
    )
    reminted = next(
        p
        for p in check_skill(skill).pois
        if p.kind == "undeclared-dependency" and p.key == "Concept.Alias"
    )
    assert reminted.poi_hash != first.poi_hash


def test_dangling_dependency_catches_unaliased_rename(tmp_path: Path) -> None:
    """RED->GREEN guard for the 591 silent-drift scenario: a declared `--from`
    whose target is renamed without an alias must break loudly."""
    skill = _write_skill(tmp_path)
    depot = tmp_path / "depot" / "design" / "100-design.md"
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Old.Name\n\n- old body\n",
        encoding="utf-8",
    )
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n> $kw: --from Old.Name\n\nUses `Old.Name` here.\n",
        encoding="utf-8",
    )

    # GREEN baseline: the declared target resolves, no dangling POI.
    assert not any(p.kind == "dangling-dependency" for p in check_skill(skill).pois)

    # RED: rename the block without leaving an alias — the declaration dangles.
    depot.write_text(
        depot.read_text(encoding="utf-8").replace("## Old.Name", "## New.Name"),
        encoding="utf-8",
    )
    dangling = [p for p in check_skill(skill).pois if p.kind == "dangling-dependency"]
    assert [p.key for p in dangling] == ["Old.Name"]
    # A dangling name is not also reported as unhonored.
    assert not any(
        p.kind == "unhonored-dependency" and p.key == "Old.Name"
        for p in check_skill(skill).pois
    )

    # GREEN again: restore the name as a meta alias — the binding resolves.
    depot.write_text(
        depot.read_text(encoding="utf-8").replace(
            "- old body", "- old body\n\n### meta\n\n- aliases: `Old.Name`"
        ),
        encoding="utf-8",
    )
    assert not any(p.kind == "dangling-dependency" for p in check_skill(skill).pois)


def test_dangling_dependency_is_blessable(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n> $kw: --from Gone.Block\n\nMentions `Gone.Block`.\n",
        encoding="utf-8",
    )
    from agentos.skillware.build import bless_skill

    poi = next(p for p in check_skill(skill).pois if p.kind == "dangling-dependency")
    assert poi.key == "Gone.Block"
    bless_skill(skill, poi.poi_hash)
    assert not any(p.kind == "dangling-dependency" for p in check_skill(skill).pois)


def test_unresolved_recipe_from_is_caught_as_unresolvable(tmp_path: Path) -> None:
    """An unresolved copy/derived --from cannot materialize, so it is caught
    upstream (and louder) as an `unresolvable` build failure — dangling-dependency
    is the depends/pointer-specific check, whose target is never materialized."""
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## D\n\n> $kw: --derived --from Missing.Source\n"
        "> --intent x\n\n- body\n\n> $kw. end\n",
        encoding="utf-8",
    )
    pois = check_skill(skill).pois
    assert any(p.kind == "unresolvable" for p in pois)
    assert not any(p.kind == "dangling-dependency" for p in pois)


def test_status_counts_constructs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n> $kw: ^frag\nf\n> $kw. end\n\n"
        "## R\n\n> $kw: #r\n\n> $kw: --when\ns\n"
        "> $kw: --then\nr\n> $kw. end\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(skill=str(skill), json=True)
    assert _cmd_skillware_status(args) == 0
    payload = json.loads(capsys.readouterr().out)
    mod = next(f for f in payload["files"] if f["src"] == "references/mod.skw.md")
    assert mod["constructs"] == {"text": 1, "router": 1, "when": 1, "then": 1}


def test_status_counts_annotated_router_constructs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^row --router-row --table ^driver --flag --x "
        "--match explicit --to X.Module\n"
        "> $kw: ^view --routing-view calls --table ^driver\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(skill=str(skill), json=True)
    assert _cmd_skillware_status(args) == 0
    payload = json.loads(capsys.readouterr().out)
    mod = next(f for f in payload["files"] if f["src"] == "references/mod.skw.md")
    assert mod["constructs"] == {
        "routing-table": 1,
        "router-row": 1,
        "routing-view": 1,
    }


def test_parse_errors_gate_semantic_checks_per_file(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    # make mod's derived stale AND break a standalone file with a parse error
    depot_file = tmp_path / "depot" / "design" / "100-design.md"
    depot_file.write_text(
        depot_file.read_text(encoding="utf-8").replace(
            "- concept line", "- concept line v2"
        ),
        encoding="utf-8",
    )
    extra = skill / ".skillware" / "src" / "references" / "extra.skw.md"
    extra.write_text(
        "# extra\n\n> $kw: --derived --from X.Y\n\nnever closed\n", encoding="utf-8"
    )

    check = check_skill(skill)
    extra_entry = _entry(check, "references/extra.md")
    assert extra_entry.status == "parse-error"
    assert extra_entry.copy_drift == () and extra_entry.derived_stale == ()
    extra_pois = [p for p in check.pois if str(p.target) == "references/extra.md"]
    assert extra_pois and all(p.kind == "parse-error" for p in extra_pois)
    assert len(check.diagnostics) == len(extra_pois)
    assert all(
        diagnostic.evidence["origin"] == "Closure.Parser"
        and diagnostic.evidence["compatibility_poi"]
        in {poi.instance_id for poi in extra_pois}
        for diagnostic in check.diagnostics
    )
    # the sibling file still checks semantically
    mod_entry = _entry(check, "references/mod.md")
    assert "Derived" in mod_entry.derived_stale
    assert any(p.kind == "derived-stale" and p.key == "Derived" for p in check.pois)
    # a parse-broken file poisons its importers as unresolvable, not silently
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8") + "\n> $kw: --derived --from X.Y\n\nopen\n",
        encoding="utf-8",
    )
    check = check_skill(skill)
    assert _entry(check, "references/lib.md").status == "parse-error"
    assert _entry(check, "references/mod.md").status == "unresolvable"


def test_poi_hash_is_stable_and_situation_bound(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"),
        encoding="utf-8",
    )
    build_skill(skill)

    first = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    second = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    assert first and [p.poi_hash for p in first] == [p.poi_hash for p in second]
    identity = (
        f"{first[0].target_path}|{first[0].kind}|{first[0].key}|"
        f"{first[0].evidence['identity_payload']}"
    )
    assert (
        first[0].poi_hash == hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    )

    # the dependency moves again: same POI kind/key, new situation, new hash
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two v2", "- alpha two v3"),
        encoding="utf-8",
    )
    build_skill(skill)
    third = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    assert third and third[0].key == first[0].key
    assert third[0].poi_hash != first[0].poi_hash


def test_cli_parse_failure_has_distinct_diagnostic_and_compatibility_poi(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    src.write_text(
        src.read_text(encoding="utf-8") + "\n> $kw: --derived --from X.Y\n\nopen\n",
        encoding="utf-8",
    )

    assert _cmd_skillware_check(argparse.Namespace(skill=str(skill), json=True)) == 1
    payload = json.loads(capsys.readouterr().out)
    parse_poi = next(
        poi for poi in payload["pois"] if poi["evidence"]["kind"] == "parse-error"
    )
    diagnostic = next(
        item for item in payload["diagnostics"] if item["code"] == "parse-error"
    )
    assert diagnostic["evidence"] == {
        "compatibility_poi": parse_poi["instance_id"],
        "origin": "Closure.Parser",
    }


def test_legacy_callout_raises_a_poi(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        src.read_text(encoding="utf-8") + "\n> [!skw]- derived\n> from: X.Y\n",
        encoding="utf-8",
    )
    check = check_skill(skill)
    assert any(p.kind == "legacy-callout" for p in check.pois)
    # fenced examples never trigger it
    src.write_text(
        src.read_text(encoding="utf-8").replace(
            "\n> [!skw]- derived\n> from: X.Y\n",
            "\n````md\n```\n> [!skw]- derived\n> from: X.Y\n````\n",
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not any(p.kind == "legacy-callout" for p in check.pois)


def test_cli_check_uses_common_grouped_renderer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"),
        encoding="utf-8",
    )
    build_skill(skill)

    args = argparse.Namespace(skill=str(skill), json=False)
    assert _cmd_skillware_check(args) == 1
    out = capsys.readouterr().out
    assert (
        sum(line == "Skillware.Linter/Derived.Stale" for line in out.splitlines()) == 1
    )
    assert out.count("Documentation: index://agentos-pkg/") == 1
    row = next(line for line in out.splitlines() if "[ADVISORY]" in line)
    assert "references/mod.md" in row
    assert any(len(token.strip("[]")) == 10 for token in row.split())


def test_bless_clears_derived_stale_without_touching_the_body(tmp_path: Path) -> None:
    from agentos.skillware.build import bless_skill

    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"),
        encoding="utf-8",
    )
    build_skill(skill)

    poi = next(p for p in check_skill(skill).pois if p.kind == "derived-stale")
    src_before = (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(
        encoding="utf-8"
    )
    target_before = (skill / "references" / "mod.md").read_text(encoding="utf-8")

    record = bless_skill(skill, poi.poi_hash)
    assert record.key == "Derived" and str(record.target) == "references/mod.md"
    assert record.deps  # old -> new dep hashes named

    # body and target untouched; flag cleared
    assert (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(
        encoding="utf-8"
    ) == src_before
    assert (skill / "references" / "mod.md").read_text(
        encoding="utf-8"
    ) == target_before
    check = check_skill(skill)
    assert not check.pois

    # the dependency moves again: a NEW POI with a new hash appears
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two v2", "- alpha two v3"),
        encoding="utf-8",
    )
    build_skill(skill)
    fresh = next(p for p in check_skill(skill).pois if p.kind == "derived-stale")
    assert fresh.poi_hash != poi.poi_hash


def test_bless_refuses_unblessable_and_unknown_pois(tmp_path: Path) -> None:
    from agentos.skillware.build import bless_skill

    skill = _write_skill(tmp_path)
    build_skill(skill)
    with pytest.raises(SkillwareError):
        bless_skill(skill, "0000000000")  # unknown hash

    src = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    src.write_text(
        src.read_text(encoding="utf-8") + "\n> $kw: --derived --from X.Y\n\nopen\n",
        encoding="utf-8",
    )
    poi = next(p for p in check_skill(skill).pois if p.kind == "parse-error")
    with pytest.raises(SkillwareError) as excinfo:
        bless_skill(skill, poi.poi_hash)
    assert "not blessable" in str(excinfo.value)


def test_cli_bless_round_trip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from agentos.skillware.commands import _cmd_skillware_bless

    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"),
        encoding="utf-8",
    )
    build_skill(skill)
    poi = next(p for p in check_skill(skill).pois if p.kind == "derived-stale")

    args = argparse.Namespace(skill=str(skill), poi=poi.poi_hash, json=True)
    assert _cmd_skillware_bless(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blessed"]["key"] == "Derived"
    assert check_skill(skill).pois == ()

    with pytest.raises(CliError):
        _cmd_skillware_bless(
            argparse.Namespace(skill=str(skill), poi="ffffffffff", json=True)
        )


def test_cli_bulk_bless_clears_kind_only_for_current_situations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from agentos.skillware.commands import _cmd_skillware_bless

    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text("# mod\n\nUses `Concept.One`.\n", encoding="utf-8")

    assert any(p.kind == "undeclared-dependency" for p in check_skill(skill).pois)
    args = argparse.Namespace(
        skill=str(skill),
        poi=None,
        kind="undeclared-dependency",
        all=True,
        json=True,
    )
    assert _cmd_skillware_bless(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["blessed"] == 1
    assert not any(p.kind == "undeclared-dependency" for p in check_skill(skill).pois)
    build_skill(skill)
    assert not any(p.kind == "undeclared-dependency" for p in check_skill(skill).pois)

    depot = tmp_path / "depot" / "design" / "100-design.md"
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Concept.Two\n\n- concept two\n",
        encoding="utf-8",
    )
    src.write_text(
        src.read_text(encoding="utf-8") + "\nAlso `Concept.Two`.\n", encoding="utf-8"
    )
    fresh = [p for p in check_skill(skill).pois if p.kind == "undeclared-dependency"]
    assert [poi.key for poi in fresh] == ["Concept.Two"]


def test_crlf_target_reads_ok(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    target = skill / "references" / "mod.md"
    # simulate a CRLF checkout of the identical content
    crlf = target.read_text(encoding="utf-8").replace("\n", "\r\n")
    target.write_bytes(crlf.encode("utf-8"))
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "ok"


def test_skw_backend_satisfies_surface_provider_protocol() -> None:
    # The skw-skills backend binds into the shared dependency-sync engine
    # through the SurfaceProvider protocol (Impl.Req 700, slice 2).
    from agentos.skillware.build import _SkwSurfaceProvider
    from agentos.skw import SurfaceProvider

    assert issubclass(_SkwSurfaceProvider, SurfaceProvider)


def test_dependency_sync_findings_are_advisory() -> None:
    # The surface-agnostic engine raises the three drift kinds and marks every
    # one advisory — drift is never a gated error in any backend.
    from agentos.skw import dependency_sync_findings

    ADVISORY = "advisory"

    findings = dependency_sync_findings(
        Path("t.md"),
        declared={"Only.Declared"},
        declared_from_depends={"Only.Declared"},
        mention_resolutions={"Some.Mention": "hash"},
        declared_resolutions={"Only.Declared": "unresolved:gone"},
    )
    assert {f.kind for f in findings} == {
        "dangling-dependency",
        "undeclared-dependency",
    }
    assert all(f.severity == ADVISORY for f in findings)
