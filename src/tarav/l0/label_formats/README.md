# LabelFormats

`Label` is the shared immutable string value for structured semantic labels.
`LabelFormatsWorkflow` owns the vocabulary. A label is editable by replacement;
Ships provide identity separately.
<!-- tarav.breadcrumb 76715cd25f4c -->

```python
from tarav.l0.label_formats import Label, DottedFormat

Label("Semantic.Independence.And.Integration")
Label("/properties/text")
Label("")  # JSON Pointer root

class DottedLabel(Label):
    formats = (DottedFormat,)
```

DottedFormat requires at least two capitalized alphanumeric segments separated
by dots. JSONPointerFormat follows RFC 6901 string syntax, including ~0/~1
escapes and the empty root. Input is preserved exactly, without normalization.
Malformed input raises ValueError; non-string input raises TypeError. Pydantic
fields parse the same values and expose each permitted pattern in JSON Schema.
Subtypes can narrow or extend `formats` with classes providing `pattern` and
`matches(text)`. No unrestricted free-text fallback is provided.

Consumers:

- `TaravClass.name` validates a nonempty Label; Record loading uses the same type.
- `tarav.l1.lines.LabelLine` carries a Label as a contextual Line; its text setter
  validates edits. `tarav.l1.notebook.evidence.ReviewedLabel` adds Notebook support
  and review requirements. Both remain normal Lines in their authoring Blocks.
- PathRegistry uses JSONPointerFormat specifically for positions within a View.
  Accepting dotted labels there would violate the path contract.
- The extension reads LabelLine titles and can search both dotted and path forms.

The Python BlockTitle and ReviewedBlockTitle APIs were removed. Their existing
Type Ships and wire names (`Tarav.Lines.BlockTitle` and
`Tarav.Notebook.ReviewedBlockTitle`) remain the declared identities of LabelLine
and ReviewedLabel. This avoids rewriting exact historical Git states or
invalidating existing review evidence. There are no Python compatibility aliases.

Ordinary captions, file names, SKW local slugs, schema producer keys (`record`,
`instance`) and other text fields do not automatically become semantic Labels.
This workflow adds no Path Notebook or schema viewer.
