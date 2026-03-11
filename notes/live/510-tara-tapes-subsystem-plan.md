# Tara Tapes Subsystem Plan

## Objective

Implement a new `tara_tapes` subsystem inside AgentOS that is compliant with the Tara tape specifications, while leaving the current `agentos tape` subsystem untouched as legacy behavior.

This note is intentionally scoped to the new subsystem only.
It does **not** include any migration, merge, overwrite, or cutover plan for the existing `agentos tape` interface.
That decision will be triggered manually later.

## Canonical Spec Sources

Tara spec root:

- `/Users/pereiro/projects/tara-proj-specs`

Index notes:

- `/Users/pereiro/projects/tara-proj-specs/notes/index/103-tara-tapes-spec-v0.md`
- `/Users/pereiro/projects/tara-proj-specs/notes/index/104-tara-dataclass-spec-v0.md`
- `/Users/pereiro/projects/tara-proj-specs/notes/index/105-tara-class-resolution.md`

These notes are the source of truth for the new subsystem.

## Decision Summary

1. The current `agentos tape` subsystem remains in place as legacy behavior.
2. The new implementation should live in a separate subsystem named `tara_tapes`.
3. `tara_tapes` must be spec-first and directly aligned with the Tara notes.
4. `tara_tapes` must not contain compatibility shims for the legacy tape implementation.
5. Migration and cutover are out of scope for this note.

## Why A New Subsystem Is The Right Move

The current `agentos tape` implementation is not just a slightly different Tara tape.
It is a different storage profile with different on-disk rules and different behavioral assumptions.

Main incompatibilities:

1. Manifest mismatch:
   the legacy implementation uses `tape.manifest.json`, while the Tara spec defines `tape.json`.
2. Stage layout mismatch:
   the legacy implementation uses `staging/*.jsonl`, while the Tara spec defines `stage/<writer_id>/<segment>.jsonl`.
3. Record model mismatch:
   the legacy implementation enforces object-shaped records with required keys like `class`, `writer`, and `created_at`, while the Tara tape core treats each JSON line as opaque.
4. Metadata header mismatch:
   the legacy implementation reserves line 1 of staging and segment files for metadata records, while the Tara tape core treats JSONL lines as records.
5. Core feature mismatch:
   the legacy implementation includes type restrictions, schema validation, and query features inside the main subsystem, while the Tara tape core treats those concerns as layered or out of scope.

Trying to force the existing subsystem into Tara compliance would create unnecessary coupling and confusion.
Keeping it frozen and building a new subsystem gives us a clean compliance target.

## Compliance Target For `tara_tapes`

The new subsystem should implement the Tara tape core exactly.

Required properties:

1. Directory layout:

```text
<tape_root>/
  tape.json
  segments/
    <segment>.jsonl
  stage/
    <writer_id>/
      <segment>.jsonl
```

2. Manifest contract:
   `tape.json` must contain the minimal required Tara fields and must preserve unknown fields on read and write.

3. Record contract:
   each JSONL line is an opaque JSON value.
   The core subsystem must not require a specific record envelope.

4. Write contract:
   writes go to stage files.
   Commit merges staged records into committed segments.
   Processed stage files are deleted after commit.

5. Read contract:
   segment readers iterate JSON lines as records.
   Tape scans are based on enumerating committed segments.

6. Core boundaries:
   no required schema validation, no required class filtering, no query language, no typed-record assumptions inside the core tape layer.

## Relationship To Tara DataClass

`tara_tapes` should implement the Tara tape core only.

Important consequences:

1. A tape may contain plain JSON values, JSON objects without type identity, and typed records mixed together.
2. The tape core should not assume that every record is a DataClass.
3. If a typed layer is introduced later, it should use Tara DataClass semantics:
   `class_id`, optional `class_version`, and disk-grounded resolution rules.
4. The legacy `class` field model should not be copied into `tara_tapes`.

## First Implementation Scope

The first implementation should stay narrow and spec-focused.

Include:

1. Tape initialization.
2. Tape manifest load/store.
3. Stage append operations.
4. Commit/consolidate operations.
5. Segment listing and raw record scanning.
6. Basic structural verification against Tara tape rules.

Exclude:

1. Schema validation.
2. Allowed-class enforcement.
3. Record envelope enforcement.
4. JMES or other query/filter features.
5. Migration from legacy tape folders.
6. Automatic unification with `agentos tape`.

## Recommended Subsystem Boundary

Keep the subsystem split conceptually into two layers:

1. Core storage layer:
   owns tape layout, manifest IO, stage append, commit, and raw record scanning.
2. CLI layer:
   exposes those deterministic operations without adding non-spec storage rules.

The important design rule is not the exact file/module names.
The important rule is that the core storage layer remains visibly Tara-compliant and free of legacy behavior.

## Recommended CLI Direction

Use a separate CLI namespace first, for example a dedicated `agentos tara-tapes ...` surface.

Goals of the separate namespace:

1. Avoid ambiguity between legacy tape behavior and Tara-compliant behavior.
2. Let the new subsystem evolve independently.
3. Make conformance testing and manual usage obvious.

The initial CLI should stay minimal and map closely to the storage contract.

Likely operations:

1. initialize a tape root
2. append to stage
3. commit staged data
4. scan committed data
5. inspect manifest / verify layout

## Execution Plan

### 1. Build A Conformance Checklist

Turn the Tara notes into a concrete implementation checklist.

Deliverables:

1. exact layout rules
2. exact manifest rules
3. exact stage append rules
4. exact commit/delete behavior
5. exact read/scan behavior
6. explicit list of what is out of scope

Purpose:
this becomes the acceptance surface for the new subsystem and keeps implementation decisions anchored to the spec instead of to the legacy code.

### 2. Scaffold `tara_tapes`

Create a new subsystem namespace for Tara-compliant storage.

Deliverables:

1. new package area for the subsystem
2. CLI registration for the new namespace
3. isolated tests for the new subsystem

Purpose:
this establishes hard separation from `agentos tape`.

### 3. Implement Manifest And Bootstrap

Implement tape-root creation and manifest read/write according to the Tara spec.

Deliverables:

1. `tape.json` creation
2. `segments/` creation
3. `stage/` creation
4. unknown manifest field preservation

Purpose:
this locks down the on-disk identity and layout early.

### 4. Implement Stage Append

Implement append operations that write to `stage/<writer_id>/<segment>.jsonl`.

Deliverables:

1. writer-specific staging paths
2. JSONL append behavior
3. no mandatory header records
4. opaque JSON record acceptance

Purpose:
this is the first place where the new subsystem proves it is different from the legacy one.

### 5. Implement Commit / Consolidate

Implement commit behavior that merges staged records into committed segment files and then deletes processed stage files.

Deliverables:

1. deterministic staged-file discovery
2. merge into `segments/*.jsonl`
3. deletion of processed stage files
4. clear result reporting from the CLI

Purpose:
this is one of the most important compliance points and should be validated early.

### 6. Implement Raw Read Operations

Implement simple committed-data reading that matches the tape core.

Deliverables:

1. segment enumeration
2. segment read as raw JSON values
3. tape scan across committed segments

Purpose:
the read path should reflect the Tara rule that querying and typed dispatch are layered concerns, not core tape responsibilities.

### 7. Add Conformance Tests

Build tests directly from the spec expectations.

Required coverage:

1. exact directory layout
2. exact manifest filename and minimal required fields
3. unknown manifest field preservation
4. acceptance of opaque JSON values
5. acceptance of mixed plain JSON and typed JSON objects
6. stage-file deletion after commit
7. no dependence on metadata header records

Purpose:
these tests define success for the subsystem more clearly than implementation detail tests.

### 8. Add Developer Documentation

Document the new subsystem explicitly as Tara-compliant and separate from legacy tape.

Deliverables:

1. README or subsystem docs for `tara_tapes`
2. CLI usage examples
3. explicit note that legacy `agentos tape` is separate

Purpose:
prevent accidental mixing of the two mental models.

## Explicit Non-Goals

These items are intentionally excluded from this note and from the first `tara_tapes` implementation track:

1. replacing `agentos tape`
2. migration tooling
3. compatibility aliases
4. automatic manifest conversion
5. preserving legacy staging or segment formats
6. embedding typed-record rules into the Tara tape core

## Definition Of Success

The work is successful when:

1. a new `tara_tapes` subsystem exists in parallel with legacy tape
2. its on-disk format matches the Tara notes directly
3. its tests validate spec-level behavior rather than legacy behavior
4. there is no compatibility logic contaminating the new subsystem

## Final Guiding Rule

Treat `tara_tapes` as a clean, spec-first implementation.

If a design choice is ambiguous, prefer the interpretation that keeps the subsystem simpler, more literal to the Tara notes, and less influenced by the current `agentos tape` implementation.
