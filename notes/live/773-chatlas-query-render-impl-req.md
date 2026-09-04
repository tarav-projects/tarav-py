# Chatlas Query and Render — Impl.Req

## Impl.Abstract

- **Status:** Implemented and verified
- **Source session:** `01a05752-fa8d-7c62-abb2-5ff20c8260da`
- **Objective:** add a bounded Chatlas Query engine for exact Turn-hash-prefix findings and expose default and explicitly selected named Renderer paths through the umbrella CLI.
- **Boundary:** Query owns finding selection and Turn-to-Message assembly. Renderers receive structured findings and own only their presentation.
- **Out of scope:** general document-reference parsing, persistent renderer configuration, dynamic plugin discovery, broad full-text search, and Diagram rendering changes.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` / `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Impl.Req.Collection:** `773.Impl.Req` / `7a7d0e1b-1e66-48e5-bfbf-341633536db6` (`Closed`)
- **Diagram.Draft:** `8ea79144-7bff-4ced-ada0-7905e4677c98` / `/Users/pereiro/Documents/tarav/diagram/drafts/8ea79144-7bff-4ced-ada0-7905e4677c98.json`
- **Capture.Authorization.Gate:** `58f7d2c9-1550-4048-a588-a4084083a972`

The Collection hosts only supported implementation constraints. Its editions remain semantically attached to the existing `Context.Provider` and `Kernel.Writing` Blocks.

## Execution.Plan

### Slice 1 — Structured Chatlas Query

- Add a Chatlas-owned query model that selects exact Turns by hash prefix and assembles their referenced Messages from the streamable Normal Model cache.
- Preserve query order and reject malformed, missing, or ambiguous prefixes explicitly.
- Observable: one prefix yields one structured finding without materializing Events or Loaded Contexts.
- Check: focused Query unit tests cover successful, missing, ambiguous, malformed, multi-message, and ordered multi-prefix cases.
- **Status:** Completed.

### Slice 2 — Named Renderer paths

- Add a named Chatlas Renderer registry with one fully qualified default Renderer.
- Make `tarav chatlas query` run shared query mechanics and the default Renderer.
- Make `tarav chatlas render` accept the same repeatable query flags plus an optional fully qualified `--renderer`; omission uses the same default and a Renderer receives the complete ordered Finding batch.
- Observable: equivalent default invocations render identical text, while registry lookup supports another in-process Renderer without changing Query.
- Check: renderer and CLI tests cover equivalence, discovery failure, JSON envelopes, and custom registration.
- **Status:** Completed.

### Slice 3 — Integration and live verification

- Export the public Query and Renderer primitives and align current Chatlas package documentation and CLI expectations.
- Reinstall the editable command and exercise both commands against a real current-session Turn prefix.
- Observable: the earlier product-surface context reference resolves to its exact User message through both commands.
- Check: focused Chatlas suites, Ruff, architecture tests, and proportional complete-package tests.
- **Status:** Completed.

## Risks and deviation triggers

- If existing Normal Model cache streams cannot assemble one Turn without loading unrelated collections, stop and revise the Query boundary rather than hiding full-model materialization inside a Renderer.
- If fully dynamic external plugin loading is required for the first registered Renderer, keep registration in-process and defer distribution discovery instead of adding an unrequested plugin system.
- If query flags begin encoding presentation choices, move them to the Renderer surface before continuing.

## Acceptance signals

- Query and Render share one Query parser and execution path.
- Default Query and default Render output are byte-identical.
- A Renderer is addressed by its full opaque registered name.
- The CLI resolves compact Turn-hash prefixes and prints every referenced Chat.Message in Turn order.
- Repeating `--turn-hash-prefix` renders the selected Turn batch in query order.
- Existing Normal Model, update, index, and raw commands remain unchanged.

## Impl.Log

- Repository inspection found no current Chatlas Query engine or Renderer registry; the implementation introduces the smallest reusable versions inside `tarav.chatlas`.
- The streamable Normal Model cache already separates `turns.jsonl` and `messages.jsonl`, allowing Query to avoid loading unrelated Events and Loaded Contexts.
- Renderer registration is an in-process extension primitive in this slice; workflow/plugin discovery remains deferred.
- The required pre-edit checkpoint is `d3da6f6`; all implementation changes after it remain uncommitted for User review.
- Query and Render use the same Query argument builder and execution function. Repeating `--turn-hash-prefix` produces one ordered batch passed once to the selected Renderer.
- Architecture validation initially caught direct imports of a Normal Model internal type alias. Query now depends only on its reader protocol, and command composition injects the Normal Model cache reader.
- Final verification: focused Chatlas/Normal Model/architecture tests passed (`107 passed`), Ruff passed, and the complete package suite passed (`1531 passed`).
- Installed-command verification resolved `aec74b84`, produced byte-identical default Query/Render output, and rendered the ordered batch `aec74b84`, `0aac2ee7`.
- Diagram Draft `8ea79144-7bff-4ced-ada0-7905e4677c98` was checked and applied. It created the closed Impl.Req Collection, two supported Line ships, and their Capture.Authorization Gate.
- Expected nonblocking Diagram POIs remain for unasserted semantic records, unavailable Archive grounding, collection-hosted Model staleness, and pre-existing Model typing debt.
- Product.Surface context is not yet representable through a landed Diagram Annotation; the exact implementation surfaces and verification remain recorded here as a retryable capture POI.
