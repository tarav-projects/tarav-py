# $kw: ^native-surface-tests --from Floor.Model --from Normalization.Pipeline --note [TP] native models remain small and independent of Skillware syntax ^c20260812-0u
from __future__ import annotations

from agentos.surfaces.markdown import normalize_markdown
from agentos.surfaces.python import normalize_python


def test_python_normalizer_uses_tokens_and_classifies_external_directives() -> None:
    model = normalize_python(
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
    model = normalize_python("# retained\nvalue = '''\n")
    assert [comment.text for comment in model.comments] == ["# retained"]
    assert len(model.diagnostics) == 1


def test_markdown_normalizer_recognizes_headings_outside_fences() -> None:
    model = normalize_markdown("# First\n```python\n## Inert\n```\n### Last\n")
    assert [(heading.level, heading.text) for heading in model.headings] == [
        (1, "First"),
        (3, "Last"),
    ]
    assert len(model.fences) == 1
    assert model.fences[0].start.start_line == 2
    assert model.fences[0].end is not None
    assert model.fences[0].end.start_line == 4


def test_markdown_normalizer_retains_unclosed_fence() -> None:
    model = normalize_markdown("~~~\ncontent\n")
    assert len(model.fences) == 1
    assert model.fences[0].end is None


def test_markdown_normalizer_requires_a_matching_complete_fence_closer() -> None:
    model = normalize_markdown(
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
