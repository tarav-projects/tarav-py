# 748 — Index library and workspaces

## Impl.Abstract

- **Goal:** replace the laboratory's path-only `IndexLabWorkspace` with the accepted
  `Index.Workspace` and `Index.Library` model, while preserving the explicit write boundary.
- **Status:** complete and verified.
- **Scope:** the experimental `tarav.indexlab` namespace, the small Bloberia initialization seam it
  needs, its CLI, tests, playground, and developer guide.
- **Out of scope:** production `tarav.index`, migration of `/Users/pereiro/Documents/bloberia/tarav-index`,
  semantic-assertion scoring, shared POI catalog integration, and multi-machine portability.
- **Design authority:** the recording-kernel design session, the current implementation discussion,
  and the existing IndexLab MVP.
- **User support:** Chatlas session
  `c9d44ac37e655c397de8ea8322baeffa87469c1ec55ae98532144bc5ff50ddb5`, especially messages
  `0bb12970…5b005c` (official workspace, stable identity, registry, configurable mocks),
  `8881f147…7b343` (workspace-scoped Git delegated to Bloberia), and `307b8866…95bdf`
  (autonomous development authorization).

## Impl.Index

### Library.And.Workspace

- [DC] `Index.Library` is a user-level registry and collection of independently configured
  `Index.Workspace` objects; it is not itself a Bloberia depot. Support: `0bb12970…5b005c`.
- [DC] Every workspace has one stable UUID and one mutable human-facing name; the library resolves
  either selector to the same workspace root. Support: `0bb12970…5b005c`.
- [DC] Development and production use the same workspace contract. Isolation comes from selecting
  a different configured workspace, never from `test_mode` or a parallel implementation. Support:
  `0bb12970…5b005c`.
- [DR] The experimental CLI keeps library selection explicit. A future production composition may
  supply the conventional library root without changing the kernel.

### Root.Algebra

- [DC] For this Index realization,
  `Index.Workspace.Root = Bloberia.Depot.Root = Git.Repository.Root`. The workspace configuration,
  Bloberia metadata, private cargo layout, and Git repository coexist at that root. Support:
  `8881f147…7b343`.
- [DC] Bloberia owns record persistence and checkpoint commits. The Index workspace creation
  operation establishes the repository and passes `git="."` to Bloberia; record workflows do not
  implement commits themselves. Support: `8881f147…7b343`.
- [DC] `Bloberia.Record.Namespace` remains placement inside one depot. It is not a library,
  workspace, or isolation boundary.
- [DR] Bloberia needs one public metadata-initialization operation so an empty workspace is already
  an unambiguous shards depot and can be queried by the generic CLI before its first record.

### Configuration.And.Adapters

- [DC] Workspace configuration selects external adapters explicitly. A mock artifact appearing on
  disk must never silently replace Chatlas as the touch source. Support: `0bb12970…5b005c`.
- [DC] A mock-backed workspace and a Chatlas-backed workspace exercise the same record store,
  projection, linter, and CLI mechanics; only their configured `UserTouchSource` differs. Support:
  `0bb12970…5b005c`.
- [DR] This slice records the selected touch adapter (`chatlas` or `mock`) in `workspace.json` and
  fails closed when its required backing material is absent. General capability policy and a POI
  for forbidden adapters remain future work rather than an invented production/test mode.

### Query.Surface

- [DC] The Index CLI resolves a library workspace name or UUID, then passes the resolved object to
  writers and semantic consumers.
- [DC] The generic Bloberia CLI can query the same records by receiving the resolved workspace root
  as `--depot`; it exposes storage queries, not Index projection or lint semantics.
- [DR] Workspace creation output includes the exact depot path so the lower-level query boundary is
  directly inspectable and testable.

## Execution.Plan

### Slice 1 — Bloberia empty-depot initialization

- **Status:** complete.
- **RED:** an explicitly initialized empty shards depot has authoritative `meta.json`, preserves its
  type/key/Git configuration when reopened, and does not create a Git repository itself.
- **GREEN:** add the smallest public initialization operation over Bloberia's existing metadata
  writer.
- **Check:** focused Bloberia contract, shards, and Git tests.

### Slice 2 — official workspace root contract

- **Status:** complete.
- **RED:** a new workspace has stable identity/configuration, owns a Git repository, is also the
  Bloberia depot root, and its records are readable through both `RecordStore` and generic
  `BloberiaDepot`.
- **GREEN:** replace `IndexLabWorkspace` with `IndexWorkspace`; place the store at the workspace
  root and configure the touch adapter explicitly.
- **Check:** focused workspace/store tests and Git assertions.

### Slice 3 — library registry and selectors

- **Status:** complete.
- **RED:** an explicit library creates two isolated named workspaces, resolves names and UUIDs,
  rejects collisions and traversal, and never treats its own root as a depot.
- **GREEN:** add the versioned library registry and workspace lifecycle.
- **Check:** focused library tests using temporary roots only.

### Slice 4 — CLI and end-to-end queryability

- **Status:** complete.
- **RED:** CLI tests create a library/workspace, capture and project records by workspace name, lint
  with the configured adapter, and query the same cargo with `tarav bloberia --depot <root>`.
- **GREEN:** replace path-only IndexLab commands with explicit `--library` plus name/UUID selectors;
  expose the resolved depot path in workspace results.
- **Check:** IndexLab CLI tests and installed command smoke tests.

### Slice 5 — playground, guide, and closure

- **Status:** complete.
- Create a new ignored development library under `var/indexlab/` without touching the old sandbox
  or the production Index depot.
- Update the developer guide and architecture guidance for the library/workspace/root contract.
- Run IndexLab and Bloberia focused tests, architecture tests, Ruff, `git diff --check`, the real
  playground query/lint, and the proportionate full suite.
- Audit final product surfaces; add no annotation that merely restates self-evident code.

## Impl.Log

- **Execution authority:** `$tarav-hugentics --impl --dev --AUTO` at Chatlas message
  `307b8866…95bdf`.
- **Design inference:** adapter authorization policy is deliberately narrower than the user's
  eventual linter vision in this slice. Explicit selection removes accidental mock activation;
  general allowed-capability findings require a concrete non-mock scenario before enlarging the
  linter vocabulary.
- **Checkpoint:** `a6e2d9a` preserved the complete pre-execution worktree, including the prior
  IndexLab MVP, this ready Impl.Req, and concurrently present user work. No later implementation
  commit was created.
- **Bloberia seam:** added `BloberiaDepot.initialize()` to materialize an empty depot's declared
  type, key, and Git metadata without fake cargo and without creating a repository.
- **Workspace root:** replaced `IndexLabWorkspace` with `IndexWorkspace`. Its UUID/config marker,
  Bloberia metadata/private records, and Git repository now share one exact root; `RecordStore`
  exposes and uses that root directly.
- **Library:** added `IndexLibrary`, whose versioned `library.json` maps safe human names to stable
  workspace UUIDs. It creates, lists, and resolves isolated workspaces by either selector while
  remaining neither a depot nor a Git repository itself.
- **Adapters:** moved touch-source selection into `workspace.json`. Mock scenarios require an
  explicitly mock-configured workspace and missing mock material fails closed; file presence no
  longer changes a Chatlas workspace's behavior.
- **CLI:** added `indexlab library init`, `workspace create`, and `workspace list`; capture,
  records, project, lint, and scenarios now resolve `--workspace <name|uuid>` through an explicit
  `--library`. Workspace results expose the exact lower-level `depot` path.
- **Playground:** created the ignored `var/indexlab/dev-library` and captured the existing six
  same-chat records into its `current-chat` workspace. It projects two blocks, lints verified with
  zero findings, and a generic Bloberia query returns its two `block.create` cargos.
- **Git observation:** Bloberia committed the initialized workspace configuration. The subsequent
  six-record burst occurred inside its 900-second interval and remains pending until a later
  eligible write. This exposes the existing write-triggered final-burst gap; Index workflows do
  not bypass it with direct Git calls.
- **Product capture:** the final audit found no maintenance fact that belongs as an SKW annotation.
  Production Index backpropagation was intentionally not invoked because this slice's safety scope
  permits writes only to the experimental workspace and product files.
- **Verification:** 150 focused IndexLab/Bloberia/CLI/architecture tests pass; Ruff and
  `git diff --check` pass; the editable installed CLI passes workspace and generic-depot smoke
  queries; the complete suite passes with 2,255 tests.
