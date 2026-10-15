# 912 — Cumulative Context views and typed navigation steps

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous. Phase: Develop.
Status: implemented and verified; capture closure in progress.

Context represents a subject under accumulated typed qualifications. A view
extends the current Context; entries advertise contextualization steps or open
ordinary nodes. Multiple requested views apply left to right and preserve all
earlier qualifications. Implement `obj.context(views=(View, Request(...)))`
and the equivalent `obj.context.explore(views=...)`, with explicit rejection of
unsupported combinations. The User delegates implementation choices.
<!-- tarav.context 473c89a0:3cae519d8e79ad5b -->

## Design narrative

Context is a graph exposed as folders. Keys are navigation labels; entries and
values are typed objects. Specialized entry Types can express the relationship
of a local step; generic entries and grouping nodes remain valid. The same
value may occur on different paths with different relationship semantics.
<!-- tarav.context 473c89a0:ba32e41d46ab46db -->
<!-- tarav.context 473c89a0:5696389e9d36d4fc -->

The User wants progressive contextualization: begin with the subject, add
views, and expose material compatible with all accumulated qualifications.
`.ls()` offers available next steps; `.open()` opens a resulting view or a
direct node. Selecting a view directly and opening a corresponding entry must
reuse the same derivation operation. Repeated relationships across views are
valid; no disjointness or monotonic growth of result sets is required.
<!-- tarav.context 473c89a0:926997d41da95b26 -->
<!-- tarav.context 473c89a0:9b167562b00b0279 -->

Accepted naming: rename the returned folder base Python class `Context` to
`ContextView`; retain the `SomeType.Context` namespace, ContextEntry,
ContextExplorer, `.ls()` and `.open()`. Use plural `views=` consistently,
including one-element selections. Static view classes and parameterized typed
requests both participate. Existing callers and extensions are migrated;
there are no compatibility aliases for the retired Python class or `type=`.
<!-- tarav.context 473c89a0:818e903fec5c70c5 -->
<!-- tarav.context 473c89a0:4c4bb8bf8f117d07 -->
<!-- tarav.context 473c89a0:3cae519d8e79ad5b -->

Scope excludes an annotations storage system, a documentation representation,
new standard documentation keys, and a general compatibility solver. The
earlier examples did not settle documentation semantics.
<!-- tarav.context 473c89a0:4cc56a88bd2425f3 -->

### Current code and implementation decisions

`l1/context/__init__.py` currently selects one `Context.for_subject()` factory.
ContextBuilder already supports specialized entries; retained listing erases
their concrete Types by rebuilding generic handles. Kernel's bound Context
namespace delegates to l3 without upward imports. ContextScope and cumulative
dispatch belong in l1; storage integration stays in l2; runtime and CLI in l3.

Agent decisions: ContextScope is immutable and navigation-local, containing
the subject and ordered qualifications. Expose it as `context_scope` to avoid
colliding with the existing LineScope.scope relationship. View classes extend
`accepts(scope)` and `for_context(current)`; parameterized ContextViewRequest
objects implement `accepts(scope)` and `apply(current)`. A shared derivation function validates selectors, keeps the
subject, attaches the cumulative scope, and raises UnsupportedContextView
instead of silently dropping a step. Compatibility is each view's explicit
responsibility. Existing ObjectGroup/LineScope accept only an unqualified
input until they declare further composition semantics.

Generic grouping views inherit the containing view's scope when their subject
matches. Opening a different subject starts a fresh scope; explorer origin and
history retain the incoming route. ContextViewEntry and builder.add_view()
reuse cumulative derivation for navigable steps. Runtime view entries are
computed navigation handles, not a new persisted request schema. A dedicated
typed-entry storage operation and retained listing preserve registered concrete
ContextEntry subtypes. Persistent custom entries use their existing typed
Record contracts and trusted Type registry. Existing generic Context storage
and its create-only placement policy remain intact.

Preserve existing Type Ships and retained Record labels while changing Python
names. Named Context queries use ordered view names; the CLI accepts repeated
`--view` options. This is a new list interface, with existing single CLI uses
still expressing a one-element selection.

## Impl.Req.Wiki

Owner: `../tarav-md/notes/wiki/`; topical `context-graph.md`, daily
`daily/2026-10-15.md`. Capture cumulative qualifications, typed local steps,
shared direct/navigation semantics and explicit limits. Keep implementation
choices distinct from User decisions; inspect supporting User Turns above.

## Execution.Plan

1. Feature/refactor: ContextView naming, ContextScope, cumulative dispatch,
   view/request extension contracts, typed step navigation and current caller
   migration. Prove multiple parameterized qualifications, equality of direct
   and entry routes, generic grouping preservation, explicit incompatibility,
   lazy opening and independent explorer histories. Status: verified.
2. Feature: retain specialized entry Types through typed writes and reads;
   migrate query/CLI to ordered views and advertise typed steps. Prove subtype
   metadata survives an Archive round trip, CLI repeated-view dispatch and
   compatibility failures. Status: verified.
3. Documentation/integration: architecture and Wiki capture, configured/full
   tests, Ruff, Project status, inlined capture/audit and evidence commits.
   Status: pending.

## Impl.Log

- Product baseline: 31 focused tests passed. Both product and Wiki worktrees
  clean. Product start checkpoint: `f9ead85`.
- Exact session refresh completed in writable `/tmp/tarav-context-chatlas`;
  current User-Turn hashes resolved through the timestamped Chatlas ledger.
  Main data depot writes remain sandbox-protected. Evidence registration
  failed for the start checkpoint; plain Git fallback follows the skill.
- Data shape first: one accumulated ContextScope. Subtract before adding:
  migrate the single-view selector and returned class, preserving ontology
  identity. Boundary discipline: no Context runtime imports enter Kernel;
  retained entry loading remains trusted Type dispatch. No stored navigation
  history or new documentation/annotation schema is introduced.
- Cold reload confirmed the plan before product edits. The first two slices
  share the selector migration and were implemented as one integrated slice to
  keep runtime and CLI callers operational. Focused integration: 53 passed;
  subsequent propagation/compatibility checks: 33 passed. Ruff passes.
- Added explicit accepts(scope) hooks, used by both discovery and dispatch.
  ContextViewEntry checks an entire offered chain using scopes without running
  factories. Registered next-step contributors follow derived views as well as
  the root; they do not re-add unqualified retained content to filtered views.
- TypeModel's accessor, root entry, and explicit view selection share its
  qualification. It uses the configured root model contribution without an l1
  storage import. Semantic member listings omit navigation-only view steps.
- A full discovery run found 483 passes and the previously known unrelated
  ProjectModels(None) test failure. The new object-group next step required one
  literal POI Context listing expectation to change; its old expected list
  omitted that now-advertised step. No unrelated Model behavior was changed.
- Inspection found that query traversal compared a path segment with the final
  segment's text instead of its position. Repeated labels could skip a subject
  Context hop. Switched to the index and added a public-query regression test.
- Code identity/retained labels remain unchanged. Scope and computed view steps
  are navigation-local. Registered concrete relationship entry records keep
  their own Type and fields through write, reload, listing and explorer binding.
- Final full discovery: 485 tests passed; the one known ProjectModels(None)
  expectation still fails independently of these changes (as reproduced and
  documented in request 911). The new pipeline, typed entries, CLI, model and
  architecture integration tests pass. Ruff and git diff --check pass.
- Reused relationship handles now drop old explorer bindings before being
  placed in a different view; a regression test verifies independent routes.
- Product Inlined Capture ran separately on every supported changed surface,
  including code, tests, architecture and this request. New submissions cannot
  write to the main Breadcrumb store. Pure mechanical caller migrations with
  no new marker report no active provisional markers; no support was invented.
  TOML has no supported embedding convention. Batch audit remains non-clean,
  with pending markers and unresolved older position/attachment concerns.
- `tarav status --project --all` reached Actions persistence and failed writing
  the sandbox-protected central registry. A checks-only harness run is in
  progress. Editable reinstall was attempted (including offline mode); uv
  panicked in macOS system-configuration before installation. The installed
  editable tool still reads this source, and its Context help advertises the
  repeated --view interface successfully.
- Wiki start checkpoint: `3281e92`. Wiki text is drafted in context-graph.md
  and daily/2026-10-15.md; both parse through WikiNote.parse.
