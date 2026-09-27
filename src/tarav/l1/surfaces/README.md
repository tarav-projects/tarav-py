# Native surface models

SurfacesWorkflow owns MarkdownNormalModel and PythonNormalModel, both registered
TaravObjects. Construct them with `from_text(text)` or `from_path(path)`.
Parsing helpers live in each model's module; the model class is the public
entrypoint. No file wrapper or shared model base is required.

Models contain the text and parsed structures from that invocation. Their
Records preserve those structures, positions, and diagnostics without rerunning
the parser. Shared spans and extracted items remain lightweight dataclasses.
Consumers such as Wiki and Breadcrumbs supply domain interpretation.

The standalone `tarav surfaces` command is disconnected from runtime composition.
Its command adapter remains here for deliberate future reuse, with isolated
tests. The Surfaces workflow is registered independently from that CLI adapter.

The Markdown parser remains an active dependency of `tarav.stdlib.mdblocks`.
Do not remove it or confuse this retained parser foundation with the retired
Skillware annotation compiler. Python parser tests are also retained.
