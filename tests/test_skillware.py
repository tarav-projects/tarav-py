# $kw: ^test-skillware --supp boundary coverage for dependency roles and whole-file context assemblies ^c20260725-27u
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
from agentos.skillware.model import parse_skw_source

SRC = """# agentos-index2 --ground

Intro prose.

## Copied

> $kw: --copy --from references/lib.skw.md#Alpha

- copied body line

> $kw. end

## Derived

> $kw: --derived --from references/lib.skw.md#Alpha
> --from Concept.One
> --intent reshape alpha for
> --cont this consumer

- derived body

> $kw. end

## Mixed

> $kw: --derived --from Concept.One --intent short

- derived part

> $kw. end

Hand tail prose.

## Hand

Plain hand section.
"""


def test_parse_recipes_fields_and_spans() -> None:
    source = parse_skw_source(SRC)
    assert not source.findings
    assert [recipe.verb for recipe in source.recipes] == ["copy", "derived", "derived"]

    copy = source.recipes[0]
    assert copy.heading == "Copied"
    assert copy.froms == ("references/lib.skw.md#Alpha",)
    assert copy.body_text() == "- copied body line"

    derived = source.recipes[1]
    assert derived.froms == ("references/lib.skw.md#Alpha", "Concept.One")
    assert derived.intent == "reshape alpha for this consumer"
    assert derived.body_text() == "- derived body"

    mixed = source.recipes[2]
    assert mixed.body_text() == "- derived part"


def test_parse_hand_sections_carry_no_recipe() -> None:
    source = parse_skw_source(SRC)
    assert all(recipe.heading != "Hand" for recipe in source.recipes)


def test_parse_findings() -> None:
    unknown_flag = parse_skw_source("## A\n\n> $kw: #a --derived\n> --transmute x\n> --from X\n\n- b\n\n> $kw. end\n")
    assert any("unknown flag: --transmute" in f.message for f in unknown_flag.findings)

    missing_from = parse_skw_source("## A\n\n> $kw: --copy\n\n- body\n\n> $kw. end\n")
    assert any("from" in finding.message for finding in missing_from.findings)

    legacy_end = parse_skw_source("## A\n\n> $kw: #a --derived --from X\n\n- b\n\n> $kw. end-derived\n")
    assert any("bare 'end'" in finding.message for finding in legacy_end.findings)

    orphan_end = parse_skw_source("## A\n\nprose\n\n> $kw. end\n")
    assert any("without an open content block" in f.message for f in orphan_end.findings)


# --- v3 grammar: sigil pair, flags, belonging lines ---------------------------

def test_flag_value_may_contain_spaces() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --copy --from references/lib.skw.md#Construct Grammar\n\n- b\n\n> $kw. end\n"
    )
    assert not source.findings
    assert source.recipes[0].froms == ("references/lib.skw.md#Construct Grammar",)


def test_inline_and_belonging_flags_are_equivalent() -> None:
    inline = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y --intent one rule\n\n- b\n\n> $kw. end\n"
    )
    split = parse_skw_source(
        "## A\n\n> $kw: --derived\n> --from X.Y\n> --intent one rule\n\n- b\n\n> $kw. end\n"
    )
    assert not inline.findings and not split.findings
    for source in (inline, split):
        assert source.recipes[0].froms == ("X.Y",)
        assert source.recipes[0].intent == "one rule"


def test_stray_belonging_line_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n\nbody prose\n\n> --intent too late\n\n> $kw. end\n"
    )
    assert any("stray" in f.message for f in source.findings)


def test_unknown_flag_in_flag_position_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --derived\n> --wat nope\n> --from X.Y\n\n- b\n\n> $kw. end\n"
    )
    assert any("unknown flag: --wat" in f.message for f in source.findings)


def test_unregistered_dashes_mid_value_are_prose() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n"
        "> --intent restate the levels for the --ground module\n"
        "> --cont as the drafting checklist --edit enforces\n"
        "\n- b\n\n> $kw. end\n"
    )
    assert not source.findings
    assert source.recipes[0].intent == (
        "restate the levels for the --ground module as the drafting checklist --edit enforces"
    )


def test_flagless_block_is_a_content_span() -> None:
    # v2 has no command word: a flag-less block is a content span that owns its
    # `end`. A nameless one is legal; an addressed one carries its address.
    nameless = parse_skw_source("## A\n\n> $kw: \nliteral body\n> $kw. end\n")
    assert not nameless.findings
    assert nameless.constructs[0].command == "text"
    assert "literal body" in "\n".join(nameless.constructs[0].body)


def test_labeled_span_carries_its_address() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: ^frag\nlabeled literal fragment\n> $kw. end\n"
    )
    assert not source.findings
    construct = source.constructs[0]
    assert (construct.command, construct.label, construct.address) == ("text", "frag", "^frag")
    assert "labeled literal fragment" in "\n".join(construct.body)


def test_legacy_callout_is_plain_text_to_the_parser() -> None:
    source = parse_skw_source(
        "## A\n\n> [!skw]- derived\n> from: X.Y\n\n- body\n\n> [!skw]- end-derived\n"
    )
    assert source.recipes == ()
    assert source.constructs == ()
    assert source.findings == ()
    assert source.machinery_spans == ()


def test_to_flag_is_reserved_and_inert() -> None:
    # `--to` is parsed and preserved but drives no behavior yet
    source = parse_skw_source(
        "## A\n\n> $kw: #x --to references/lang.md\nbody\n> $kw. end\n"
    )
    assert not source.findings
    assert source.constructs[0].address == "#x"


def test_note_and_supp_are_parsed_typed_and_anchored() -> None:
    source = parse_skw_source(
        "## A\n\n"
        "> $kw: #register_anchor --note [DF] mints an anchor at a turn ^c20260721-2\n"
        "> --supp split dangling out of unhonored ^c20260721-3\n\n"
        "some surface prose\n"
    )
    assert not source.findings
    assert [(n.flag, n.type, n.text, n.anchor) for n in source.notes] == [
        ("note", "DF", "mints an anchor at a turn", "^c20260721-2"),
        ("supp", None, "split dangling out of unhonored", "^c20260721-3"),
    ]
    # the note block attaches by address and self-closes; prose stays surface
    assert source.constructs[0].address == "#register_anchor"


def test_cont_continues_previous_flag_and_orphan_is_a_finding() -> None:
    cont = parse_skw_source(
        "## A\n\n> $kw: #d --derived --from X\n"
        "> --intent reshape the alpha\n> --cont for this consumer\n\n- b\n\n> $kw. end\n"
    )
    assert not cont.findings
    assert cont.recipes[0].intent == "reshape the alpha for this consumer"

    orphan = parse_skw_source("## A\n\n> $kw: #d --cont nothing before me\n\nprose\n")
    assert any("orphan --cont" in f.message for f in orphan.findings)


def test_depends_is_void_and_records_froms() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --from Concept.A --from Concept.B\n\nplain body\n"
    )
    assert not source.findings
    assert [dependency.froms for dependency in source.dependencies] == [
        ("Concept.A", "Concept.B")
    ]
    assert source.recipes == ()


def test_dependency_self_closes_and_following_text_is_surface() -> None:
    # a declaration-only `--from` block owns no `end`; following native text is
    # surface, not the block's body, and it is no error.
    source = parse_skw_source(
        "## A\n\n> $kw: --from Concept.A\n\nplain surface prose that is not body.\n"
    )
    assert not source.findings
    assert [dep.froms for dep in source.dependencies] == [("Concept.A",)]
    assert source.constructs == ()


def test_parse_dependency_roles_and_context_assembly() -> None:
    source = parse_skw_source(
        "> $kw: --context-assembly\n"
        "> --from Concept.One\n"
        "> --from references/context.md#Rules\n\n"
        "# Capture Context\n\n"
        "Curated context.\n\n"
        "> $kw: --from Concept.Two\n"
        "> --dev-from references/capture-context.skw.md\n"
        "> --cite Concept.Three\n"
    )

    assert not source.findings
    assembly = source.dependencies[0]
    assert assembly.context_assembly is True
    assert assembly.froms == ("Concept.One", "references/context.md#Rules")

    dependency = source.dependencies[1]
    assert dependency.froms == ("Concept.Two",)
    assert dependency.dev_froms == (
        "references/capture-context.skw.md",
    )
    assert dependency.cites == ("Concept.Three",)


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ("--context-assembly", "requires at least one --from"),
        ("--context-assembly --from Concept.One", "must be declared at the file point"),
    ],
)
def test_context_assembly_requires_identity_and_sources(
    declaration: str, message: str
) -> None:
    prefix = "prose before the declaration\n\n" if "--from" in declaration else ""
    source = parse_skw_source(f"{prefix}> $kw: {declaration}\n")
    assert any(message in finding.message for finding in source.findings)


# --- S2: locators + expansion + compile -------------------------------------

BASE = """# base

## Root

- root line
"""

LIB = """# lib

## Alpha

- alpha one
- alpha two

## Beta

> $kw: --copy --from references/base.skw.md#Root

- stale beta copy

> $kw. end
"""

MOD = """# mod

Intro prose.

## Copied

> $kw: --copy --from references/lib.skw.md#Alpha

- stale copy

> $kw. end

## Chained

> $kw: --copy --from references/lib.skw.md#Beta

- stale chain

> $kw. end

## Derived

> $kw: --derived --from references/lib.skw.md#Alpha
> --from Concept.One
> --intent reshape alpha for this consumer

- derived solution

> $kw. end

Hand tail.
"""

DEPOT_CHAPTER = """> router

****

## Concept.One

- concept line
****
"""

DEPOT_ALIAS_CHAPTER = """> router

****

## Concept.One

- canonical line

### meta

- aliases: `Concept.Alias`, `Concept.Taken`
****

## Concept.Taken

- taken canonical line
****
"""

MOD_COMPILED = """# mod

Intro prose.

## Copied

- alpha one
- alpha two

## Chained

- root line

## Derived

- derived solution

Hand tail.
"""


def _write_skill(root: Path) -> Path:
    skill = root / "skill"
    src = skill / ".skillware" / "src" / "references"
    src.mkdir(parents=True)
    (src / "base.skw.md").write_text(BASE, encoding="utf-8")
    (src / "lib.skw.md").write_text(LIB, encoding="utf-8")
    (src / "mod.skw.md").write_text(MOD, encoding="utf-8")
    (skill / ".skillware" / "skillware.json").write_text(
        json.dumps({"depots": ["../depot"]}), encoding="utf-8"
    )
    (skill / "references").mkdir()
    (skill / "references" / "hand.md").write_text("# hand\n\nhand-owned\n", encoding="utf-8")
    depot = root / "depot"
    (depot / "design").mkdir(parents=True)
    (depot / "000-INDEX.md").write_text("- `design/100-design.md` — Concept.One\n", encoding="utf-8")
    (depot / "design" / "100-design.md").write_text(DEPOT_CHAPTER, encoding="utf-8")
    return skill


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
    (src / "a.skw.md").write_text("## A\n\n> $kw: --copy --from references/b.skw.md#B\n\n- x\n\n> $kw. end\n", encoding="utf-8")
    (src / "b.skw.md").write_text("## B\n\n> $kw: --copy --from references/a.skw.md#A\n\n- x\n\n> $kw. end\n", encoding="utf-8")
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
    )._resolve_locator(skillware, "Concept.Alias", stack=(Path("references/mod.skw.md"),))
    canonical_lines, canonical_detail = __import__(
        "agentos.skillware.build", fromlist=["_resolve_locator"]
    )._resolve_locator(skillware, "Concept.One", stack=(Path("references/mod.skw.md"),))
    collision_lines, collision_detail = __import__(
        "agentos.skillware.build", fromlist=["_resolve_locator"]
    )._resolve_locator(skillware, "Concept.Taken", stack=(Path("references/mod.skw.md"),))

    assert alias_detail is None and canonical_detail is None and collision_detail is None
    assert alias_lines == canonical_lines == ["- canonical line"]
    assert collision_lines == ["- taken canonical line"]


# --- S3: build + lock + check ------------------------------------------------

def _entry(report, target: str):
    return next(entry for entry in report.entries if str(entry.target) == target)


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
    src_text = (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(encoding="utf-8")
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
    target.write_text(target.read_text(encoding="utf-8") + "\nrogue edit\n", encoding="utf-8")
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "hand-edited"


def test_check_stale_build_on_src_edit(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(src.read_text(encoding="utf-8").replace("Intro prose.", "Intro prose, revised."), encoding="utf-8")
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "stale-build"


def test_copy_drift_and_derived_stale_on_dep_edit(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two revised"), encoding="utf-8")

    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert "Copied" in entry.copy_drift
    assert "Derived" in entry.derived_stale

    # rebuild repairs the copy but must NOT silently bless the stale derived body
    build_skill(skill)
    assert "- alpha two revised" in (skill / "references" / "mod.md").read_text(encoding="utf-8")
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert not entry.copy_drift
    assert "Derived" in entry.derived_stale

    # the agent re-derives (edits the derived body in src) and rebuilds: flag clears
    mod = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    mod.write_text(mod.read_text(encoding="utf-8").replace("- derived solution", "- derived solution v2"), encoding="utf-8")
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
    second = next(p for p in check_skill(skill).pois if p.kind == "undeclared-dependency")
    assert first.poi_hash == second.poi_hash

    src.write_text(src.read_text(encoding="utf-8").replace("Concept.Two", "Concept.Three"), encoding="utf-8")
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Concept.Three\n\n- concept three\n",
        encoding="utf-8",
    )
    changed = next(p for p in check_skill(skill).pois if p.kind == "undeclared-dependency")
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
        poi.kind == "unresolvable" and "dev-from" in poi.detail
        for poi in check.pois
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
    assert not any(
        poi.kind == "uncited-dependency" for poi in check_skill(skill).pois
    )


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
        "# mod\n\n"
        "> $kw: --cite Concept.One\n\n"
        "Uses `Concept.One` explicitly.\n",
        encoding="utf-8",
    )
    build_skill(skill)

    bypass = [
        poi
        for poi in check_skill(skill).pois
        if poi.kind == "context-assembly-bypass"
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
            "> $kw: --cite Concept.One\n"
            "> --dev-from references/context.skw.md",
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
    second = next(p for p in check_skill(skill).pois if p.kind == "undeclared-dependency")
    assert first.poi_hash == second.poi_hash

    from agentos.skillware.build import bless_skill

    bless_skill(skill, first.poi_hash)
    assert not any(
        p.kind == "undeclared-dependency" and p.key == "Concept.Alias"
        for p in check_skill(skill).pois
    )

    depot_file.write_text(
        depot_file.read_text(encoding="utf-8").replace("- canonical line", "- canonical line v2"),
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
        depot_chapter.read_text(encoding="utf-8").replace("## Shared.Block", "## Renamed.Block"),
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


# --- S4: CLI -------------------------------------------------------------------

def test_skw_config_parse_warns_unknown_keys_and_rejects_bad_types(tmp_path: Path) -> None:
    from agentos.skillware.build import SkillwareError, parse_skw_config

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
    from agentos.skillware.build import SkillwareError, parse_skw_config

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
        SkillwareError,
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
    (sib / ".skw" / "skw.json").write_text(json.dumps({"depots": ["depot"]}), encoding="utf-8")

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


def test_check_payload_uses_skw_command_name(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_skill(tmp_path)
    _cmd_skillware_build(argparse.Namespace(skill=str(skill), json=True))
    capsys.readouterr()
    _cmd_skillware_check(argparse.Namespace(skill=str(skill), json=True))
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "agentos skw check"



def test_cli_build_check_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_skill(tmp_path)
    args = argparse.Namespace(skill=str(skill), json=True)

    assert _cmd_skillware_build(args) == 0
    build_payload = json.loads(capsys.readouterr().out)
    assert {entry["action"] for entry in build_payload["entries"]} == {"built"}

    assert _cmd_skillware_check(args) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["summary"]["pois"] == 0

    target = skill / "references" / "mod.md"
    target.write_text(target.read_text(encoding="utf-8") + "\nrogue\n", encoding="utf-8")
    assert _cmd_skillware_check(args) == 1
    check_payload = json.loads(capsys.readouterr().out)
    statuses = {entry["target"]: entry["status"] for entry in check_payload["entries"]}
    assert statuses["references/mod.md"] == "hand-edited"

    assert _cmd_skillware_status(args) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["lock_present"] is True
    mod = next(f for f in status_payload["files"] if f["src"] == "references/mod.skw.md")
    assert mod["recipes"] == {"copy": 2, "derived": 1}

    with pytest.raises(CliError):
        _cmd_skillware_build(argparse.Namespace(skill=str(tmp_path / "nope"), json=True))


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


def test_fenced_machinery_is_inert() -> None:
    source = parse_skw_source(
        "# Spec\n"
        "\n"
        "## Example\n"
        "\n"
        "```md\n"
        "## Fenced Heading\n"
        "\n"
        "> $kw: --derived --from Some.Block\n"
        "> --intent fenced example, not a real recipe\n"
        "\n"
        "- example body\n"
        "\n"
        "> $kw. end\n"
        "```\n"
        "\n"
        "hand tail after the fence\n"
    )
    assert source.recipes == ()
    assert source.findings == ()
    assert source.machinery_spans == ()


# --- strict construct + structural commands --------------------------------

def test_bare_end_closes_and_legacy_end_is_a_finding() -> None:
    # v2 closes every content block with a bare `$kw. end`
    ok = parse_skw_source("## A\n\n> $kw: --derived --from X.Y\n\n- body\n\n> $kw. end\n")
    assert not ok.findings
    assert [r.verb for r in ok.recipes] == ["derived"]

    # a legacy `end-<command>` closer is a clear finding directing to migration
    legacy = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n\n- body\n\n> $kw. end-derived\n"
    )
    assert any("bare 'end'" in f.message for f in legacy.findings)

    # a router closes with one bare end; its rows peer-close
    router = parse_skw_source(
        "## R\n\n> $kw: #r\n> $kw: --when\nsituation\n"
        "> $kw: --then\nresponse\n> $kw. end\n"
    )
    assert not router.findings
    assert [c.command for c in router.constructs] == ["when", "then", "router"]


def test_open_construct_at_heading_and_eof() -> None:
    at_heading = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n\n- body\n\n## B\n\nprose\n"
    )
    assert any("left open at heading" in f.message for f in at_heading.findings)

    at_eof = parse_skw_source("## A\n\n> $kw: --derived --from X.Y\n\n- body\n")
    assert any("left open at EOF" in f.message for f in at_eof.findings)


def test_position_free_and_text_primitive() -> None:
    source = parse_skw_source(
        "## A\n\nhand prose first.\n\n"
        "> $kw: --derived --from X.Y --intent mid-section derivation\n\n- body\n\n> $kw. end\n\n"
        "more hand prose.\n\n"
        "> $kw: text\n\ntagged literal span\n\n> $kw. end\n"
    )
    assert not source.findings
    assert [r.verb for r in source.recipes] == ["derived"]
    assert [c.command for c in source.constructs] == ["text"]
    assert "tagged literal span" in "\n".join(source.constructs[0].body)


def test_nesting_inside_primitive_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n\n"
        "> $kw: text\nnested\n> $kw. end\n\n- body\n\n> $kw. end\n"
    )
    assert any("may not nest inside" in f.message for f in source.findings)


def test_router_structural_checks() -> None:
    outside = parse_skw_source("## A\n\n> $kw: --when\ns\n")
    assert any("outside a router" in f.message for f in outside.findings)

    unpaired = parse_skw_source(
        "## R\n\n> $kw: #r\n\n> $kw: --when\ns\n\n> $kw. end\n"
    )
    assert any("has no 'then'" in f.message for f in unpaired.findings)

    then_first = parse_skw_source(
        "## R\n\n> $kw: #r\n\n> $kw: --then\nr\n\n> $kw. end\n"
    )
    assert any("alternate when/then" in f.message for f in then_first.findings)


def test_router_compiles_to_pure_prose(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Router Table\n\n"
        "> $kw: #r\n\n"
        "> $kw: --when\nWhen the caller wants alpha context.\n\nSecond paragraph of the key.\n\n"
        "> $kw: --then\nLoad `references/lib.md`.\n\n"
        "> $kw. end\n\nHand tail.\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    compiled = "\n".join(expansion.fresh_lines)
    assert "$kw" not in compiled
    assert "When the caller wants alpha context." in compiled
    assert "Second paragraph of the key." in compiled
    assert "Load `references/lib.md`." in compiled
    assert "Hand tail." in compiled


def test_two_derived_under_one_heading_key_distinctly(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Pair\n\n"
        "> $kw: --derived --from references/lib.skw.md#Alpha --intent first\n\n- one\n\n> $kw. end\n\n"
        "> $kw: --derived --from Concept.One --intent second\n\n- two\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert set(expansion.dep_hashes) == {"Pair", "Pair@1"}

    build_skill(skill)
    check = check_skill(skill)
    assert not check.pois

    # editing the second recipe's dep flags only Pair@1
    depot_file = tmp_path / "depot" / "design" / "100-design.md"
    depot_file.write_text(
        depot_file.read_text(encoding="utf-8").replace("- concept line", "- concept line v2"),
        encoding="utf-8",
    )
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert entry.derived_stale == ("Pair@1",)


# --- span labels ---------------------------------------------------------------

def test_labeled_text_and_labeled_derived() -> None:
    source = parse_skw_source(
        "## A\n\n"
        "> $kw: ^frag-1\nlabeled literal fragment\n> $kw. end\n\n"
        "> $kw: ^model --derived --from X.Y --intent i\n\n- body\n\n> $kw. end\n"
    )
    assert not source.findings
    text = source.constructs[0]
    assert (text.command, text.label) == ("text", "frag-1")
    assert "labeled literal fragment" in "\n".join(text.body)
    assert source.recipes[0].label == "model"


def test_bare_end_closes_top_and_duplicate_address() -> None:
    # a bare `end` closes the innermost open block — no closer-label matching
    ok = parse_skw_source("## A\n\n> $kw: ^one\nbody\n> $kw. end\n")
    assert not ok.findings

    dup = parse_skw_source(
        "## A\n\n> $kw: ^x\na\n> $kw. end\n\n> $kw: ^x\nb\n> $kw. end\n"
    )
    assert any("duplicate address" in f.message for f in dup.findings)

    mixed = parse_skw_source(
        "## R\n\n> $kw: ^table\n\n"
        "> $kw: --when\ns\n"
        "> $kw: --then\nr\n"
        "> $kw. end\n"
    )
    assert not mixed.findings


def test_labels_never_reach_compiled_output(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## A\n\n> $kw: ^frag\nfragment prose\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    compiled = "\n".join(expansion.fresh_lines)
    assert "frag" not in compiled.replace("fragment prose", "")
    assert "fragment prose" in compiled


def test_label_locators_resolve(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Alpha\n\nintro prose around the span.\n\n"
        "> $kw: ^alpha-core\n- alpha core one\n- alpha core two\n> $kw. end\n\n"
        "trailing prose outside the span.\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n"
        "> $kw: ^local-frag\nlocal fragment\n> $kw. end\n\n"
        "## Copied\n\n> $kw: --copy --from references/lib.skw.md^alpha-core\n\n- stale\n\n> $kw. end\n\n"
        "## Derived\n\n> $kw: --derived --from ^local-frag --intent local digest\n\n- solution\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    refreshed = "\n".join(expansion.src_refresh_lines)
    assert "- alpha core one" in refreshed
    assert "- stale" not in refreshed
    assert set(expansion.dep_hashes["Derived"]) == {"^local-frag"}

    missing = (src / "mod.skw.md").read_text(encoding="utf-8").replace("^alpha-core", "^nope")
    (src / "mod.skw.md").write_text(missing, encoding="utf-8")
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert any("nope" in f.message for f in expansion.findings)


def test_label_spans_hash_fine_grained(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Alpha\n\nprose outside.\n\n"
        "> $kw: ^core\n- core line\n> $kw. end\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n## Derived\n\n> $kw: ^consumer --derived --from references/lib.skw.md^core --intent i\n\n- solution\n\n> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not check.pois

    # edit OUTSIDE the labeled span: no drift
    lib = src / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("prose outside.", "prose outside, edited."), encoding="utf-8")
    build_skill(skill)
    check = check_skill(skill)
    assert not check.pois

    # edit INSIDE the span: derived-stale, keyed by the consumer's label
    lib.write_text(lib.read_text(encoding="utf-8").replace("- core line", "- core line v2"), encoding="utf-8")
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert entry.derived_stale == ("^consumer",)


def test_region_body_is_fence_aware(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Spec\n\nintro line.\n\n"
        "```md\n## Fenced Heading\nfenced content\n```\n\n"
        "bullet after the example.\n\n## Next\n\nother.\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n## Copied\n\n> $kw: --copy --from references/lib.skw.md#Spec\n\n- stale\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    refreshed = "\n".join(expansion.src_refresh_lines)
    assert "bullet after the example." in refreshed
    assert "fenced content" in refreshed
    assert "other." not in refreshed


# --- review fixes: lock continuity + adjacent blockquotes -----------------------

def test_ordinal_shift_does_not_bless_stale_derived(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Pair\n\n"
        "> $kw: --derived --from references/lib.skw.md#Alpha --intent i\n\n- solution\n\n> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha one", "- alpha one v2"), encoding="utf-8")
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").derived_stale == ("Pair",)

    # insert a NEW derived above the stale one under the same heading; rebuild
    src.write_text(
        "# mod\n\n## Pair\n\n"
        "> $kw: --derived --from Concept.One --intent new first\n\n- new solution\n\n> $kw. end\n\n"
        "> $kw: --derived --from references/lib.skw.md#Alpha --intent i\n\n- solution\n\n> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    # the old recipe now keys Pair@1 — its staleness must survive the key shift
    assert _entry(check, "references/mod.md").derived_stale == ("Pair@1",)


def test_adjacent_blockquotes_are_body_not_args() -> None:
    source = parse_skw_source(
        "## A\n\n"
        "> $kw: ^frag\n"
        "> a markdown quote that is body content\n"
        "more body\n"
        "> $kw. end\n"
        "> a prose quote right after the end line\n"
    )
    assert not source.findings
    body = "\n".join(source.constructs[0].body)
    assert "a markdown quote that is body content" in body
    # the end line consumes only its own line
    assert (5, 6) in source.machinery_spans


def test_quote_after_end_survives_compilation(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## A\n\n"
        "> $kw: ^frag\nbody line\n> $kw. end\n"
        "> quoted prose after the construct\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    compiled = "\n".join(expansion.fresh_lines)
    assert "> quoted prose after the construct" in compiled
    assert "body line" in compiled


# --- review cleanup pass --------------------------------------------------------

def test_copy_with_multiple_froms_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --copy --from a.md#X --from b.md#Y\n\n- body\n\n> $kw. end\n"
    )
    assert any("copy takes exactly one" in f.message for f in source.findings)


def test_labeled_span_resolves_nested_copies_fresh(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Alpha\n\n- alpha one\n",
        encoding="utf-8",
    )
    (src / "frag.skw.md").write_text(
        "# frag\n\n## Frag\n\n> $kw: ^frag\nspan prose.\n\n"
        "> $kw: --copy --from references/lib.skw.md#Alpha\n\n- stale inner copy\n\n> $kw. end\n"
        "> $kw. end\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n## Uses\n\n> $kw: --copy --from references/frag.skw.md^frag\n\n- stale\n\n> $kw. end\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    refreshed = "\n".join(expansion.src_refresh_lines)
    assert "- alpha one" in refreshed          # fresh, not the stale inner body
    assert "- stale inner copy" not in refreshed


def test_force_closed_router_still_checks_rows() -> None:
    source = parse_skw_source(
        "## R\n\n> $kw: #r\n\n> $kw: --when\ns\n\n## Next\n\nprose\n"
    )
    assert any("left open" in f.message for f in source.findings)
    assert any("has no 'then'" in f.message for f in source.findings)


def test_unclosed_fence_is_a_finding() -> None:
    source = parse_skw_source("## A\n\nprose\n\n```md\nnever closed\n")
    assert any("unclosed code fence" in f.message for f in source.findings)


def test_status_counts_constructs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
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


# --- Poi.Linter: gating, identity, output; Poi.Bless -----------------------------

def test_parse_errors_gate_semantic_checks_per_file(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    # make mod's derived stale AND break a standalone file with a parse error
    depot_file = tmp_path / "depot" / "design" / "100-design.md"
    depot_file.write_text(
        depot_file.read_text(encoding="utf-8").replace("- concept line", "- concept line v2"),
        encoding="utf-8",
    )
    extra = skill / ".skillware" / "src" / "references" / "extra.skw.md"
    extra.write_text("# extra\n\n> $kw: --derived --from X.Y\n\nnever closed\n", encoding="utf-8")

    check = check_skill(skill)
    extra_entry = _entry(check, "references/extra.md")
    assert extra_entry.status == "parse-error"
    assert extra_entry.copy_drift == () and extra_entry.derived_stale == ()
    extra_pois = [p for p in check.pois if str(p.target) == "references/extra.md"]
    assert extra_pois and all(p.kind == "parse-error" for p in extra_pois)
    # the sibling file still checks semantically
    mod_entry = _entry(check, "references/mod.md")
    assert "Derived" in mod_entry.derived_stale
    assert any(
        p.kind == "derived-stale" and p.key == "Derived" for p in check.pois
    )
    # a parse-broken file poisons its importers as unresolvable, not silently
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8") + "\n> $kw: --derived --from X.Y\n\nopen\n", encoding="utf-8")
    check = check_skill(skill)
    assert _entry(check, "references/lib.md").status == "parse-error"
    assert _entry(check, "references/mod.md").status == "unresolvable"


def test_poi_hash_is_stable_and_situation_bound(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"), encoding="utf-8")
    build_skill(skill)

    first = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    second = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    assert first and [p.poi_hash for p in first] == [p.poi_hash for p in second]

    # the dependency moves again: same POI kind/key, new situation, new hash
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two v2", "- alpha two v3"), encoding="utf-8")
    build_skill(skill)
    third = [p for p in check_skill(skill).pois if p.kind == "derived-stale"]
    assert third and third[0].key == first[0].key
    assert third[0].poi_hash != first[0].poi_hash


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
            "\n```md\n> [!skw]- derived\n> from: X.Y\n```\n",
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not any(p.kind == "legacy-callout" for p in check.pois)


def test_cli_check_prints_legend_and_bare_rows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"), encoding="utf-8")
    build_skill(skill)

    args = argparse.Namespace(skill=str(skill), json=False)
    assert _cmd_skillware_check(args) == 1
    out = capsys.readouterr().out
    # legend: once per present kind, with the prescribed response
    assert out.count("derived-stale —") == 1
    assert "bless" in out
    # bare row: kind, target, key, hash
    row = next(line for line in out.splitlines() if line.startswith("- [derived-stale]"))
    assert "references/mod.md" in row and "Derived" in row
    assert any(len(tok.strip("()")) == 10 for tok in row.split())


def test_bless_clears_derived_stale_without_touching_the_body(tmp_path: Path) -> None:
    from agentos.skillware.build import bless_skill

    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"), encoding="utf-8")
    build_skill(skill)

    poi = next(p for p in check_skill(skill).pois if p.kind == "derived-stale")
    src_before = (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(encoding="utf-8")
    target_before = (skill / "references" / "mod.md").read_text(encoding="utf-8")

    record = bless_skill(skill, poi.poi_hash)
    assert record.key == "Derived" and str(record.target) == "references/mod.md"
    assert record.deps  # old -> new dep hashes named

    # body and target untouched; flag cleared
    assert (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(encoding="utf-8") == src_before
    assert (skill / "references" / "mod.md").read_text(encoding="utf-8") == target_before
    check = check_skill(skill)
    assert not check.pois

    # the dependency moves again: a NEW POI with a new hash appears
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two v2", "- alpha two v3"), encoding="utf-8")
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
    src.write_text(src.read_text(encoding="utf-8") + "\n> $kw: --derived --from X.Y\n\nopen\n", encoding="utf-8")
    poi = next(p for p in check_skill(skill).pois if p.kind == "parse-error")
    with pytest.raises(SkillwareError) as excinfo:
        bless_skill(skill, poi.poi_hash)
    assert "not blessable" in str(excinfo.value)


def test_cli_bless_round_trip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from agentos.skillware.commands import _cmd_skillware_bless

    skill = _write_skill(tmp_path)
    build_skill(skill)
    lib = skill / ".skillware" / "src" / "references" / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("- alpha two", "- alpha two v2"), encoding="utf-8")
    build_skill(skill)
    poi = next(p for p in check_skill(skill).pois if p.kind == "derived-stale")

    args = argparse.Namespace(skill=str(skill), poi=poi.poi_hash, json=True)
    assert _cmd_skillware_bless(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["blessed"]["key"] == "Derived"
    assert check_skill(skill).pois == ()

    with pytest.raises(CliError):
        _cmd_skillware_bless(argparse.Namespace(skill=str(skill), poi="ffffffffff", json=True))


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
    assert not any(
        p.kind == "undeclared-dependency" for p in check_skill(skill).pois
    )
    build_skill(skill)
    assert not any(
        p.kind == "undeclared-dependency" for p in check_skill(skill).pois
    )

    depot = tmp_path / "depot" / "design" / "100-design.md"
    depot.write_text(
        depot.read_text(encoding="utf-8") + "\n## Concept.Two\n\n- concept two\n",
        encoding="utf-8",
    )
    src.write_text(src.read_text(encoding="utf-8") + "\nAlso `Concept.Two`.\n", encoding="utf-8")
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
    from agentos.skwlint import SurfaceProvider

    assert issubclass(_SkwSurfaceProvider, SurfaceProvider)


def test_dependency_sync_findings_are_advisory() -> None:
    # The surface-agnostic engine raises the three drift kinds and marks every
    # one advisory — drift is never a gated error in any backend.
    from agentos.skwlint import ADVISORY, dependency_sync_findings

    findings = dependency_sync_findings(
        Path("t.md"),
        declared={"Only.Declared"},
        declared_from_depends={"Only.Declared"},
        mention_resolutions={"Some.Mention": "hash"},
        declared_resolutions={"Only.Declared": "unresolved:gone"},
    )
    assert {f.kind for f in findings} == {"dangling-dependency", "undeclared-dependency"}
    assert all(f.severity == ADVISORY for f in findings)


# --- cross-package deps: the Skw.Pkg.Dependency registry (@<id>/…) ------------

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
