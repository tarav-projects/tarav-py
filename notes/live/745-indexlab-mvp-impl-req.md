# 745 — IndexLab recording-kernel MVP

## Impl.Abstract

- **Goal:** implement the new Touched.Index recording kernel as an isolated `tarav.indexlab`
  laboratory, including a namespaced CLI, deterministic touch mocks, a same-chat playground,
  mechanical linting, and a maintained developer guide.
- **Status:** ready for autonomous execution.
- **Design authority:**
  `tarav-md/notes/live/642-touched-index-recording-kernel-design-session.md` and the current
  design/implementation conversation.
- **Safety boundary:** existing Chatlas, Index, and Bloberia surfaces may be read through explicit
  adapters. Every IndexLab write requires an explicitly initialized `IndexLab.Workspace` and stays
  inside that workspace.
- **MVP workspace:** ignored runtime state under `var/indexlab/`; deterministic tests use temporary
  directories. No existing Index surface or Chatlas archive is mutated.

## Impl.Index

### Recording.Kernel

- `Touched.Index` is a maintained sequence of context-attached `Index.Record` objects.
- Each record is a persisted, context-bounded, auditable semantic-query result over the immutable
  `Chat.Surface`.
- A record contains an exact identity, ordering coordinate, `Record.Context`, typed operation,
  targets, one `Support.Set`, and opaque assertions.
- The operation determines what its `Support.Set` supports; the MVP does not introduce named
  support kinds or a general assertion type system.
- The index remains a curated `WIP.Surface`: records may be repaired or purged. Replacing a record
  is allowed only when its identity, order, and original context remain fixed.

### Semantic.Units

- `Index.Line` is the minimum addressable and capturable unit.
- `Index.Block` is the minimum self-interpreting semantic unit; line wording is interpreted in its
  block.
- Every persisted record performs at least one line or block operation.
- Exact `Line.Id` and `Block.Id` identify editions. `Isoline.Id` and `Isoblock.Id` assert semantic
  equivalence across editions.
- A same-isoline or same-isoblock operation is itself an assertion of semantic equivalence; a new
  meaning receives a new iso-object.
- `Trace.Support` is derived as the union of support captured by equivalent line records. Block
  support is derived from the current lines' trace support.

### Context.And.Support

- `Record.Context` identifies the producer chat and one horizon turn. It bounds what the record
  producer could derive and is independent of the touched material being indexed.
- `Visible.Context` is the visible chat prefix through that horizon. `Agent.Context` may include
  additional loaded sources or tool results; the MVP records the distinction without pretending it
  can reconstruct every provider-private context detail.
- `Support.Set` contains selected evidence neighborhoods. Each neighborhood names grounding user
  messages and any contextual agent messages required to understand them.
- A record may index its own chat or another chat. External capture therefore attaches the record
  to the producer chat while its support points to the source chat.
- A line's wording must be derivable from its producer `Record.Context`; support may later grow
  through a new `support.add` record without rewriting the wording.

### Operations.And.Projection

The MVP operation vocabulary is deliberately small:

- `block.create` creates an exact block edition and its isoblock.
- `block.rename` creates a same-isoblock edition with a new name and carries current membership.
- `line.capture` creates an exact line edition in a block and assigns an isoline.
- `support.add` targets one exact line edition and contributes additional support.
- `line.reblock` places a new exact line edition in another block; retaining its isoline asserts
  semantic equivalence in the new block context.
- `isoline.group` records a later-context claim that existing line editions are semantically
  equivalent under one resulting isoline.

The current semantic projection is derived by folding valid records in workspace order. It is a
queryable view, not another authoritative write surface.

### Workspace.And.Storage

- `IndexLab.Workspace` is an explicit, initialized directory carrying a versioned marker.
- Writers accept a workspace object, never a hidden default path or the production Index depot.
- Records are opaque JSON cargo persisted with the existing `BloberiaDepot` primitive inside the
  workspace.
- Record ordering is a workspace-owned monotonic ordinal; chat coordinates provide provenance,
  not global event ordering.
- Reads from another subsystem cross a named adapter boundary. The kernel does not import arbitrary
  application domains.

### Touch.Sources

- A small `UserTouchSource` protocol resolves contexts and message references required by capture
  and linting.
- `ChatlasTouchSource` adapts the public `tarav.chatlas.lossless` API without writing to Chatlas.
- `UserTouchMock` provides deterministic user/agent messages, contexts, and cross-chat scenarios
  for tests and CLI demonstrations.

### Mechanical.Linter

- The linter validates mechanics; future machinery may score semantic assertions.
- Required checks include record shape, non-empty support, exact reference resolution, message
  side, same-chat visible-horizon constraints, referenced target existence/order, operation
  invariants, and projection integrity.
- Invalid or unresolvable material produces addressable findings/POIs. The linter reports the
  problematic state and does not prescribe deletion versus amendment.

### CLI.And.Developer.Surface

- Register a top-level `tarav indexlab` command, separate from the production `tarav index` CLI.
- The first surface supports workspace initialization, record ingestion, record listing, semantic
  projection, linting, and a deterministic mock scenario.
- Batch ingestion accepts a JSON manifest so a landed block can create its block and line records
  in one invocation while retaining atomic records.
- Maintain a live developer guide under `notes/live/` explaining the laboratory boundary, model,
  command surface, playground, tests, design authority, and current limitations. Route it from the
  local `AGENTS.md` so another agent can resume work without reconstructing this session.

## Execution.Plan

### Slice 1 — workspace, records, and persistence

- **Status:** pending.
- **RED:** uninitialized directories and writes outside an explicit workspace are rejected;
  initialized temporary workspaces round-trip ordered records.
- **GREEN:** add strict models, the workspace marker, and a Bloberia-backed record store.
- **Check:** focused workspace/store tests and architecture import checks.

### Slice 2 — semantic evolution projection

- **Status:** pending.
- **RED:** simulate create/capture, support growth, rename, reblock, iso grouping, repair, and purge;
  assert current blocks/lines and accumulated support.
- **GREEN:** add the small operation vocabulary, invariant checks, record replacement/removal, and
  deterministic projection fold.
- **Check:** focused evolution scenario tests.

### Slice 3 — touch sources and linter

- **Status:** pending.
- **RED:** cover self-chat capture, external capture, contextual agent turns, invalid sides,
  out-of-horizon references, missing targets, and unresolved external sources.
- **GREEN:** implement `UserTouchMock`, the read-only Chatlas adapter, and mechanical findings.
- **Check:** mock and Chatlas-adapter tests using public APIs only.

### Slice 4 — CLI and same-chat playground

- **Status:** pending.
- **RED:** CLI tests prove explicit initialization, ingest/list/project/lint behavior, and mock
  scenario repeatability.
- **GREEN:** register `tarav indexlab`; initialize `var/indexlab/current-chat`; ingest records whose
  producer/support references target this design session through Chatlas.
- **Check:** CLI tests plus installed-command smoke tests. All writes remain below the workspace.

### Slice 5 — maintained developer guide and closure

- **Status:** pending.
- Allocate a live-note prefix, write the IndexLab developer guide, and route it from `AGENTS.md`.
- Run focused tests after each slice, then IndexLab/CLI/architecture tests, Ruff, `git diff --check`,
  and the proportionate full suite.
- Audit the design session, this implementation record, code, tests, CLI help, and developer guide
  for conformance and residual gaps.

## Impl.Log

- **Execution authority:** `$tarav-hugentics --impl --dev --AUTO`; implement the IndexLab MVP,
  target this same chat, and include testable touch mocks.
- **User support:** the sandbox requirement is recorded by Chatlas message
  `7fdaaf67…704b463`; the explicit CLI/workspace/adapter decisions by
  `eeb622ea…633a5ce`; the maintained dev-guide requirement by `fa06a049…042419`.
- **Checkpoint gate:** before the first product-code edit, commit the current tarav-py worktree,
  including this implementation record and the pre-existing Index model wording edits. Preserve all
  unrelated work and make no further implementation commits.
