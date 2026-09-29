# AGENTS.md

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

- `.tarav/project.json` is the canonical project marker. It stores portable
  project identity and metadata, not machine-local paths.
- A bare `--project` selects the current directory where a command supports it.
  Commands decide whether project selection is required.
- Environment variables and machine-state paths retain the names encoded by
  their current storage contracts until an explicit migration changes them.

## Native surfaces and SKW

- Skill packages with a `loading` declaration use `tarav.l1.skw.skills` for
  compilation. The installed `skw document` CLI receives this specialization
  through runtime composition. Plain `Document` is the generic engine, not a
  substitute for compiling skill primitives. Loading graphs are declared data;
  never infer parent attachments or context satisfaction from Markdown links.

- SKW context navigation defaults to compact listings. Agents select entries
  for head/tail/cat reads or use exposed absolute paths. Keep payload
  resolution for dependency checks separate from context presentation.

- JSON document sources under `.skw/src/` own all literal and generated text
  for their product. Edit generation outputs in source, record them explicitly,
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
- `tarav.l1.skw.document` owns typed JSON document sources under `.skw/src/`.
  `tarav.l1.skw.skills` specializes those documents for deployable packages.
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

- The Python library is the primary interface. Use `tarav python run --file`
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
