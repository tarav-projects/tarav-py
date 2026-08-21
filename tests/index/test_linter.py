from __future__ import annotations

import pathlib

import pytest

from tarav.index import linter

from tarav.index.gates import GateRef
from tarav.index.linter import (
    CHECK_REGISTRY,
    Tier,
    POI_TEST_MARKER,
    LintError,
    bless,
    lint,
    select_checks,
)
from tarav.index.record import IndexStore, LineRecord, SupportRef

SURFACE = "skills/tarav-pkg/design/100-design.md"
APPENDIX = "skills/tarav-pkg/appendix/Index.Depth-appendix.md"
BLOCK = "tarav-pkg/design#Index.WIP.Surface"

CHAPTER = """****

## Index.WIP.Surface

{lines}

****
"""


def _surface(project_root, *lines: str, at: str = SURFACE):
    depot = project_root / "skills" / "tarav-pkg"
    depot.mkdir(parents=True, exist_ok=True)
    router = depot / "000-INDEX.md"
    if not router.exists():
        router.write_text("# test Index\n", encoding="utf-8")
    path = project_root / at
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(CHAPTER.format(lines="\n".join(lines)), encoding="utf-8")
    return path


def _classes(report):
    return {f.poi_class for f in report.findings}


def _entry(scope=BLOCK, body="fine", **kw):
    return LineRecord.create(scope, "CT", body, **kw)


def _gate(token="tok"):
    return GateRef("chat", "s1", token, "user-turn", "agent-turn")


def _landed(project_root, geo, body="fine", label="^c20260818-1u"):
    """One line on a HEAD.Surface, with the gate that licensed it."""

    _surface(project_root, f"- [CT] {body} {label}")
    return IndexStore(geo).put(
        _entry(body=body, support=[SupportRef("chat", "s1", "m1")])
        .relabel(label)
        .with_landing(_gate())
    )


class TestCatalog:
    def test_check_names_are_unique(self):
        names = [c.name for c in CHECK_REGISTRY]
        assert len(names) == len(set(names))

    def test_selectors_narrow_the_reportable_run(self):
        reportable = [
            c.name for c in select_checks(check=["line-typed"]) if c.tier is not Tier.STRUCTURAL
        ]
        assert reportable == ["line-typed"]

    def test_a_named_check_still_runs_the_structural_checks_it_reads(self):
        """`--check` narrows what is reported, never what establishes the context.

        The structural tier is what loads the surfaces and records every other check reads,
        so dropping it leaves the named check examining an empty corpus and reporting it
        clean -- the same failure the targeted-run selection already refuses to allow.
        """

        assert Tier.STRUCTURAL in {c.tier for c in select_checks(check=["line-typed"])}

    def test_skip_removes_a_default_check(self):
        assert "line-typed" not in {c.name for c in select_checks(skip=["line-typed"])}

    def test_unknown_check_is_refused(self):
        with pytest.raises(LintError, match="unknown check"):
            select_checks(check=["no-such-check"])


class TestTheBar:
    def test_an_alias_may_not_have_its_own_block(self, geo, project_root):
        depot = project_root / "skills" / "tarav-pkg"
        (depot / "design").mkdir(parents=True)
        (depot / "000-INDEX.md").write_text(
            "- `design/100-design.md` — Canonical.Name\n", encoding="utf-8"
        )
        (depot / "design" / "100-design.md").write_text(
            """****

## Canonical.Name

- [DF] canonical

### meta

- aliases: `Alias.Name`

****
""",
            encoding="utf-8",
        )
        _surface(
            project_root,
            "- [DF] duplicate alias block",
            at="skills/tarav-pkg/design/200-design.md",
        ).write_text(
            """****

## Alias.Name

- [DF] duplicate alias block

****
""",
            encoding="utf-8",
        )

        report = lint(geo, check=["alias-has-no-block"])

        finding = next(
            f for f in report.findings if f.poi_class == "Index.Linter/Alias.HasBlock"
        )
        assert finding.subject == "Alias.Name"
        assert finding.operands["canonical"] == "Canonical.Name"
        assert finding.surface == "skills/tarav-pkg/design/200-design.md"

    def test_an_alias_without_a_second_block_is_clean(self, geo, project_root):
        depot = project_root / "skills" / "tarav-pkg"
        (depot / "design").mkdir(parents=True)
        (depot / "000-INDEX.md").write_text(
            "- `design/100-design.md` — Canonical.Name\n", encoding="utf-8"
        )
        (depot / "design" / "100-design.md").write_text(
            """****

## Canonical.Name

- [DF] canonical

### meta

- aliases: `Alias.Name`

****
""",
            encoding="utf-8",
        )

        assert "Index.Linter/Alias.HasBlock" not in _classes(
            lint(geo, check=["alias-has-no-block"])
        )

    def test_a_redundant_self_alias_is_not_a_second_block(self, geo, project_root):
        depot = project_root / "skills" / "tarav-pkg"
        (depot / "design").mkdir(parents=True)
        (depot / "000-INDEX.md").write_text(
            "- `design/100-design.md` — Canonical.Name\n", encoding="utf-8"
        )
        (depot / "design" / "100-design.md").write_text(
            """****

## Canonical.Name

- [DF] canonical

### meta

- aliases: `Canonical.Name`

****
""",
            encoding="utf-8",
        )

        assert "Index.Linter/Alias.HasBlock" not in _classes(
            lint(geo, check=["alias-has-no-block"])
        )

    def test_untyped_surface_line_is_reported(self, geo, project_root):
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        assert "Index.Linter/Line.Untyped" in _classes(lint(geo))

    def test_unknown_line_type_is_reported(self, geo, project_root):
        _surface(project_root, "- [ZZ] not a known code ^c20260818-1u")
        assert "Index.Linter/Line.Type.Unknown" in _classes(lint(geo))

    def test_ungrounded_entry_is_debt_not_deletion(self, geo, project_root):
        _surface(project_root, "- [CT] fine ^c20260818-1u")
        store = IndexStore(geo)
        store.put(_entry(body="no support"))
        assert "Index.Linter/Line.Ungrounded" in _classes(lint(geo))
        assert store.count() == 1, "reporting debt must not remove the entry"

    def test_duplicate_record_labels_are_reported_as_a_poi(self, geo, project_root):
        store = IndexStore(geo)
        first = _entry(body="first").relabel("^c20260818-1u")
        second = _entry(body="second").relabel("^c20260818-1u")
        store.depot.insert(first.to_json())
        store.depot.insert(second.to_json())

        report = lint(geo, check=["records-loadable", "record-label-unique"])

        finding = next(
            f
            for f in report.findings
            if f.poi_class == "Index.Linter/Record.LabelCollision"
        )
        assert finding.subject == "^c20260818-1u"
        assert finding.operands["ids"] == " ".join(sorted((first.id, second.id)))


class TestScopeChecks:
    def test_an_unresolvable_scope_is_reported(self, geo, project_root):
        IndexStore(geo).put(_entry(scope="ghost-depot/design#Nowhere"))
        assert "Index.Linter/Scope.Unresolved" in _classes(lint(geo))

    def test_an_annotation_scope_resolves_to_its_product_file(self, geo, project_root):
        module = project_root / "thing.py"
        module.write_text("# $kw: --from C --note [CT] a\n", encoding="utf-8")
        IndexStore(geo).put(_entry(scope="@thing.py/C", body="a"))
        assert "Index.Linter/Scope.Unresolved" not in _classes(lint(geo))

    def test_scope_kind_mismatch_is_reported(self, geo, project_root):
        _surface(project_root, "- [CT] block hosted ^c20260818-1u")
        IndexStore(geo).put(
            _entry(scope="@thing.py/C", body="block hosted").relabel("^c20260818-1u")
        )
        assert "Index.Linter/Scope.KindMismatch" in _classes(lint(geo))


class TestReviewSplit:
    def test_a_reviewed_trace_may_not_carry_an_ungrounded_member(self, geo, project_root):
        """Reviewed.Cite.Closure: reviewed standing may not rest on nothing touched."""
        IndexStore(geo).put(_entry(body="reviewed but unsupported").with_review(_gate()))
        assert "Index.Linter/Reviewed.Cite.Closure" in _classes(lint(geo))

    def test_a_grounded_reviewed_entry_is_clean(self, geo, project_root):
        IndexStore(geo).put(
            _entry(body="reviewed and grounded", support=[SupportRef("chat", "s1", "m1")])
            .with_review(_gate())
        )
        assert "Index.Linter/Reviewed.Cite.Closure" not in _classes(lint(geo))


class TestHeadSurface:
    """HEAD is presence on a declared surface; the gate is what licensed the presence."""

    def test_an_ungated_line_on_a_head_surface_is_reported(self, geo, project_root):
        _surface(project_root, "- [CT] promoted by nobody ^c20260818-1u")
        IndexStore(geo).put(
            _entry(body="promoted by nobody", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260818-1u")
        )
        assert "Index.Linter/Landing.Unevidenced" in _classes(lint(geo))

    def test_a_gated_line_on_a_head_surface_is_clean(self, geo, project_root):
        _landed(project_root, geo)
        found = _classes(lint(geo))
        assert "Index.Linter/Landing.Unevidenced" not in found
        assert "Index.Linter/Landing.Unhonored" not in found

    def test_a_gated_trace_on_no_head_surface_is_reported(self, geo, project_root):
        """Approved and never landed, or quietly demoted — the gate outlives the edit."""
        _surface(project_root, "- [CT] unrelated ^c20260818-2u")
        IndexStore(geo).put(
            _entry(body="approved, never landed", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260818-1u")
            .with_landing(_gate())
        )
        assert "Index.Linter/Landing.Unhonored" in _classes(lint(geo))

    def test_an_appendix_line_needs_a_landing_gate_like_any_other(self, geo, project_root):
        """All of a user home is HEAD. Appendix is depth, not weaker standing, so a line
        landed there answers for its gate exactly as a chapter line does."""
        _surface(project_root, "- [CT] depth ^c20260818-1u", at=APPENDIX)
        IndexStore(geo).put(
            _entry(body="depth", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260818-1u")
        )
        assert "Index.Linter/Landing.Unevidenced" in _classes(lint(geo))

    def test_the_live_surface_cut_is_structurally_discovered(self, geo, project_root):
        _surface(project_root, "- [CT] live ^c20260818-1u", at=APPENDIX)
        from tarav.index.surfaces import discover_surfaces

        assert APPENDIX in discover_surfaces(geo, project_root)

    def test_a_superseded_wording_on_a_head_surface_is_reported(self, geo, project_root):
        store = IndexStore(geo)
        first = store.put(
            _entry(body="the first wording", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260818-1u")
            .with_landing(_gate())
        )
        store.put(first.successor("CT", "the second wording").relabel("^c20260818-2u"))
        _surface(
            project_root,
            "- [CT] the first wording ^c20260818-1u",
            "- [CT] the second wording ^c20260818-2u",
        )
        assert "Index.Linter/Materialization.Standing" in _classes(lint(geo))


class TestSurfaceAndRecord:
    def test_unanchored_line_is_reported(self, geo, project_root):
        _surface(project_root, "- [CT] no anchor here")
        assert "Index.Linter/Line.Unanchored" in _classes(lint(geo))

    def test_surface_line_without_an_entry_is_reported(self, geo, project_root):
        _surface(project_root, "- [CT] written by hand ^c20260818-9u")
        assert "Index.Linter/Line.Unrecorded" in _classes(lint(geo))

    def test_drift_shows_both_sides_without_privileging_either(self, geo, project_root):
        _surface(project_root, "- [CT] reworded on the surface ^c20260818-1u")
        IndexStore(geo).put(
            _entry(body="the record still says this").relabel("^c20260818-1u")
        )
        finding = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/Line.Drift"
        )
        assert finding.operands["surface"] == "reworded on the surface"
        assert finding.operands["record"] == "the record still says this"

    def test_anchor_collision_is_reported(self, geo, project_root):
        _surface(
            project_root,
            "- [CT] first ^c20260818-1u",
            "- [DF] second, same anchor ^c20260818-1u",
        )
        assert "Index.Linter/Anchor.Collision" in _classes(lint(geo))

    def test_anchor_collision_includes_line_type_in_projection(
        self, geo, project_root
    ):
        _surface(
            project_root,
            "- [CT] same body ^c20260818-1u",
            "- [DF] same body ^c20260818-1u",
        )
        assert "Index.Linter/Anchor.Collision" in _classes(lint(geo))

    def test_entry_materialized_nowhere_is_reported(self, geo, project_root):
        _surface(project_root, "- [CT] unrelated ^c20260818-1u")
        IndexStore(geo).put(_entry(body="orphan").relabel("^c20260818-7u"))
        assert "Index.Linter/Record.Unplaced" in _classes(lint(geo))


class TestSupport:
    def test_unreachable_support_names_the_archive(self, geo, project_root):
        _surface(project_root, "- [CT] grounded ^c20260818-1u")
        IndexStore(geo).put(
            _entry(body="grounded", support=[SupportRef("chat", "absent-session", "a")])
            .relabel("^c20260818-1u")
        )
        report = lint(geo)
        finding = next(
            f
            for f in report.blocked
            if f.poi_class == "Index.Linter/Support.Unreachable"
        )
        assert finding.operands["session"] == "absent-session"
        assert finding.blocked, "an absent archive is unverifiable, not a defect"
        assert finding not in report.findings, "unverifiable is never counted as an error"
        assert not report.verified, "and never counted as clean either"


class TestBless:
    def test_a_blessed_finding_leaves_the_report(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "an untyped assertion is fine here")])
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        finding = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/Line.Untyped"
        )
        bless(geo, finding.identity, "DC", "this surface predates the fence",
              support=[SupportRef("chat", "s1", "m1")])
        after = lint(geo)
        assert finding.identity not in {f.identity for f in after.findings}
        assert finding.identity in {f.identity for f in after.blessed}

    def test_blessing_one_finding_does_not_disable_the_check(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "an untyped assertion is fine here")])
        _surface(
            project_root,
            "- first untyped ^c20260818-1u",
            "- second untyped ^c20260818-2u",
        )
        first = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/Line.Untyped"
        )
        bless(geo, first.identity, "DC", "this one predates the fence",
              support=[SupportRef("chat", "s1", "m1")])
        after = lint(geo)
        assert "Index.Linter/Line.Untyped" in _classes(after)



class TestCleanRun:
    def test_an_empty_project_is_clean(self, geo):
        assert lint(geo).clean

    def test_the_report_counts_what_it_scanned(self, geo, project_root):
        _surface(project_root, "- [CT] a ^c20260818-1u", "- [DF] b ^c20260818-2u")
        report = lint(geo)
        assert report.surface_lines_checked == 2
        assert report.checks_run


class TestConvergence:
    """Grounded coverage only grows; the bytes of the index are free to move."""

    def _repo(self, geo):
        """The depot's repo, not the project's.

        Coverage is compared against the history of the records themselves, and the records
        moved user-side — so the tracked tree that matters is the depot's own.
        """
        import subprocess

        geo.index_depot.mkdir(parents=True, exist_ok=True)
        for args in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "t@example.com"],
            ["git", "config", "user.name", "t"],
        ):
            subprocess.run(args, cwd=geo.index_depot, check=True, capture_output=True)

    def _commit(self, geo, message="state"):
        import subprocess

        subprocess.run(
            ["git", "add", "-A"], cwd=geo.index_depot, check=True, capture_output=True
        )
        # `--allow-empty` because the depot commits itself: its git handler checkpoints on
        # the first write, so by the time a test asks for a commit there is often nothing
        # left staged. An empty commit here still marks the HEAD the check compares against.
        subprocess.run(
            ["git", "commit", "--quiet", "--allow-empty", "-m", message],
            cwd=geo.index_depot, check=True, capture_output=True,
        )

    def test_an_untracked_project_is_not_a_defect(self, geo, project_root):
        IndexStore(geo).put(_entry(support=[SupportRef("chat", "s1", "m1")]))
        assert "Index.Linter/Coverage.Shrank" not in _classes(lint(geo))

    def test_losing_a_grounded_line_shrinks_coverage(self, geo, project_root):
        self._repo(geo)
        store = IndexStore(geo)
        record = store.put(_entry(support=[SupportRef("chat", "s1", "m1")]))
        self._commit(geo)
        store.remove(record.id)
        assert "Index.Linter/Coverage.Shrank" in _classes(lint(geo))

    def test_rewording_a_grounded_line_keeps_coverage(self, geo, project_root):
        """The bytes may move freely — only coverage is conserved."""
        self._repo(geo)
        store = IndexStore(geo)
        record = store.put(_entry(body="first wording", support=[SupportRef("chat", "s1", "m1")]))
        self._commit(geo)
        store.put(record.amend("CT", "a much better wording").relabel("^c20260818-9u"))
        assert "Index.Linter/Coverage.Shrank" not in _classes(lint(geo))

    def test_removing_an_ungrounded_line_keeps_coverage(self, geo, project_root):
        self._repo(geo)
        store = IndexStore(geo)
        record = store.put(_entry(support=()))
        self._commit(geo)
        store.remove(record.id)
        assert "Index.Linter/Coverage.Shrank" not in _classes(lint(geo))

    def test_removing_a_grounded_line_is_reported_without_excuse(self, geo, project_root):
        """No index-side ledger can excuse the loss; the commit is the record."""
        self._repo(geo)
        store = IndexStore(geo)
        record = store.put(_entry(support=[SupportRef("chat", "s1", "m1")]))
        self._commit(geo)
        store.remove(record.id)
        assert "Index.Linter/Coverage.Shrank" in _classes(lint(geo))


class TestGateVerification:
    """The check that makes every other standing mean something."""

    def test_a_fabricated_gate_is_caught(self, geo, project_root, chat):
        chat("s1", [("agent-turn", "agent", "no token here"), ("user-turn", "user", "ok")])
        _landed(project_root, geo)
        finding = next(
            f
            for f in lint(geo).findings
            if f.poi_class == "Index.Linter/Gate.Evidence.Invalid"
        )
        assert finding.operands["gate"] == "landing"
        assert "token" in finding.operands["reason"]

    def test_a_real_gate_passes(self, geo, project_root, chat):
        chat(
            "s1",
            [("agent-turn", "agent", "proposing fine\ntok"), ("user-turn", "user", "::approve tok")],
        )
        _landed(project_root, geo)
        assert "Index.Linter/Gate.Evidence.Invalid" not in _classes(lint(geo))


class TestBlessingEvidence:
    """A blessing silences a check, so it is the last place to demand evidence.

    What licenses it is not a user's approval token but an agent's claim plus the user turns
    that claim rests on -- the same thing that licenses every other index line.
    """

    def _probe(self, geo, project_root, tag="alpha"):
        _surface(project_root, f"- [CT] a probe {POI_TEST_MARKER}#{tag}")
        return next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        )

    def test_a_grounded_blessing_silences_its_poi(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "we do not lint legacy stuff")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "a probe is not a defect",
              support=[SupportRef("chat", "s1", "m1")])

        after = lint(geo)
        assert finding.identity in {f.identity for f in after.blessed}
        assert finding.identity not in {f.identity for f in after.findings}

    def test_blessing_one_poi_does_not_silence_another(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "we do not lint legacy stuff")])
        _surface(
            project_root,
            f"- [CT] first probe {POI_TEST_MARKER}#alpha",
            f"- [CT] second probe {POI_TEST_MARKER}#beta",
        )
        probes = {
            f.subject: f for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        }
        alpha = probes[f"{SURFACE}#alpha"]
        bless(geo, alpha.identity, "DC", "this one is deliberate",
              support=[SupportRef("chat", "s1", "m1")])

        after = lint(geo)
        assert {f.subject for f in after.blessed} == {f"{SURFACE}#alpha"}
        assert f"{SURFACE}#beta" in {f.subject for f in after.findings}

    def test_an_ungrounded_blessing_silences_nothing(self, geo, project_root, chat):
        """An agent cannot silence its own finding with a claim it writes itself."""
        chat("s1", [("m1", "user", "anything")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "trust me")

        after = lint(geo)
        assert finding.identity in {f.identity for f in after.findings}
        assert "Index.Linter/Blessing.Ungrounded" in _classes(after)

    def test_support_that_does_not_resolve_silences_nothing(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "anything")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "a claim",
              support=[SupportRef("chat", "s1", "absent-message")])

        after = lint(geo)
        assert finding.identity in {f.identity for f in after.findings}
        assert "Index.Linter/Blessing.Support.Unresolved" in _classes(after)

    def test_support_on_an_agent_turn_silences_nothing(self, geo, project_root, chat):
        """`Touched.Authority` comes from a user turn; an agent turn carries none."""
        chat("s1", [("m1", "agent", "I think this is fine")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "a claim",
              support=[SupportRef("chat", "s1", "m1")])

        after = lint(geo)
        assert finding.identity in {f.identity for f in after.findings}
        assert "Index.Linter/Blessing.Support.Untouched" in _classes(after)

    def test_a_blessing_whose_poi_stopped_occurring_is_reported(self, geo, project_root, chat):
        chat("s1", [("m1", "user", "we do not lint legacy stuff")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "a claim",
              support=[SupportRef("chat", "s1", "m1")])

        # The probe is removed; its blessing now points at nothing.
        _surface(project_root, "- [CT] an ordinary line ^c20260818-1u")
        assert "Index.Linter/Blessing.Orphaned" in _classes(lint(geo))

    def test_a_finding_about_a_blessing_cannot_itself_be_blessed(
        self, geo, project_root, chat
    ):
        """The escape hatch may not cover its own hatch.

        Without this an agent answers `Blessing.Ungrounded` with a second ungrounded
        blessing, and the grounding requirement becomes decorative.
        """

        chat("s1", [("m1", "user", "we do not lint legacy stuff")])
        finding = self._probe(geo, project_root)
        bless(geo, finding.identity, "DC", "no support here")

        ungrounded = next(
            f for f in lint(geo).findings
            if f.poi_class == "Index.Linter/Blessing.Ungrounded"
        )
        bless(geo, ungrounded.identity, "DC", "and neither here",
              support=[SupportRef("chat", "s1", "m1")])

        after = lint(geo)
        assert ungrounded.identity in {f.identity for f in after.findings}
        assert ungrounded.identity not in {f.identity for f in after.blessed}


class TestSelectionKeepsItsContext:
    def test_a_named_reportable_check_reports_on_a_corpus_it_can_see(self, geo, project_root):
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        report = lint(geo, check=["line-typed"])
        assert "Index.Linter/Line.Untyped" in _classes(report)

    def test_a_named_probe_check_reports_on_a_corpus_it_can_see(self, geo, project_root):
        _surface(project_root, f"- [CT] a probe {POI_TEST_MARKER}")
        report = lint(geo, check=["poi-test"])
        assert "Index.Linter/POI.Test" in _classes(report)


class TestRegistryOrder:
    def test_a_check_is_registered_after_whatever_loads_what_it_reads(self):
        """Registry order is load order, and nothing else says so.

        `LintContext` starts empty; the structural checks fill it as they run. A check
        registered before its provider therefore reads an empty field and silently reports
        clean -- which is how `poi-test` first shipped finding nothing at all.
        """

        providers = {"surface_lines": "surfaces-readable", "records": "records-loadable"}
        position = {check.name: index for index, check in enumerate(CHECK_REGISTRY)}
        for check in CHECK_REGISTRY:
            for field, provider in providers.items():
                if field not in check.run.__code__.co_names or check.name == provider:
                    continue
                assert position[check.name] > position[provider], (
                    f"{check.name} reads ctx.{field} before {provider} fills it"
                )

    def test_a_check_reading_the_whole_run_is_registered_last(self):
        """`ctx.produced` is filled by the run itself, one check at a time.

        A check asking what did *not* occur therefore has to be last, or it reports the
        checks registered after it as absences.
        """

        consumers = [c.name for c in CHECK_REGISTRY if "produced" in c.run.__code__.co_names]
        assert consumers, "the guard is vacuous if nothing reads ctx.produced"
        assert consumers == [CHECK_REGISTRY[-1].name]


class TestPoiTestProbe:
    """The summonable finding: a real POI on demand, for working on the linter itself.

    Every other check needs a genuine defect to fire. That makes the linter's own behaviour
    -- selection, targeting, reporting, blessing -- awkward to exercise against a real corpus,
    because exercising it means damaging one. This check fires on a marker instead.
    """

    def test_a_marker_summons_one_finding(self, geo, project_root):
        _surface(project_root, f"- [CT] a probe {POI_TEST_MARKER}")
        subjects = [
            f.subject for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        ]
        assert subjects == [f"{SURFACE}#default"]

    def test_no_marker_summons_nothing(self, geo, project_root):
        _surface(project_root, "- [CT] an ordinary line ^c20260818-1u")
        assert "Index.Linter/POI.Test" not in _classes(lint(geo))

    def test_tagged_probes_are_independent_findings(self, geo, project_root):
        _surface(
            project_root,
            f"- [CT] first probe {POI_TEST_MARKER}#alpha",
            f"- [CT] second probe {POI_TEST_MARKER}#beta",
        )
        subjects = {
            f.subject for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        }
        assert subjects == {f"{SURFACE}#alpha", f"{SURFACE}#beta"}

    def test_the_probe_identity_survives_the_marker_moving(self, geo, project_root):
        """A probe exists to be blessed and stay blessed while its file is worked on.

        The other surface checks subject on `scope:lineno`, which moves whenever a line is
        inserted above. That is right for them and wrong here: it would revoke the blessing
        this check exists to let a test place.
        """

        _surface(project_root, f"- [CT] a probe {POI_TEST_MARKER}#alpha")
        before = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        )
        _surface(
            project_root,
            "- [CT] an unrelated line added above ^c20260818-9u",
            f"- [CT] a probe {POI_TEST_MARKER}#alpha",
        )
        after = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/POI.Test"
        )
        assert after.identity == before.identity


class TestResolutions:
    def test_every_check_documents_its_resolutions(self):
        undocumented = [c.name for c in CHECK_REGISTRY if not c.resolutions]
        assert undocumented == [], f"checks without resolutions: {undocumented}"

    def test_no_resolution_is_presented_as_the_fix(self):
        """A POI prescribes no remedy, so single-resolution checks are the exception."""
        for check in CHECK_REGISTRY:
            if check.name in {"record-scoped", "scope-kind", "review-evidence"}:
                continue
            assert len(check.resolutions) >= 2, check.name


class TestTheEstimator:
    """A state is value + err/unknown; a report that cannot say which is not an estimate."""

    def test_clean_and_verified_are_different_claims(self, geo, project_root):
        """No errors over nine checks is not the same position as no errors over all of them."""
        report = lint(geo)
        assert report.clean
        assert not report.verified, "git is absent, so coverage was never compared"

    def test_a_blocked_check_is_reported_not_skipped(self, geo, project_root):
        blocked = {r.name for r in lint(geo).blocked_checks}
        assert "coverage-converges" in blocked

    def test_a_blocked_check_names_its_reason(self, geo, project_root):
        result = next(r for r in lint(geo).blocked_checks if r.name == "coverage-converges")
        assert result.reason and "git" in result.reason

    def test_an_unavailable_gate_is_blocked_not_silent(self, geo, project_root):
        _landed(project_root, geo)
        classes = {f.poi_class for f in lint(geo).blocked}
        assert "Index.Linter/Gate.Evidence.Unavailable" in classes
        finding = next(
            finding
            for finding in lint(geo).blocked
            if finding.poi_class == "Index.Linter/Gate.Evidence.Unavailable"
        )
        assert finding.operands["archive"] == "chat"
        assert "archive unavailable" in finding.operands["reason"]

    def test_a_verified_project_says_so(self, geo, project_root, chat):
        """With the archive present and git tracking, nothing is left unchecked."""
        import subprocess

        chat("s1", [("agent-turn", "agent", "proposing fine\ntok"), ("user-turn", "user", "::approve tok")])
        IndexStore(geo).put(_entry(support=[SupportRef("chat", "s1", "m1")]))
        for args in (
            ["git", "init", "--quiet"],
            ["git", "config", "user.email", "t@example.com"],
            ["git", "config", "user.name", "t"],
        ):
            subprocess.run(args, cwd=geo.index_depot, check=True, capture_output=True)
        subprocess.run(
            ["git", "add", "-A"], cwd=geo.index_depot, check=True, capture_output=True
        )
        subprocess.run(
            ["git", "commit", "--quiet", "-m", "base"],
            cwd=geo.index_depot, check=True, capture_output=True,
        )
        assert not lint(geo).blocked_checks

    def test_every_check_reports_a_status(self, geo, project_root):
        report = lint(geo)
        assert len(report.results) == len(report.checks_run)
        assert all(r.status for r in report.results)


class TestSignalNotSemantics:
    """A finding is a typed signal of a declared computation, carrying no reading of it."""

    def test_findings_carry_operands_not_prose(self, geo, project_root):
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        finding = lint(geo).findings[0]
        assert not hasattr(finding, "detail")
        assert finding.operands

    def test_a_finding_points_at_the_code_that_produced_it(self, geo, project_root):
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        finding = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/Line.Untyped"
        )
        assert finding.source and finding.source.startswith("linter.py:")

    def test_findings_carry_an_evaluator(self, geo, project_root):
        _surface(project_root, "- an untyped assertion ^c20260818-1u")
        assert str(lint(geo).findings[0].evaluator) == "code"

    def test_operands_do_not_change_a_finding_identity(self, geo, project_root):
        """A blessing must survive the value it accepted drifting slightly."""
        from tarav.index.linter import Finding

        a = Finding("X/Y", "ln_1", {"body": "one"})
        b = Finding("X/Y", "ln_1", {"body": "two"})
        assert a.identity == b.identity


class TestPoiClassCatalog:
    """Registry-specific catalog hygiene.

    That every emitted class declares a resolving managed block is asserted system-wide in
    `test_architecture.py`; what only this registry can answer is whether a declaration has
    outlived the check that emitted it.
    """

    def _annotations(self) -> dict[str, str]:
        import re

        source = pathlib.Path(linter.__file__).read_text("utf-8")
        return {
            match.group(1): match.group(0)
            for match in re.finditer(r"\$kw: (Index\.Linter/[A-Za-z.]+)[^\n]*", source)
        }

    def test_a_bare_declaration_nothing_emits_is_removed(self):
        """A `$kw` block left behind by a deleted check declares a class that cannot occur.

        Only bare declarations are held to this. One carrying a `--note` is a deliberate
        statement about a class agents raise, not a leftover -- which is a property of the
        annotation rather than a list someone has to maintain.
        """

        emitted = set().union(*(set(c.poi_classes) for c in CHECK_REGISTRY))
        annotations = self._annotations()
        stale = sorted(
            name
            for name, annotation in annotations.items()
            if name not in emitted and "--note" not in annotation
        )
        assert stale == [], "declared but emitted by nothing: " + ", ".join(stale)


class TestCodeIsTheDocumentation:
    def test_no_check_carries_a_prose_title(self):
        assert not any(hasattr(c, "title") for c in CHECK_REGISTRY)

    def test_every_check_points_at_its_implementation(self):
        for check in CHECK_REGISTRY:
            assert check.source.startswith("linter.py:"), check.name

    def test_every_check_says_why_it_exists(self):
        undocumented = [c.name for c in CHECK_REGISTRY if not c.why]
        assert undocumented == [], f"checks with no rationale: {undocumented}"

    def test_the_docstring_is_not_a_restatement_of_the_name(self):
        """The docstring says why; the body says what. They must not be the same sentence."""
        for check in CHECK_REGISTRY:
            words = set(check.name.replace("-", " ").split())
            first = set(check.why.split("\n")[0].lower().split())
            assert not words <= first, f"{check.name} docstring restates its own name"


class TestRephraseChain:
    def test_a_rename_chain_carries_no_rephrase_signal(self, geo, project_root):
        from tarav.index.record import EquivalenceKind

        store = IndexStore(geo)
        first = store.put(
            _entry(body="the old name", support=[SupportRef("chat", "s1", "m1")])
            .with_review(_gate())
        )
        store.put(first.successor("CT", "the new name", kind=EquivalenceKind.RENAME))
        assert "Index.Linter/Review.ViaRephrase" not in _classes(lint(geo))

    def test_a_rephrase_in_a_reviewed_chain_is_distinguishable(self, geo, project_root):
        """Untyped agent state on the path that grants reviewed standing."""
        store = IndexStore(geo)
        first = store.put(
            _entry(body="the original claim", support=[SupportRef("chat", "s1", "m1")])
            .with_review(_gate())
        )
        store.put(first.successor("CT", "a materially different sentence"))
        finding = next(
            f for f in lint(geo).findings if f.poi_class == "Index.Linter/Review.ViaRephrase"
        )
        assert str(finding.evaluator) == "agent", "no code decided this; it is escalated"


class TestReviewCoversSupport:
    def test_a_review_turn_that_never_showed_the_support(self, geo, project_root, chat):
        chat("s1", [("agent-turn", "agent", "fine\ntok"), ("user-turn", "user", "::approve tok")])
        IndexStore(geo).put(
            _entry(body="fine", support=[SupportRef("chat", "s1", "m1")]).with_review(_gate())
        )
        assert "Index.Linter/Review.SupportUnseen" in _classes(lint(geo))

    def test_a_review_turn_that_showed_it(self, geo, project_root, chat):
        chat("s1", [("agent-turn", "agent", "fine\ntok\nsupport: m1"), ("user-turn", "user", "::approve tok")])
        IndexStore(geo).put(
            _entry(body="fine", support=[SupportRef("chat", "s1", "m1")]).with_review(_gate())
        )
        assert "Index.Linter/Review.SupportUnseen" not in _classes(lint(geo))


class TestDevLane:
    def test_a_dev_check_never_runs_outside_the_dev_lane(self):
        from tarav.index.linter import select_checks

        names = {c.name for c in select_checks()}
        assert "gate-verifies-dev" not in names
        assert "gate-verifies" in names

    def test_a_dev_check_cannot_be_summoned_by_name(self):
        """Naming it is not consent. A relaxed check reachable from an ordinary
        run is one that will eventually be reached by accident."""
        from tarav.index.linter import select_checks

        assert "gate-verifies-dev" not in {
            c.name for c in select_checks(check=["gate-verifies-dev"])
        }

    def test_the_dev_check_displaces_the_one_it_stands_in_for(self):
        from tarav.index.linter import select_checks

        names = {c.name for c in select_checks(dev=True)}
        assert "gate-verifies-dev" in names
        assert "gate-verifies" not in names

    def test_the_report_names_the_dev_checks_it_used(self, geo, project_root):
        report = lint(geo, dev=True)
        assert report.dev == ("gate-verifies-dev",)
        assert report.is_dev
        assert not lint(geo).is_dev

    def test_the_dev_gate_relaxes_touch_and_nothing_else(self, geo, project_root):
        """A forged token stays invalid in the dev lane.

        The dev gate drops only `carries_touch`. Token round-trip and verbatim
        containment still hold, so a gate that did not happen is still caught.
        """
        store = IndexStore(geo)
        store.put(
            _entry(body="a gated line", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260819-19u")
            .with_landing(_gate(token="idx-edition:forged"))
        )
        report = lint(geo, dev=True)
        raised = {f.poi_class for f in (*report.findings, *report.blocked)}
        assert raised & {
            "Index.Linter/Gate.Evidence.Invalid",
            "Index.Linter/Gate.Evidence.Unavailable",
        }


class TestSupersededPlacement:
    def test_a_superseded_member_is_not_reported_unplaced(self, geo, project_root):
        """A revision replaces the predecessor's wording on the surface.

        The predecessor is therefore absent by construction. Reporting it would
        make every revision leave a permanent finding behind, and the absence is
        already readable through the trace.
        """
        store = IndexStore(geo)
        first = store.put(
            _entry(body="the first wording", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260819-19u")
        )
        store.put(first.successor("DF", "the second wording").relabel("^c20260819-20u"))
        _surface(project_root, "- [DF] the second wording ^c20260819-20u")
        assert "Index.Linter/Record.Unplaced" not in _classes(lint(geo))

    def test_an_unsucceeded_record_off_every_surface_still_reports(self, geo, project_root):
        IndexStore(geo).put(
            _entry(body="orphan", support=[SupportRef("chat", "s1", "m1")])
            .relabel("^c20260819-21u")
        )
        assert "Index.Linter/Record.Unplaced" in _classes(lint(geo))


def test_no_corpus_scoped_check_reports_a_finding_about_one_record() -> None:
    """Scope and subject must agree, or a targeted run silently under-reports.

    `Check.record_scoped` decides whether a check is offered to `linter --label` /
    `--record-id`. A check left out of that set while still naming a record as its subject
    is a finding a targeted run can never produce — and the caller sees a clean result for
    a record that was never examined, which is worse than a slow one.

    Twice already: the gate checks reach records through a shared helper, and `line-drift`,
    `scope-kind` and `review-closure` reach them sideways through surface labels and trace
    members. Both were invisible to a scope derivation reading only the top-level body.
    Asserted structurally so the third one fails here rather than in the field.
    """

    import inspect
    import re

    from tarav.index.linter import CHECK_REGISTRY

    #: Subject expressions that name something other than a record. A trace, a surface, a
    #: label and a session are all legitimately corpus-scoped subjects.
    #: `blessing.id` is a Blessing.Record, which is a different subject in a different
    #: depot; the heuristic below only recognises the string `.id`.
    NOT_A_RECORD = ("trace.id", "str(ctx.store.directory)", "blessing.id")

    gaps: list[str] = []
    for check in CHECK_REGISTRY:
        if check.record_scoped:
            continue
        source = inspect.getsource(check.run)
        for poi_class, subject in re.findall(
            r'Finding\(\s*\n?\s*"([^"]+)",\s*\n?\s*([^,\n]+),', source
        ):
            subject = subject.strip()
            if ".id" in subject and subject not in NOT_A_RECORD:
                gaps.append(f"{check.name} reports {poi_class} about {subject}")

    assert gaps == [], (
        "these checks name a record as their subject but are not record-scoped, so "
        "`linter --record-id` would never report them: " + "; ".join(gaps)
    )


def test_check_scope_follows_through_a_module_local_helper() -> None:
    """A check that delegates its traversal is still the scope of what it traverses.

    `gate-verifies` and `gate-verifies-dev` are two-line wrappers over one shared body;
    reading only the wrapper called both corpus-scoped and dropped every
    `Gate.Evidence.Invalid` finding from targeted runs.
    """

    from tarav.index.linter import CHECK_REGISTRY

    by_name = {check.name: check for check in CHECK_REGISTRY}
    assert by_name["gate-verifies"].record_scoped
    assert by_name["gate-verifies-dev"].record_scoped


def test_a_reference_the_model_cannot_address_fails_the_current_assertion(
    geo, chat, tmp_path
) -> None:
    """`Current.Model.Only`: a superseded coordinate fails, exactly as any address that does not resolve.

    5,755 of the corpus's support refs address Chatlas1 turns — `turn-r1326`, or a provider
    uuid — which the current model cannot look up. They used to be siphoned into a class of
    their own, reported `BLOCKED`, and thereby excluded from the count of things that do not
    conform. That named migration history rather than a check result, and it hid the backlog
    inside a category the linter had to keep carrying.

    They now fail the one reference assertion, so the count of non-conformant refs *is* the
    migration's progress measure. The archive they name is preserved in the operands, which
    keeps the backlog legible without giving it a class.
    """

    from tarav.index.linter import Status, lint
    from tarav.index.record.model import LineRecord, SupportRef
    from tarav.index.record.store import IndexStore
    from tarav.index.scope import parse_scope

    chat("s-1", [("m-1", "user", "the turn that grounds it")])
    store = IndexStore(geo)
    record = store.put(
        LineRecord.create(
            parse_scope("d/design#Concept"),
            "DF",
            "a line grounded on a superseded coordinate",
            support=[
                SupportRef(archive="chat-turn", session_id="s-1", message_id="turn-r1326")
            ],
        )
    )

    report = lint(geo, subjects=[record.id])
    finding = next(
        f for f in report.findings if f.poi_class == "Index.Linter/Support.Unresolved"
    )
    assert finding.status is Status.FAILED, "non-conformant is a result, not an unknown"
    assert finding.operands["message"] == "turn-r1326"
    assert finding.operands["archive"] == "chat-turn"
    assert finding not in report.blocked


def test_a_message_coordinate_that_is_absent_does_not_resolve(geo, chat) -> None:
    """One assertion, one result: the archive named changes the evidence, never the class."""

    from tarav.index.linter import lint
    from tarav.index.record.model import LineRecord, SupportRef
    from tarav.index.record.store import IndexStore
    from tarav.index.scope import parse_scope

    chat("s-1", [("m-1", "user", "the turn that grounds it")])
    store = IndexStore(geo)
    record = store.put(
        LineRecord.create(
            parse_scope("d/design#Concept"),
            "DF",
            "a line citing a message that is not there",
            support=[SupportRef(archive="chat", session_id="s-1", message_id="m-absent")],
        )
    )

    report = lint(geo, subjects=[record.id])
    classes = {f.poi_class for f in (*report.findings, *report.blocked)}
    assert "Index.Linter/Support.Unresolved" in classes
