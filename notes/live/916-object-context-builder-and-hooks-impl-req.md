# 916 — Composable ObjectContext construction

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: implemented and verified; conversational grounding and status persistence
remain pending because of the environment restrictions recorded below.

Replace `.context.triplets()` with explicit `.context.build()` returning an
`ObjectContext`. Build the result through class, instance, then external
hooks, all mutating the same result. Keep `.context()` as the existing
Explorer operation, and retain each built result in the Explorer.

Scope: Kernel namespace binding and hooks; Context construction and external
registration; runtime composition; Explorer, CLI wording, tests and developer
guidance. Verify the extension against the changed core without introducing
extension-specific code into Tarav. Non-goals: an Annotations workflow,
domain graph enrichment, persistence, refresh/retraction of collected graphs,
hook dependency scheduling, or a new configuration framework.

## Design narrative

The User requested a construction system in which the class contributes,
then the instance, then registered external workflows. Each hook receives
the same mutable `ObjectContext`: it can add/remove triples, change options,
and retain other context data. Return this object, rather than only its
triples, to retain construction information useful for debugging.

The accepted entry point is `obj.context.build()`, followed by reading
`result.triplets`. There is no shortcut `.context.triplets()`. Uniform class
access delegates to the representing object: `Document.context.build()` is
equivalent to `entity(Document).context.build()` (the discussion used
`identity`, while the maintained operation is named `entity`). This runs
TaravClass's class hook, then that identity object's instance hook, then
external hooks. It does not invoke Document's instance hooks on its Python
class. Hooks are named `_class_context_hook(cxt)` and
`_obj_context_hook(cxt)`. Each can compose via ordinary cooperative
`super()`; explicit NamespaceBase composition remains required for
independent multiple-inheritance contributions. The builder calls each
selected hook once, never walks and calls every base separately.

Current inspected state: `TaravType.Context` owns `triplets()` and callable
Explorer access; the descriptor binds class access to the Python class.
`ContextExplorer.open()` collects this method once per graph node.
`TaravRuntime.context()` constructs the Explorer and supplies identifier
resolution. No Type currently overrides `triplets()` outside the Context
tests. The extension already consumes the core Explorer; no script calls
the method being removed. Baseline curated suite: 306 passed.

Implementation choices (Agent, within autonomous alignment):

- `ObjectContext(TaravObject)` owns subject, mutable `triplets`, `options`,
  opaque `hints`, build status and a list of hook-run diagnostics.
- `ContextBuilder` owns a runtime-local named registry. External hooks run
  in insertion order; duplicate names fail; unregister is explicit. Snapshot
  registrations at build start so a callback cannot grow the current pass.
- The default class hook adds the type triple; the default instance hook
  does nothing. Both are bound through the subject's Context namespace.
- Kernel delegates building and exploring through configured host callbacks,
  keeping Context and RDFLib out of Kernel.
- A hook failure raises `ContextBuildError` retaining the partial result,
  original cause and failed run. Do not silently publish a partial graph.
  Diagnostics record stage/name, elapsed time, before/after triple counts
  and an error where present; they do not claim per-base contribution tracing.
- Explorer construction accepts an already-built ObjectContext. Opening a
  new subject uses the selected builder and retains the result by graph
  node. Validate its triples before publishing them to the growing graph.
  Removing a triple during a build does not retract earlier collected facts.
- Keep the current extension UI and transport shape; verify the real worker.

## Impl.Req.Wiki

Product: `tarav-py`; Wiki owner: `tarav-md/notes/wiki/`.
Relevant context: `rdf-diagram-experiment.md`, especially "The projection
contract" and "The context engine, and all of Tarav migrated". Request 914
is the prior implementation, not the current hook design.

Supporting current native session: codex
`01a1176b-f14c-7fd0-a97c-b22279c3f8c8`, neutral identity
`473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f`.
Capture gap: the exact-session update failed writing the protected Chatlas
cache. Read-only `compute_normal_model` verified identity but retained data
ends before the current hook discussion. Exact supporting Turn hashes are
unavailable; do not attach older unrelated Turns or invent provisional
references. Recover the current turns after a permitted Chatlas update.

## Execution.Plan

Data shape: `ObjectContext(subject, triplets, options, hints, runs, status)`;
`ContextHookRun(stage, name, elapsed_seconds, before, after, error)`;
`ContextBuilder.register/unregister/build`; Explorer retains `contexts`.

- [x] Slice 1 — feature + replacement: Kernel hooks and binding, builder,
  runtime-local registration and Explorer integration; migrate existing
  tests from the removed method. Prove ordered shared mutation, superclass
  and multiple-inheritance composition, class identity equivalence, external
  registration/isolation, failure diagnostics and Explorer retention. Run
  Context, namespace and architecture tests, then the curated suite.
- [x] Slice 2 — documentation: update maintained guidance through its SKW
  source, architecture and CLI help; add a runnable tutorial. Prove the
  tutorial and installed CLI, extension real-worker integration, Ruff and
  required Project checks. Capture the daily/topical Wiki and complete.

Cold execution review: this note distinguishes accepted design from Agent
choices, names existing consumers and risks, and has rerunnable checks.
Re-read it before product edits. Record any material deviation explicitly.

## Impl.Log

- Start checkpoints: tarav-py `8a67d35`; tarav-md `8608027` (both clean).
- Baseline: `UV_CACHE_DIR=/private/tmp/tarav-review-uv-cache uv run --no-sync pytest -q`:
  306 passed in 69.95 seconds.
- Initial todo: implement slice 1; verify and capture; document and verify slice 2;
  capture Wiki; close request and commit.
- Design Inlined Capture: no justified exact Turn positions could be
  registered because current discussion is not retained. Session and reason
  above are the recovery trace; no labels were fabricated.

### Slice 1 — implemented and verified

- Added `construction.py` with ObjectContext, ordered builder registration,
  hook-run diagnostics and ContextBuildError. Kernel owns only the namespace
  hooks and host callbacks; class access binds to its representing instance.
- Runtime owns one builder per composition. Explorer retains the completed
  result and validates all its triples before publishing the graph addition.
- Migrated the Context tests and architecture contract; default graph output
  and CLI behavior remain the same. The old method has no compatibility path.
- Measured: focused Context/namespace/CLI/architecture suite 72 passed; full
  curated suite 313 passed (baseline 306); Ruff clean; diff whitespace clean.
- During review, kept ObjectContext as an ordinary contextualizable object:
  only the Explorer constructor accepts a built result. `open(cxt)` and
  `cxt.context()` describe that object, not its original subject. Regression
  coverage exercises this distinction. This refines, rather than expands,
  the requirement that every Tarav object has context.
- Slice Inlined Capture covered Kernel records, Context construction and
  Explorer, runtime, Context/architecture tests and this note. Exact current
  Turn hashes remain unavailable, so no new markers were justified. Ran one
  batch audit over these seven surfaces; registration/position recovery is
  pending in the protected data depot. Full output is in
  `/private/tmp/tarav-context-slice1-audit.json` for this run.

### Slice 2 — documentation and integration verified

- Slice 1 commit: `7019ebe`.
- Updated ARCHITECTURE.md, Context workflow and CLI help, and the authoritative
  `.tarav/skillware/src/AGENTS.skw.json`; compiled the agents file and lock with
  `tarav skw document compile --source AGENTS.skw.json --depot .tarav/skillware`:
  written, no findings. Added the Context README and runnable example.
- Measured: `tarav run -- examples/object_context.py` prints the ordered stages,
  3 triples, the expected title/length SPARQL row and the class identity.
  `tarav context --id Tarav.POI --json` retains its default type edge.
  CLI tests after wording changes: 7 passed. Ruff (src/tests/examples) and
  diff whitespace checks pass.
- Extension verification: `TARAV_CENTER_TEST_COMMAND=tarav npm test`: all
  13 passed, none skipped; `npm run test:context`: 1 passed. No extension
  source or transport shape change was required. Actual VS Code rendering
  was not inspected.
- `uv tool install --reinstall --editable . --offline` failed in uv's macOS
  system-configuration initialization (NULL object panic), before a successful
  reinstall. The existing editable installed CLI ran the example, Context
  command and extension worker against this code successfully.
- Required `tarav status --project tarav-py --all` ran through checks but
  could not persist actions: sandbox PermissionError on the central Record
  Registry `.write.lock`. No successful status result is claimed. A routine
  read-only `tarav check` is used to inspect findings without action writes.
- Routine Project check: 14 completed, none incomplete; only the two existing
  `Tarav.Test.Actions.MarkerPOI` findings. The pytest suite is excluded from
  the routine command and was run separately as recorded above. No new
  agents-file drift, hook or POI-rendering finding was reported.
- Slice Inlined Capture: inspected the changed architecture, CLI, workflow,
  example, README, SKW source and product. Current User-Turn grounding remains
  unavailable, as in slice 1; the JSON SKW source has no native Breadcrumb
  convention. No unsupported markers or substitute old Turns were added.
- Wiki capture writes the mandatory daily narrative in
  `tarav-md/notes/wiki/daily/2026-10-16.md` and the topical section
  "ObjectContext construction through ordered hooks" in
  `tarav-md/notes/wiki/rdf-diagram-experiment.md`. Both parse through WikiNote.
  They preserve the exact native session and selected User phrases for later
  grounding; registration and existing stale-position repair are pending.

### Completion

Product and documentation are implemented and verified. Product commits:
`7019ebe` (construction), `10b40d0` (guide, example and compiled guidance).
Wiki capture commit: tarav-md `d1230ba`. This closing commit records the
final resolver correction and evidence report.

Final review found that `runtime.context("Tarav.POI")`, supported by the
previous Explorer's identifier-aware constructor, now reached the builder
with a string. A regression assertion first failed with the expected
ObjectContext subject TypeError. Resolve identifiers in the runtime before
building, preserving that existing behavior. After the correction, the
Context and CLI suites pass all 20 tests; Ruff and whitespace checks pass.
The complete 313-test run was before this final targeted correction.

Final Inlined Capture outcome: no new Breadcrumb IDs; exact current User
Turns cannot yet be resolved from retained Chatlas data. The seven-file
audit resolved 9 existing labels and reported 28 existing labels as
unresolvable; labels were retained and the report path is recorded above.
No conversational coverage is claimed for newly implemented positions.

Outstanding environment work: refresh this exact Chatlas session and attach
the supporting Turns to the request, product surfaces and the two Wiki
sections; repair existing label observations as needed; rerun status where
it can write the central action registry. Tool reinstall also remains
uncompleted after uv's initialization panic; the installed editable tool's
real behavior was verified. These gaps do not invalidate the product tests.
