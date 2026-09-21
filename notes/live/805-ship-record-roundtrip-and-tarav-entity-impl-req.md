# Ship Record Round-trip and TaravEntity — Impl.Req

## Impl.Abstract

- **Status:** Planned for autonomous execution
- **Source session:** `01a0b984-4664-7871-934a-89cf92595b64`
- **Objective:** make `Ship` a lossless Pydantic field type for Tarav Records and introduce `TaravEntity` as the identity-bearing `TaravObject` base.
- **Boundary:** raw Records and JSON retain canonical UUID strings; typed `RecordInterface` views expose `Ship` objects.
- **Out of scope:** Context Graph navigation or retention, an entity repository, global identity rebinding enforcement, CLI work, and migration of existing record classes to `TaravEntity`.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` / `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Semantic Block:** `Tarav.Record` / `e63beedb-3007-4391-b339-215dea550cff`
- **Impl.Req.Collection:** `805.Impl.Req` / `97946d16-a0ed-42c0-9692-3d931ecfd89c` (`Open`)
- **Diagram.Draft:** `0036245b-bf44-456a-bdcd-fa0f74d600a4` / `/Users/pereiro/Documents/tarav/diagram/drafts/0036245b-bf44-456a-bdcd-fa0f74d600a4.json`
- **Capture.Authorization.Gate:** `f6520ecc-2c4f-4bba-a61e-a7ffdd4d8929`

The Collection hosts two supported candidate Lines. Both remain semantically attached to `Tarav.Record`: one defines the JSON/typed-view identity boundary and one defines identity composition with record storage shapes.

## Execution.Plan

### Slice 1 — Ship as a RecordInterface field

- Add Pydantic v2 validation and serialization for `Ship` and its subclasses.
- Parse canonical UUID strings into the declared Ship class and serialize them back to the same canonical string.
- Preserve the raw Record boundary: live `Ship` instances remain invalid in `TaravObject.record` and `from_json()` input.
- Check: focused tests cover strict Pydantic validation, subclass preservation, JSON schema, exact `TaravObject` round-trip, and rejection of live Ships in raw Records.
- **Status:** Planned.

### Slice 2 — TaravEntity identity base

- Add `TaravEntity(TaravObject)` with `RecordInterface.id: Ship`.
- Expose the typed entity identity and include it in `ships()` after the runtime TypeShip.
- Export the public base without adding identity storage or rebinding registries.
- Check: focused tests cover construction, missing/invalid identity, detached typed views, JSON round-trip, and `ships()` order.
- **Status:** Planned.

### Slice 3 — Storage-shape composition and integration

- Prove that entity identity composes with `FileRecord` and `DirectoryRecord` through explicit `RecordInterface` inheritance.
- Document the identity boundary in current architecture guidance.
- Run focused harness tests, architecture checks, Ruff, and the proportional package suite.
- **Status:** Planned.

## Risks and deviation triggers

- If Pydantic cannot accept a strict raw UUID string while returning a typed Ship without changing the serialized value, stop and revise the schema boundary rather than weakening `TaravObject.validate_record()`.
- If multiple inheritance requires framework-specific coupling between identity and storage shape, record the mismatch and keep `TaravEntity` storage-neutral.
- If an existing record uses an `id` field with incompatible semantics, do not migrate it in this slice.

## Acceptance signals

- A `Ship`-typed field reads a canonical UUID string and returns the declared Ship class.
- Pydantic JSON dumping writes that field as the identical canonical UUID string.
- `TaravObject.record`, `to_json()`, and `from_json()` remain JSON-only and lossless.
- `TaravEntity.id` is a `Ship`, while its retained raw Record contains a string.
- `TaravEntity.ships()` exposes both the runtime type and entity identity.
- Entity identity composes with file and directory Record shapes without special storage behavior.

## Impl.Log

- The existing exact-record validation deliberately compares Pydantic JSON output with the raw Record. Ship support must therefore transform only the typed view and serialize back losslessly.
- The durable UUID non-rebinding rule remains a system invariant in this slice; enforcement requires a later identity repository or retained attachment boundary.
- Diagram check reports expected nonblocking POIs for unasserted semantic records, unavailable Archive grounding, collection-hosted Model staleness, and pre-existing Model typing debt.
