"""JSON metadata and TOML comments through the Breadcrumb transaction."""
# tarav.breadcrumb b6216ffba709

import json
import tomllib

import pytest

from tarav.l1.breadcrumbs import BreadcrumbError
from tarav.l1.breadcrumbs.store import BreadcrumbStore
from tarav.l1.breadcrumbs.surfaces import infer_surface_language, submit_annotations
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow, PreparedAnnotation
from tarav.l2.breadcrumb_workflows.chatlas_context.workflow import provisional_markers
from tarav.l3.cli.cli import main


MARKER = "tarav.context abcdef12:0123456789abcdef"


class Markers(BreadcrumbAnnotationWorkflow):
    name = "test-data"

    def prepare(self, surface, request):
        return tuple(PreparedAnnotation(item.position, MARKER, None)
                     for item in provisional_markers(surface.text, surface.language))

    def attachments(self, annotation, breadcrumb_id):
        return ()

    def audit(self, context, request):
        return ()


@pytest.mark.parametrize("language", ["json", "toml"])
def test_submit_resolve_and_cli_audit_data_surfaces(tmp_path, capsys, language):
    path = tmp_path / ("config." + language)
    text = (json.dumps({"enabled": True, "example": MARKER,
                        "tarav.breadcrumbs": [MARKER]}, indent=2) + "\n"
            if language == "json" else f'enabled = true # {MARKER}\nexample = "{MARKER}"\n')
    path.write_text(text)
    store = BreadcrumbStore(tmp_path / "store")
    result = submit_annotations(path, store=store, workflow=Markers(), request=None)
    [breadcrumb] = result.breadcrumbs
    assert infer_surface_language(path) == language
    parsed = json.loads(path.read_text()) if language == "json" else tomllib.loads(path.read_text())
    assert parsed["enabled"] is True
    assert parsed["example"] == MARKER
    if language == "json":
        assert parsed["tarav.breadcrumbs"] == [breadcrumb.label]
    assert store.resolve(breadcrumb.id).position.path == path
    assert main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(path),
                 "--breadcrumbs-root", str(store.root), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["language"] == language
    assert [(r["id"], r["status"]) for r in report["breadcrumbs"]] == [(breadcrumb.id, "resolved")]


def test_json_uses_only_explicit_metadata_and_preserves_string_spans():
    text = json.dumps({"text": MARKER, "nested": [{"tarav.breadcrumbs": [MARKER]}]}, indent=2)
    [marker] = provisional_markers(text, "json")
    position = marker.position
    line = text.splitlines()[position.line - 1]
    assert json.loads(line[position.start_column:position.end_column]) == MARKER
    assert (marker.alias, marker.turn_prefix) == ("abcdef12", "0123456789abcdef")


def test_compact_json_replaces_multiple_markers_without_shifting_spans(tmp_path):
    path = tmp_path / "compact.json"
    path.write_text(json.dumps({"tarav.breadcrumbs": [MARKER, MARKER], "value": 4}))
    store = BreadcrumbStore(tmp_path / "store")
    result = submit_annotations(path, store=store, workflow=Markers(), request=None)
    parsed = json.loads(path.read_text())
    assert parsed["tarav.breadcrumbs"] == [b.label for b in result.breadcrumbs]
    assert len(result.breadcrumbs) == 2 and parsed["value"] == 4
    assert all(store.resolve(b.id).position.path == path for b in result.breadcrumbs)


def test_toml_does_not_read_comments_inside_any_string_form():
    text = '''basic = "# tarav.context abcdef12:1111111111111111"
literal = '# tarav.context abcdef12:2222222222222222'
multi = """inside
# tarav.context abcdef12:3333333333333333
"""
multi_literal = ''' + "'''inside\n# tarav.context abcdef12:4444444444444444\n'''\n" + '''value = "escaped \\\" # still a string" # tarav.context abcdef12:0123456789abcdef
'''
    [marker] = provisional_markers(text, "toml")
    assert marker.turn_prefix == "0123456789abcdef"
    assert marker.position.line == 9


@pytest.mark.parametrize("text", [
    '{"tarav.breadcrumbs": ["bad",}',
    '{"tarav.breadcrumbs": "bad"}',
    '{"tarav.breadcrumbs": [12]}',
    '{"tarav.breadcrumbs": [], "tarav.breadcrumbs": []}',
])
def test_invalid_json_is_rejected_before_retaining_any_breadcrumb(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    store = BreadcrumbStore(tmp_path / "store")
    with pytest.raises(BreadcrumbError):
        submit_annotations(path, store=store, workflow=Markers(), request=None)
    assert path.read_text() == text
    assert not store.root.exists()


def test_invalid_toml_is_rejected():
    with pytest.raises(BreadcrumbError, match="Invalid TOML"):
        provisional_markers('value = "unterminated\n# ' + MARKER, "toml")


@pytest.mark.parametrize("language, text", [
    ("json", '{"tarav.breadcrumbs": ["tarav.breadcrumb wrong", "tarav.context wrong"]}'),
    ("toml", '# tarav.breadcrumb wrong\n# tarav.context wrong\n'),
])
def test_cli_audit_reports_malformed_data_markers(tmp_path, capsys, language, text):
    path = tmp_path / ("bad." + language)
    path.write_text(text)
    main(["breadcrumbs", "audit", "chatlas-context", "--surface", str(path),
          "--breadcrumbs-root", str(tmp_path / "store"), "--json"])
    report = json.loads(capsys.readouterr().out)
    assert {p["type"] for p in report["pois"]} >= {
        "Tarav.Breadcrumbs.Audit.POI.LabelMalformed",
        "Tarav.Breadcrumbs.Audit.POI.ChatlasContext.MarkerMalformed"}
