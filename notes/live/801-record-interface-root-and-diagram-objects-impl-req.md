# 801 — Record interface root and Diagram objects — implementation request

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

- **Status:** Ready for execution.
- **Alignment.Mode:** Autonomous.
- **Objective:** make `TaravObject.RecordInterface` the common root for every Pydantic model describing complete or embedded Tarav record structure, then apply the clarified object/interface boundary to References and Diagram.
- **Starting state:** the worktree already contains the uncommitted Reference `RecordInterface` implementation and its tests. Preserve and complete that work.
- **Boundary:** independently meaningful serialized data belongs to `TaravObject`; embedded structural records belong to the `TaravObject.RecordInterface` hierarchy. Runtime bindings, repositories, services, and derived projections remain ordinary classes.
- **No legacy path:** remove replaced dataclasses, manual serializers, old schemas, and compatibility aliases. Persisted schema changes require explicit code-and-data migration.

The object boundary applies across Tarav, while this request implements it in the already-active Reference work and the Diagram subsystem inspected in this session.
<!-- tarav.context 1f561f5d:6f31163c2575c733 -->
<!-- tarav.context 1f561f5d:3e139040afacf22e -->
<!-- tarav.context 1f561f5d:d85885cd6bb75d0a -->

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Project Model:** `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Semantic Block:** `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- **Grounded View:** `7674a926-b123-4dc1-8f55-4be1d6c8624b`
- **Impl.Req.Collection:** `801.Impl.Req` — `1a98fd2d-941e-40fd-83ff-d0e5ea9f2d4c` (`Open`)
- **Diagram.Draft:** `3939a6e2-0134-4b19-a04e-fb2495fa8542` — `/Users/pereiro/Documents/tarav/diagram/drafts/3939a6e2-0134-4b19-a04e-fb2495fa8542.json`
- **Capture.Authorization.Gate:** `dba34df4-f585-400d-b8fb-f6b7ce2e6c4e`

## Execution.Plan

### Slice 1 — Embedded Reference interfaces

- Change every Pydantic locator, check, and metadata model introduced by the active Reference work to derive from `TaravObject.RecordInterface`.
- Retain each model's explicit open or closed `extra` policy and strict field validation.
- Keep `issubrecord()` and `isrecordsubclass()` scoped to `TaravObject` classes; use ordinary `issubclass()` for interface ancestry.
- **Observable:** every nested Reference interface shares the common root without gaining a Type Ship or registry entry.
- **Check:** focused Reference/Harness tests validate ancestry, exact round trips, type dispatch, optional-field omission, and resolution behavior.

### Slice 2 — Diagram structural interfaces

- Replace Diagram's plain structural dataclasses and manual `to_dict()` / `from_dict()` paths with module-level interfaces rooted at `TaravObject.RecordInterface`.
- Cover Chatlas turn coordinates, support members, locations, argument and host references, capture Ship/Annotation drafts, and retained View scope/configuration structures.
- Preserve current JSON shapes, strict validation, immutable use at domain boundaries, and exact round trips. Update all consumers directly; add no aliases or dual readers.
- Remove Diagram's duplicate semantic interpretation of Chatlas turn references where the canonical Reference subsystem can own it without changing the inline record shape; otherwise keep one shared embedded interface rather than another semantic object.
- **Observable:** retained nested Diagram objects validate through the common interface ancestry and no replaced manual serializer remains.
- **Check:** focused Diagram capture, collection/draft, view, rendering, and CLI tests.

### Slice 3 — Standalone Diagram TaravObjects

- Migrate independently serialized Diagram data including capture manifests/receipts, durable drafts, retained View records, and Diagram configuration to concrete `TaravObject` classes with declared Type Ships and nested `RecordInterface`s.
- Keep filesystem paths, Namespace bindings, repositories, and multi-file storage mechanics as runtime bindings around those object records rather than serialized semantic fields.
- Replace ad hoc `"class"` dispatch with ordinary Tarav Type resolution. Explicitly migrate affected maintained retained data before removing the old readers.
- Keep `DiagramShip`, `DiagramAnnotation`, `DiagramNamespace`, `DiagramModel`, repositories, evaluators, renderers, and computed projections outside the semantic object hierarchy.
- **Observable:** every independently retained Diagram datum loads through registered Tarav Type authority; operational objects remain unregistered.
- **Check:** runtime registration round trips, retained-corpus loading, Draft/View/Configuration persistence tests, CLI vertical slices, and an explicit migration verification.

### Slice 4 — Integration and closure

- Update architecture guidance only where the public contract changes.
- Run Ruff, focused suites after each slice, architecture checks, then the complete pytest suite.
- Reinstall the editable CLI if command behavior or registered runtime composition changes and smoke the affected Diagram/Reference commands.
- Reconcile newly relevant supported material into the same Draft, append the Collection's `Closed` edition, run the final overlay check, and apply the Draft once.

## Risks and deviation triggers

- If an apparent embedded value has independent semantic identity or standalone dispatch, promote it to `TaravObject` rather than hiding it behind an interface.
- If replacing a dataclass changes retained JSON shape accidentally, stop that slice and preserve the shape through the interface model before proceeding.
- If a multi-file Diagram surface cannot honestly be represented by one object record, separate its retained semantic records from its repository binding instead of serializing paths or inventing a universal storage abstraction.
- If maintained retained instances use a changed schema, migrate them explicitly and verify identity/history before deleting the old reader.
- Existing Diagram POIs for unasserted records, Archive grounding, missing historical Types, and collection-hosted Model staleness do not block mutation.

## Acceptance signals

- Every Pydantic model that describes any portion of a retained Tarav record derives from `TaravObject.RecordInterface`.
- Embedded interfaces do not declare `type_ship` and are not runtime-registered.
- Independently meaningful serialized Diagram objects derive from `TaravObject` and dispatch through their registered Type authority.
- Replaced manual record serializers and legacy readers are absent.
- References and Diagram preserve exact current JSON meaning through explicit migrations where schemas change.
- Focused checks, Ruff, architecture validation, and the complete suite pass.
- The `801.Impl.Req` Collection closes and its Draft applies once with a retained receipt.

## Impl.Log

- The existing `Tarav.Record` Block is the semantic attachment point; its grounded View has 14 Lines and no View findings.
- A full-Model View bootstrap was stopped after exposing quadratic-style repeated corpus scans during review assessment. A focused Block View completed successfully. This performance behavior is a retryable Diagram.View POI and does not block the implementation.
- Initial Draft overlay checking produced only expected semantic/Archive/staleness and pre-existing corpus POIs; no capture-shape, support-resolution, gate, or Object.Type error was found for the new material.
