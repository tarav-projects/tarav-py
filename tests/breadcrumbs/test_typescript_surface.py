"""TypeScript as a native Breadcrumb surface (request 885)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import entity
from tarav.l1.breadcrumbs import BreadcrumbError
from tarav.l1.breadcrumbs.store import BreadcrumbStore
from tarav.l1.breadcrumbs.surfaces import (
    infer_surface_language,
    render_surface_label,
    submit_annotations,
)
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow, PreparedAnnotation
from tarav.l1.surfaces import SurfacesWorkflow
from tarav.l1.surfaces.typescript import TypeScriptNormalModel
from tarav.l2.breadcrumb_workflows.chatlas_context.workflow import provisional_markers
from tarav.l3.cli.cli import main

TRICKY = '''// head comment
const url = "https://example.com"; // after a string
const single = 'it\\'s // not a comment';
const regex = /["'\\/]/g; // after a regex
const slashes = /\\/\\//.test(url);
const ratio = width / height; // division, then a comment
const inClass = /[/]+/;
const html = `<a href="//x">${items.map((item) => `<b>${item["//"]}</b>`).join("")}</a>`;
/* block // with slashes */
function f() { return /a\\/b/.source; }
const object = { key: "}" }; // braces in strings
'''


def _line_comments(text: str) -> list[tuple[int, str]]:
    model = TypeScriptNormalModel.from_text(text)
    assert model.diagnostics == ()
    return [(item.span.start_line, item.text) for item in model.comments if item.kind == "line"]


# tarav.breadcrumb 4410faf72d338db67f784063310687d6a41d266dacb28ac0673e61c501613ba0
def test_lexer_finds_only_real_comments() -> None:
    assert _line_comments(TRICKY) == [
        (1, "// head comment"),
        (2, "// after a string"),
        (4, "// after a regex"),
        (6, "// division, then a comment"),
        (11, "// braces in strings"),
    ]
    blocks = [item for item in TypeScriptNormalModel.from_text(TRICKY).comments
              if item.kind == "block"]
    assert [(item.span.start_line, item.text) for item in blocks] == [
        (9, "/* block // with slashes */")]


def test_comment_spans_are_columns_on_their_line() -> None:
    text = 'call(); // tarav.context abcdef12:0123456789abcdef\n'
    (comment,) = TypeScriptNormalModel.from_text(text).comments
    assert (comment.span.start_line, comment.span.start_column) == (1, 8)
    assert text.splitlines()[0][comment.span.start_column:comment.span.end_column] == comment.text


@pytest.mark.parametrize("text, message", [
    ("const a = `open ${b}", "template"),
    ("const a = 'open\n", "string"),
    ("/* open", "block comment"),
    ("const a = /open\n", "regular expression"),
])
def test_unterminated_tokens_are_diagnostics(text: str, message: str) -> None:
    diagnostics = TypeScriptNormalModel.from_text(text).diagnostics
    assert len(diagnostics) == 1 and message in diagnostics[0].message


def test_model_is_a_surfaces_record() -> None:
    model = TypeScriptNormalModel.from_text(TRICKY)
    assert entity(TypeScriptNormalModel).workflow is SurfacesWorkflow()
    restored = TypeScriptNormalModel.records.from_record(model.records.to_record())
    assert restored.comments == model.comments


def test_language_and_label_rendering() -> None:
    for suffix in (".ts", ".tsx", ".mts", ".cts"):
        assert infer_surface_language(Path("a" + suffix)) == "typescript"
    assert render_surface_label("typescript", "tarav.breadcrumb x") == "// tarav.breadcrumb x"


def test_context_markers_only_in_line_comments() -> None:
    text = (
        "// tarav.context abcdef12:0123456789abcdef\n"
        "const s = '// tarav.context abcdef12:fedcba9876543210';\n"
        "/* tarav.context abcdef12:1111111111111111 */\n"
        "run(); // tarav.context abcdef12:2222222222222222\n"
    )
    markers = provisional_markers(text, "typescript")
    assert [(item.position.line, item.position.start_column) for item in markers] == [(1, 0), (4, 7)]


def test_markers_refuse_a_surface_the_lexer_lost() -> None:
    with pytest.raises(BreadcrumbError, match="TypeScript surface has normalization"):
        provisional_markers("const a = `open\n// tarav.context abcdef12:0123456789abcdef\n", "typescript")


class _MarkerOnly(BreadcrumbAnnotationWorkflow):
    """Submits every chatlas-context marker without resolving a session."""

    name = "test-markers"

    def prepare(self, surface, request):
        return tuple(PreparedAnnotation(item.position, "provisional", item)
                     for item in provisional_markers(surface.text, surface.language))

    def attachments(self, annotation, breadcrumb_id):
        return ()

    def audit(self, context, request):
        return ()


def test_submit_replaces_the_comment_and_audit_reads_the_label(
    tmp_path: Path, capsys,
) -> None:
    surface = tmp_path / "view.ts"
    surface.write_text(
        "export const a = 1; // tarav.context abcdef12:0123456789abcdef\n"
        "const s = `// tarav.context abcdef12:0123456789abcdef`;\n",
        encoding="utf-8",
    )
    store_root = tmp_path / "store"
    result = submit_annotations(surface, store=BreadcrumbStore(store_root),
                                workflow=_MarkerOnly(), request=None)
    assert result.language == "typescript" and len(result.breadcrumbs) == 1
    lines = surface.read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"export const a = 1; // {result.breadcrumbs[0].label}"
    assert lines[1].startswith("const s = `// tarav.context")

    assert main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(surface),
                 "--breadcrumbs-root", str(store_root), "--json"]) in (0, 1)
    report = json.loads(capsys.readouterr().out)
    assert report["language"] == "typescript"
    assert [item["id"] for item in report["breadcrumbs"]] == [result.breadcrumbs[0].id]


def test_audit_reports_a_malformed_label(tmp_path: Path, capsys) -> None:
    surface = tmp_path / "broken.ts"
    surface.write_text("// tarav.breadcrumb not-an-id\n", encoding="utf-8")
    main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(surface),
          "--breadcrumbs-root", str(tmp_path / "store"), "--json"])
    assert "malformed" in capsys.readouterr().out.lower()
