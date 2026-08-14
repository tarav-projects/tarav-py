# Cross-Skill Context Reachability Impl.Req

## Impl.Abstract

- status: complete
- scope: extend `Context.Loading.Model` across Skillware package boundaries, type cross-skill router loads as whole-file graph edges, add target-side `--reachable-from` assertions, expose graph-wide reachability auditing, and make every Skillware-managed public skill in `agentos-md/skills` reachable from `tarav-pkg/SKILL.md`
- source: the current autonomous Hugentics implementation request ^c20260802-12u
- out of scope: Workspace.Context.Path composition, addressed-content dependency modes beyond the existing local model, converting unmanaged external skills to Skillware, and inferring load edges from free-form `--to` text

## Impl.Index

### Runtime.File.Identity

- Runtime graph nodes are whole runnable files identified by package id plus package-relative path.
- `skw.json` owns the package's explicit `id`; its `deps` registry maps other package ids to package roots.
- Runtime file locators use the existing package-qualified form `@<package-id>/path` across packages and ordinary relative paths within one package.

### Cross.Skill.Loading.Edge

- `Routing.Table --load` is the typed whole-file loading edge. `--to` remains the routed effect and is never parsed as a file reference.
- A local `--load references/x.md` connects two files in one package. A qualified `--load @<other-skill>/SKILL.md` connects the loader to another package's skill root.
- Skillware validates that the destination package is registered, its declared id agrees with the registry key, and the runnable target exists.

### Context.Reachable.From

- Repeatable `--reachable-from <runtime-file-locator>` is a file-level assertion over the loading graph, distinct from `Context.Loading.Path` and `Context.Loading.Dependency`.
- The assertion is satisfied when at least one directed loading path exists from the named file to the declaring target file.
- Each satisfied assertion returns a deterministic witness path. Missing package identities, files, edges, and paths fail closed.

### Context.Graph.Audit

- `agentos skw context --skill <root>` audits every `--reachable-from` assertion visible in the root package graph without merging path contexts.
- `agentos skw context --skill <root> --target @<package>/SKILL.md` projects the target's witness path; existing local-target projection remains unchanged.
- Text output stays compact and JSON exposes package-qualified steps, typed edge provenance, and per-target satisfaction.

### Agentos.Root.Adoption

- `tarav-pkg` registers its public Skillware-managed skill packages, gives every public target a semantic router row with a qualified `--load`, and types the existing unmanaged Chatlas destination as a load edge without claiming a target-side assertion.
- Every managed public target declares `--reachable-from @<tarav-pkg>/SKILL.md` at the file point.
- The graph audit is the acceptance check that the root remains a discoverability origin without requiring every route to be direct in future revisions.

## Execution.Plan

### Vertical.Slice::Language.And.Identity

- status: complete
- change: add explicit package ids, parse `--reachable-from`, and validate canonical runtime-file locators
- RED.GREEN.Test.Suite: parser and config tests reject missing values, malformed locators, misplaced declarations, duplicate ids, and registry/id disagreement while accepting repeatable file-level assertions
- observable result: Skillware sources and package configs carry stable runtime graph identities

### Vertical.Slice::Cross.Package.Graph

- status: complete
- change: generalize router `--load` edges across registered packages and add deterministic reachability witness resolution
- RED.GREEN.Test.Suite: context tests cover direct and transitive cross-package paths, an unmanaged runnable target, unknown packages, missing files, and unreachable assertions
- observable result: qualified router loads behave as typed whole-file edges without interpreting `--to`

### Vertical.Slice::Audit.Command

- status: complete
- change: make `--target` optional for graph-wide audit and support package-qualified target projection
- RED.GREEN.Test.Suite: command tests cover compact audit output, JSON witness paths, failure on an unsatisfied declaration, and unchanged local projection behavior
- observable result: one command verifies all reachability assertions visible from a root skill

### Vertical.Slice::Agentos.Adoption

- status: complete
- change: register and route every managed public Agentos skill from `tarav-pkg`, annotate each target, rebuild managed surfaces, and update Skillware operator/developer documentation plus `agentos-py/AGENTS.md`
- check: run the real root graph audit, all affected Skillware builds/checks, focused and full `agentos-py` suites, Ruff, and `git diff --check`
- observable result: every managed public Agentos skill has a verified path from `tarav-pkg/SKILL.md`; all existing root cross-skill rows carry typed load edges

## Impl.Agendix

- touched: the current implementation gate authorizes cross-skill typed loading edges and root reachability enforcement ^c20260802-12u
- structural: `notes/live/717-context-loading-model-impl-req.md` owns the local Context.Loading.Model slice this request extends
- structural: `agentos-md/skills/tarav-pkg/.skw/src/SKILL.skw.md^package-driver-router` owns the root routing table being typed

## Impl.Log

- 2026-08-02: autonomous execution authorized by the current `--impl --dev --AUTO` turn ^c20260802-12u
- 2026-08-02: the first real package build exposed a second local-only router-load validator in expansion; generalized it to the same registered package-qualified runtime locator contract rather than special-casing the Agentos root.
- 2026-08-02: Agentos Project Doctor still depended on the retired Hugentics `^index-ground-entry`; reconciled it to `^driver-index-literacy` and re-derived the consumer wording before final checks.
- 2026-08-02: completed with thirteen managed public Agentos skill witnesses from `tarav-pkg/SKILL.md`, typed loading to the unmanaged Chatlas skill, zero affected Skillware POIs, 102 focused tests, 632 full-suite tests, and Ruff/diff checks clean.
