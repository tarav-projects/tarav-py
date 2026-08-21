from __future__ import annotations

import pytest

from tarav.index.scope import (
    LineScope,
    ScopeError,
    ScopeKind,
    annotation_scope,
    block_scope,
    parse_scope,
    resolve_scope_surface,
)


class TestBlockPath:
    def test_a_block_path_scopes_a_kernel_block(self):
        scope = parse_scope("tarav-pkg/design#Scope.Axis")
        assert scope.kind is ScopeKind.BLOCK
        assert (scope.depot, scope.chapter, scope.concept) == (
            "tarav-pkg",
            "design",
            "Scope.Axis",
        )

    def test_the_label_is_the_concept(self):
        assert parse_scope("d/design#Touched.Data").label == "Touched.Data"

    def test_round_trips_through_its_address(self):
        address = "tarav-pkg/design#Index.Line.Record"
        assert parse_scope(address).address == address

    def test_a_typed_concept_scope_uses_the_canonical_double_colon(self):
        scope = parse_scope("tarav-pkg/design#Natural.Placement::Skills")
        assert scope.concept == "Natural.Placement::Skills"


class TestLocatorName:
    def test_a_locator_scopes_an_annotation_attachment_point(self):
        scope = parse_scope("@src/tarav/index/linter.py/Finding")
        assert scope.kind is ScopeKind.ANNOTATION
        assert scope.file == "src/tarav/index/linter.py"
        assert scope.region == "Finding"

    def test_the_at_sigil_is_agent_maintained_and_may_be_omitted(self):
        assert parse_scope("src/a.py/Thing").address == "@src/a.py/Thing"

    def test_a_file_without_a_region_is_still_a_scope(self):
        scope = parse_scope("@src/a.py")
        assert scope.kind is ScopeKind.ANNOTATION
        assert scope.region is None

    def test_the_label_falls_back_to_the_region(self):
        assert parse_scope("@src/a.py/Finding").label == "Finding"


class TestOneAddressSpace:
    def test_both_kinds_are_the_same_type(self):
        assert isinstance(block_scope("d", "design", "C"), LineScope)
        assert isinstance(annotation_scope("src/a.py", "C"), LineScope)

    def test_an_illegal_address_is_refused(self):
        with pytest.raises(ScopeError, match="not a legal scope address"):
            parse_scope("just some words")

    def test_an_empty_address_is_refused(self):
        with pytest.raises(ScopeError, match="empty"):
            parse_scope("   ")


class TestResolution:
    def test_a_block_resolves_through_the_depot_layout(self, project_root):
        chapters = project_root / "skills/tarav-pkg/design"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("", encoding="utf-8")
        path = resolve_scope_surface(parse_scope("tarav-pkg/design#C"), project_root)
        assert path == chapters / "100-design.md"

    def test_an_annotation_resolves_to_its_product_file(self, project_root):
        path = resolve_scope_surface(parse_scope("@src/a.py/Thing"), project_root)
        assert path == project_root / "src/a.py"

    def test_both_kinds_answer_the_same_question(self, project_root):
        """One resolver, because name syntax does not change the entity's semantics."""
        chapters = project_root / "skills/d/design"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("", encoding="utf-8")
        for address in ("d/design#C", "@src/a.py/C"):
            assert resolve_scope_surface(parse_scope(address), project_root) is not None


class TestStructuralResolution:

    def _chapter(self, root):
        path = root / "skills" / "d" / "design" / "100-design.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("****\n\n## C\n\n****\n", encoding="utf-8")
        return path

    def test_a_chapter_in_the_depot_resolves(self, project_root):
        expected = self._chapter(project_root)
        assert resolve_scope_surface(parse_scope("d/design#C"), project_root) == expected

    def test_a_chapter_in_no_depot_resolves_to_nothing(self, project_root):
        assert resolve_scope_surface(parse_scope("d/design#C"), project_root) is None


class TestSurfaceDisambiguation:
    def test_contains_picks_the_file_holding_the_line(self, tmp_path):
        """Several files can answer to one chapter name.

        `100-design.md` and `900-design.md` are both the `design` chapter, so
        globbing alone points a revision at whichever sorts first. The label of a
        line known to be on the surface is what distinguishes them.
        """
        from tarav.index.scope import block_scope, resolve_scope_surface

        chapters = tmp_path / "skills" / "pkg" / "design"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("- [DF] other ^c20260819-19u\n")
        (chapters / "900-design.md").write_text("- [DF] wanted ^c20260819-20u\n")

        scope = block_scope("pkg", "design", "Concept")
        assert resolve_scope_surface(scope, tmp_path).name == "100-design.md"
        found = resolve_scope_surface(scope, tmp_path, contains="^c20260819-20u")
        assert found.name == "900-design.md"

    def test_an_unmatched_label_falls_back_to_the_first(self, tmp_path):
        from tarav.index.scope import block_scope, resolve_scope_surface

        chapters = tmp_path / "skills" / "pkg" / "design"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("- [DF] other ^c20260819-19u\n")
        scope = block_scope("pkg", "design", "Concept")
        found = resolve_scope_surface(scope, tmp_path, contains="^nope-0u")
        assert found.name == "100-design.md"
