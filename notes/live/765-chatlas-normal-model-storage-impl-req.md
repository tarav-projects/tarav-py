# 765 — Chatlas Normal Model storage and CLI projection

## Impl.Abstract

- **Goal:** restore one directory per materialized Chatlas Normal Model, split its
  independently useful collections into JSONL files, and make `normal-model` print
  Events by default while adding other collections only through explicit flags.
- **Status:** approved for implementation by the user's explicit `implement` instruction.
- **Scope:** Normal Model cache persistence and reader APIs, the `tarav chatlas
  normal-model` output contract, focused tests, and installed CLI verification.
- **Out of scope:** incremental append mutation, generalized querying, pagination,
  compatibility aliases, and revival of retired Chatlas semantic systems.

## Impl.Index

- [CT] One Normal Model materialization is a directory addressed by its exact Session
  identity hash.
- [CT] `metadata.json` is the cache envelope: storage-owned freshness and integrity data
  wrapped around the small semantic model header. It is not chat content.
- [CT] Events, Messages, Turns, and Loaded Contexts are independent JSONL streams so a
  reader can consume one collection without loading the others.
- [CT] Materialization rebuilds a complete temporary directory and atomically replaces the
  visible directory. Incremental append is intentionally excluded.
- [CT] The default CLI projection contains the model header, Sources, and Events. The
  `--messages`, `--turns`, and `--loaded-contexts` flags add their collections;
  `--all` adds all three.
- [CT] `--include-raw` remains an additive, uncached direct-computation option.
- [IP] Event observations require Sources to resolve, so Sources remain in every CLI
  projection even though Events are the only default large collection.

## Execution.Plan

### Vertical.Slice 1 — Multi-file materialization

- Replace the single `<identity>.json` cache with
  `normal-model/<identity>/metadata.json` plus `events.jsonl`, `messages.jsonl`,
  `turns.jsonl`, and `loaded-contexts.jsonl`.
- Add a narrow reader that streams each collection and can reconstruct the complete model.
- Preserve cache-key freshness checking, locking, and atomic whole-directory replacement.
- **Check:** focused cache tests prove exact files, envelope/header separation, JSONL row
  counts, freshness behavior, and full reconstruction.

### Vertical.Slice 2 — CLI projections

- Make the default command return the header plus Events.
- Add additive `--messages`, `--turns`, `--loaded-contexts`, and `--all` flags.
- Apply the same projection contract when `--include-raw` performs uncached computation.
- **Check:** command tests prove every flag combination and ensure default output omits the
  non-Event collections.

### Vertical.Slice 3 — Product verification

- Run Ruff, focused Chatlas tests, architecture tests, and the full maintained suite.
- Reinstall the editable CLI and inspect help/output against a real retained session.
- Replace the superseded live single-file materialization with the verified directory form.
- **Check:** all tests pass; the installed CLI exposes the accepted flags; the real model
  directory contains the five expected files and default output contains no optional
  collection.

## Impl.Log

- [IP] The previous split-cache implementation is used only as evidence for the physical
  boundary. Its query, View, Anchory, and semantic-product machinery remains deleted.
- [IP] Product capture may end with a retryable gap because the old Chatlas grounding path
  was deliberately removed during the core reimplementation.
