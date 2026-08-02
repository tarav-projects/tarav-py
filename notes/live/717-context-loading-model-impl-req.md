# Context.Loading.Model Skillware Support Impl.Req

## Impl.Abstract

- status: complete
- scope: add Skillware runtime-context support through file-level `Context.Loading.Path` declarations, route-backed skill-local path resolution, path-specific `Projected.Context` assembly, addressed `Context.Loading.Dependency` validation, canonical Batchy contract materialization, and Hugentics adoption
- source: the current Hugentics design discussion and the parked `Context.Loading.Model` agendix block
- out of scope: workspace-provided context, inline and semantic dependency modes, global path-coverage enforcement, automatic agent prompting, and runtime guarantees beyond the declared model

## Impl.Index

### Context.Loading.Path.Declaration

- A managed target may declare one or more complete normal paths with addressed top-of-file `--context-loading-path` annotations and repeatable ordered `--step` values.
- The declaring file is the implicit final step; written steps use runnable skill-root-relative paths such as `SKILL.md`, not `.skw/src` paths.
- Every declared local path contains `SKILL.md`. Existing skill-local `AGENTS.md` files may precede it when explicitly declared; `.skw/AGENTS.md` is builder guidance and never consumer context.
- Several addressed declarations on one file remain separate paths. Their projected contexts are never merged.

### Local.Loading.Graph

- Skillware derives loader-owned edges from `Routing.Table` rows and their `--load` targets.
- `SKILL.md` is the mandatory skill-loading transition. Explicit skill-local `AGENTS.md` steps before it are constitutive local-context nodes rather than dynamic router loads.
- Dynamic adjacent steps after `SKILL.md` must be realizable through declared `--load` edges. The model reports missing files, invalid roots, repeated/cyclic steps, and unrealized dynamic edges rather than inventing an implicit route.
- The first slice validates declared/selected paths without requiring every existing router target in every skill to opt into the model at once.

### Projected.Context

- `Projected.Context` is computed for one target and one declared path by accumulating whole runnable files in appearance order through the target step.
- `agentos skw context --skill <skill> --target <file>` resolves all declared paths for the target and returns each projection independently with path identity, ordered steps, edge provenance, per-step content, and the assembled context.
- Text output is developer-readable; `--json` is the stable machine-consumable projection. A target with no declaration or a path that cannot be realized fails without mutation.

### Skillware.Boundary

- `--dev-from` remains builder context and is not reinterpreted as runtime loading.
- `Context.Assembly.Module` remains a curated builder-context surface and is not a substitute for a runtime loading path.
- The annotation is stripped during compilation; its model remains available from `.skw/src` to the Skillware developer and checker.

### Context.Loading.Dependency

- `--loading-dep <source-locator>` is repeatable on any annotation and declares addressed runtime content that the consuming file fundamentally requires.
- The first satisfaction mode is context-available: the locator must resolve to addressed content in a managed provider whose runnable file occurs earlier on every declared path reaching the consumer.
- Skillware verifies that the resolved addressed content is actually materialized in the provider's runnable file; a declaration alone is insufficient.
- Dependency results remain path-specific and are never satisfied from the unsafe union of several paths.

## Execution.Plan

### Vertical.Slice::Language.Model

- status: complete
- change: extend the SKW parser with addressed, top-of-file `--context-loading-path` declarations and repeatable `--step` fields represented explicitly in `SkwSource`
- observable result: valid declarations parse as separate ordered paths and malformed declarations produce focused parser findings
- check: parser RED/GREEN tests covering one path, multiple paths, missing address/step/SKILL, and non-file-point placement

### Vertical.Slice::Projection.Command

- status: complete
- change: add the skill-local loading graph and `agentos skw context --skill ... --target ... [--json]` command
- observable result: a declared target returns path-specific ordered projections with route or constitutive-edge provenance and assembled whole-file content
- check: command tests for a direct route, local `AGENTS.md`, multiple paths, missing declarations/files, and unrealized dynamic edges

### Vertical.Slice::Documentation.And.Adoption

- status: complete
- change: document the syntax and command in the managed `agentos-skillware` surfaces, update `agentos-py/AGENTS.md`, declare the direct `SKILL.md -> references/capture.md` path in `agentos-hugentics`, and rebuild both managed skills
- observable result: the real Hugentics capture module projects successfully through the installed CLI and no Skillware drift remains
- check: run the real projection, both affected Skillware builds/checks, focused Skillware tests, Ruff, and `git diff --check`

### Vertical.Slice::Loading.Dependency

- status: complete
- change: add repeatable `--loading-dep` locators, path-specific addressed-content validation, compact shared Hugentics runtime contracts in `SKILL.md`, and accurate child declarations
- observable result: each projected child reports its required root contracts as satisfied by the earlier `SKILL.md` step and fails when a provider is missing, later, unresolved, or not materially present
- check: parser and projection RED/GREEN tests, real Hugentics projections, both affected Skillware checks, Ruff, and `git diff --check`

### Vertical.Slice::Canonical.Batchy.Contract

- status: complete
- change: author one addressed runner-facing Batchy runtime contract, materialize it into Batchy and Hugentics `SKILL.md` files, consolidate duplicated Hugentics Batchy contracts, and remove the reverse Batchy-to-Hugentics build dependency
- observable result: Hugentics children depend on one local materialized Batchy contract whose exact source resolves to `agentos-batchy-skills`, while Hugentics-specific command and authority contracts remain locally owned
- check: build/check both managed skills, resolve every real Hugentics projection, verify copy equality and the directional package registry, and run `git diff --check`

## Parked.Extensions

These extensions are intentionally remembered but are outside this implementation's acceptance criteria:

- `Workspace.Context.Path`: explicit external `AGENTS.md` parents plus symbolic `SKILL.Description`, `User.Turn`, and bound `Skill.Arg` contributions, composed with the skill-local path at `SKILL.md`
- additional `Context.Loading.Dependency` satisfaction modes such as explicitly inlined content
- semantic dependency requirements and prompts supplied to the developing agent
- validation that every declared addressed-content dependency actually exists in every applicable path projection
- full bidirectional POI coverage for router targets without path declarations and declared predecessor paths without a corresponding route or prompted-load command

## Deviation.Triggers

- stop if the first slice requires defining the Workspace prefix vocabulary to produce a useful local projection
- stop if runtime paths can only be represented by reinterpreting `--dev-from` or context assemblies
- record and reassess if route/path validation would force immediate all-file adoption across existing skills
- do not silently union multiple paths or count `.skw/AGENTS.md` as consumer context

## Acceptance.Signals

- the SKW parser exposes addressed ordered loading-path declarations
- the context command resolves and assembles every declared path separately
- skill-local `AGENTS.md` steps are supported before the mandatory `SKILL.md` transition
- post-`SKILL.md` dynamic edges are backed by `Routing.Table --load` declarations
- Hugentics `references/capture.md` produces a real `Projected.Context`
- repeatable `--loading-dep` locators resolve to addressed content materially present in an earlier provider on every path
- all routed Hugentics children declare their fundamental root-contract dependencies without duplicating those contracts locally
- universal Batchy runtime behavior is copied exactly from one addressed `agentos-batchy-skills` provider into consuming root skills; concrete arguments, commands, and domain authority remain local extensions
- affected tests, static checks, builds, and Skillware checks pass
- parked extensions remain explicit and unimplemented

## Impl.Agendix

- [CT] The user accepted the first local path slice, required skill-local `AGENTS.md` files to be representable, and requested the later subsystem work remain parked in this artifact. ^c20260802-1u
- [CT] The user explicitly invoked the end-to-end implementation workflow for this slice. ^c20260802-1u
- [CT] The provisional conceptual source is `agentos-md/skills/agentos-pkg/agendix/Context.Loading.Path-agendix.md#Context.Loading.Path/Agendix/Context.Loading.Model`.

## Impl.Log

- 2026-08-02: Design phase completed from the current SKW parser, Routing.Table model, command registrar, managed Skillware documentation, and the agreed local projection boundary. ^c20260802-1u
- 2026-08-02: Added the addressed file-point `--context-loading-path` language, ordered `--step` parsing, declaration validation, and explicit `SkwSource` path records. ^c20260802-1u
- 2026-08-02: Added route-backed local graph resolution and `agentos skw context`, preserving each complete path as a separate provenance-bearing `Projected.Context`. ^c20260802-1u
- 2026-08-02: Documented the language and command, updated project guidance, and adopted a direct loading path for the Hugentics capture module. Deferred Workspace context and dependency semantics remain parked above. ^c20260802-1u
- 2026-08-02: Verified 612 Python tests, focused Ruff checks and formatting, clean Skillware checks for 8 Skillware files and 32 Hugentics files, and a real 47,966-byte `SKILL.md -> references/capture.md` projection. ^c20260802-1u
- 2026-08-02: Reopened the artifact for addressed `Context.Loading.Dependency` support; added `--loading-dep`, path-specific provider/materialization validation, and dependency results in `Projected.Context`.
- 2026-08-02: Added six compact operator-facing contracts to Hugentics `SKILL.md` and declared accurate dependencies across all 30 routed child modules; the real graph resolves 102 satisfied dependencies at the earlier `SKILL.md` step.
- 2026-08-02: Verified 617 Python tests, Ruff, both managed Skillware checks, all 30 real Hugentics projections, and repository diff integrity.
- 2026-08-02: Added `^batchy-skill-runtime-contract` to the Batchy runner guide and mechanically copied it into both the Batchy and Hugentics roots; the three duplicated Hugentics run/router/module contracts collapsed into one local materialization.
- 2026-08-02: Kept concrete Hugentics argument, command, authority, and Index contracts local; migrated all 30 children to the copied Batchy address, producing 90 satisfied real dependencies without runtime cross-skill loading.
- 2026-08-02: Removed Batchy's reverse build dependency on Hugentics, registered the directional `hugentics -> batchy` package dependency, verified exact copy equality, and completed all affected Skillware checks without POIs.
