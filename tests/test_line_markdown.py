"""LineMarkdown is a floor: exact on conforming text, a hard stop otherwise."""

import pytest

from tarav.l1.surfaces.markdown import (
    LineMarkdownModel,
    LineMarkdownViolation,
    MarkdownNormalModel,
)
from tarav.l1.surfaces.markdown.line import (
    FENCE_INLINE_CLOSE,
    FENCE_UNCLOSED,
    MATH_NOT_ALONE,
    MATH_UNCLOSED,
)

CONFORMING = """# Title

Prose with inline $x$ math.

$$
E = mc^2 \\tag{1}
# not a heading
```
$$

```python
$$ not math inside code
# not a heading either
```

## Section ##
"""


def test_conforming_text_yields_blocks_and_headings():
    model = LineMarkdownModel.from_text(CONFORMING)

    assert isinstance(model, MarkdownNormalModel)
    assert [(h.level, h.text, h.span.start_line) for h in model.headings] == [
        (1, "Title", 1),
        (2, "Section", 16),
    ]
    assert [(b.start.start_line, b.end.start_line) for b in model.math_blocks] == [(5, 9)]
    assert [(f.marker, f.start.start_line, f.end.start_line) for f in model.fences] == [
        ("`", 11, 14)
    ]
    assert model.diagnostics == ()
    assert model.math_line_numbers() == frozenset(range(5, 10))
    assert model.fenced_line_numbers() == frozenset(range(11, 15))


def test_record_round_trip_preserves_math_blocks():
    model = LineMarkdownModel.from_text(CONFORMING)

    restored = LineMarkdownModel.from_record(model.to_record())

    assert restored == model


@pytest.mark.parametrize(
    ("text", "rule", "line"),
    [
        ("intro\n\n$$ x = 1 $$\n", MATH_NOT_ALONE, 3),
        ("$$ x = 1\n$$\n", MATH_NOT_ALONE, 1),
        ("$$\nx = 1 $$\n", MATH_NOT_ALONE, 2),
        ("$$\nx = 1\n$$ (3)\n", MATH_NOT_ALONE, 3),
        ("text $$x$$ text\n", MATH_NOT_ALONE, 1),
        ("ok\n$$\nx = 1\n", MATH_UNCLOSED, 2),
        ("```x```\n", FENCE_INLINE_CLOSE, 1),
        ("a\n```\ncode\n", FENCE_UNCLOSED, 2),
    ],
)
def test_each_rule_stops_with_its_code_and_line(text, rule, line):
    with pytest.raises(LineMarkdownViolation) as raised:
        LineMarkdownModel.from_text(text)

    assert raised.value.rule == rule
    assert raised.value.line == line


def test_parsing_stops_at_the_first_violation():
    text = "$$ a $$\n\n```b```\n"

    with pytest.raises(LineMarkdownViolation) as raised:
        LineMarkdownModel.from_text(text)

    assert (raised.value.rule, raised.value.line) == (MATH_NOT_ALONE, 1)


def test_escaped_dollars_and_tilde_info_strings_conform():
    model = LineMarkdownModel.from_text("costs \\$$5\n\n~~~ `odd` info\nx\n~~~\n")

    assert [f.marker for f in model.fences] == ["~"]


def test_lenient_parser_is_unchanged_on_floor_violations():
    lenient = MarkdownNormalModel.from_text("```x```\nrest\n")

    assert type(lenient) is MarkdownNormalModel
    assert lenient.fences[0].end is None
