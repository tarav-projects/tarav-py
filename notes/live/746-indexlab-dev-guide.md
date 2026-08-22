# 746 — IndexLab developer guide

IndexLab is the experimental implementation of the context-attached Touched.Index recording
kernel. This is the entry surface for another agent continuing the experiment.

Status: recording kernel and workspace library running. The production `tarav.index` system is
unchanged.

## Enter here

Read, in order:

1. [recording-kernel design session](../../../tarav-md/notes/live/642-touched-index-recording-kernel-design-session.md)
2. [MVP implementation record](745-indexlab-mvp-impl-req.md)
3. this guide
4. [implementation](../../src/tarav/indexlab) and [behavior tests](../../tests/indexlab)

The design session owns the model and rationale. The Impl.Req owns the current implementation
scope and execution record. This guide owns how to enter, run, inspect, and maintain the lab today.

## Safety boundary

Every writer requires an explicit `Index.Workspace` resolved through an explicit initialized
`Index.Library`. There is no inferred library or workspace. Initialization refuses non-empty
unowned directories. Existing systems enter through named read adapters; the Chatlas adapter
computes a Normal Model without mutating the archive or its cache.

Each workspace is one isolation boundary with this root algebra:

```text
Index.Workspace.Root = Bloberia.Depot.Root = Git.Repository.Root
```

The library is only a user-level name registry. It is not a Bloberia depot or Git repository.
Workspace creation initializes Git; Bloberia receives `git="."` and owns best-effort checkpoint
commits after record writes. The selected touch adapter is stored in `workspace.json`; a mock file
cannot silently activate mock behavior in a Chatlas-configured workspace.

Tests write only to `tmp_path`. Manual libraries belong under the ignored `var/indexlab/` tree.
Never point a library or workspace initializer at an existing production surface. The conventional
future user-level library root is `/Users/pereiro/Documents/bloberia/tarav-index`, but the lab CLI
still requires it explicitly and this experiment does not migrate or write that surface.

## Quickstart

```sh
uv run tarav indexlab library init --library var/indexlab/dev-library
uv run tarav indexlab workspace create --library var/indexlab/dev-library --name my-run --touch-adapter mock
uv run tarav indexlab scenario seed-mock --library var/indexlab/dev-library --workspace my-run
uv run tarav indexlab records --library var/indexlab/dev-library --workspace my-run
uv run tarav indexlab project --library var/indexlab/dev-library --workspace my-run
uv run tarav indexlab lint --library var/indexlab/dev-library --workspace my-run
```

The retained same-chat playground is the `current-chat` workspace in
`var/indexlab/dev-library/`. It contains six records grounded in the design conversation and
currently lints cleanly through the real Chatlas adapter:

```sh
uv run tarav indexlab workspace list --library var/indexlab/dev-library
uv run tarav indexlab project --library var/indexlab/dev-library --workspace current-chat
uv run tarav indexlab lint --library var/indexlab/dev-library --workspace current-chat
```

The workspace create/list result includes its exact `depot` path. That path is directly queryable
through the storage-level CLI:

```sh
uv run tarav bloberia all --depot <depot-from-workspace-result> --query-json '{"operation.type":{"equals":"block.create"}}'
```

Runtime playground files are intentionally ignored. The previous path-only
`var/indexlab/current-chat/` sandbox remains untouched as historical local data.

## Capture manifest

`tarav indexlab capture` accepts one `tarav.indexlab-capture-manifest.v1` JSON document containing
a non-empty `records` list. Each record supplies:

- exact record id; persistence assigns its ordinal;
- producer `Record.Context` as session identity plus horizon `Turn.Ref`;
- typed operation and parameters;
- one `Support.Set` of evidence neighborhoods;
- optional opaque assertions.

One evidence neighborhood has a source session, grounding user message refs, and optional
contextual agent message refs. The producer context and selected touched material are independent,
so one chat may index another.

## Current kernel

- `model.py` — record, context, support, operation, and reference values.
- `workspace.py` — library registry, stable workspace identity/configuration, Git/depot root
  composition, and the Bloberia-backed curated record store.
- `projection.py` — fold for `block.create`, `block.rename`, `line.capture`, `support.add`,
  `line.reblock`, and `isoline.group`.
- `touch.py` — `UserTouchSource`, read-only `ChatlasTouchSource`, and deterministic
  `UserTouchMock`.
- `linter.py` — addressable mechanical findings with `failed` or `blocked` standing, explicit
  operands, stable identities, and computed check-source locations.
- `commands.py` — the isolated `tarav indexlab` developer surface with explicit library and
  name/UUID workspace selection.

Exact line/block ids identify editions, while each line label is its public citation.
Isoline/isoblock ids assert semantic equivalence. The current projection is derived by folding
records; it is not another authoritative stored surface. `Line.Reblock` changes the projection of
one exact line; its support grounds placement and does not enlarge line or Isoline support.
Store replacement preserves record id, ordinal, and original context. Purge and replacement are
available through the Python store API for context-local curation and Bad.Indexing repair.

## Test map

```sh
uv run pytest tests/indexlab -q
uv run pytest tests/test_architecture.py -q
uv run ruff check src/tarav/indexlab tests/indexlab
```

`test_workspace.py` guards library/workspace isolation, stable identities, the shared
workspace/depot/Git root, and the mutable boundary. `test_projection.py` runs semantic evolution
simulations. `test_touch_and_linter.py` covers evidence resolution and mechanical findings.
`test_usage_scenarios.py` runs the seven grounded Design.Session scenarios end to end through the
record store, projection, touch source, and linter. `test_cli.py` protects library resolution,
storage-level Bloberia queryability, and the explicitly configured mock scenario.

## Linter tiers and verdicts

`lint_store` runs the structural tier first: cargo that cannot be read back as an `Index.Record`
becomes an `IndexLab.Linter/Record.Unloadable` finding and **stops the run**, because linting on
past it would examine a silently truncated corpus and report the remainder as clean. `lint_records`
is the reportable tier alone, for callers holding records already.

A report exposes `clean` (nothing failed), `verified` (nothing failed and nothing blocked), and
`short_circuited`. There is deliberately no single `ok` boolean — collapsing three-valued verdicts
into two is what the tier and standing model exists to prevent. The CLI fails closed: only a
verified run exits zero.

Resolution standings distinguish absence from corruption. `MISSING` means the reference does not
resolve; `MALFORMED` means it resolves but the stored Chat.Surface material cannot be read as a
touch primitive, and carries a `detail`. They map to distinct POI classes (`Support.Unresolved` vs
`Support.Malformed`, `Context.Unresolved` vs `Context.Malformed`) so a corrupt chat is never
reported as a dangling reference.

`fold_records` collects every record that cannot be applied and keeps folding, so one run reports
all independently broken records; `project_records` keeps the strict raise-on-first behavior.
`ProjectionError.record_id` carries the offending record structurally — never parse it back out of
the message.

## Current gaps

- semantic assertions are opaque; no scoring machinery exists;
- experimental POI classes have managed identities beside the checks, but are not yet exposed
  through the shared selectable-check catalog and renderer;
- `RecordStore.replace` enforces only that identity, ordinal, and `Record.Context` are preserved;
  the `Index.Record.Mutation.Boundary` is otherwise unenforced, and even its mechanical half
  (replacement support still inside the original horizon, refs still resolving, fold still valid)
  is not yet checked;
- support and Isoline membership can only grow: there is no retraction verb and no isoline split,
  so an honestly grounded but wrong equivalence claim has no in-vocabulary remedy;
- the fold is order-dependent and ordinals are workspace write-order, which the design does not
  yet settle either way;
- line-wording derivability from full `Agent.Context` remains a semantic check;
- capture manifests are authored directly; no Chatlas-assisted authoring command exists;
- replacement and purge have no CLI yet;
- there is no SKW/project-secondary-surface consumer integration;
- workspace names cannot yet be renamed and library registry updates have no concurrency protocol;
- adapter selection is explicit, but a general allowed-capability policy and its POI vocabulary do
  not exist yet;
- Bloberia checkpoints are write-triggered; a final burst inside the configured interval can remain
  uncommitted until another interval-eligible write occurs;
- ordinal allocation is an MVP single-writer mechanism, not a concurrency protocol.

The next useful slice should be driven by a concrete usage scenario. Do not grow a general
assertion framework or project workflow speculatively.

## Maintenance rule

Update this guide whenever the workspace contract, CLI, adapter boundary, playground workflow,
source map, or next-entry gaps change. Keep detailed design rationale in the design session and
execution history in the active Impl.Req rather than duplicating them here.
