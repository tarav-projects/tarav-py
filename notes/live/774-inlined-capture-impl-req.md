# Inlined Capture — Impl.Req

## Impl.Abstract

- **Status:** Implemented and verified
- **Source session:** `01a05752-fa8d-7c62-abb2-5ff20c8260da`
- **Objective:** implement the first Markdown vertical slice of `tarav-hugentics --capture --inline <surface>`.
- **Boundary:** the Agent-operated workflow chooses relevant User Turns and edits the selected surface; Chatlas Query resolves those Turns; a named Renderer formats references.
- **Out of scope:** Diagram capture of the inline references, alias registries, Git-history auditing, assertion scoring, generalized impact maps, and non-Markdown surface syntax.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` / `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Impl.Req.Collection:** `774.Impl.Req` / `6eba09be-c8db-43b7-95f8-db2e03f21f57` (`Closed`)
- **Diagram.Draft:** `c203b5a5-1ce7-4183-9475-0dff6a001959` / `/Users/pereiro/Documents/tarav/diagram/drafts/c203b5a5-1ce7-4183-9475-0dff6a001959.json`
- **Capture.Authorization.Gate:** `6f6450d0-f214-407c-9a56-b836fee04137`

## Execution.Plan

### Slice 1 — Markdown reference rendering

- Register a fully qualified Chatlas Renderer for ordered `Inlined.Chat.Reference` comments.
- Require a document-local session alias as Renderer input while leaving selection entirely in Chatlas Query.
- Check focused renderer and CLI behavior, including batches.
- **Status:** Completed.

### Slice 2 — Agent-operated Inlined.Capture workflow

- Add `--capture --inline <surface>` to `tarav-hugentics` and route it to a focused workflow module.
- Define the Markdown attachment convention, bounded session aliases, 16-character prefix convention, direct surface mutation, and nonblocking collision handling.
- Keep richer digestion and Diagram capture explicitly separate.
- **Status:** Completed.

### Slice 3 — End-to-end verification

- Exercise the workflow mechanics against a Markdown fixture with more than one referenced Turn.
- Reinstall the editable CLI and run focused, architectural, and complete-package checks.
- **Status:** Completed.

## Acceptance signals

- `tarav-hugentics --capture --inline <surface>` is discoverable and operational for Markdown.
- Query mechanics are reused without selection logic in the Renderer.
- Repeated Turn prefixes render an ordered reference batch.
- Inline references contain only the session alias and compact Turn-hash prefix.
- The workflow makes no Diagram, registry, or Git-history mutation beyond editing the selected surface.

## Impl.Log

- Pre-edit checkpoints: `ddd9f8a` (`tarav-py`) and `965c355` (`tarav-md`).
- The current Chatlas identity is `91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`.
- Renderer and CLI-focused tests pass (`15 passed`); Ruff passes over the touched Chatlas surfaces.
- The active `tarav-hugentics` skill now routes `--capture --inline` to its focused Markdown workflow and passes skill validation.
- The workflow was hot-tested against note 772: one PhD Turn and two Tarav Turns resolved through Chatlas Query, rendered as 16-character references, and were inserted into the ordinary Markdown surface.
- Installed-command verification emitted the expected PhD reference. Focused Chatlas and architecture checks passed (`73 passed`), Ruff passed, and the complete package suite passed (`1535 passed`).
- Diagram Draft `c203b5a5-1ce7-4183-9475-0dff6a001959` was checked and applied in Namespace commit `f06c16d`. It created the closed Impl.Req Collection, one supported Line ship, and its Capture.Authorization Gate.
- The request's only specific nonblocking check finding was the expected `model-staleness` POI for a Collection-hosted implementation Line.
- Product changes remain uncommitted after the workflow checkpoints for User review.
