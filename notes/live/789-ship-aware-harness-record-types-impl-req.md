# 789 — Ship-aware Harness Record Types

Status: Executed — Collection closed, Draft applied

## Impl.Abstract

The reviewed Ship identity design is implemented in the dependency-clean
`tarav.harness` boundary. Every `TaravRecordType` subclass now declares a
class-local Type Ship beside its human-facing `type_name`, the Type Registry
indexes both and treats the UUID as authoritative, retained `type` values may
be a legacy label or a structural `{id, name}` reference, and typed Records
expose explicit Ship occurrences. Diagram is the first consuming application:
its Record classes declare Type Ships, its read paths accept both reference
forms, and its typed Records expose their structural Ships.

The retained Diagram corpus was not rewritten. All 1761 Ships and 1051
Annotations across the mounted Namespaces still read and specialize, and the
`User.Touched.Chatlas.Index` corpus produces no Type-reference findings.
PaperSON integration, Assertion scoring, POI storage/blessing, and generalized
state-machine behavior remain later slices.

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
- Authorization Gates:
  - Design — `6c29d5e2-a41c-4ca3-b6cd-13d78550f0c4`
  - Execute — `1fed6cf8-744d-49c0-bfe5-09a55925fd12`

The sole retained Session.View for this chat is stale and scoped to PaperSON,
not Tarav. Grounding therefore used the freshly resolved Tarav Project Model
directly. The View mismatch remains an explicit POI.

## Execution.Plan

1. **Done.** Dependency-clean `Ship`, `TypeShip`, and `ShipOccurrence`
   primitives in `src/tarav/harness/ships.py`. A Ship's universal state is only
   its UUID; equality and hashing follow that identity across specialized Ship
   classes. Covered by `tests/harness/test_ships.py`.
2. **Done.** `TaravRecordType.__init_subclass__` requires a class-local
   `type_ship` from every subclass, including intermediate bases, while
   `type_name` remains the human-facing label. Covered by
   `tests/harness/test_record_type_declaration.py`.
3. **Done.** `TypeRegistry` carries a UUID index beside its name index,
   `RecordTypeReference` parses both retained forms, and `reference_findings`
   reports missing, unknown, and conflicting components. A known Type Ship
   resolves independently of label drift and never falls back to a label.
   Covered by `tests/harness/test_record_type_references.py`.
4. **Done.** `ship_occurrences()` defaults to the Record Type Ship; application
   classes opt into cargo Ships by returning concrete `Ship` instances. Covered
   by `tests/harness/test_ship_occurrences.py`.
5. **Done.** All 17 Diagram `TaravRecordType` subclasses declare stable Type
   Ships, `DiagramShip`/`DiagramAnnotation` expose `type_reference` and accept
   both retained forms, per-class guards match by Ship, and typed Records
   expose their structural Ship occurrences. Covered by
   `tests/diagram/test_record_type_ships.py`; the retained corpus is unchanged.
6. **Done.** `ARCHITECTURE.md` and the Harness exports are updated,
   `tests/test_architecture.py` asserts the Harness-owned Ship boundary, and
   the full suite (1317 passed), Ruff, and installed-CLI smoke checks pass.

Deviation triggers: stop and record a deviation if UUID-authoritative
resolution requires a wholesale corpus migration, if type declarations create
an application import into Harness, if label drift cannot remain observable
without introducing the deferred POI subsystem, or if implementation overlaps
unrelated dirty user changes. None of these triggers fired.

## Impl.Log

- Alignment.Mode: Autonomous.
- Design Chatlas session: `01a07228-313a-7ab3-b6e0-aedcb5216b3c`
  (`33afe59c2f13ac5d4b59e56f7a3761d3d91c1206a1b6287b0872036739b370fd`).
  The explicit design authorization is User Turn `c6a1a0a5b673826a`.
- Execute Chatlas session: `b69e11dc-dc6d-4903-97a5-25f895655718`
  (`a99c4bd996fed3236949d3208e7a8819a55d05cf06186fe39ed22b7bcffc48fd`).
  The execution authorization is User Turn `0aeaab6f0b9b7619`.
- Git checkpoint before the first product edit: `7c18408`. Post-checkpoint
  implementation changes are left uncommitted for User review.
- Capture.Receipt: Namespace commit `eacd271` on base `d3b64c6`. The Collection
  is Closed and the Draft is Applied. The Execute Gate covers the closing
  Collection edition; the Design Gate covers the Design Line edition.
- Design reuses the reviewed `Ship.Identity` and `Tarav.Record` Lines landed at
  Diagram commit `d3b64c6`; it does not duplicate those claims.
- Autonomous assumption, unchanged: Ship equality is UUID-only across
  subclasses. Revisit only if a concrete consumer demonstrates that
  role-sensitive equality is required.
- Existing unrelated worktree changes were preserved in the checkpoint commit
  and are outside this request.

### Deviations

- Diagram Type Ship assignment moved from slice 5 into slice 2. Requiring a
  class-local `type_ship` makes `tarav.diagram` unimportable until its classes
  declare theirs, so deferring the assignment would have left the tree broken
  at a slice boundary. Slice 5 still owns the registry and read-path migration.
- Duplicate Type Ship and duplicate Type name are rejected by `TypeRegistry`
  rather than by a process-global table at class-definition time. A global
  table would be the independent Type-registry authority the design rejects;
  `tests/diagram/test_record_type_ships.py` asserts global uniqueness across
  both default Diagram registries instead.
- The `ship_occurrences()` default landed in slice 2, on `TaravRecordType`,
  because that is its only coherent home. Slice 4 delivered the surface's
  default and application-specialization checks.
- Write-side acceptance was widened beyond the plan's read paths:
  `ShipDraft`, `AnnotationDraft`, and `_merge_ship_record` accept structured
  references. Without this a structured Record could never be written, leaving
  the new read path unreachable end to end. Retained Records are unchanged and
  Capture still emits label-only `type` values.
- The Execute `Capture.Authorization.Gate` token is the literal skill argument
  string `--impl --exec 789 --AUTO`, because that is what the permission Turn
  contains in this harness. The Design Gate's `$tarav-hugentics ...` form does
  not occur in this session's evidence and would have failed its Token
  Assertion.

### Implementation notes

- Zero-argument `super()` is unusable inside `@dataclass(slots=True)` classes
  because the decorator rebuilds the class; every override uses the explicit
  two-argument form.
- `DiagramShip.type` and `DiagramAnnotation.type` still return the retained
  human-facing label, so Namespace Type-policy lists and existing comparisons
  are unaffected. Resolution and the per-class guards go through the Ship.

### POIs

- The stale PaperSON-scoped Session.View for this chat remains unresolved.
- Draft records carry the expected `semantic-record-unasserted` and
  `archive-grounding-unassessable` POIs.
- `producer-turn-unresolved`: the Design Line edition's producer Turn resolves
  with standing AMENDED. The design session's raw artifact changed after
  capture; the Line itself is unchanged.
- Closing the Collection surfaces `impl-req-closed-write` for its one hosted
  Design Line edition. Every previously closed Impl.Req Collection in this
  corpus shows the same pattern, so it is the expected closed state rather
  than a new defect.
- The overlay check also surfaces corpus-wide `model-staleness`,
  `block-type-missing`, and `line-type-missing` POIs across the Model. These
  predate this request and are untouched by it.
- Product.Landing.Capture could not annotate the produced Product.Surface
  editions: the Product.Surface context mechanic is itself in progress under
  live note 772. The exact produced surfaces are retained here instead.

### Product.Surfaces

- `src/tarav/harness/ships.py` (new)
- `src/tarav/harness/types.py`
- `src/tarav/harness/__init__.py`
- `src/tarav/diagram/__init__.py`
- `tests/harness/test_ships.py` (new)
- `tests/harness/test_record_type_declaration.py` (new)
- `tests/harness/test_record_type_references.py` (new)
- `tests/harness/test_ship_occurrences.py` (new)
- `tests/harness/test_types.py`
- `tests/diagram/test_record_type_ships.py` (new)
- `tests/test_architecture.py`
- `ARCHITECTURE.md`
