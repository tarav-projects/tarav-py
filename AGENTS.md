# AGENTS.md

## Read first

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

- `tarav.runtime.create_runtime()` is the composition root. CLI and daemon
  adapters may import it; domain foundations must not.
- Keep subsystem imports acyclic outside runtime composition.
- Provider-neutral orchestration belongs in `tarav.agent`; concrete adapters
  belong in `tarav.agent.providers.<provider>`.
- Shared infrastructure enters `tarav._core` only after multiple consumers have
  demonstrated the same semantics. Callers retain policy, schema validation,
  locking, and error translation.
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

## Native surfaces and Skillware

- `tarav.surfaces` owns deliberately thin Python and Markdown normal models.
  Native parsers expose syntax and source spans only; they do not know Skillware
  attachment policy or Index domain policy.
- Project-aware discovery supplies a file plus its surface context. Domain
  adapters assign domain interpretation from that context.
- `tarav.skillware` consumes native models and decides legal annotation points.
  It discovers Python annotations statically and never imports product modules
  for discovery.
- `.skw/skw.json` is the project declaration for tracked Skillware/code
  surfaces. `tarav skw` is the sole public command name.
- Skillware managed files are generated from `.skw/src/**/*.skw.md`. Never edit
  a generated copy as a substitute for changing its source.

## Index

- `tarav index` uses a required project selection for evaluation. The same
  project must produce the same verdict from every working directory.
- Native Index surfaces, SKW annotations, and other domain surfaces are one
  distributed Index under Natural.Placement. An Index line on code is still an
  ordinary Index line and must receive a LineRecord through the same mechanics.
- `LineRecord.id` is immutable record/version identity; `trace` is semantic
  lineage; `line.label` is the mutable public selector; scope and support are
  grounding edges. Do not collapse their roles.
- Bloberia depot types own their formats and storage behavior. Do not impose one
  serializer or envelope across depot types.
- Index linting builds one JSON-serializable run model. Text and JSON renderers
  consume that model; filters and limits must not rerun checks or silently
  change completeness.
- A check is executable machinery, a `POI.Class` is a finding category, and a
  `POI.Instance` is one occurrence. Output and storage must preserve the
  distinction.
- POI class blocks may be naturally placed beside check code as SKW annotations.
  Their identity is independent of the Python symbol. Discovery is static.
- Before adding or changing a check, read
  `tarav-md/skills/tarav-pkg/references/poi-linter.md` — the run loop, tier and
  gate choice, selection and narrowing, the three-valued verdict, and what
  licenses a blessing.
- Capture preview and landing consume one `Capture.Manifest`. Validate chat
  references and content expectations before writes, derive all planned effects
  from one model, and audit LineRecords after landing.

## IndexLab

- `tarav.indexlab` is an experimental recording kernel isolated from the
  production `tarav.index` model. Before changing or operating it, read
  [the IndexLab developer guide](notes/live/746-indexlab-dev-guide.md).
- Every IndexLab writer requires an explicit `IndexWorkspace` resolved through
  an explicit `IndexLibrary`. Each workspace is also its Bloberia depot and Git
  repository root. Existing Index and Chatlas systems are read-only inputs
  through named adapters.

## Chatlas

- `tarav.chatlas` owns archives, session indexes, and provider adapters.
  `tarav.chatlas.lossless` owns the provider-neutral Normal Model and its cache.
- Nothing in the lower Chatlas layer imports `lossless`; command composition is
  the exception that registers the public `tarav chatlas` leaves.
- Consumers import `tarav.chatlas.lossless`, not its internal modules.
- Chat surfaces are immutable evidence. Stable derived surfaces are maintained
  and may be corrected or deleted; stability is not immutability.
- Persisted `tarav.chatlas2.*` identifiers remain valid historical storage
  contracts until a dedicated migration changes them.

## Editing and tests

- Preserve unrelated changes in the shared worktree.
- Use `apply_patch` for hand edits.
- When a manual investigation exposes a durable constraint, add a focused test
  for that constraint.
- Architecture changes update `tests/test_architecture.py` with the maintained
  docs.
- For Markdown block extraction, prefer `tarav stdlib mdblocks blocks`, `links`,
  and `find` over ad-hoc parsers.
