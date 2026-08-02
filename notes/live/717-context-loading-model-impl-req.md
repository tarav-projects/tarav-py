# Context.Loading.Model Skillware Support Impl.Req

## Impl.Abstract

- status: ready for execution
- scope: add the first Skillware runtime-context vertical slice: file-level `Context.Loading.Path` declarations, route-backed skill-local path resolution, path-specific `Projected.Context` assembly, and one real Hugentics adoption
- source: the current Hugentics design discussion and the parked `Context.Loading.Model` agendix block
- out of scope: workspace-provided context, semantic or addressed-content dependencies, global path-coverage enforcement, automatic agent prompting, and runtime guarantees beyond the declared model

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

## Execution.Plan

### Vertical.Slice::Language.Model

- status: pending
- change: extend the SKW parser with addressed, top-of-file `--context-loading-path` declarations and repeatable `--step` fields represented explicitly in `SkwSource`
- observable result: valid declarations parse as separate ordered paths and malformed declarations produce focused parser findings
- check: parser RED/GREEN tests covering one path, multiple paths, missing address/step/SKILL, and non-file-point placement

### Vertical.Slice::Projection.Command

- status: pending
- change: add the skill-local loading graph and `agentos skw context --skill ... --target ... [--json]` command
- observable result: a declared target returns path-specific ordered projections with route or constitutive-edge provenance and assembled whole-file content
- check: command tests for a direct route, local `AGENTS.md`, multiple paths, missing declarations/files, and unrealized dynamic edges

### Vertical.Slice::Documentation.And.Adoption

- status: pending
- change: document the syntax and command in the managed `agentos-skillware` surfaces, update `agentos-py/AGENTS.md`, declare the direct `SKILL.md -> references/capture.md` path in `agentos-hugentics`, and rebuild both managed skills
- observable result: the real Hugentics capture module projects successfully through the installed CLI and no Skillware drift remains
- check: run the real projection, both affected Skillware builds/checks, focused Skillware tests, Ruff, and `git diff --check`

## Parked.Extensions

These extensions are intentionally remembered but are outside this implementation's acceptance criteria:

- `Workspace.Context.Path`: explicit external `AGENTS.md` parents plus symbolic `SKILL.Description`, `User.Turn`, and bound `Skill.Arg` contributions, composed with the skill-local path at `SKILL.md`
- `Context.Loading.Dependency`: addressed requirements with satisfaction modes such as context-available versus inlined in the consuming surface
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
- affected tests, static checks, builds, and Skillware checks pass
- parked extensions remain explicit and unimplemented

## Impl.Agendix

- [CT] The user accepted the first local path slice, required skill-local `AGENTS.md` files to be representable, and requested the later subsystem work remain parked in this artifact. ^c20260802-1u
- [CT] The user explicitly invoked the end-to-end implementation workflow for this slice. ^c20260802-1u
- [CT] The provisional conceptual source is `agentos-md/skills/agentos-pkg/agendix/Context.Loading.Path-agendix.md#Context.Loading.Path/Agendix/Context.Loading.Model`.

## Impl.Log

- 2026-08-02: Design phase completed from the current SKW parser, Routing.Table model, command registrar, managed Skillware documentation, and the agreed local projection boundary. ^c20260802-1u
