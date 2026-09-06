# 789 — Ship-aware Harness Record Types

Status: Ready for execution

## Impl.Abstract

Implement the reviewed Ship identity design in the dependency-clean
`tarav.harness` boundary. The slice gives every `TaravRecordType` subclass a
durable Type Ship, makes UUID the authoritative registry identity, represents
Record type references structurally, and supplies explicit Ship-occurrence
introspection. Diagram is the first consuming application.

This request does not rewrite the complete retained Diagram corpus. Existing
label-only Records must remain readable while structured `{id, name}` type
references are introduced and validated. PaperSON integration, Assertion
scoring, POI storage/blessing, and generalized state-machine behavior are later
slices.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` —
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Blocks:
  - `Ship.Identity` — `87654e2d-6ebe-4b1f-8753-6cf5b99fe935`
  - `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- Collection: `789.Impl.Req` —
  `b1225095-2356-43bb-a444-ac6b0d92b6a9`
- Draft: `d43c6e29-c2bf-4c4f-af18-636173a7cca4`
- Authorization Gate: `6c29d5e2-a41c-4ca3-b6cd-13d78550f0c4`

The sole retained Session.View for this chat is stale and scoped to PaperSON,
not Tarav. Grounding therefore used the freshly resolved Tarav Project Model
directly. The View mismatch remains an explicit POI.

## Execution.Plan

1. Add dependency-clean `Ship`, `TypeShip`, and `ShipOccurrence` primitives.
   A Ship's universal state is only its UUID; equality and hashing follow that
   identity across specialized Ship classes. Check: focused tests cover UUID
   validation, sameness, specialization, and occurrence paths.
2. Require every subclass of `TaravRecordType`, including intermediate bases,
   to declare a class-local `type_ship`, while retaining its human-facing
   `type_name`. Check: class-definition and registry tests reject missing,
   inherited-only, duplicate-UUID, and duplicate-name declarations.
3. Extend `TypeRegistry` with UUID-authoritative structured references and a
   separate explicit name index for retained label-only Records. Known UUIDs
   resolve independently of label drift, while deterministic diagnostics expose
   missing, unknown, or conflicting reference components. Check: tests cover
   structured and legacy resolution without dynamic imports.
4. Give typed Records an explicit `ship_occurrences()` surface. The default
   exposes the Record Type Ship; application classes opt into cargo Ships by
   returning concrete Ship instances rather than by scanning UUID-shaped data.
   Check: Harness tests prove the default and an application specialization.
5. Assign stable Type Ships to all Diagram `TaravRecordType` subclasses and
   migrate Diagram registries/read paths as the first consumer. Preserve current
   retained Records and CLI behavior; do not bulk-rewrite the namespace or make
   PaperSON changes. Check: Diagram characterization and corpus read tests pass.
6. Update the Harness architecture note and exports, then run focused Harness,
   Diagram, architecture, full-suite, Ruff, and installed-CLI smoke checks.
   Reconcile this Draft, close the Collection, and apply it once only after the
   implementation and evidence agree.

Deviation triggers: stop and record a deviation if UUID-authoritative
resolution requires a wholesale corpus migration, if type declarations create
an application import into Harness, if label drift cannot remain observable
without introducing the deferred POI subsystem, or if implementation overlaps
unrelated dirty user changes.

## Impl.Log

- Alignment.Mode: Autonomous.
- Chatlas session: `01a07228-313a-7ab3-b6e0-aedcb5216b3c`
  (`33afe59c2f13ac5d4b59e56f7a3761d3d91c1206a1b6287b0872036739b370fd`).
- The explicit design authorization is User Turn `c6a1a0a5b673826a`.
- Design reuses the reviewed `Ship.Identity` and `Tarav.Record` Lines landed at
  Diagram commit `d3b64c6`; it does not duplicate those claims.
- Draft checking reports only the expected local design-stage POIs:
  `semantic-record-unasserted` and `archive-grounding-unassessable`.
- Autonomous assumption: Ship equality is UUID-only across subclasses. Revisit
  only if a concrete consumer demonstrates that role-sensitive equality is
  required.
- Live-note number `789` avoids the in-progress local `788` checkpoint named by
  the current repository HEAD.
- Existing unrelated worktree changes are preserved and outside this request.
