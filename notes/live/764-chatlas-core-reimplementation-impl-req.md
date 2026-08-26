# 764 — Chatlas core reimplementation

## Impl.Abstract

- **Goal:** reduce Chatlas to the smallest coherent substrate that captures provider-native
  chat artifacts, indexes sessions, materializes a provider-neutral `Normal.Model`, and
  preserves traceability from normalized objects to retained raw artifacts.
- **Status:** approved for execution by the user's explicit `MAKE THE REIMPLEMENTATION`
  instruction; implementation pending.
- **Scope:** `src/tarav/chatlas`, its CLI/runtime composition, direct consumers, tests, and
  architecture guidance whose contracts change with the reduction.
- **Out of scope:** `Tarav.Diagram`, replacement semantic annotation machinery, rich search,
  dashboards, continuation workflows, generalized query systems, and compatibility aliases.
- **Rollback floor:** baseline commit `8e48405` contains every pre-existing worktree change.

## Impl.Index

### Accepted constraints

- [CT] Chatlas captures chats, normalizes them, and preserves traceability. It does not
  interpret, organize, search, annotate, or contextualize them unless a minimal mechanism is
  required to perform those three responsibilities. Supported by the current user discussion.
- [CT] The provider-neutral model is named `Normal.Model`; `Lossless` is removed from the
  product vocabulary and Python namespace. Supported by the current user correction.
- [CT] Chatlas Anchory is removed. It was a prototype `Diagram.Record`, not a Chatlas
  responsibility. Supported by the current user correction.
- [CT] Query and convenience tooling are removed aggressively. Functionality may return later
  only when an actual consumer demonstrates the need. Supported by the current user direction.
- [CT] Backward compatibility is not a goal. The reimplementation must not leave aliases,
  forwarding modules, deprecated commands, or parallel semantic models.

### Core boundary

```text
Provider.Home
    ↓
Raw.Archive
    ↓
Session.Index
    ↓
Normal.Model
```

- Raw capture remains dumb and provider-native.
- Session Index retains only mechanically discoverable metadata needed to identify and locate
  captured sessions.
- `Normal.Model` is the sole provider-neutral semantic materialization.
- Traceability is structural: normalized objects retain enough source information to navigate
  back to raw artifacts. It does not require Anchory or a relationship graph.
- Exact reference resolution and narrow inspection needed to test or operate the core may
  remain. Broad discovery, semantic search, projections, and workflow products do not.

## Execution.Plan

### Vertical.Slice 1 — Establish the one-model boundary

- Rename `tarav.chatlas.lossless` to a namespace named for `Normal.Model`.
- Remove the old `normalization.session_model` dependency from Session Index.
- Preserve the capture, index, provider normalizers, Normal Model cache, and raw trace fields.
- **Check:** capture/index modules do not import the Normal Model layer; the Normal Model can be
  produced from a captured/indexed Claude or Codex session and exposes raw-source traceability.

### Vertical.Slice 2 — Delete semantic and convenience systems

- Remove Chatlas Anchory, Products, annotations/tagging, old views/model/query machinery,
  heuristics, recents, ping, broad query/projection commands, and orphaned compatibility code.
- Remove runtime and subsystem integrations that depended on those Chatlas-owned semantic
  facilities rather than preserving them through adapters.
- **Check:** static import scans find no removed namespaces or old model dependencies; importing
  every remaining Chatlas module succeeds.

### Vertical.Slice 3 — Reduce the public operating surface

- Rebuild command composition around capture/update, Session Index maintenance/inspection,
  raw-artifact access, and explicit Normal Model materialization or exact resolution only.
- Remove tests for intentionally deleted commands and replace them with boundary tests for the
  remaining core.
- **Check:** installed CLI help exposes only the minimal leaves; focused Chatlas tests pass.

### Vertical.Slice 4 — Reconcile the monolith

- Update `AGENTS.md`, `ARCHITECTURE.md`, imports, and direct consumers to the new ownership
  boundary and vocabulary.
- Run Ruff, architecture checks, focused Chatlas tests, then the full maintained suite.
- **Check:** no `lossless` product namespace, Chatlas Anchory, or parallel Session Model remains;
  the full suite passes or every unrelated failure is reported precisely.

## Impl.Log

- [IP] The implementation workflow's legacy Anchory capture path is intentionally not used:
  the user explicitly identified Chatlas Anchory as a proto-Diagram system to delete. This
  artifact preserves the implementation handoff without creating new records in the system
  being removed.
- [IP] Existing persisted `tarav.chatlas2.*` values may remain as historical data schema values
  when changing them would require a data migration; they must not keep the removed Python or
  product vocabulary alive.
- [IP] Exact resolution is retained only where capture, normalization, traceability, or their
  verification cannot function without it. Anything broader fails the deletion test.
