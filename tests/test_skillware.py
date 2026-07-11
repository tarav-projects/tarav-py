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
)
from agentos.skillware.model import parse_skw_source

SRC = """# agentos-index2 --ground

Intro prose.

## Copied

> [!skw]- copy
> from: references/lib.skw.md#Alpha

- copied body line

> [!skw]- end-copy

## Derived

> [!skw]- derived
> from: references/lib.skw.md#Alpha
> from: Concept.One
> intent: reshape alpha for
> this consumer

- derived body

> [!skw]- end-derived

## Mixed

> [!skw]- derived
> from: Concept.One
> intent: short

- derived part

> [!skw]- end-derived

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
    unknown = parse_skw_source("## A\n\n> [!skw]- transmute\n> from: x.md\n\n- body\n")
    assert any("transmute" in finding.message for finding in unknown.findings)

    missing_from = parse_skw_source("## A\n\n> [!skw]- copy\n\n- body\n\n> [!skw]- end-copy\n")
    assert any("from" in finding.message for finding in missing_from.findings)

    bare_end = parse_skw_source("## A\n\nprose\n\n> [!skw] end\n")
    assert any("bare 'end' is invalid" in finding.message for finding in bare_end.findings)

    orphan_end = parse_skw_source("## A\n\n> [!skw]- end-copy\n")
    assert any("without an open construct" in f.message for f in orphan_end.findings)


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

> [!skw]- copy
> from: references/base.skw.md#Root

- stale beta copy

> [!skw]- end-copy
"""

MOD = """# mod

Intro prose.

## Copied

> [!skw]- copy
> from: references/lib.skw.md#Alpha

- stale copy

> [!skw]- end-copy

## Chained

> [!skw]- copy
> from: references/lib.skw.md#Beta

- stale chain

> [!skw]- end-copy

## Derived

> [!skw]- derived
> from: references/lib.skw.md#Alpha
> from: Concept.One
> intent: reshape alpha for this consumer

- derived solution

> [!skw]- end-derived

Hand tail.
"""

DEPOT_CHAPTER = """> router

****

## Concept.One

- concept line
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
    assert "> [!skw]- copy" in refreshed
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
        "## A\n\n> [!skw]- copy\n> from: references/missing.skw.md#X\n\n- body\n\n> [!skw]- end-copy\n"
        "\n## B\n\n> [!skw]- copy\n> from: references/lib.skw.md#Nope\n\n- body\n\n> [!skw]- end-copy\n"
        "\n## C\n\n> [!skw]- copy\n> from: Concept.Missing\n\n- body\n\n> [!skw]- end-copy\n",
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
    (src / "a.skw.md").write_text("## A\n\n> [!skw]- copy\n> from: references/b.skw.md#B\n\n- x\n\n> [!skw]- end-copy\n", encoding="utf-8")
    (src / "b.skw.md").write_text("## B\n\n> [!skw]- copy\n> from: references/a.skw.md#A\n\n- x\n\n> [!skw]- end-copy\n", encoding="utf-8")
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/a.skw.md"))
    assert any("cycle" in finding.message for finding in expansion.findings)


def test_load_skillware_requires_src(tmp_path: Path) -> None:
    with pytest.raises(SkillwareError):
        load_skillware(tmp_path / "nope")


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
    assert "[!skw]" not in compiled
    # src refreshed: stale copy body replaced in the src file
    src_text = (skill / ".skillware" / "src" / "references" / "mod.skw.md").read_text(encoding="utf-8")
    assert "- stale copy" not in src_text

    second = build_skill(skill)
    assert all(entry.action == "unchanged" for entry in second.entries)

    check = check_skill(skill)
    assert not check.findings
    assert all(entry.status == "ok" for entry in check.entries)


def test_check_never_built_and_hand_edited(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    check = check_skill(skill)
    assert all(entry.status == "never-built" for entry in check.entries)
    assert check.findings

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
    assert not check.findings
    assert _entry(check, "references/mod.md").derived_stale == ()


# --- S4: CLI -------------------------------------------------------------------

def test_cli_build_check_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    skill = _write_skill(tmp_path)
    args = argparse.Namespace(skill=str(skill), json=True)

    assert _cmd_skillware_build(args) == 0
    build_payload = json.loads(capsys.readouterr().out)
    assert {entry["action"] for entry in build_payload["entries"]} == {"built"}

    assert _cmd_skillware_check(args) == 0
    check_payload = json.loads(capsys.readouterr().out)
    assert check_payload["summary"]["findings"] == 0

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
    assert "agentos skillware build" in AGENTS_MD_TEXT
    assert "agentos-skillware" in AGENTS_MD_TEXT


def test_build_overwrites_hand_edited_agents_md(tmp_path: Path) -> None:
    from agentos.skillware.build import AGENTS_MD_TEXT

    skill = _write_skill(tmp_path)
    build_skill(skill)
    agents = skill / ".skillware" / "AGENTS.md"
    agents.write_text("# my local notes\n", encoding="utf-8")
    build_skill(skill)
    assert agents.read_text(encoding="utf-8") == AGENTS_MD_TEXT


def test_fenced_callouts_are_not_recipes() -> None:
    source = parse_skw_source(
        "# Spec\n"
        "\n"
        "## Example\n"
        "\n"
        "```md\n"
        "## Fenced Heading\n"
        "\n"
        "> [!skw]- derived\n"
        "> from: Some.Block\n"
        "> intent: fenced example, not a real recipe\n"
        "\n"
        "- example body\n"
        "\n"
        "> [!skw]- end-derived\n"
        "```\n"
        "\n"
        "hand tail after the fence\n"
    )
    assert source.recipes == ()
    assert source.findings == ()
    assert source.machinery_spans == ()


# --- v2: strict construct + structural commands --------------------------------

def test_owned_end_mismatch_and_multi_close() -> None:
    mismatch = parse_skw_source(
        "## A\n\n> [!skw]- derived\n> from: X.Y\n\n- body\n\n> [!skw]- end-copy\n"
    )
    assert any("expected end-derived" in f.message for f in mismatch.findings)

    multi = parse_skw_source(
        "## R\n\n> [!skw]- router\n\n> [!skw]- when\nsituation\n> [!skw]- end-when\n"
        "> [!skw]- then\nresponse\n> [!skw]- end-then end-router\n"
    )
    assert not multi.findings
    assert [c.command for c in multi.constructs] == ["when", "then", "router"]

    wrong_order = parse_skw_source(
        "## R\n\n> [!skw]- router\n\n> [!skw]- when\ns\n> [!skw]- end-when\n"
        "> [!skw]- then\nr\n> [!skw]- end-router end-then\n"
    )
    assert any("mismatched close" in f.message for f in wrong_order.findings)


def test_open_construct_at_heading_and_eof() -> None:
    at_heading = parse_skw_source(
        "## A\n\n> [!skw]- derived\n> from: X.Y\n\n- body\n\n## B\n\nprose\n"
    )
    assert any("left open at heading" in f.message for f in at_heading.findings)

    at_eof = parse_skw_source("## A\n\n> [!skw]- derived\n> from: X.Y\n\n- body\n")
    assert any("left open at EOF" in f.message for f in at_eof.findings)


def test_position_free_and_text_primitive() -> None:
    source = parse_skw_source(
        "## A\n\nhand prose first.\n\n"
        "> [!skw]- derived\n> from: X.Y\n> intent: mid-section derivation\n\n- body\n\n> [!skw]- end-derived\n\n"
        "more hand prose.\n\n"
        "> [!skw]- text\n\ntagged literal span\n\n> [!skw]- end-text\n"
    )
    assert not source.findings
    assert [r.verb for r in source.recipes] == ["derived"]
    assert [c.command for c in source.constructs] == ["text"]
    assert "tagged literal span" in "\n".join(source.constructs[0].body)


def test_nesting_inside_primitive_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> [!skw]- derived\n> from: X.Y\n\n"
        "> [!skw]- text\nnested\n> [!skw]- end-text\n\n- body\n\n> [!skw]- end-derived\n"
    )
    assert any("may not nest inside" in f.message for f in source.findings)


def test_router_structural_checks() -> None:
    outside = parse_skw_source("## A\n\n> [!skw]- when\ns\n> [!skw]- end-when\n")
    assert any("outside a router" in f.message for f in outside.findings)

    unpaired = parse_skw_source(
        "## R\n\n> [!skw]- router\n\n> [!skw]- when\ns\n> [!skw]- end-when\n\n> [!skw]- end-router\n"
    )
    assert any("has no 'then'" in f.message for f in unpaired.findings)

    then_first = parse_skw_source(
        "## R\n\n> [!skw]- router\n\n> [!skw]- then\nr\n> [!skw]- end-then\n\n> [!skw]- end-router\n"
    )
    assert any("alternate when/then" in f.message for f in then_first.findings)


def test_router_compiles_to_pure_prose(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Router Table\n\n"
        "> [!skw]- router\n\n"
        "> [!skw]- when\nWhen the caller wants alpha context.\n\nSecond paragraph of the key.\n> [!skw]- end-when\n\n"
        "> [!skw]- then\nLoad `references/lib.md`.\n> [!skw]- end-then\n\n"
        "> [!skw]- end-router\n\nHand tail.\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    compiled = "\n".join(expansion.fresh_lines)
    assert "[!skw]" not in compiled
    assert "When the caller wants alpha context." in compiled
    assert "Second paragraph of the key." in compiled
    assert "Load `references/lib.md`." in compiled
    assert "Hand tail." in compiled


def test_two_derived_under_one_heading_key_distinctly(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Pair\n\n"
        "> [!skw]- derived\n> from: references/lib.skw.md#Alpha\n> intent: first\n\n- one\n\n> [!skw]- end-derived\n\n"
        "> [!skw]- derived\n> from: Concept.One\n> intent: second\n\n- two\n\n> [!skw]- end-derived\n",
        encoding="utf-8",
    )
    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert set(expansion.dep_hashes) == {"Pair", "Pair@1"}

    build_skill(skill)
    check = check_skill(skill)
    assert not check.findings

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
        "> [!skw]- ^frag-1\nlabeled literal fragment\n> [!skw]- end-^frag-1\n\n"
        "> [!skw]- derived ^model\n> from: X.Y\n> intent: i\n\n- body\n\n> [!skw]- end-derived\n"
    )
    assert not source.findings
    text = source.constructs[0]
    assert (text.command, text.label) == ("text", "frag-1")
    assert "labeled literal fragment" in "\n".join(text.body)
    assert source.recipes[0].label == "model"


def test_label_closer_matching_and_duplicates() -> None:
    mismatch = parse_skw_source(
        "## A\n\n> [!skw]- ^one\nbody\n> [!skw]- end-^two\n"
    )
    assert any("mismatched close" in f.message for f in mismatch.findings)

    dup = parse_skw_source(
        "## A\n\n> [!skw]- ^x\na\n> [!skw]- end-^x\n\n> [!skw]- ^x\nb\n> [!skw]- end-^x\n"
    )
    assert any("duplicate label" in f.message for f in dup.findings)

    mixed = parse_skw_source(
        "## R\n\n> [!skw]- router ^table\n\n"
        "> [!skw]- when\ns\n> [!skw]- end-when\n"
        "> [!skw]- then\nr\n> [!skw]- end-then\n"
        "> [!skw]- end-^table\n"
    )
    assert not mixed.findings


def test_labels_never_reach_compiled_output(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## A\n\n> [!skw]- ^frag\nfragment prose\n> [!skw]- end-^frag\n",
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
        "> [!skw]- ^alpha-core\n- alpha core one\n- alpha core two\n> [!skw]- end-^alpha-core\n\n"
        "trailing prose outside the span.\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n"
        "> [!skw]- ^local-frag\nlocal fragment\n> [!skw]- end-^local-frag\n\n"
        "## Copied\n\n> [!skw]- copy\n> from: references/lib.skw.md^alpha-core\n\n- stale\n\n> [!skw]- end-copy\n\n"
        "## Derived\n\n> [!skw]- derived\n> from: ^local-frag\n> intent: local digest\n\n- solution\n\n> [!skw]- end-derived\n",
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
        "> [!skw]- ^core\n- core line\n> [!skw]- end-^core\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n## Derived\n\n> [!skw]- derived ^consumer\n> from: references/lib.skw.md^core\n> intent: i\n\n- solution\n\n> [!skw]- end-derived\n",
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not check.findings

    # edit OUTSIDE the labeled span: no drift
    lib = src / "lib.skw.md"
    lib.write_text(lib.read_text(encoding="utf-8").replace("prose outside.", "prose outside, edited."), encoding="utf-8")
    build_skill(skill)
    check = check_skill(skill)
    assert not check.findings

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
        "# mod\n\n## Copied\n\n> [!skw]- copy\n> from: references/lib.skw.md#Spec\n\n- stale\n\n> [!skw]- end-copy\n",
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
        "> [!skw]- derived\n> from: references/lib.skw.md#Alpha\n> intent: i\n\n- solution\n\n> [!skw]- end-derived\n",
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
        "> [!skw]- derived\n> from: Concept.One\n> intent: new first\n\n- new solution\n\n> [!skw]- end-derived\n\n"
        "> [!skw]- derived\n> from: references/lib.skw.md#Alpha\n> intent: i\n\n- solution\n\n> [!skw]- end-derived\n",
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    # the old recipe now keys Pair@1 — its staleness must survive the key shift
    assert _entry(check, "references/mod.md").derived_stale == ("Pair@1",)


def test_adjacent_blockquotes_are_body_not_args() -> None:
    source = parse_skw_source(
        "## A\n\n"
        "> [!skw]- ^frag\n"
        "> a markdown quote that is body content\n"
        "more body\n"
        "> [!skw]- end-^frag\n"
        "> a prose quote right after the end line\n"
    )
    assert not source.findings
    body = "\n".join(source.constructs[0].body)
    assert "a markdown quote that is body content" in body
    # the end callout consumes only its own line
    assert (5, 6) in source.machinery_spans


def test_quote_after_end_survives_compilation(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## A\n\n"
        "> [!skw]- ^frag\nbody line\n> [!skw]- end-^frag\n"
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
        "## A\n\n> [!skw]- copy\n> from: a.md#X\n> from: b.md#Y\n\n- body\n\n> [!skw]- end-copy\n"
    )
    assert any("copy takes exactly one from" in f.message for f in source.findings)


def test_labeled_span_resolves_nested_copies_fresh(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skillware" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Alpha\n\n- alpha one\n",
        encoding="utf-8",
    )
    (src / "frag.skw.md").write_text(
        "# frag\n\n## Frag\n\n> [!skw]- ^frag\nspan prose.\n\n"
        "> [!skw]- copy\n> from: references/lib.skw.md#Alpha\n\n- stale inner copy\n\n> [!skw]- end-copy\n"
        "> [!skw]- end-^frag\n",
        encoding="utf-8",
    )
    (src / "mod.skw.md").write_text(
        "# mod\n\n## Uses\n\n> [!skw]- copy\n> from: references/frag.skw.md^frag\n\n- stale\n\n> [!skw]- end-copy\n",
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
        "## R\n\n> [!skw]- router\n\n> [!skw]- when\ns\n> [!skw]- end-when\n\n## Next\n\nprose\n"
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
        "# mod\n\n> [!skw]- ^frag\nf\n> [!skw]- end-^frag\n\n"
        "## R\n\n> [!skw]- router\n\n> [!skw]- when\ns\n> [!skw]- end-when\n"
        "> [!skw]- then\nr\n> [!skw]- end-then\n> [!skw]- end-router\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(skill=str(skill), json=True)
    assert _cmd_skillware_status(args) == 0
    payload = json.loads(capsys.readouterr().out)
    mod = next(f for f in payload["files"] if f["src"] == "references/mod.skw.md")
    assert mod["constructs"] == {"text": 1, "router": 1, "when": 1, "then": 1}


def test_crlf_target_reads_ok(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    build_skill(skill)
    target = skill / "references" / "mod.md"
    # simulate a CRLF checkout of the identical content
    crlf = target.read_text(encoding="utf-8").replace("\n", "\r\n")
    target.write_bytes(crlf.encode("utf-8"))
    check = check_skill(skill)
    assert _entry(check, "references/mod.md").status == "ok"
