from __future__ import annotations

from pathlib import Path

import pytest

from tarav.skillware.build import (
    build_skill,
    check_skill,
    content_hash,
    expand_file,
    load_skillware,
)
from tarav.skillware.model import parse_skw_source
from _skillware_helpers import (
    write_index,
    SRC,
    _entry,
    _write_skill,
)


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
    unknown_flag = parse_skw_source(
        "## A\n\n> $kw: #a --derived\n> --transmute x\n> --from X\n\n- b\n\n> $kw. end\n"
    )
    assert any("unknown flag: --transmute" in f.message for f in unknown_flag.findings)

    missing_from = parse_skw_source("## A\n\n> $kw: --copy\n\n- body\n\n> $kw. end\n")
    assert any("from" in finding.message for finding in missing_from.findings)

    legacy_end = parse_skw_source(
        "## A\n\n> $kw: #a --derived --from X\n\n- b\n\n> $kw. end-derived\n"
    )
    assert any("bare 'end'" in finding.message for finding in legacy_end.findings)

    orphan_end = parse_skw_source("## A\n\nprose\n\n> $kw. end\n")
    assert any(
        "without an open content block" in f.message for f in orphan_end.findings
    )


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
    assert (construct.command, construct.label, construct.address) == (
        "text",
        "frag",
        "^frag",
    )
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
    assert dependency.dev_froms == ("references/capture-context.skw.md",)
    assert dependency.cites == ("Concept.Three",)


def test_parse_context_loading_paths_at_file_point() -> None:
    source = parse_skw_source(
        "> $kw: ^direct --context-loading-path\n"
        "> --step SKILL.md\n"
        "> $kw: ^workspace-local --context-loading-path\n"
        "> --step AGENTS.md\n"
        "> --step SKILL.md\n\n"
        "# Module\n"
    )

    assert not source.findings
    assert [(path.address, path.steps) for path in source.context_loading_paths] == [
        ("^direct", ("SKILL.md",)),
        ("^workspace-local", ("AGENTS.md", "SKILL.md")),
    ]
    assert [construct.command for construct in source.constructs] == [
        "context-loading-path",
        "context-loading-path",
    ]


def test_parse_loading_dependencies_on_any_annotation() -> None:
    source = parse_skw_source(
        "> $kw: ^direct --context-loading-path\n"
        "> --step SKILL.md\n"
        "> --loading-dep SKILL.skw.md^run-contract\n"
        "> --loading-dep SKILL.skw.md^command-contract\n\n"
        "# Module\n\n"
        "> $kw: ^body --derived --from Concept.Source\n"
        "> --loading-dep SKILL.skw.md^authority-contract\n"
        "Derived body.\n\n"
        "> $kw. end\n"
    )

    assert not source.findings
    assert [
        (dependency.locator, dependency.line, dependency.address)
        for dependency in source.context_loading_dependencies
    ] == [
        ("SKILL.skw.md^run-contract", 1, "^direct"),
        ("SKILL.skw.md^command-contract", 1, "^direct"),
        ("SKILL.skw.md^authority-contract", 8, "^body"),
    ]
    assert source.constructs[0].loading_deps == (
        "SKILL.skw.md^run-contract",
        "SKILL.skw.md^command-contract",
    )
    assert source.recipes[0].loading_deps == ("SKILL.skw.md^authority-contract",)


def test_loading_dependency_requires_a_locator() -> None:
    source = parse_skw_source("> $kw: ^deps --loading-dep\n")
    assert any(
        "--loading-dep requires a locator" in finding.message
        for finding in source.findings
    )


def test_parse_context_reachability_at_file_point() -> None:
    source = parse_skw_source(
        "> $kw: ^root-reachability\n"
        "> --reachable-from @<tarav-pkg>/SKILL.md\n"
        "> --reachable-from SKILL.md\n\n"
        "# Skill\n"
    )

    assert not source.findings
    assert [
        (requirement.locator, requirement.line, requirement.address)
        for requirement in source.context_reachabilities
    ] == [
        ("@<tarav-pkg>/SKILL.md", 1, "^root-reachability"),
        ("SKILL.md", 1, "^root-reachability"),
    ]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("> $kw: ^reachability --reachable-from\n", "requires a runtime file"),
        (
            "# Skill\n\n> $kw: ^reachability --reachable-from SKILL.md\n",
            "must be declared at the file point",
        ),
        (
            "> $kw: ^reachability --reachable-from @<tarav-pkg>\n",
            "must name a runtime file",
        ),
        (
            "> $kw: ^reachability --reachable-from ../SKILL.md\n",
            "must name a runtime file",
        ),
    ],
)
def test_context_reachability_parse_findings(text: str, message: str) -> None:
    source = parse_skw_source(text)
    assert any(message in finding.message for finding in source.findings)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        (
            "> $kw: --context-loading-path --step SKILL.md\n",
            "requires an explicit address",
        ),
        ("> $kw: ^path --context-loading-path\n", "requires at least one --step"),
        (
            "> $kw: ^path --context-loading-path --step AGENTS.md\n",
            "must contain SKILL.md",
        ),
        (
            "# Module\n\n> $kw: ^path --context-loading-path --step SKILL.md\n",
            "must be declared at the file point",
        ),
        (
            "> $kw: ^path --context-loading-path --step .skw/AGENTS.md --step SKILL.md\n",
            ".skw/AGENTS.md is builder guidance",
        ),
    ],
)
def test_context_loading_path_parse_findings(text: str, message: str) -> None:
    source = parse_skw_source(text)
    assert any(message in finding.message for finding in source.findings)


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


def test_bare_end_closes_and_legacy_end_is_a_finding() -> None:
    # v2 closes every content block with a bare `$kw. end`
    ok = parse_skw_source(
        "## A\n\n> $kw: --derived --from X.Y\n\n- body\n\n> $kw. end\n"
    )
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

    unpaired = parse_skw_source("## R\n\n> $kw: #r\n\n> $kw: --when\ns\n\n> $kw. end\n")
    assert any("has no 'then'" in f.message for f in unpaired.findings)

    then_first = parse_skw_source(
        "## R\n\n> $kw: #r\n\n> $kw: --then\nr\n\n> $kw. end\n"
    )
    assert any("alternate when/then" in f.message for f in then_first.findings)


def test_annotated_routing_table_rows_are_addressed_objects() -> None:
    source = parse_skw_source(
        "## Routing.Table\n\n"
        "> $kw: ^driver --routing-table --select many\n\n"
        "> $kw: ^impl-develop --router-row --table ^driver\n"
        "> --flag --impl --develop\n"
        "> --alias --develop\n"
        "> --alias --dev\n"
        "> --match explicit-or-semantic\n"
        "> --default implementation input without an Impl.Req\n"
        "> --to Implementation.Develop.Workflow.Module\n"
        "> --load references/lib.md\n"
        "> --when the caller wants end-to-end implementation\n"
        "> --then design an Impl.Req and execute it\n\n"
        "> $kw: ^calls --routing-view calls --table ^driver\n"
    )

    assert not source.findings
    assert source.routing_tables[0].address == "^driver"
    row = source.router_rows[0]
    assert row.address == "^impl-develop"
    assert row.flags == ("--impl --develop",)
    assert row.aliases == ("--develop", "--dev")
    assert row.match == "explicit-or-semantic"
    assert row.destinations == ("Implementation.Develop.Workflow.Module",)
    assert row.loads == ("references/lib.md",)
    assert source.routing_views[0].kind == "calls"
    assert [c.command for c in source.constructs] == [
        "routing-table",
        "router-row",
        "routing-view",
    ]


def test_annotated_router_row_validation() -> None:
    source = parse_skw_source(
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^bad --router-row --table ^missing --alias --x "
        "--match semantic --to X.Module\n"
        "> $kw: ^view --routing-view unknown --table ^driver\n"
    )
    messages = [finding.message for finding in source.findings]
    assert "--alias requires at least one --flag" in messages
    assert "semantic router row requires --when" in messages
    assert "router row references unknown table: ^missing" in messages
    assert "--routing-view requires one value: calls, modules, or full" in messages


def test_annotated_router_rejects_duplicate_explicit_keys() -> None:
    source = parse_skw_source(
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^one --router-row --table ^driver --flag --x "
        "--match explicit --to One.Module\n"
        "> $kw: ^two --router-row --table ^driver --alias --x --flag --y "
        "--match explicit --to Two.Module\n"
    )
    assert any(
        "duplicate explicit route key '--x'" in finding.message
        for finding in source.findings
    )


def test_router_compiles_to_pure_prose(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
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


def test_annotated_router_views_compile_from_one_table(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "## Public Calls\n\n"
        "> $kw: ^calls --routing-view calls --table ^driver\n\n"
        "## Modules\n\n"
        "> $kw: ^modules --routing-view modules --table ^driver\n\n"
        "## Routing.Table\n\n"
        "> $kw: ^driver --routing-table --select many\n\n"
        "> $kw: ^impl-develop --router-row --table ^driver\n"
        "> --flag --impl --develop\n"
        "> --alias --develop\n"
        "> --alias --dev\n"
        "> --match explicit-or-semantic\n"
        "> --default actionable implementation input\n"
        "> --to Implementation.Develop.Workflow.Module\n"
        "> --load references/lib.md\n"
        "> --when the caller wants end-to-end implementation\n"
        "> --then design an Impl.Req and execute it\n\n"
        "> $kw: ^full --routing-view full --table ^driver\n",
        encoding="utf-8",
    )

    skillware = load_skillware(skill)
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert not expansion.findings
    compiled = "\n".join(expansion.fresh_lines)
    assert (
        "| Canonical configuration | Aliases | Resolution | Routed effect |" in compiled
    )
    assert "`--impl --develop`" in compiled
    assert "`--develop`<br>`--dev`" in compiled
    assert "### Workflow Modules" in compiled
    assert "`Implementation.Develop.Workflow.Module`" in compiled
    assert "Selection cardinality: `many`." in compiled
    assert "### `^impl-develop`" in compiled
    assert "$kw" not in compiled


def test_annotated_router_load_target_must_resolve(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^bad --router-row --table ^driver --flag --bad "
        "--match explicit --load references/missing.md\n",
        encoding="utf-8",
    )
    expansion = expand_file(load_skillware(skill), Path("references/mod.skw.md"))
    assert any(
        finding.message == "unresolvable router load: references/missing.md"
        for finding in expansion.findings
    )


def test_annotated_router_load_resolves_registered_package_file(
    tmp_path: Path,
) -> None:
    dependency = tmp_path / "dependency"
    dependency.mkdir()
    (dependency / "SKILL.md").write_text("# Dependency\n", encoding="utf-8")
    skill = _write_skill(tmp_path)
    (skill / ".skw" / "skw.json").write_text(
        '{"deps": {"dependency": "../dependency"}}\n',
        encoding="utf-8",
    )
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^dependency --router-row --table ^driver --match semantic "
        "--load @<dependency>/SKILL.md --when load the dependency\n",
        encoding="utf-8",
    )

    expansion = expand_file(load_skillware(skill), Path("references/mod.skw.md"))

    assert not expansion.findings


def test_addressed_router_row_is_nonempty_dependency_content(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n"
        "> $kw: ^driver --routing-table --select many\n"
        "> $kw: ^search --router-row --table ^driver --flag --search "
        "--alias --ground --match explicit --to Search.Module\n\n"
        "> $kw: ^summary --derived --from ^search\n"
        "Search summary.\n"
        "> $kw. end\n",
        encoding="utf-8",
    )

    expansion = expand_file(load_skillware(skill), Path("references/mod.skw.md"))
    assert not expansion.findings
    digest = expansion.dep_hashes["^summary"]["^search"]
    assert digest == content_hash(
        [
            "Batchy.Router.Row ^search",
            "table: ^driver",
            "match: explicit",
            "flag: --search",
            "alias: --ground",
            "destination: Search.Module",
        ]
    )


def test_two_derived_under_one_heading_key_distinctly(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
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
    write_index(
        tmp_path, (("depot/design#Concept.One", (("CT", "concept line v2"),), ()),)
    )
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert entry.derived_stale == ("Pair@1",)


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
        "## R\n\n> $kw: ^table\n\n> $kw: --when\ns\n> $kw: --then\nr\n> $kw. end\n"
    )
    assert not mixed.findings


def test_labels_never_reach_compiled_output(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
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
    src = skill / ".skw" / "src" / "references"
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

    missing = (
        (src / "mod.skw.md").read_text(encoding="utf-8").replace("^alpha-core", "^nope")
    )
    (src / "mod.skw.md").write_text(missing, encoding="utf-8")
    expansion = expand_file(skillware, Path("references/mod.skw.md"))
    assert any("nope" in f.message for f in expansion.findings)


def test_label_spans_hash_fine_grained(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references"
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
    lib.write_text(
        lib.read_text(encoding="utf-8").replace(
            "prose outside.", "prose outside, edited."
        ),
        encoding="utf-8",
    )
    build_skill(skill)
    check = check_skill(skill)
    assert not check.pois

    # edit INSIDE the span: derived-stale, keyed by the consumer's label
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- core line", "- core line v2"),
        encoding="utf-8",
    )
    check = check_skill(skill)
    entry = _entry(check, "references/mod.md")
    assert entry.derived_stale == ("^consumer",)


def test_region_body_is_fence_aware(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references"
    (src / "lib.skw.md").write_text(
        "# lib\n\n## Spec\n\nintro line.\n\n"
        "````md\n```\n## Fenced Heading\nfenced content\n````\n\n"
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


def test_ordinal_shift_does_not_bless_stale_derived(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
    src.write_text(
        "# mod\n\n## Pair\n\n"
        "> $kw: --derived --from references/lib.skw.md#Alpha --intent i\n\n- solution\n\n> $kw. end\n",
        encoding="utf-8",
    )
    build_skill(skill)
    lib = skill / ".skw" / "src" / "references" / "lib.skw.md"
    lib.write_text(
        lib.read_text(encoding="utf-8").replace("- alpha one", "- alpha one v2"),
        encoding="utf-8",
    )
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
    src = skill / ".skw" / "src" / "references" / "mod.skw.md"
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


def test_copy_with_multiple_froms_is_a_finding() -> None:
    source = parse_skw_source(
        "## A\n\n> $kw: --copy --from a.md#X --from b.md#Y\n\n- body\n\n> $kw. end\n"
    )
    assert any("copy takes exactly one" in f.message for f in source.findings)


def test_labeled_span_resolves_nested_copies_fresh(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    src = skill / ".skw" / "src" / "references"
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
    assert "- alpha one" in refreshed  # fresh, not the stale inner body
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
