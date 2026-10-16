# Project System Prompt

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
64298cbc = claude-code:9da4cef5-68b7-4d17-8a06-1351ca51e82f @64298cbc8db2e7aa971e0828653c07bcb483cfed40931fdf87d5abe7ce1c60b3
-->

## Read first

- Load the `tarav-pkg` skill and read its `CONSTITUTION.md`. Any surface claiming
  to be part of Tarav must comply with it.
- `tarav-py` is the single maintained Agentos Python distribution.
- Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing subsystem ownership or
  cross-domain imports.
- Keep this file and `ARCHITECTURE.md` current when a change affects their
  contracts. They are guidance, not an implementation history.
- `_DEPRECATED/` contains historical snapshots. Do not implement there.

## Tooling

- Use `uv` for environments, commands, tests, and package operations.
- Confirm the installed CLI with `tarav --version` and discover command details
  through `tarav --help` and `tarav <command> --help`.
- Prefer direct `tarav ...` commands when the tool is installed.
- After changing an entrypoint or installed command behavior, run
  `uv tool install --reinstall --editable .`.
- Run focused tests first, then validation proportional to the affected
  boundaries. Ruff covers `src`, `tests`, and tooling; maintained checks exclude
  `_DEPRECATED/`.

## Architecture

- `tarav.l3.runtime.create_runtime()` currently assembles the installed
  workflows. Its location and responsibilities do not define the architecture;
  lower layers must not import it.
- `tarav.l3.runtime.get_runtime()` exposes the lazy process-wide current runtime. Kernel's
  current Record-registry accessor lets Record Archive load and validate without
  importing that runtime. Select custom runtimes with `tarav.l3.runtime.set_runtime()`.
- Keep subsystem imports acyclic outside runtime composition.
- Record Archive lives in `tarav.l1.archive.records`, matching its Archive parent.
  Artifact-registration Record types live in `tarav.l1.archive.artifact_records`.
- Context construction is explicit: `cxt = obj.context.build()` returns an
  `ObjectContext`, then `cxt.triplets` supplies its graph contribution.
  `_class_context_hook(cxt)`, `_obj_context_hook(cxt)`, then external hooks
  share that mutable result. Compose hooks through `super()`. Register
  external `ContextHook` instances on `runtime.contexts`; registrations are
  runtime-local. Each hook's `run(cxt)` decides whether to contribute.
  Class access builds its identity object's context: `Type.context` is
  `entity(Type).context`. `obj.context()` opens a `ContextExplorer` that
  retains built results and whose graph only grows. Identifier resolvers
  are composed in `TaravRuntime.context_queries()`. Kernel delegates through
  host callbacks without importing Context or RDFLib. Named views still fail.
  <!-- tarav.breadcrumb ad0f4807b92fcc359c084cc69e7966cba5579b315e690981d7f52748b89856bb -->
  <!-- tarav.breadcrumb 0094f5ae9193c13bbbd28788ad4a2cb23d873dd94c4bd39237357af38be25256 -->
- Provider-neutral orchestration belongs in `tarav.l1.agent`; concrete adapters
  belong in `tarav.l1.agent.providers.<provider>`.
- Shared infrastructure enters `tarav.l0._core` only after multiple consumers have
  demonstrated the same semantics. Callers retain policy, schema validation,
  locking, and error translation.
- Shared utilities and Kernel live under `tarav.l0`. Independent workflow
  mechanics live under `tarav.l1`; cross-workflow features and integrations
  live under `tarav.l2`; the installed runtime and process adapters live under
  `tarav.l3`. A workflow may have modules in several layers, as Context and SKW
  do. The root package contains metadata only; use explicit layered imports.
  Lower layers do not import higher layers.
- Lower-level modules do not import or shell out to the umbrella CLI.
- Do not add compatibility aliases or fallback paths unless the user explicitly
  requests a migration design.

## Project model

- Explicit Project-local harness mechanics live in `tarav.l2.project.harness`;
  runtime bootstrap and command launch live in `tarav.l3.project`. Discovery
  never provisions. `tarav project harness` scaffolds, inspects, and syncs
  `.tarav/env`; `tarav run [--project [PATH]] -- <python arguments>` is the sole
  Python execution CLI.
  <!-- tarav.breadcrumb 62f9b9610c90a49367930ec4ceb23870ff8317959192d9ffba572c3d1d2a409c -->

- This folder is a `Tarav.Project.PythonPackage` child of the Taravangian
  root (`../.tarav/project.json`) and uses the root's environment
  (`harness.project`). `tarav status --project --all` runs the pytest
  tests as a `PyTestSuite`, one suite per test file; each failing test is a POI.
  Without `--all` the tests are left out. Development still uses this folder's own
  `.venv` through `uv run`.
  <!-- tarav.breadcrumb 2407cd94597e19dd391e332b269374527b2c4be897c48078f7d31ae1d691c845 -->
- A harness manifest may list several trusted Project Types
  (`[tool.tarav.harness] projects`), started through `tarav.l3.project.launch`.
  `RootProject` (`tarav.l2.project.root`) lists child Projects in its marker
  and its `checks` are theirs; a child may declare `harness.project` to use
  the environment of an ancestor that lists it. Tarav does not model the
  Python library; a Project Type is an object inside one.
  <!-- tarav.breadcrumb d310f661f8f7879f3921034bdf5fde72b44b06fc86b842b082a64c57cf5ce6d8 -->
- `.tarav/project.json` is the canonical project marker. It stores portable
  project identity and metadata, not machine-local paths.
- The featured `Project.workspaces()` interface delegates to the independent
  Workspaces workflow; minimal `TaravProject` does not import it. Workspace
  manifests live under `~/Documents/tarav/workspaces/` and are not Project
  marker fields. Git worktrees are created and removed through `GitRepository`.
  <!-- tarav.breadcrumb 974d29f6f10401aa7ea49d4165f6cb29d198adc956fff1f28f085109dcad2bff -->
- `Project.decisions()` is the Project's Decision store, `.tarav/decisions/`:
  one append-only file per Record, any `Decision` subtype, filtered by Type
  including subtypes. Project blessings live there through
  `Project.decisions().blessings()`. The Decisions workflow owns no storage,
  and other workflows may still keep Decisions elsewhere.
  <!-- tarav.breadcrumb 8f4344f85bcaecfe7ab8c9fc47cddb92f71f93869fd489846ad5bc69136ad845 -->
- For `tarav run`, a bare `--project` discovers the nearest Project from the
  current directory upward, and fails when there is none. Without the flag,
  `tarav run` uses the installed Tarav interpreter even inside a Project.
  <!-- tarav.breadcrumb a063022465541b6bdc1076d3a5ad853099d0c2c8f01eb8243e32c7b976917a5f -->
- `TaravProject` is a `CheckProvider`: base checks cover its agents file and
  the skill bootstrap; a subtype adds its suite in `Checks.suite()` and calls
  `super().suite()`. `project.checks.run()` executes the composed suite.
  <!-- tarav.breadcrumb e975fb22535bf1b80fc7ee95b2b15fb340d677036ab7ba55adbba1f3c064deaf -->
  <!-- tarav.breadcrumb f1b6c4d85568e1afc1b76afc02983662c5d2be806b568698cd7b28b853a639e6 -->
  <!-- tarav.breadcrumb 2cad01bfc733b3b450e3908f187d06d110c511dd5329d9b74e0165b87839fbc9 -->
- A Project whose root is a Git repository selects Tarav Git hook handlers in
  the `git` section of its config (`tarav.l1.git.hooks`). `tarav git hooks
  install --project [PATH] [--handler NAME]` writes `.tarav/git-hooks/` and
  sets `core.hooksPath`; the scripts call `tarav git hook`, and a missing or
  failing `tarav` never blocks Git. The Project suite reports drift. The first
  handler, `tarav-change` (`tarav.l1.git.change`), gives each commit an ID in a
  `tarav-change:` trailer and a line of `.tarav/changes`, so `tarav git change
  find --id <id>` finds the commit after a history rewrite. This repository
  uses it.
  <!-- tarav.breadcrumb 3ac71846f72a6a9632d30bfe3a73cfd107bb0cd34eb6539f7428fa690a94e9c0 -->
  <!-- tarav.breadcrumb 1e1e0a27ff6ad6e419e9317087e988a49b106cd6494a4a888e07f3ffec8731ed -->
  A handler may also stop Git on purpose (`GitHookRefusal`, exit 75), so
  whoever commits rethinks; `TARAV_GIT_HOOKS_OVERRULE=<handler>` overrules it.
  tarav-change stops a commit whose `.tarav/changes` lost IDs that the
  witness (`tarav.l1.git.witness`, under `~/Documents/tarav/git-changes/`, per
  Project and branch) saw at the branch's last commit; stops and overrules
  become actions of the Project.
  <!-- tarav.breadcrumb 1413fcedc6ffd4d8a10e9416bda015b20e328a738611e646ebd91c144b1418dd -->
- `project.agents.skills` discovers skill folders in Project and home
  `.agents/skills`, using each `SKILL.md` declared name. Set
  `agents.package_skill` in `.tarav/project.json`; the built-in Tarav skill
  name is `tarav-pkg`. Project and home must each have `.agents/skills`
  and `.claude/skills` resolving to the same directory. Checks report
  missing skills and folder structure through typed POIs.
  <!-- tarav.breadcrumb cf13f560fbda5e4ee266ba51759419ed3ae8d3bd3e954f8b6b0f3d8b9f33ef7c -->
- `CheckProvider.checks.suite()` returns a `CheckSuite`. A suite does not contain
  checks: it holds the code that runs them (`produce()`), because which checks
  exist is only known while it runs. `run(select=...)` runs it whole or filtered
  and returns the suite itself, which holds the results of that one run, the
  summary and the report; there is no separate run object. A subclass is a suite
  with its own Type id, and a `key` binds an instance to a subject. A class with
  `routine = False` is left out of the commands unless `--all` is given.
  `tarav check --project [PATH] [--json]` runs the suite in the
  Project harness and reports grouped POIs (20 groups by default). It exits
  0 only when all Checks completed without findings. It knows nothing of actions.
  <!-- tarav.breadcrumb 1b6aa81a76ec0d6ff43faa8d080ab26dd80ab3a9098cf814f141182b5e2ff406 -->
- Environment variables and machine-state paths retain the names encoded by
  their current storage contracts until an explicit migration changes them.

## Native surfaces and SKW

- `tarav.l1.skw.code` is the common developer-side source workflow. It owns
  neutral documents, blocks, annotations, reading declarations, and compilation
  contracts. Compiled products are ordinary reader-facing surfaces; readers do
  not interpret SKW Records. `skw.skills` specializes this workflow for skill
  package layout, components, loading analysis, deployment, and checks.
  <!-- tarav.breadcrumb 2d3d132a3afb327f527fb79ac581c93e13fc762438dff57a3948de0fc14da6f7 -->

- Skill packages with a `loading` declaration use `tarav.l1.skw.loading` for
  declared slot composition and `tarav.l1.skw.skills` for typed components.
  `tarav.l1.skw.code.ReadingGraph` is the common static-analysis contract;
  `SkillReadingGraph` owns the existing package binding, rendering, and path
  analysis. `ProjectReadingGraph` is only a Project-owned specialization point
  until concrete Project onboarding routes establish shared mechanics.
  <!-- tarav.breadcrumb db4b6b30bfab0d34c188dea34dfea40b0dc9cd0eff9908b7bee01f5cedf08ad5 -->
  SKW blocks are Entities with UUID Ships and separate local labels. Typed
  reading declarations belong to source blocks; the loading Record binds
  blocks and routes, while l2 reading Checks interpret path analysis into POIs.
  <!-- tarav.breadcrumb 9ec8816777a876da7cc365666a9b4796b3c702774e5e9936a9c4f266212d0ddb -->
  The installed `skw document` CLI receives this specialization
  through runtime composition. Plain `Document` is the generic engine, not a
  substitute for compiling skill primitives. Loading graphs are declared data;
  never infer parent attachments or context satisfaction from Markdown links.

- SKW context navigation defaults to compact listings. Agents select entries
  for head/tail/cat reads or use exposed absolute paths. Keep payload
  resolution for dependency checks separate from context presentation.

- JSON document sources under `.skw/src/` own all retained text for their
  product. `SkwBlock` is the neutral concrete block Type: it carries `content`,
  a typed local `objects_index`, and typed workflow-owned `annotations`.
  Generation is a `GenerationAnnotation`; reading declarations are annotation
  subtypes. Code production writes `content` explicitly. Edit agent-generated
  content in source, record it explicitly,
  and lint/compile through `tarav skw document`. Compilation must not refresh
  generation baselines or suppress stale-generation findings.

- `tarav.l1.skw.generation` is an independent Python-first generation
  workflow. Keep its template, invocation, and dependency semantics separate
  from the existing compiler and Index. Checks report evidence without repair
  or automatic generation; callers own agent execution and explicit persistence.

- `tarav.l1.surfaces` owns deliberately thin Python and Markdown normal models.
  Native parsers expose syntax and source spans only; they do not know SKW
  attachment policy or Index domain policy.
- Project-aware discovery supplies a file plus its surface context. Domain
  adapters assign domain interpretation from that context.
- `tarav.l1.skw.code` owns typed JSON document sources under `.skw/src/`.
  `tarav.l1.skw.skills` owns skill-specific component Types;
  `tarav.l2.skw.skills` owns deployable package operations and checks.
  The retired Skillware annotation compiler and `.skw.md` machinery has no
  live compatibility path.

## Chatlas

- `tarav.l1.chatlas` captures provider-native chat artifacts, indexes sessions,
  materializes the provider-neutral Normal Model, provides bounded structural
  Query and named rendering over it, and preserves traceability from normalized
  objects to retained raw artifacts.
- Chatlas Query owns selection and record assembly; Chatlas Renderers own only
  presentation. Semantic interpretation, annotation, contextualization, and
  workflow products belong to consumer domains.
- Capture and Session Index modules do not import `normal_model`; command
  composition is the exception that registers the public `tarav chatlas`
  leaves.
- Consumers import `tarav.l1.chatlas.normal_model`, not its internal modules.
- The aggregate Normal Model is a registered `DirectoryRecord`; its `main.json`
  and JSONL streams are semantic representation. Chatlas cache mechanics live
  outside that module and may decorate a cache-managed model directory with
  `cache.json` without participating in model validity.
- `chatlas.references` is a Normal Model consumer owning typed Turn references;
  capture/index modules remain independent of normalization.
- Retained raw artifacts are the evidence surface. The Session Index and
  materialized Normal Model directories are derived, replaceable, and
  rebuildable.

## Operational logging

- Library modules emit through `logging.getLogger(__name__)` and never configure
  handlers at import time. Tarav-owned entrypoints configure process logging.
- Operational diagnostics are structured JSONL under
  `~/.tarav/logs/operational/`; debug lifecycle stays there while warnings and
  errors may also reach stderr.
- Direct stdout/stderr remains appropriate for command results, progress, and
  interactive UI. Durable domain event logs are semantic data, not operational
  diagnostics, and retain their own schemas and locations.

## Editing and tests

- The Python library is the primary interface. Use `tarav run -- script.py`
  for scripts in Tarav's installed environment; source paths are available
  through `create_runtime().source_root`.
- Record/provider registration is explicit trusted code. External Record Types
  may be bound to installed class paths through `TaravEnvironment`; Records
  never select import paths. Resolution hints never affect location or identity
  checks.
- Prefer an explicit `hints` field for opaque consumer context so its role is
  self-documenting. This is a convention across objects, not a requirement that
  all hints occupy that field; mechanics must ignore hint content.
- Every `TaravType` inherits class-level `help()` as a context entry point. Its
  default returns the qualified class name, source path and line when available;
  classes can extend it with documentation and skills. Keep this mechanically
  sourced and return information rather than printing it.
- Every `TaravType` subclass defines a class-local `class_entity()` that returns
  its direct `TaravClass` ontology projection. Access Diagram identity and
  Workflow ownership through `entity(Type)`, not parallel class attributes.
- Schema changes migrate code and affected data explicitly. Runtime readers
  and validators never repair retained state.
- Prefer mechanically obtained facts, especially from the operating system
  and Git, or leave information absent. Introduce agent-generated claims only
  when necessary for a defined purpose; keep their amount deliberate and bounded.
  Examples and fixtures must model this practice too.
- Agent-facing data does not imply agent authorship. This is a development
  principle, not a runtime origin check on opaque hints. Diagram's producer,
  support, and Assertion mechanisms make agent-generated claims traceable and
  subject to validation and scoring.

- Preserve unrelated changes in the shared worktree.
- Use `apply_patch` for hand edits.
- When a manual investigation exposes a durable constraint, add a focused test
  for that constraint.
- Architecture changes update `tests/test_architecture.py` with the maintained
  docs.
- For Markdown block extraction, prefer `tarav stdlib mdblocks blocks`, `links`,
  and `find` over ad-hoc parsers.

Runtime provider wiring lives in `tarav.l3.runtime`, not the package root.
Import that assembly module before using current-registry or Workflow-instance
resolution, or explicitly configure the lower-level hooks in a custom host.
Importing `tarav` alone initializes no services or layered modules.

## Import entry points

- Run Python scripts that import Tarav with `tarav run -- <script>` or
  `tarav run --project -- <script>`. Plain `import tarav` raises an error
  outside a Tarav-started process. Deliberate direct callers import
  `tarav_bypass` first; it is the explicit alternative entry point.
  <!-- tarav.breadcrumb 0319d00f271187db1c68b562c9b9e9cf8d775c549d5e9d8b0113fa24d30a42c0 -->
- `tarav run` retains the code it executes in a best-effort registry under
  `~/.tarav/run-registry/`, one folder per Project id plus `global`, bounded by
  size. Browse it for recent examples of Tarav scripts, including other
  Projects'. `tarav.l1.python_env.registry` owns it; it must never change a run.
- A Type that needs configuration extends `SettingsProvider` (`tarav.l1.settings`)
  and declares a nested `SettingsInterface`; its objects get `.settings`. Settings
  are controls, not object data. A parent's settings are included only through
  `settings_include`. See ARCHITECTURE.md, Settings capability.
- POI Types are atomic: a POI has no `code`, and each Type states one situation.
  Give related situations one class each under a family parent that is never raised.
  The model is `POI` (Type, message), `SituationPOI` (adds `situation`; Type plus
  situation is the identity) and specializations. There is no `subject` or
  `evidence`: what a line needs beside the situation it declares as a field of its
  own Type, named for what it holds. `CheckPOI` adds `check`, `details`, `failure`.
- A POI is an event. A `CheckPOI` is actionable: it spins one action,
  `Tarav.Actions.POI.Resolution` (`tarav.l1.actions.pois`), kept in the central Record
  Registry and not in the Project. Three pieces stay apart: `project.checks` only
  runs checks; `project.actions` (`tarav.l1.actions.project`) only handles the
  actions registered under the Project and never runs a check; `project.status()`
  composes them, and a container asks each member Project to do the same for itself.
  The actions register the action of each new POI and hand the results to every
  registered action; the Action Type decides what they mean (`Action.on_checks`).
  `tarav status --project` runs that and is the command to repeat;
  `tarav check --project` only runs the checks. Read actions with
  `tarav action list --project` and `tarav context --id <action-id>` (the id of its
  POI finds it too). A POI is a flag between detecting and working: momentary,
  nothing stores one that was printed; a consumer keeps its record
  (`poi.records.to_record()`). The Record system is the one way a Tarav object
  becomes data: no `as_dict()`, `to_dict()` or `describe()` beside it.
  Blessing and standing are asked of the Project (`project.actions`), never of a
  POI listing. A Project sees the actions of the Projects it lists as children:
  `project.actions.list()` and `tarav action list --project` include them, and
  `own=True` or `--own` leaves them out. An action still belongs to one Project.
  An action records the suites above the check that raised its POI. It closes as
  `gone` only when the nearest of them that is in the run ran its own code to the
  end without reporting the POI: the signal is gone when the detector no longer
  detects it. A suite that was left out leaves the action, with the situation
  `not run`; a failed check leaves it with `check failed`. Checks
  only emit, and a run that no Project hands over records nothing. `tarav action` and
  `tarav operator-context` print a summary by default and the full result with
  `--json`. `blessed` is an operator's exit: the action closes
  although the situation still exists, with a reason, for a POI whose Type extends
  `BlessablePOI`; `tarav status` counts a blessed finding as settled. Every closing
  leaves a typed record on the action (`Tarav.Actions.POI.Gone`,
  `Tarav.Blessings.Blessing`), and that Type decides whether the POI raised again
  reopens it. Status is three axes: situation, action, closing. See ARCHITECTURE.md,
  `actions` and `blessings`.

# Tarav System Prompt

This Project participates in Tarav, an agents harness for collaboration between
people and agents. Tarav records data a person has touched, keeps paths back to
that data, and helps agents recover the context needed for current work. The
Project System Prompt in this file describes this particular Project. Read both
before changing its files.

### Start here

Treat this agents file as the entry point. Read the Project's `.tarav/project.json`
to identify its Type and any parent or child Projects. Follow local project
guidance before editing. If the Project has an `AGENTS.md` in a nested folder,
read it before working there. The Tarav Constitution states the system-wide
boundaries; when available, use the `tarav-pkg` skill to find it and the
maintained design surfaces. Consult the Project's Wiki and live notes when
present, then inspect code and tests for current mechanics.

Use `tarav --help` and the relevant subcommand's `--help` to discover the
installed CLI. `tarav status --project [PATH]` runs the Project's checks
and updates its actions from the results; run it as often as needed. It leaves
out the slow suites, such as a Project's tests, and says so; add `--all` to run
everything, at least before you finish a task.
`tarav check --project [PATH]` only runs the checks. A
reported point of interest (POI) is a signal to investigate, not an automatic
instruction to repair or a reason to stop unrelated work. A check may report
missing context, stale generated output, or a problem that needs user judgment.
A POI is only a flag: what persists is the action the status opens for it.
Before acting, read the action in `tarav action list --project`;
`tarav context --id <action-id>` opens its Context graph, which for now holds
only its type.

### Work with Tarav data

Tarav Archive records artifacts and retains records about them. A recorded
artifact may live in the Archive or elsewhere. Tarav Diagram links, structures,
and annotates archived data for contextualization. Follow references back to
supporting data when a claim matters. An annotation, summary, or score does not
replace its source. Other workflows can keep their own storage while using
Tarav's primitives.

Capture user-touched data before curating it when loss is possible. Validation
judges state after a change and must not block writing. The user controls the
foreground task; do not interrupt development to demand Diagram enrichment.
When a check finds something suspicious, give the user or the responsible
agent enough context to decide what to do.

### Find the right surface

For project-specific work, use this file's Project System Prompt and the local
Project model. For Tarav-wide concepts and boundaries, read the Constitution
through `tarav-pkg`. For a design's rationale, inspect the relevant Wiki note
and its linked user turns; for current behavior, inspect the maintained code,
tests, and CLI. If those surfaces disagree, make the disagreement visible and
resolve it with the user when it affects the work.

This file is a Skillware product. Its source is under `.tarav/skillware/src/`.
Change the source, then produce and compile it with `tarav skw document` using
`--depot .tarav/skillware`. A Project may declare aliases for the main agents
file; those aliases are symlinks to the main file. Do not edit the compiled file
or an alias as the source of truth.
