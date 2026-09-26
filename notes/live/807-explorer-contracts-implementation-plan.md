# Explorer contracts and conformance — implementation plan

## Status and scope

- Date: 2026-09-25.
- Status: implemented as a lightweight Kernel contract and adopted by Archive
  and Context; this note itself is not the authorization.
- Source: current design conversation, including the user's request for common
  method names/base typings, behavioral contracts, and a shared suite to which
  implementation classes supply their test support.
- This is an Agent-authored coordination note, not an approved specification or
  a complete Hugentics Impl.Req. No Diagram Collection, Draft, or capture is
  claimed. Resolve that grounding separately if entering the formal workflow.

Objective: provide optional, public Explorer base classes that independent
workflows can implement, then demonstrate interoperability with Archive and
Context. Shared contracts do not exhaust the meaning of a workflow: its code,
data, and evidence remain available for deeper interpretation.

## Design constraints from the discussion

- Define `ExplorerEntry`, `ExplorerFolder`, `ExplorerList`, and `Explorer`.
- Prefer explicit type-family membership through thin abstract base classes.
- Separate interface conformance from implementation reuse: implementing an
  Explorer contract does not prescribe inheritance or composition for storage.
- Entries attach workflow-specific data and operations to values. Values need
  not be native to the workflow, and need not be navigable.
- `ls()` returns entries, not just keys; `get(key)` selects an entry;
  `open(key)` returns its value without changing navigation.
- `cd(key)` enters a navigable value. Opening a leaf is valid; entering it is not.
- Navigation history belongs to the explorer, not the underlying collection.
  Back retraces visits; it must not silently mean a graph parent relationship.
- Named and positional collections have distinct types (`Folder` and `List`).
- Do not introduce a base Location type without operative semantics.
- Graphs need not be trees: do not impose unique parents or acyclicity.
- Implementations supply the support required to run the common tests. A class
  registration may expose a helper/factory through a hook; normal operations
  should not require loading a test framework.

## Ownership and current implementation

Proposed home: `src/tarav/kernel/explorer.py`, publicly exported through
`tarav.kernel`. Kernel owns shared semantic contracts, not workflow storage.
See [ARCHITECTURE.md](../../ARCHITECTURE.md#package-layers).

Relevant existing surfaces:

- [kernel/context.py](../../src/tarav/kernel/context.py): ContextEntry,
  Context, ContextFolder, ContextList, and ContextExplorer. Collections
  already expose entries; the explorer owns history and contextual follow.
- [record_archive/__init__.py](../../src/tarav/record_archive/__init__.py):
  ArchiveEntry, RecordArchive, DictionaryArchive, and VectorArchive. Collection
  `ls()` currently returns keys. `RecordArchive.open(root)` is a class-level
  loading operation: it conflicts with a proposed instance `open(key)` and
  must be resolved explicitly, not hidden by inheritance order.
- [record_archive/navigation.py](../../src/tarav/record_archive/navigation.py):
  ArchiveCursor, TaravArchive, and ArchivePartition. Navigation currently uses
  Archive-owned paths separately from opening an entry value.
- [context_workflow.py](../../src/tarav/context_workflow.py): retained Context
  integration; must preserve workflow-owned attachments and lazy access.
- [navigation/__init__.py](../../src/tarav/navigation/__init__.py): an existing
  Record-provider workflow, not the owner of these general base contracts.
- [testing.py](../../src/tarav/testing.py): existing public test support is a
  module, so do not assume `tarav.testing.explorer` is already a package path.

Archive naming direction discussed: `RecordArchive` → `ArchiveEntity`,
`DictionaryArchive` → `ArchiveFolder`, `VectorArchive` → `ArchiveList`,
`TaravArchive` → `ArchiveRoot`, and a stateful `ArchiveExplorer` replacing the
cursor's exploration role. Root and Partition sharing `ExplorerFolder` does
not itself settle whether they inherit `ArchiveFolder` or `ArchiveEntity`.

## Decisions to settle before implementation

1. Exact signatures and ownership of convenience operations: entry `open()`,
   collection `ls()/get()`, and explorer `ls()/get()/open()/cd()/pwd()`; whether
   collections also expose `open(key)`. Preserve one meaning per operation.
2. Listing shape and placement typing: prior illustrations used both mappings
   and sequences. Proposed starting point is a sequence of typed entries,
   matching Context today, with string or integer selection by collection type.
   Confirm the placement contract rather than treating examples as approval.
3. Relationship to TaravType/TaravObject, abstract class projections, and
   records. Shared exploration must not accidentally require persistence.
4. History boundaries, forward-history invalidation after a new visit,
   failure behavior, and route display in `pwd()`. A displayed route must not
   become an assumed global identity. Parent syntax is distinct from back.
5. Test-support hook, registration location, and portable runner surface.
   Choose the smallest explicit API; no automatic plugin discovery is required.
6. Migration scope for the Archive names and retained Type names. Keep stable
   identities stable; do not assume a Python rename requires a data rewrite.

## Execution plan

All slices below were implemented after the user authorized implementation.
The shared worktree contained substantial unrelated changes, which were left
in place.

### 1. Establish the minimal contract

- Resolve the decisions above with the user where they affect behavior.
- Add the four bases, method typings/docstrings, and only universal defaults.
- Keep Kernel independent of Archive, Context workflow storage, and test runners.
- Add small synthetic implementations proving named/positional selection and
  leaf/container distinctions without persistence.
- Check: incomplete subclasses cannot instantiate; complete synthetic classes
  interoperate through one consumer using only the shared interface.

### 2. Build reusable conformance support

- Provide separately importable support for Entry, Folder, List, and Explorer
  contracts. Final module path is an implementation decision, not fixed here.
- A registered class exposes a test-support helper producing isolated fixtures,
  known keys/values, navigable and leaf cases, and resource cleanup.
- Keep test-only construction out of ordinary explorer initialization. Fixtures
  must not use live user data, global production paths, or shared mutable state.
- Check `get`/`ls` agreement, correct opening, navigation-neutral reads, valid
  `cd`, leaf rejection without history mutation, and back/forward behavior.
- Exercise empty collections, invalid keys, duplicate values at different
  placements, revisits/cycles, and history branching as relevant to each contract.
- Include deliberately broken implementations: the suite must detect violations,
  not merely accept conforming examples. Validate cleanup even when checks fail.
- Check: an external-package example can register its class and run the suite
  without importing Tarav's repository-local `tests` or changing the runner.

### 3. Adopt the contracts in Context

- Make Context entry and named/positional collections implement the bases.
- Reuse common explorer mechanics where their semantics actually match.
- Preserve Context-specific subject following, origin information, attachments,
  subclass behavior, and deferred opening.
- Register Context test support and retain its domain-specific tests.
- Check: common conformance plus `tests/kernel/test_context.py` and
  `tests/kernel/test_context_workflow.py`; explicitly test parent versus back.

### 4. Adopt the contracts in Archive

- Apply the agreed naming changes within the confirmed migration scope.
- Change collection listings to expose entries and update affected consumers.
- Resolve the loading `open(root)` collision before introducing convenience
  `open(key)`; no ambiguous dispatch based on arguments or inheritance order.
- Separate collection objects from ArchiveExplorer navigation state.
- Model root/partition/grouping navigation consistently: a navigable entry opens
  the container it enters; workflow metadata may be exposed separately.
- Retain Archive-owned persistence and Git policy. Do not force Root or Partition
  into the persistence hierarchy merely because they are folders.
- Check: common conformance, `tests/record_archive/`, and retained Context tests;
  verify loading, identity, entry retention, and no writes during exploration.

### 5. Validate boundaries and document the public API

- Update architecture guidance, exports, and `tests/test_architecture.py` for
  the shared contract and independent test-support boundary.
- Document one small custom implementation and its conformance registration.
- Run focused checks after each slice, then relevant full tests and Ruff with
  `uv`; report commands and results rather than claiming unrun checks.
- Audit consumers for key-only listings, Archive loader calls, and cursor/history
  assumptions. No compatibility aliases unless explicitly requested.
- Check: one generic explorer consumer works with Archive and Context without
  workflow-specific type branches; domain tests continue to cover their meanings.

## Completion and deviation criteria

Complete when both workflows satisfy the same documented operational contracts,
their classes supply runnable isolated test support, and external implementations
can use the same suite. Conformance is evidence about shared mechanics, not a
proof of every workflow's semantics or all possible runtime behavior.

Pause for alignment if adoption requires new storage semantics, record repair,
loss of domain-specific behavior, forced tree structure, or a broader graph
framework. Do not resolve those by silently enlarging this implementation.

## Log

- 2026-09-25: wrote the planning note from the discussion and inspected current
  module boundaries. No implementation, test execution, staging, or commit.
- The Hugentics design checklist informed the separation of scope, decisions,
  vertical slices, observable checks, and execution readiness. This note remains
  a lightweight plan rather than claiming the full Diagram-backed workflow.
- 2026-09-25: added the four Kernel bases; Archive and Context now implement
  them. Archive listings return lazy entries and stateful navigation lives in
  `ArchiveExplorer`. Added public `tarav.explorer_testing` conformance support,
  domain and independent-implementation fixtures, and architecture assertions.
  Full pytest passed on the final state (1,270 tests). Ruff and diff whitespace
  checks passed. Retained Type identities and Record labels were preserved.
