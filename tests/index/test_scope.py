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
    def test_a_block_resolves_through_the_home_layout(self, project_root):
        chapters = project_root / "skills/tarav-pkg/homes/agent/chapters"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("", encoding="utf-8")
        path = resolve_scope_surface(parse_scope("tarav-pkg/design#C"), project_root)
        assert path == chapters / "100-design.md"

    def test_an_annotation_resolves_to_its_product_file(self, project_root):
        path = resolve_scope_surface(parse_scope("@src/a.py/Thing"), project_root)
        assert path == project_root / "src/a.py"

    def test_both_kinds_answer_the_same_question(self, project_root):
        """One resolver, because name syntax does not change the entity's semantics."""
        chapters = project_root / "skills/d/homes/ceo/chapters"
        chapters.mkdir(parents=True)
        (chapters / "100-design.md").write_text("", encoding="utf-8")
        for address in ("d/design#C", "@src/a.py/C"):
            assert resolve_scope_surface(parse_scope(address), project_root) is not None


class TestHomeAgnosticResolution:
    """A Block.Path names a depot and a chapter, never a home — no home is the SSOT."""

    def _chapter(self, root, home):
        path = root / "skills" / "d" / "homes" / home / "chapters" / "100-design.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("****\n\n## C\n\n****\n", encoding="utf-8")
        return path

    def test_a_chapter_in_the_user_home_resolves(self, project_root):
        expected = self._chapter(project_root, "ceo")
        assert resolve_scope_surface(parse_scope("d/design#C"), project_root) == expected

    def test_a_chapter_in_the_agent_home_resolves(self, project_root):
        expected = self._chapter(project_root, "agent")
        assert resolve_scope_surface(parse_scope("d/design#C"), project_root) == expected

    def test_a_chapter_in_no_home_resolves_to_nothing(self, project_root):
        assert resolve_scope_surface(parse_scope("d/design#C"), project_root) is None
