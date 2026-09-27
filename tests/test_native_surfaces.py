# $kw: ^native-surface-tests --from Floor.Model --from Normalization.Pipeline --note [TP] native models remain small and independent of Skillware syntax ^c20260812-0u
from __future__ import annotations

from tarav.surfaces.markdown import MarkdownNormalModel
from tarav.surfaces.python import PythonNormalModel


def test_models_own_parsing_and_round_trip_without_reparsing(tmp_path, monkeypatch):
    from tarav.kernel import TaravObject, entity
    from tarav.runtime import create_runtime
    from tarav.surfaces import SurfacesWorkflow

    runtime = create_runtime()
    assert runtime.workflows.get("surfaces") is SurfacesWorkflow
    for model_type, text in (
        (MarkdownNormalModel, "# Title\n```py\nx = 1\n```\n"),
        (PythonNormalModel, "# noqa\ndef example():\n    pass\n"),
        (PythonNormalModel, "def broken(:\n"),
    ):
        path = tmp_path / "source"
        path.write_text(text)
        model = model_type.from_path(path)
        assert isinstance(model, TaravObject)
        assert entity(model_type).workflow is SurfacesWorkflow()
        assert model == model_type.from_text(text)
        record = model.to_record()
        with monkeypatch.context() as patch:

            def fail(*args, **kwargs):
                raise AssertionError("Record loading must not reparse")

            patch.setattr(model_type, "from_text", fail)
            restored = runtime.records.from_record(record)
        assert restored == model
        assert restored.to_record() == record
        path.write_text("changed")
        assert model.text == text


def test_python_normalizer_uses_tokens_and_classifies_external_directives() -> None:
    model = PythonNormalModel.from_text(
        "value = '# inert'\n"
        "other = 1  # type: ignore[arg-type]\n"
        "# noqa: F403\n"
        "# ordinary explanation\n"
    )
    assert [comment.text for comment in model.comments] == [
        "# type: ignore[arg-type]",
        "# noqa: F403",
        "# ordinary explanation",
    ]
    assert [directive.kind for directive in model.directives] == [
        "typing-ignore",
        "lint-noqa",
    ]
    assert model.comments[-1].directive is None
    assert model.comments[0].span.start_line == 2
    assert not model.diagnostics


def test_python_normalizer_retains_partial_model_on_scanner_error() -> None:
    model = PythonNormalModel.from_text("# retained\nvalue = '''\n")
    assert [comment.text for comment in model.comments] == ["# retained"]
    assert not model.elements
    assert len(model.diagnostics) == 1


def test_python_normalizer_exposes_minimal_nested_declarations() -> None:
    model = PythonNormalModel.from_text(
        "@decorate(\n"
        "    option=True,\n"
        ")\n"
        "class Outer:\n"
        "    def method(\n"
        "        self,\n"
        "    ):\n"
        "        async def nested():\n"
        "            return None\n"
        "        return nested\n"
    )

    assert [
        (element.kind, element.name, element.qualified_name)
        for element in model.elements
    ] == [
        ("class", "Outer", "Outer"),
        ("function", "method", "Outer.method"),
        ("async-function", "nested", "Outer.method.nested"),
    ]
    assert model.elements[0].span.start_line == 1
    assert model.elements[0].span.end_line == 10
    assert model.elements[1].span.start_line == 5
    assert model.elements[2].span.start_line == 8


def test_python_normalizer_reports_syntax_failure_without_inventing_elements() -> None:
    model = PythonNormalModel.from_text("# retained\ndef broken(:\n    pass\n")

    assert [comment.text for comment in model.comments] == ["# retained"]
    assert not model.elements
    assert model.diagnostics


def test_markdown_normalizer_recognizes_headings_outside_fences() -> None:
    model = MarkdownNormalModel.from_text(
        "# First\n```python\n## Inert\n```\n### Last\n"
    )
    assert [(heading.level, heading.text) for heading in model.headings] == [
        (1, "First"),
        (3, "Last"),
    ]
    assert len(model.fences) == 1
    assert model.fences[0].start.start_line == 2
    assert model.fences[0].end is not None
    assert model.fences[0].end.start_line == 4


def test_markdown_normalizer_retains_unclosed_fence() -> None:
    model = MarkdownNormalModel.from_text("~~~\ncontent\n")
    assert len(model.fences) == 1
    assert model.fences[0].end is None


def test_markdown_normalizer_requires_a_matching_complete_fence_closer() -> None:
    model = MarkdownNormalModel.from_text(
        "## Before ###\n"
        "````python\n"
        "```\n"
        "```` trailing\n"
        "~~~\n"
        "## Inert\n"
        "`````\n"
        "### After ###\n"
    )

    assert [(heading.level, heading.text) for heading in model.headings] == [
        (2, "Before"),
        (3, "After"),
    ]
    assert len(model.fences) == 1
    fence = model.fences[0]
    assert (fence.marker, fence.length, fence.closing_length) == ("`", 4, 5)
    assert fence.start.start_line == 2
    assert fence.end is not None and fence.end.start_line == 7
    assert model.fenced_line_numbers() == frozenset(range(2, 8))
