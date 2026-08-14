# $kw: ^skw-surface-adapter-tests --from Skw.Backend --from Floor.Model --note [TP] native models map into one shared Skillware carrier model ^c20260812-0u
from __future__ import annotations

from tarav.skillware.adapters import adapt_markdown_skw, adapt_python_skw
from tarav.skillware.model import parse_skw_model
from tarav.surfaces.markdown import normalize_markdown
from tarav.surfaces.python import normalize_python


def test_python_adapter_classifies_host_annotations() -> None:
    surface = adapt_python_skw(
        normalize_python("# $kw: --from Design.Retry\nx = 1  # noqa\n# prose\n")
    )
    assert surface.lines[0].open_content == "--from Design.Retry"
    assert [annotation.classification for annotation in surface.annotations] == [
        "unclassified",
        "external-directive",
        "unclassified",
    ]
    parsed = parse_skw_model(surface)
    assert parsed.dependencies[0].froms == ("Design.Retry",)


def test_markdown_adapter_maps_native_headings_and_fences() -> None:
    surface = adapt_markdown_skw(
        normalize_markdown(
            "> $kw: --from Design.Retry\n# Boundary\n```\n> $kw: --from Inert\n```\n"
        )
    )
    assert surface.lines[0].open_content == "--from Design.Retry"
    assert surface.lines[1].boundary_name == "Boundary"
    assert surface.lines[2].fence is True
    assert surface.lines[4].fence is True
    parsed = parse_skw_model(surface)
    assert [dependency.froms for dependency in parsed.dependencies] == [
        ("Design.Retry",)
    ]
