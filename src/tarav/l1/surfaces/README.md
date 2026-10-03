# Native surface models

SurfacesWorkflow owns MarkdownNormalModel and PythonNormalModel, both registered
TaravObjects. Construct them with `from_text(text)` or `from_path(path)`.
Parsing helpers live in each model's module; the model class is the public
entrypoint. No file wrapper or shared model base is required.

Models contain the text and parsed structures from that invocation. Their
Records preserve those structures, positions, and diagnostics without rerunning
the parser. Shared spans and extracted items remain lightweight dataclasses.
Consumers such as Wiki and Breadcrumbs supply domain interpretation.

`LineMarkdownModel` is a strict subtype of MarkdownNormalModel for Markdown
formats a project owns. In its dialect every block delimiter sits alone on its
own line: code fences open and close on separate lines, and `$$` opens or
closes a math block only as the whole line. It is a floor: `from_text` raises
`LineMarkdownViolation` (rule, message, span) at the first violation and returns
no partial model, because later structure cannot be trusted. Its model adds
`math_blocks`, and headings inside fences or math blocks are not headings.
Higher-resolution parsers consume the model rather than the text; mapping a
violation to a POI belongs to the consuming workflow.

The standalone `tarav surfaces` command is disconnected from runtime composition.
Its command adapter remains here for deliberate future reuse, with isolated
tests. The Surfaces workflow is registered independently from that CLI adapter.

The Markdown parser remains an active dependency of `tarav.stdlib.mdblocks`.
Do not remove it or confuse this retained parser foundation with the retired
Skillware annotation compiler. Python parser tests are also retained.
