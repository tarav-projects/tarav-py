# Project integration managers

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Status: implemented and verified; native capture limitations recorded below. Knowledge.Surface: wiki.

Give Project Classes extensible ActionManager, ChecksManager, SkwManager and
RecordsManager integration objects. Move existing Project integration into
them, including the checks-to-actions status loop. Preserve current check,
POI, action identity, closing, selection and persistence behavior. This is
a refactor with new extension points, not a new action lifecycle, pipeline,
event bus or background executor.
<!-- tarav.breadcrumb 96dfae0eb3c8 -->

## Design

Workflow primitives keep their core functionality and semantics. Managers
belong to a particular Project Class, and derived Project Classes can extend
their implementations using ordinary Python inheritance. The familiar bound
paths remain project.actions, project.checks, project.skw and project.records.
<!-- tarav.breadcrumb 3a906af6c35a -->
<!-- tarav.breadcrumb 74f161cea701 -->

Managers own integration behavior, including loops and hooks. In particular,
the current status loop belongs to ActionManager; Project.status remains a
convenience entry point delegating to it. ChecksManager runs checks without
updating actions. The current POI-to-action integration is supported without
making POIs the definition of actions in general.
<!-- tarav.breadcrumb 1a8a62a93b8b -->
<!-- tarav.breadcrumb b37111fcee8e -->

Implementation choices: reuse the existing class-selected namespace mechanism.
Extract ProjectActions from l1.actions.project into l1.project.actions as
ActionManager, bind it to a Project, and remove the old module after migrating
callers. An explicit ownership-only factory supports Git signals without
loading executable Project types; only a fully bound Project runs status.
ChecksManager extends CheckProvider.Checks. RecordsManager extends the
existing Record namespace, preserving object/class serialization, and exposes
the current type registry and standard Record storage for manager consumers.
SkwManager binds source Documents to a Project; its l2 specialization discovers
skill depots and supplies their checks. DocsProject composes that suite and
Wiki checks. Preserve the agents-file local registry fallback.

The existing primitives, Record schemas and stored identities do not change.
There is no implicit universal hook dispatch. Manager methods are explicit
extension points. No compatibility alias for the removed ProjectActions path
will be added; migrate maintained consumers in this repository.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md, notes/wiki/.
Relevant context: projects.md and poi-system.md, especially the 2026-10-11
Project/checks/actions integration and 2026-10-12 detector rules.
The current code adds SuiteCheckpoint disappearance evidence; retain it.
Supporting User Turns are attached above. Completion capture will append to
projects.md and daily/2026-10-22.md. This note is implementation coordination,
not a replacement for those sources.

## Execution.Plan

One coherent refactor slice, with feature verification of subtype extension:

1. Baseline existing action, Project, agents-file and architecture tests.
2. Remove the old ProjectActions module while migrating its consumers;
   extract Project check composition and status coordination into managers.
3. Add RecordsManager registry access and base/featured SkwManagers; move
   DocsProject Skillware integration there and preserve standalone checks.
4. Verify manager selection on a derived Project Class, overridden loop and
   result handling, custom Record storage, SKW source binding and depot checks.
   Rerun baseline suites, Git integration tests, architecture checks and Ruff.
5. Update architecture and authoritative AGENTS source, rebuild its product,
   submit/audit supported inline capture, and run full Project status --all.

Data shape: bound Python manager objects; existing CheckSuite results,
ProjectStatus, ActionRun and RecordRegistry remain the retained interfaces.
Accessors select type(project).Actions/Checks/Skw/Records. No new retained
schema or migration is needed. Subtract the old hard-coded action factory,
Project-owned status loop and DocsProject-owned SKW discovery/check generator.
Keep layers directional: base managers in l1.project; skill integration in
l2.project. Evidence: existing behavioral suites before/after, plus focused
manager extension tests. If current state requires changing lifecycle semantics
or adding higher-layer imports to lower layers, stop and align first.

## Impl.Log

- Start checkpoint, clean tarav-py: 45859c454c3528c27445997fdfcc84b2941ff288.
- Start checkpoint, clean Wiki repository: 6567eee6ab14d29d206479113674b963dc9e588d.
- Single exact Chatlas refresh completed. Session ec6cf584 resolved through
  the verified current-session command; no inferred session identity.
- Practices: subtract before adding removes the former action integration
  path; boundary discipline leaves action/check semantics with their Types.
- Design-note checkpoint: 75ded0a981495e123ef4b1527cdd1fac5d288d16.
- Cold-read this request before product changes; inspected interfaces matched
  the plan. No lifecycle or retained-schema change was needed.
- Baseline: 110 existing action/Project/agents/architecture tests passed.
- Slice: moved the former ProjectActions implementation to project.actions,
  bound it as ActionManager, and moved status coordination there. Added the
  ChecksManager, RecordsManager and base/featured SkwManagers. Migrated all
  maintained old imports and moved DocsProject's SKW work into its manager.
- Updated the CLI fixture to declare the managers its borrowed accessors now
  select. Initial new tests needed a complete Project marker and the actual
  document factory's missing-depot error contract; corrected those fixtures,
  without changing the product to fit an incorrect expectation.
- Measured: 116 focused action/Project/agents/architecture/manager tests pass;
  51 manager/Git/SKW/agents/context integration tests pass. Ruff and diff
  whitespace checks pass. These suites overlap; counts are not additive.
- New tests exercise all four class-selected managers, custom action Record
  storage, direct checks without action updates, status delegation, child
  manager loops, and SKW source/depot selection. Existing detector/checkpoint,
  identity, blessing and reopening tests continue to pass.
- Reinstalled the editable CLI. Produced and compiled the authoritative
  agents source; compilation reported no findings.
- Product inline capture: 23 new Breadcrumbs across 20 Python/Markdown
  surfaces, all newly attached turns resolved. Position observations were
  refreshed after moves. Twelve older TurnUnavailable findings remain:
  nine in ARCHITECTURE.md, two in l2/project/__init__.py and one in
  tests/test_architecture.py. Their old labels were preserved.
- Native capture limitation: the authoritative AGENTS.skw.json source is
  unsupported (`Cannot infer surface language from .json`). TOML test-path
  configuration and generated lock/AGENTS products likewise have no new
  source-level Breadcrumb annotation; the supported design note and code
  retain the discussion. No guessed labels or JSON comment syntax were added.
- Wiki capture: projects.md and daily/2026-10-22.md submitted nine new
  Breadcrumbs and both audits passed with no POIs. The request's five
  design Breadcrumbs were submitted and audited before execution.
- Full root `tarav status --project . --all --json` completed: 1,329 checks
  completed, zero incomplete, and no pytest findings. It returned 1 because
  67 already-registered actions remain open. Action changes were all zero:
  none opened, reopened, closed or updated. No unrelated findings were repaired.
- Wiki closure: eb1c311e43f301d4ad5f9ab3dd50b5600a5bde62.
- Implementation slice commit: 5700e120704546e9f105967a9e620260276db1f0.
- The full status run included 59 completed pytest file checks, with zero
  pytest POIs. This is a file-check count, not an invented individual-test count.
- All five start/design/slice/Wiki commit Breadcrumb audits passed. The Wiki
  audits have no POIs; remaining product audit gaps are the explicitly listed
  older missing-turn references and unsupported source formats.
- Slice status: verified. Product and Wiki capture completed for supported
  native surfaces; the source-format limitation and older evidence gaps above
  remain explicit. Scope is the 26 implementation paths in this repository
  plus projects.md and daily/2026-10-22.md in the Wiki repository.
- Completion: no product work remains in this request. This final log update
  is the completion commit; no unrelated worktree changes were present.
