# Context foundation and integration layers

## Impl.Abstract

Knowledge.Surface: wiki. Phase: Execute. Alignment.Mode: Interactive.
Status: Context split implemented and verified.
Parent roadmap: [821](821-dependency-layer-migration.md).

Separate standalone Context navigation in l1 from Archive-backed Context and
runtime-facing convenience operations in l2. Demonstrate one workflow spanning
levels without changing its identity or graph semantics.

Non-goals: migrate all runtime composition, clean every Archive dependency,
redesign Loading or Project, add a dependency-checking framework, introduce
new Workflow identities, or change retained data formats. This slice makes l1
Context independent; it does not claim the entire l2 integration is dependency-
clean while the existing top-level runtime remains its composition boundary.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner/root: ../tarav-md/notes/wiki.
Relevant Notes: diagram-workflows.md (dependency layers), context-graph.md.
Evidence session: codex:01a0d86c-9538-7be1-af96-014cd4203d61;
identity: 6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.
User Turn 4a3e7b848da3be74 requests this Impl.Req following the review and
recommendation to split Context. Earlier turns 9567063c2dc25417 and
d7f8eab26db8fcb5 establish layering and principle-first adoption.
Detailed interfaces below are implementation proposals, not verbatim user
requirements. Capture destination: daily/2026-09-27.md; existing topical
layering rationale does not need rewriting.

## Inspected boundaries

- src/tarav/l1/context/__init__.py defines Types, folders, entries, builders,
  explorers and explore(contributors=...). Its final context() helper reaches
  get_runtime(); this is already a small separable integration entry point.
- l1/context/storage.py defines StoredDictionaryContext, StoredVectorContext,
  SubjectContextRoot, ContextService and CONTEXT_RECORD_TYPES. It imports
  Archive and uses runtime for stored-folder opening and registry fallback.
- l1/context/workflow.py declares ContextWorkflow and its service() factory.
  That factory imports storage, so leaving it unchanged would create an l1→l2
  edge after the move, including its TYPE_CHECKING annotation.
- runtime.py imports storage Types and constructs ContextService through
  ContextWorkflow.service(); TaravRuntime.context() already delegates to l1
  explore() with an explicit contributor.
- Archive consumes l1 ContextFolder/ContextBuilder. It need not follow storage
  into l2. Preserve this direction and its independent navigation semantics.

## Proposed layout and API

```text
tarav/l1/context/
  __init__.py      existing contracts, builders, explorers, explore()
  workflow.py      ContextWorkflow identity and constitution only
tarav/l2/context/
  __init__.py      context(subject): current-runtime convenience
  storage.py      Archive-backed Types and ContextService
tarav/runtime.py   explicitly constructs and wires ContextService
```

Use l1 explore(subject, contributors=...) for explicitly composed standalone
navigation; use l2 context(subject) for current-runtime retained Context.
Move context(), do not leave an upward-import alias in l1. Remove the service()
factory from the foundational Workflow class; runtime constructs ContextService
directly. Preserve the same ContextWorkflow singleton, TypeShips, Record labels,
ownership and storage paths. No second ContextWorkflow or duplicate classes.

Keep l2 initializers thin. Existing runtime lookups in storage and the convenience
helper remain explicit transitional integration dependencies in this slice;
moving them does not magically eliminate them. Full runtime/service-boundary
redesign belongs to the parent roadmap, not this bounded extraction.

## Execution.Plan

- [x] Cold-read instructions, this note and 821; inspect the shared worktree and
  checkpoint existing product work under Execute policy before edits.
- [x] Inventory consumers of context(), ContextWorkflow.service(), storage Types,
  registration tuples and Python-path strings. Check current Context Wiki and
  retained evidence before deciding any semantic change.
- [x] Create l2 package, move storage and runtime-facing helper, leave l1 contracts
  and Workflow declaration independent of Archive/storage/runtime.
- [x] Remove service factory and its storage annotation from l1; update runtime
  construction, registrations and consumer imports. Pure Context consumers
  stay l1; only retained/runtime-aware consumers move to l2.
- [x] Update existing tests, maintained examples and architecture documentation.
  No old-path shims, Record relabeling or retained-data rewrites. Inventory
  external trusted class paths and report affected consumers before changing
  anything outside the product repository.
- [x] Run verification, record results here, capture the bounded outcome in Wiki.

## Acceptance and verification

1. In fresh subprocesses, importing l1 Context and its Workflow must not load
   l2, Archive or runtime. Include annotation inspection and several import
   orders. Adapt existing architecture tests rather than build new tooling.
2. Standalone explore() supports class/object contexts, bases/target discovery,
   explicit contributors, entries and Explorer history without retained storage.
3. Runtime context() preserves stored roots, folder opening, leaf opening,
   identity checks and no-create-on-read behavior. Two explicitly selected
   runtimes retain their existing isolation behavior.
4. Existing stored Context Records load through the registry with unchanged
   TypeShips and labels. Only their Python module paths change. Verify a single
   registered class per identity and unchanged Workflow ownership.
5. Run uv run pytest -q tests/kernel/test_context.py
   tests/kernel/test_context_workflow.py tests/kernel/test_explorer_conformance.py
   tests/kernel/test_library_runtime.py tests/test_architecture.py, plus Record
   Archive tests. Then full pytest, Ruff and git diff --check.
6. Smoke-test runtime construction and installed CLI; refresh installation if
   entrypoint behavior requires it. Recheck references to the old storage path.

## Impl.Log

- Inspected source boundaries listed above. The preceding read-only review ran
  49 architecture/loading/Project tests successfully; that is baseline evidence,
  not verification of this unimplemented split.
- Existing uncommitted l1 placement work was not changed. No product edits or
  product commit made while writing this request.
- Wiki handoff added to daily/2026-09-27.md; Breadcrumb audit passed without
  findings and Wiki-only closure completed. Product note remains uncommitted.
- Execute checkpointed the preexisting l1 placement and this request as
  `340e7bc` before product edits. The new `tarav.l2.context` package owns the
  runtime convenience and Archive-backed Context Types/service. The same l1
  Context Workflow retains its identity and constitution without a service
  factory; `tarav.runtime` constructs `ContextService` directly.
- The focused Context, Explorer, Archive, and architecture suite passed 123
  tests. Fresh subprocesses check l1 imports and annotation resolution without
  l2, Archive, or runtime. Maintained external example source has no binding
  to the old Context storage Python path. Existing retained `context.json`
  files were inspected read-only; their Type labels remain unchanged, and no
  retained data was rewritten.
- Full pytest passed 1,361 tests. Ruff and `git diff --check` passed; runtime
  registration, Workflow identity, and installed CLI smoke checks passed.
- Wiki capture added the implementation outcome to `context-graph.md` and the
  daily note. Both Chatlas-context Breadcrumb audits passed with no findings;
  the Wiki-only closure commit is `0736126`. No post-checkpoint product commit
  was created.
