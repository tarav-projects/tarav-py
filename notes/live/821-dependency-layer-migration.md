# Dependency-layer migration

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Design. Alignment.Mode: Interactive.
Status: design complete; ready for a bounded foundation slice. Later layer
assignments remain proposals to validate against module dependencies.

Introduce explicit dependency levels across Tarav namespaces. A namespace can
appear at several levels; level N may import its own and lower levels, not
higher ones. Same-level imports have no extra directional policy, but Python
initialization constraints still apply. Start with the principle, not a new
architecture-enforcement framework.

This request is a migration roadmap, not authorization to execute during
Design. Preserve executable behavior, class and Workflow identities, ownership,
Record labels, storage layouts, and CLI commands. Do not turn levels into
Workflow parents. That ownership-preservation choice and the detailed mapping
below are implementation proposals, not separately established user mandates.

Non-goals: redesign loading profiles (820), namespace every object method,
rename project to projects, split Kernel into new conceptual workflows,
restore tarav.diagram, or rewrite arbitrary retained user data.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md.
Wiki root: ../tarav-md/notes/wiki.
Context: diagram-workflows.md, especially Namespaces as semantic qualification
and Dependency layers across namespaces; projects.md and loading.md for
existing integration boundaries.

Evidence: codex:01a0d86c-9538-7be1-af96-014cd4203d61,
identity 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User Turns: 9567063c2dc25417 (layers spanning namespaces), d7f8eab26db8fcb5
(principle first, avoidable versus genuine cycles), ca93a6eba36f45c9 (migration
tree), 57ae7a4d122fe368 (Design invocation).
Capture: existing topical rationale retained; daily Design handoff added in
this pass. The detailed agent-authored roadmap remains here, not Wiki truth.

## Inspected implementation

Paths below are relative to src/tarav unless stated otherwise.

- __init__.py eagerly imports Archive and installs the Workflow resolver.
  Importing any tarav.l0 module will still execute this ancestor initializer.
  A clean lower layer therefore requires a thin root, not just moved files.
- kernel/__init__.py exports identity, Records, registries and Explorer together.
  Keep this coherent foundation initially rather than manufacture separate
  types/workflows/explorer packages from the illustrative tree.
- kernel/records.py has an annotation-only ContextBuilder dependency. Include
  type-checking imports in the inventory; runtime import success alone does
  not establish a clean dependency boundary.
- context/__init__.py supplies Context contracts and a runtime-aware helper;
  context/storage.py composes Archive and calls runtime services.
- archive/records/__init__.py imports ContextFolder and ContextBuilder, and
  both it and navigation.py lazily call get_runtime(). These are actual
  dependencies even though initialization can succeed.
- loading/__init__.py combines LoadingProfile with a runtime load facade.
  project/base.py consumes the profile, not the runtime facade's semantics.
- project/models and project/wiki are existing integration boundaries;
  featured Project delegates to them while TaravProject stays minimal.
- models/records.py consumes low-level Unsorted Records; scoring/tasks.py
  consumes Lines assertions and Unsorted storage. Whole-package moves would
  conceal these distinctions.
- tests/test_architecture.py already inspects selected domains at module
  granularity and checks exact Python module paths. Update those existing
  expectations when a module moves; do not add a generalized level checker now.

## Candidate organization

```text
tarav/
  __init__.py                 thin public entry point
  l0/
    _core/                    existing shared infrastructure
    kernel/                   existing foundation kept coherent
  l1/
    context/                  contracts, builders, standalone navigation
    loading/                  profile contract and non-composed mechanics
    archive/                  Archive implementation
    references/
    surfaces/
    project/                  minimal project
    wiki/
    models/                   core handler and Records
    lines/
    scoring/                  assertions and common Records
    poi/
    unsorted/                 only demonstrated low-level legacy portions
  l2/
    context/                  Archive-backed and runtime-aware integration
    archive/                  capabilities needing composed services
    loading/                  composed load facade
    project/                  featured Project
      models/
      wiki/
    scoring/                  Lines ranking/task integration
    unsorted/                 storage/capture composition
  runtime.py                  composition boundary above migrated layers
  cli/                       application adapters
  daemon/                    application adapters
```

This is a partial target, not a claim that all modules have been allocated.
Chatlas, SKW, Iterante, agents and remaining domains need module inventories
before their own slices. Same-level cross-workflow dependencies are permitted.
Do not create empty namespace copies or force three levels to fit everything.
Names l0/l1/l2 are valid Python spellings proposed for the numerical idea.

Existing top-level packages may remain temporarily while independent slices
migrate, but new lower-level modules must not reach through them to higher-level
composition. Do not maintain duplicate class definitions or old-path shims by
default. Preserve existing intentional public root conveniences lazily; they
are composition entry points, not low-level imports.

## Execution.Plan

- [ ] Recheck shared-worktree changes, especially 820, and checkpoint the product
  repository under Execute policy before any product edits. Do not modify its
  semantics as part of this migration.
- [ ] Inventory absolute, relative, function-local and TYPE_CHECKING imports,
  parent __init__ effects, Python-path strings, runtime registrations, tests,
  scripts and installed consumers for the selected slice. Produce an exact
  old-to-new path map before moving files.
- [ ] First bounded slice: introduce l0, move _core and the coherent Kernel
  implementation there, update all maintained in-repository consumers and
  path assertions. Make tarav/__init__.py import-safe for the foundation while
  preserving deliberate public convenience behavior. Do not rename classes.
- [ ] Resolve the annotation-only ContextBuilder edge with a minimal local
  annotation contract or another concrete dependency-neutral arrangement;
  do not import l1 Context back into l0. Verify annotation tooling as well as
  runtime behavior. Do not introduce a general injection framework for this.
- [ ] Verify and hand off that foundation slice before broader moves. Update
  AGENTS.md and ARCHITECTURE.md to describe the actual transitional state.
- [ ] Next, split Context contracts from Archive-backed composition and split
  LoadingProfile from the composed loader facade. Preserve one loader engine.
- [ ] Migrate minimal Project and featured Project/integrations separately;
  then migrate Archive with its Context and shared-runtime requirements explicit.
  For each get_runtime call choose a higher-layer operation or a minimal
  lower-layer service hook wired by composition. A local import alone is not
  a fix for an upward dependency. Keep canonical registered classes singular.
- [ ] Classify Lines/Models/Scoring/Unsorted at module level and migrate bounded
  families. Inventory remaining subsystems before assigning their levels.
- [ ] Update trusted external class-path bindings and maintained documentation
  for moved Types. Inventory retained class-location metadata read-only; report
  exact affected stores and request scope before rewriting external retained
  data. Keep historical Chatlas/Attic evidence unchanged. No runtime repair.

Only the foundation slice is sufficiently bounded for immediate Execute;
later slices require refreshing their exact map. If a first-slice dependency
requires a material behavior redesign, return to alignment rather than pull
all domains into the change.

## Verification and acceptance

- Fresh subprocess imports of l0 Kernel must not initialize Archive, Context
  storage, runtime, CLI or daemon. Exercise multiple import orders and ordinary
  root conveniences after initialization.
- Compare TypeShips, WorkflowShips, owner/parent relationships and registered
  class uniqueness before/after. Only Python locations should change.
- Run focused Kernel and architecture tests first, then affected loading,
  Archive/Context Explorer, Project and integration tests; run full pytest and
  Ruff for each large import-path slice using uv.
- Test Record round trips and trusted Type dispatch with unchanged fixtures.
  Verify Workflow resolution still works through the selected runtime.
- Inspect residual old paths: distinguish historical evidence from executable
  imports, trusted bindings and maintained documentation.
- Smoke-test CLI help and runtime construction; reinstall the editable tool
  if installed entrypoint behavior changes. No new level-enforcement system.
- Retained-data migration, when separately authorized, must preserve identities,
  enumerate changed records and report unknown paths rather than guess.

## Impl.Log

- Design inspected current files and existing architecture tests. No product
  implementation or tests were run; no migration is claimed complete.
- Existing dirty product files belong to concurrent loading-profile work and
  were left untouched. This new live note is intentionally uncommitted.
- The initial illustrative tree was refined: keep Kernel together initially,
  retain singular project, and explicitly handle root initialization and
  lazy runtime dependencies. These are agent proposals grounded in inspection.
