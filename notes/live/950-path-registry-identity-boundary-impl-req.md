# PathRegistry owns schema and path identities

## Impl.Abstract

Status: implemented; verification running. Knowledge.Surface: wiki. Alignment.Mode: Interactive.

Follow up completed request 948. Restrict PathRegistry to providing and tracking
identities of schemas and positions within schemas. Remove registry-owned
attachment storage and documentation Types. Keep computed structure, explicit
identity maintenance, Project ownership, drift checks and Git history.
No new documentation/annotation workflow or extension changes in this request.

<!-- tarav.sessions
0f5bad01 = codex:01a15483-94e8-7fe0-86ad-ddd83e2bae52 @0f5bad0131260477b4cf3d712a95871496c3db92d67eaa7910243e312f7b552a
-->

## Design

The User clarified that the registry identifies schemas, rather than instances,
and gives positions within those schemas Ships. Documentation is one consumer
of those identities. Other workflows can use Path Ships in their own records;
the registry need not contain or know those associations. The User requested a
follow-up implementation request and then explicitly authorized execution.
<!-- tarav.breadcrumb 5c3b0c97a971 -->
<!-- tarav.breadcrumb fb3f8a0555bb -->
<!-- tarav.breadcrumb 60533efae9f8 -->

Current inspected product: `l1/path_registry/__init__.py` mixes identity storage
with `PathEntry.attachments`, `PathRegistry.attach()` and `PathDocumentation`, a
Lines subtype included in `PATH_REGISTRY_TYPES`. Tests and the workflow guide
exercise that API. Architecture and generated Project guidance describe it.
No maintained production consumer was found outside these surfaces. A workspace
scan found no live `.tarav/paths.json` files; isolated test fixtures create theirs.

Data shape first: keep JSONView (owning Type, name, computed value and Ship),
PathEntry (Ship, View Ship, declared path and active state), and PathRegistry
(Project Ship, accepted Views, entries). Remove the Line import, documentation
subtype, attachments field/constructor argument/example and attach method.
Keep all existing schema/path Type Ships and identity generation unchanged.
Retired entries and explicit reassignment continue preserving identity.

Consumer-owned associations remain consumer-owned data. Tests can illustrate an
ordinary external mapping keyed by Path Ship using regular Lines with their
existing Block contexts. This illustrates the boundary without designing a new
persisted annotation model. Registry serialization must exclude consumer data;
save/load and rename must leave the independently held association usable.

Subtract before adding: delete the misplaced capability and migrate examples
and tests in the same slice. No compatibility alias, ignored legacy input or
new registry of associations. Before execution, recheck for live registry data;
if any appeared, preserve it and explicitly migrate relevant associations rather
than silently discard them. Existing request 948 remains the historical account
of the original implementation; this request records the correction.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Update path-registry.md to
explain the corrected ownership and link the daily 2026-10-22 Note. Retain prior
implementation history distinctly. Use the exact refreshed Chatlas session above
for request, affected source and Wiki Breadcrumbs. No scoring/support/review work.

## Execution.Plan

- [x] Refactor: establish the existing path tests' passing baseline; remove
  registry attachment/documentation ownership and update callers. Verify schema
  and path Ships survive rename/save/load/retirement, consumer associations stay
  outside serialization and their Lines keep their authoring context. Run path,
  kernel Record-contract and architecture tests plus Ruff.
- [ ] Capture/closure: update workflow guide, architecture, Skillware source and
  rebuild guidance. Capture request and changed source, run full Project status,
  update topical/daily Wiki, audit Breadcrumbs and commit scoped evidence.

## Impl.Log

- Inspected implementation, tests, runtime registration, architecture, Project
  guidance and current Wiki. This request is the todo list. Exact current
  Chatlas session refreshed once; latest design and execution Turns resolved.
- Concurrent Product Review Tracker work exists in this shared Python tree.
  Preserve it; start checkpoint captures pre-existing work under the skill's
  normal evidence policy. Product implementation remains scoped to this request.
- Cold-read the request before product edits. Start checkpoints: Python
  `f892309dab54ad220a4b94c52e948cac24dc1c4b`, Markdown
  `36a0c6d212f4a1ccff27f3f104d813614a093234`. Baseline: 13 path tests passed.
- Removed attachment field/API, documentation subtype and Lines dependency;
  runtime registration follows the shortened PATH_REGISTRY_TYPES tuple. Updated
  consumer examples, behavior and architecture tests, architecture and Skillware
  guidance source; rebuilt AGENTS.md and its lock. Ruff passed.
- No live registry data appeared before edits. No migration or compatibility
  reader is needed. JSONView and PathEntry Type identities remain unchanged.
- ARCHITECTURE.md and tests/test_architecture.py also contain concurrent Product
  Review Tracker changes; scope commits include these mixed files in full under
  the skill policy. Product Review implementation files remain outside our slice.
- Focused run: 76 passed, one failure in the concurrent Product Review
  architecture test. All path and kernel Record-contract tests passed, including
  the exact identity-only Path record and external Line association example.
  The other session corrected its test during the run; architecture is being
  rerun without changing that session's implementation. Full Project status runs
  separately. Markdown full status completed 1,215 checks, none incomplete;
  existing harness, Git, SKW and two other Wiki marker findings remain.
- Architecture rerun passed all 55 tests after the concurrent test correction.
  Ruff passed after source capture. All eight selected request/source/Wiki
  surfaces audited successfully with zero errors; informational findings update
  moved source positions. Guidance JSON uses a registered external annotation.
