from __future__ import annotations

from tarav.index2.scope import ScopeKind
from tarav.index2.surfaces import (
    ProjectIndex,
    discover_surfaces,
    read_annotation_lines,
    read_block_lines,
    read_surface,
    resolve_surface_path,
    surface_kind_for,
)

CHAPTER_SURFACE = "skills/tarav-pkg/homes/agent/chapters/100-design.md"

CHAPTER = """> `Appendix.Discovery`: check `appendix/Concept.Name-appendix.md`

****

## Index.Line.Record

- [DF] the record is the object describing the index entry ^d20260818-1u
- [CT] the record is complete ^d20260818-2u

****

## Line.Scope

- [DF] a scope is one address covering both hosting kinds
- an untyped legacy line

****
"""


def _chapter(project_root, text=CHAPTER):
    path = project_root / CHAPTER_SURFACE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _module(project_root, body, name="thing.py"):
    path = project_root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


class TestBlockHostedLines:
    def test_lines_are_scoped_by_a_block_path(self, project_root):
        lines = read_block_lines(_chapter(project_root), CHAPTER_SURFACE)
        scope = lines[0].scope
        assert scope.kind is ScopeKind.BLOCK
        assert scope.address == "tarav-pkg/design#Index.Line.Record"

    def test_type_body_and_anchor_are_parsed(self, project_root):
        first = read_block_lines(_chapter(project_root), CHAPTER_SURFACE)[0]
        assert first.line_type == "DF"
        assert first.body == "the record is the object describing the index entry"
        assert first.label == "^d20260818-1u"

    def test_untyped_and_unanchored_lines_still_parse(self, project_root):
        lines = read_block_lines(_chapter(project_root), CHAPTER_SURFACE)
        legacy = next(line for line in lines if line.body == "an untyped legacy line")
        assert legacy.line_type is None
        assert legacy.label is None

    def test_a_heading_without_its_separator_yields_no_lines(self, project_root):
        """tarav1 index blocks are separator-anchored; without `****` the lines are prose."""
        path = _chapter(project_root, "## C\n\n- [DF] no separator above this block\n")
        assert read_block_lines(path, CHAPTER_SURFACE) == []


class TestAnnotationHostedLines:
    def test_a_skw_note_is_an_index_line_scoped_by_its_attachment_point(self, project_root):
        path = _module(
            project_root,
            "# $kw: --from Some.Concept --note [DC] why the code is shaped this way\n",
        )
        lines = read_annotation_lines(path, "skw:thing.py")
        assert len(lines) == 1
        assert lines[0].line_type == "DC"
        assert lines[0].scope.kind is ScopeKind.ANNOTATION
        assert lines[0].scope.file == "thing.py"

    def test_a_dependency_only_annotation_hosts_no_line(self, project_root):
        path = _module(project_root, "# $kw: --from Some.Concept\n", name="bare.py")
        assert read_annotation_lines(path, "skw:bare.py") == []

    def test_the_same_mechanism_serves_both_hosting_kinds(self, project_root):
        """One reader, dispatching on kind — that is what 'same mechanism' means."""
        chapter = _chapter(project_root)
        module = _module(
            project_root, "# $kw: --from C --note [CT] annotation-hosted\n"
        )
        block_lines = read_surface(chapter, CHAPTER_SURFACE)
        annotation_lines = read_surface(module, "skw:thing.py")
        assert block_lines and annotation_lines
        assert block_lines[0].scope.kind is ScopeKind.BLOCK
        assert annotation_lines[0].scope.kind is ScopeKind.ANNOTATION


class TestDiscovery:
    def test_chapters_are_discovered(self, geo, project_root):
        _chapter(project_root)
        assert CHAPTER_SURFACE in discover_surfaces(geo, project_root)

    def test_annotated_product_surfaces_are_discovered(self, geo, project_root):
        _module(project_root, "# $kw: --from C --note [CT] found\n", name="pkg/thing.py")
        assert "skw:pkg/thing.py" in discover_surfaces(geo, project_root)

    def test_unannotated_python_is_not_an_index_surface(self, geo, project_root):
        _module(project_root, "x = 1\n", name="plain.py")
        assert "skw:plain.py" not in discover_surfaces(geo, project_root)

    def test_surface_kinds_are_classified(self):
        assert surface_kind_for("skw:a/b.py") == "skw"
        assert surface_kind_for("skills/d/homes/ceo/appendix/x.md") == "appendix"
        assert surface_kind_for(CHAPTER_SURFACE) == "chapter"

    def test_a_skw_surface_resolves_to_its_product_file(self, project_root):
        assert resolve_surface_path("skw:pkg/a.py", project_root) == project_root / "pkg/a.py"


class TestHomesLayout:
    def test_ensure_layout_creates_both_homes_asymmetrically(self, project_root):
        index = ProjectIndex(project_root, "tarav-pkg")
        index.ensure_layout()
        agent_home = index.depot_root / "homes" / "agent"
        assert index.chapters_dir.exists()
        assert (agent_home / ".tarav.index").exists()
        assert not (agent_home / "chapters").exists()

    def test_a_user_home_is_not_agent_writable(self, project_root):
        import pytest

        from tarav.index2.authority import AuthorityGuardError

        with pytest.raises(AuthorityGuardError):
            ProjectIndex(project_root, "tarav-pkg", home="ceo").assert_writable()

    def test_the_agent_home_is_writable(self, project_root):
        ProjectIndex(project_root, "tarav-pkg", home="agent").assert_writable()
