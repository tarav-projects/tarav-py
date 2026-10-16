# 917 — External ContextHook instances

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented and verified; Wiki written and committed. Exact
conversational grounding and Project status persistence remain pending.

Replace external callable hooks with instances of a real ContextHook base
class exposing `run(cxt)`. Register explicitly constructed instances so
they can bundle dependencies, configuration and runtime state. Every hook
decides whether it concerns a subject. Preserve the existing shared result,
stage order, external registration order, snapshots and diagnostics.

Scope: Context construction and public exports, existing hook consumers in
tests and the runnable example, developer documentation, and bounded Wiki
capture. Non-goals: annotations storage, target-class registration,
automatic construction, dependency injection infrastructure or persistence.

## Design narrative

The User requested a ContextHook class that contributors extend, bundling
what is necessary to run. The discussion settled on registering instances
constructed with ordinary Python arguments. A class-target registration
proposal was considered and withdrawn: the User's final decision was,
“the hook itself can do the checking and ignore what it wants to ignore”.
The latest invocation authorizes Develop of the remaining typed-hook delta.

Current code (`construction.py`) calls registered functions and names
`ContextHook = Callable[[ObjectContext], None]`. The private `_run` also
uses this alias for the class/instance namespace methods. The real class
replaces the external extension contract; the private executor continues
to accept ordinary bound methods, including each external instance's run.

Implementation choices: a small Python ABC with abstract `run(cxt)`,
exported from `tarav.l1.context`; no new Ship or Record obligation for
implementing this extension interface. Validate `isinstance(hook,
ContextHook)` at registration. Reject bare functions, classes and duck
typed substitutes; no compatibility adapter. Keep names separate as the
existing registry/diagnostic keys. The builder invokes the same registered
instance on every build, allowing its constructor-owned state to persist.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki/.
Relevant note: `rdf-diagram-experiment.md`, "ObjectContext construction
through ordered hooks"; prior implementation request:
`916-object-context-builder-and-hooks-impl-req.md`.

Supporting current native session: codex
`01a1176b-f14c-7fd0-a97c-b22279c3f8c8`, neutral identity
`473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f`.
The exact-session refresh failed on the protected Chatlas cache. Grounding
new positions in exact retained User Turns remains pending; no unrelated
older Turn or invented hash may be substituted. This note preserves the
current decision and source session for recovery.

## Execution.Plan

Core data shape: `ContextHook(ABC).run(ObjectContext) -> None`;
`ContextBuilder._hooks: dict[str, ContextHook]`. Registration accepts only
instances. Existing class/instance hooks and ObjectContext are unchanged.

- [x] Slice 1 — feature and migration: replace the alias, expose the base,
  call `.run`, migrate all registered callbacks to concrete subclasses, and
  test bundled dependencies/state, self-filtering, contract rejection,
  order/snapshot/runtime isolation, failures and retained contexts. Update
  architecture, guide and example in the same coherent migration. Check:
  Context/CLI/architecture tests, runnable example, Ruff; then one full
  required Project verification rather than repeated broad suites.
- [x] Close: capture the daily and topical Wiki sections, inspect evidence
  gaps, commit verified surfaces and complete the request.

Cold execution readiness: targets and consumers were inspected, current
behavior is covered by the passing Context/CLI baseline, and the accepted
interface needs no additional User decision. Re-read this note before the
first product edit. Record material deviations rather than silently adapting.

## Impl.Log

- Start worktrees: tarav-py and tarav-md clean. Checkpoints: tarav-py
  `2326789`, tarav-md `9faf7c9`.
- Baseline Context/CLI suite: 20 passed. After implementation, Context,
  CLI and architecture: 68 passed. The added tests exercise bundled
  dependencies, retained state and ignored subjects, plus rejection of
  functions, classes and duck-typed substitutes.
- The migrated existing tests still prove class → instance → external
  order, shared mutation, registration snapshots and isolation, failure
  diagnostics and Explorer retention.
- Runnable example through the installed `tarav run`: stage order intact,
  3 triples, expected title/length SPARQL row and class identity. Ruff clean.
- Updated the guide and architecture; compiled the authoritative agents
  source with no findings. No command entrypoint or dependency changed.
- Initial todo: implement/migrate; verify; capture; commit and close.
- Design Inlined Capture: pending exact current Turn resolution because
  Chatlas refresh cannot write its protected cache. No new labels fabricated.
- Slice Inlined Capture inspected all implemented surfaces. Five surfaces
  without existing labels (construction, guide, example, Context tests and
  request) were batch-audited: all ok, zero Breadcrumbs. Existing-label
  position repair and new current-Turn registration remain pending; there
  is no justified exact Turn to submit. The JSON SKW source has no native
  Breadcrumb convention; source was edited and the product compiled.
- Wiki capture adds "External hooks as configured instances" to
  `tarav-md/notes/wiki/rdf-diagram-experiment.md` and "Configured external
  ContextHook instances" to the 2026-10-16 daily Note. They retain the
  withdrawn class-routing proposal, final User decision and recovery gap.

## Completion

Product commit: `131b035`. Wiki commit: tarav-md `a55cee0`. Both Wiki Notes
parse through WikiNote; no source or dependency changes were required in
the extension. All maintained registered-callable consumers were migrated.

Verification: baseline 20 Context/CLI tests; after migration, 68 focused
Context/CLI/architecture tests passed, Ruff and whitespace checks passed,
and the installed-tool example produced its literal expected graph/query
result. No further product edits followed these checks.

Required `tarav status --project tarav-py --all` finished its check phase
but failed when writing actions to the protected central Record Registry
(`.../records/8f3394a6-7670-4568-a71e-5120f687affd/.write.lock`). No
successful full status or aggregate test outcome is claimed from that
failed operation. Tests were not broadly repeated to reproduce the same
environment limitation.

Inlined Capture and Wiki grounding remain pending: exact-session Chatlas
refresh failed writing its protected cache, so new supporting Turn hashes
could not be resolved. Five changed surfaces audited cleanly with zero
labels. No new Breadcrumb IDs or unsupported provisional references were
invented. Current decisions, the exact session and selected User wording
remain in this request and the Wiki for later recovery. Existing labels in
other changed surfaces have not been refreshed in the protected depot.

Recovery: refresh the exact session, resolve the final class-hook and
self-filtering User Turns, attach them to justified positions in the
request/product/Wiki, and rerun status where action writes are permitted.
