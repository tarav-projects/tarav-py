# AGENTS.md

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
- Import standalone Context types and `explore()` from `tarav.l1.context`.
  Retained storage lives in `tarav.l2.context` and runtime-backed `context()`
  in `tarav.l3.context`; neither is imported by l1 Context or its Workflow declaration. Kernel's
  context hooks have no runtime Context dependency.
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

- A harness manifest may list several trusted Project Types
  (`[tool.tarav.harness] projects`), started through `tarav.l3.project.launch`.
  `RootProject` (`tarav.l2.project.root`) lists child Projects in its marker
  and its `checks()` are theirs; a child may declare `harness.project` to use
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
- `TaravProject` is a `CheckProvider`: a Project subtype exposes bound Checks
  through `checks()`; the base raises `NotImplementedError`.
  <!-- tarav.breadcrumb f1b6c4d85568e1afc1b76afc02983662c5d2be806b568698cd7b28b853a639e6 -->
  <!-- tarav.breadcrumb 2cad01bfc733b3b450e3908f187d06d110c511dd5329d9b74e0165b87839fbc9 -->
- `CheckProvider.checks()` returns a `CheckSuite`. Its `run()` accumulates a
  `CheckRun`; suites are not iterable because sources can depend on earlier
  results. `tarav check --project [PATH] [--json]` runs the suite in the
  Project harness and reports grouped POIs (20 groups by default). It exits
  0 only when all Checks completed without open POIs.
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
