# Surfaces model workflow

## Implemented

- SurfacesWorkflow owns the registered MarkdownNormalModel and
  PythonNormalModel TaravObjects.
- Both classes expose from_text(text) and from_path(path). No file wrapper or
  common model base was introduced.
- Private parsing helpers live beside their owning models. The previous public
  normalize_markdown/normalize_python functions and modules were removed;
  Wiki, Breadcrumbs, mdblocks, and the retained CLI adapter use class methods.
- Records retain source text, extracted structures, positions, and diagnostics.
  Loading reconstructs the stored model without parsing the source again.
- Extracted elements and shared spans remain lightweight dataclasses.

## Verification

57 focused tests passed across native parsers, the retained surface adapter,
Wiki, object Record contracts, architecture, and Breadcrumbs. Eight stdlib CLI
tests passed, including the Markdown-block consumer. The editable installation
was refreshed and the installed CLI version and mdblocks help were checked.

## Capture

This note records implementation coordination. No implementation Diagram Draft
or Collection was created; that capture remains unreconciled.
