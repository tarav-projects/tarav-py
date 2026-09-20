from __future__ import annotations

import json

from tarav.breadcrumbs import BreadcrumbStore, breadcrumb_label


def test_store_separates_identity_observations_and_typed_attachments(tmp_path):
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    breadcrumb = store.create("a" * 64)
    surface = tmp_path / "surface.md"
    surface.write_text(f"before\n<!-- {breadcrumb_label('a' * 64)} -->\nafter\n")

    store.observe_position(
        "a" * 64,
        file=str(surface),
        line=2,
        previous_line="before",
        next_line="after",
    )
    store.attach("a" * 64, {"type": "Example.Annotation", "value": 3})

    main = json.loads((breadcrumb.directory / "main.json").read_text())
    assert main == {"type": "Tarav.Breadcrumb", "id": "a" * 64}
    shown = store.show("a" * 64)
    assert shown["observations"][0]["locator"]["locator"] == {
        "file": str(surface),
        "line": 2,
    }
    assert shown["observations"][0]["hints"] == {
        "previous_line": "before",
        "next_line": "after",
    }
    assert shown["attachments"] == [{"type": "Example.Annotation", "value": 3}]
    resolution = store.resolve(breadcrumb_label("a" * 64))
    assert resolution.ok
    assert resolution.position.line == 2


def test_resolution_reports_missing_and_multiple_recorded_positions(tmp_path):
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    store.create("b" * 64)
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("# absent\n")
    second.write_text("# absent\n")
    for path in (first, second):
        store.observe_position("b" * 64, file=str(path), line=1)
    assert store.resolve("b" * 64).status == "unresolvable"

    label = breadcrumb_label("b" * 64)
    first.write_text(f"# {label}\n")
    second.write_text(f"# {label}\n")
    resolution = store.resolve("b" * 64)
    assert resolution.status == "ambiguous"
    assert resolution.findings[0].code == "breadcrumb-position-ambiguous"
