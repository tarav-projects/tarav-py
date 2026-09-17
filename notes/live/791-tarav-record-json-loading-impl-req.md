# 791 — Tarav Record JSON Loading

Status: Executed

## Impl.Abstract

Rename the Harness record-interpreter base from `TaravRecordType` to
`TaravRecord`, add explicit JSON loading through registered Type authority,
and make a bounded first pass over Diagram's class tree. The registry performs
dynamic opaque dispatch to the exact registered class. A registered class or
its deliberate subclass may instead load the same Record as itself. Harness
does not create an opaque wrapper for unregistered JSON.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` —
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- Collection: `791.Impl.Req` —
  `03e44825-e0df-41e3-97ea-8443a887cce1`
- Draft: `b5073714-b291-4200-9448-2142c27456ca`
- Authorization Gate: `ccec5541-eb73-442a-8adc-e0a2ae2830cc`

## Execution.Plan

1. **Harness naming and construction.** Hard-rename `TaravRecordType` to
   `TaravRecord`, establish `Class(record)` as the Record interpreter's
   construction surface, and update public exports and architecture wording.
2. **JSON loading.** Add `TypeRegistry.json_load(file)` for exact registered
   dispatch and inherited `RecordClass.json_load(file, registry=...)` for
   construction by a compatible registered class or subclass. Reject
   non-object JSON, unknown Types, incompatible callers, and the unregistered
   `TaravRecord` root explicitly.
3. **Diagram class-tree pass.** Rename Diagram's Harness ancestry and replace
   the generic Ship/Annotation wrapper-specialization path where it can be
   done coherently without redesigning retained storage. Preserve Namespace
   context, file-address identity, and current projections.
4. **Verification.** Add focused public-behavior tests, run Harness and
   Diagram suites, Ruff, full tests, CLI reinstall/smoke, and live-corpus
   specialization checks.

The Diagram pass is intentionally bounded: the current records derive identity
from their file address and Namespace from their repository, so this request
does not migrate retained schemas or force those facts into JSON.

## Impl.Log

- Alignment.Mode: Interactive.
- Chatlas session: `01a07228-313a-7ab3-b6e0-aedcb5216b3c`
  (`33afe59c2f13ac5d4b59e56f7a3761d3d91c1206a1b6287b0872036739b370fd`).
- Direct-input Execute authorization: User Turn `c41ec6b77644c0522`.
- Grounded Model and `Tarav.Record` Block were resolved before execution.
- Workflow checkpoint: `8d9bb11`.
- Harness now exposes `TaravRecord`, `TypeRegistry.json_load(file)`, and
  inherited `RecordClass.json_load(file, registry=...)`; the former
  `TaravRecordType` name was removed rather than retained as an alias.
- Diagram's registered Ship and Annotation interpreters now accept the
  retained Record directly. The existing `DiagramShip` and
  `DiagramAnnotation` objects remain as optional storage bindings for
  file-address identity and Namespace-dependent behavior.
- Type-private score-vector interpretation moved out of the generic
  `DiagramAnnotation` storage binding and into the registered
  `LineAnnotationRecord` interpreter.
- Verification: Ruff clean; full suite `1348 passed`; editable CLI reinstall
  and `tarav --version` smoke succeeded. All 1,768 retained Ships and 1,055
  retained Annotations loaded through their registries and specialized with
  zero errors.
- Capture applied at Namespace commit
  `baf97e958c4c70276411c75d9c4148d3fbf45634`. The authorization Gate covers
  every amended or created Design edition and the Collection close.
- Capture surfaced the expected `semantic-record-unasserted` and
  `archive-grounding-unassessable` findings on this material, plus existing
  corpus-wide model-staleness and missing-Type findings. None indicates a
  product implementation failure.
- Product changes remain uncommitted after the workflow checkpoint.

### Deviations

- The bounded Diagram pass did not remove the storage-binding classes.
  Instead, it separated their storage role from registered Record semantics.
  Removing them would require deciding how file-address identity and
  Namespace context enter otherwise raw Record interpreters, which belongs to
  the later Diagram class-tree redesign.
- Product-surface annotations were not emitted because that capture mechanic
  remains unavailable; the exact surfaces are retained below.

### Product.Surfaces

- `src/tarav/harness/types.py`
- `src/tarav/harness/__init__.py`
- `src/tarav/diagram/__init__.py`
- `tests/harness/`
- `tests/diagram/`
- `tests/test_architecture.py`
- `ARCHITECTURE.md`
