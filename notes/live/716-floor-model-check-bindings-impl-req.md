# Floor.Model Check Bindings Impl.Req

## Impl.Abstract

- status: ready for execution
- scope: make Index linter check applicability explicit over its parser-produced `Floor.Model`, include agendix in depot inventory, and bind reviewed-only Chatlas checks to reviewed surfaces
- source: the current Hugentics design discussion and the existing `Floor.Model`, `POI.Linter`, `POI.Check`, and `POI.Class` contracts
- out of scope: new public CLI flags, new regression tests, changes to POI class semantics, and a repository-wide generic checker framework

## Impl.Index

### Check.Function.And.Binding

- `LinterCheck` remains the named detector and declares the POI classes it can emit through its finding codes and package ownership.
- A distinct binding owns where and how that detector participates in one linter: target `IndexSurfaceKind`s, default activation, structural tier, and prerequisite gate.
- Severity, meaning, documentation, and resolution policy remain outside the binding; those belong to emitted findings and their `POI.Class` definitions.

### Floor.Model.Execution

- The Index parser's `IndexDepotModel` is the linter's dependable `Floor.Model`.
- Before reportable checks execute, the linter assembles the complete parsed model for configured depot surfaces.
- A binding projects target documents from that complete model. The check receives both the complete model context and its selected targets so cross-surface checks remain possible without hiding applicability conditionals inside iteration code.
- Structural producer stages may consume an empty or partial projection while they establish legacy inventories needed by later checks; this slice does not redesign the structural pipeline.

### Agendix.Inventory

- Depot discovery derives `agendix/` beside `appendix/`; no `--agendix` input is added.
- Agendix files appear in the same public depot file/surface inventory as chapter and appendix documents.
- `--scope <agendix path>` therefore filters real inventoried files and findings rather than relying on parser-only side discovery.

### Surface.Applicability

- General syntax, anchor, and support-reference checks target chapter, appendix, and agendix documents as applicable.
- Reviewed cite closure targets chapter and appendix while retaining agendix in the complete model as comparison context.
- Chatlas approval and verbatim-gate checks target chapter and appendix only.
- Chatlas grounding provenance remains applicable to all live content surfaces because agendix support references still require resolvable provenance.

## Execution.Plan

### Vertical.Slice::Binding.Model

- status: pending
- change: introduce the Index-linter check binding and floor projection, then register existing structural and parser-backed checks through it
- observable result: applicability is declared at registration and parser check loops consume selected target documents
- check: run the existing Index linter selector and line-check suites
- risk: breaking the external-check socket; update the Chatlas bridge in the same slice

### Vertical.Slice::Agendix.Inventory

- status: pending
- change: derive agendix paths from depots and include them in configured surfaces, discovered files, parser loading, JSON inventory, and scoped reporting
- observable result: depot-wide JSON lists `files.agendix` and an agendix-only scope is recognized without a new flag
- check: run the existing Index linter suite and a direct CLI JSON probe against `agentos-pkg/agendix`
- risk: appendix-specific structural checks accidentally consuming agendix; keep their bindings and inventories distinct

### Vertical.Slice::Reviewed.Bindings

- status: pending
- change: bind Chatlas approval and verbatim checks to chapter/appendix while keeping grounding provenance on all content surfaces
- observable result: the external checks receive explicit target projections rather than scanning every parsed kernel line
- check: run the existing Chatlas Index-check suites
- risk: external API drift between editable packages; verify both repositories against the installed editable environment

### Vertical.Slice::Documentation

- status: pending
- change: update affected `AGENTS.md` architecture notes and this artifact's final state
- observable result: project guidance describes agendix depot inventory and explicit check bindings accurately
- check: inspect final diffs and run focused lint/type checks already present in the repositories

## Deviation.Triggers

- stop if implementing the binding requires changing POI class identity or resolution semantics
- stop if agendix cannot be inventoried without adding a public `--agendix` flag
- record and reassess if existing structural checks require a full parser-pipeline rewrite rather than a bounded adapter

## Acceptance.Signals

- agendix is present in depot surface and file inventory
- agendix paths work with ordinary `--scope`
- check applicability is explicit in bindings rather than scattered solely through surface-kind guards
- approval and verbatim-gate checks do not target agendix
- no new tests were added
- focused existing suites pass

## Impl.Agendix

- [CT] The user explicitly invoked end-to-end implementation development for this design. ^c20260801-8u
- [CT] `Floor.Model` is the producer-independent structured input consumed by downstream interpretation: `agentos-pkg/design/107-design.md#Floor.Model`.
- [CT] `POI.Linter` evaluates a `Floor.Model` through `POI.Check`s: `agentos-pkg/design/107-design.md#POI.Linter`.
- [CT] detection mechanics belong to `POI.Check`, while meaning and resolution policy belong to `POI.Class`: `agentos-pkg/design/107-design.md#POI.Check`, `agentos-pkg/design/107-design.md#POI.Class`.

## Impl.Log

- 2026-08-01: Design phase completed from the current code and index contracts. The user explicitly excluded new regression tests; verification will use existing suites and direct CLI probes.
