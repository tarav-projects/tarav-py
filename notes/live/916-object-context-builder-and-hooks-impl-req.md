# 916 — Composable ObjectContext construction

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: slice 1 implemented and verified; documentation and closure pending.

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
- [ ] Slice 2 — documentation: update maintained guidance through its SKW
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
- Todo: implement slice 1; verify and capture; document and verify slice 2;
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
