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

- The Index is a collection of `Index.Record`s held in an `Index.Workspace`,
  resolved through an explicit `Index.Library`. Markdown is a secondary surface
  and nothing reads it as the Index.
- `.tarav/project.json` names the library and workspace holding a project's
  records. `tarav.indexlab.IndexResolver` is the one reader: block by address or
  bare `Dotted.Name`, block aliases, and citation resolution.
- One resolver folds the record stream once and serves every consumer. A
  consumer that folds for itself holds a private projection able to disagree
  with the linter's.
- Resolution is global within one workspace. There is no depot visibility and no
  `depots` key: a name defined by two blocks is a reported collision, never a
  lookup order.
- A bare `Dotted.Name` prefers a chapter block over one written on a product
  surface. A citation carries no `~n` occurrence suffix, so it resolves to the
  isoline and returns every projection of that one semantic line.
- `Line.Type` lives on a record assertion under the `line_type` key. Assertions
  are otherwise opaque; a reader that understands a key may read it. An `alias`
  assertion states a name *for* a block, so it stays out of any materialized
  body.
- Every writer requires an explicit `IndexWorkspace` resolved through an
  explicit `IndexLibrary`. Each workspace is also its Bloberia depot and Git
  repository root. Before changing or operating the kernel, read
  [the IndexLab developer guide](notes/live/746-indexlab-dev-guide.md).
- The kernel declares ports; other subsystems provide adapters.
  `ChatlasTouchSource` lives in `chatlas.lossless`, and the CLI takes a
  touch-source factory from the composition root.
- `tarav.index_model` is not the Index model. It holds the written form of an
  Index line — label grammar and the identity hashes Chatlas dossiers assert
  over the `Line.Type + body + anchor` triplet.
- Bloberia depot types own their formats and storage behavior. Do not impose one
  serializer or envelope across depot types.
- Index linting builds one JSON-serializable run model. Text and JSON renderers
  consume that model; filters and limits must not rerun checks or silently
  change completeness.
- A check is executable machinery, a `POI.Class` is a finding category, and a
  `POI.Instance` is one occurrence. Output and storage must preserve the
  distinction.
- Shared-runtime check registries contain `Check` classes. One run instantiates
  each selected class with the resolved domain context and calls `run()`.
  Preconditions are ordinary earlier check results expressed through check
  dependencies; do not add a separate gate lifecycle to the shared runtime.
- POI class blocks are `<depot>/poi#<Class>` blocks in the records, and may also
  be naturally placed beside check code as SKW annotations. Their identity is
  independent of the Python symbol. Discovery is static.
- Before adding or changing a check, read
  `tarav-md/skills/tarav-pkg/references/poi-linter.md` — the run loop, tier,
  selection and narrowing, the three-valued verdict, and what licenses a
  blessing.

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
