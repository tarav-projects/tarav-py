# 857 — A Project's Decision store

<!-- tarav.sessions
5a029cbf = claude-code:8c55cc60-f28a-439f-a6a0-0521567e600e @5a029cbf49a299c9709013b8ccb3fc517b2fb56fed373d3da819b6ea842afa2f
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented.

Give every Project one place for its Decisions: `.tarav/decisions/`, opened
with `Project.decisions()`. It holds any `Decision` subtype, blessings
included, and is filtered by Type, where a Type selects itself and its
subtypes. What is in this store is what counts as the decisions of the
Project. The Decisions workflow itself keeps no storage.

Non-goals: no migration of existing blessing data (the Archive partition,
`.skw/blessings`, md-library's per-document folders); no rule that a workflow
must use this store; no CLI; no attention or scheduling policy; no change to
how a blessing's standing is computed; no md-library adoption (a separate
md-library request).

## Design narrative

### User direction

Each Project gets a storage solution for its Decisions. Everything that is a
subtype of Decision has this place. Workflows may still put theirs elsewhere,
but this store exists for the decisions of the Project, and what is tracked as
the Project's decisions is what is put in it.
<!-- tarav.breadcrumb 9749b5b4c5bf -->

By default, blessings attached to a Project go to this store. The Decision
types differ but the location is the same; nothing is reinvented per type, and
a general filter by Type, including subtypes, serves all of them.
<!-- tarav.breadcrumb 9faa55267ccf -->

Earlier direction this builds on: a Decision is not forced to have storage and
the Decisions workflow does not handle it; a single store per Project, linked
to the Project workflow, is the first arrangement to establish.
<!-- tarav.breadcrumb 88d7c93ed0c6 -->

The request is designed and implemented in one pass.
<!-- tarav.breadcrumb c6b86ed25d80 -->

### Current behaviour (inspected)

`tarav.l1.decisions.DecisionStore` lives in the Decisions workflow and, since
856, holds only the types its caller lists. `Project.poi_board()` creates one
at `.tarav/decisions` by default and passes blessings only when the caller
supplies a `BlessingStore`. `BlessingStore` is a separate class with its own
directory; reading a directory, it reports every record whose type it does not
know as `invalid-blessing-record`. `BlessingAssessmentRecord`, the older score
record, is stored beside blessings and is not a Decision.
`tarav.l0.kernel.current.current_records()` exposes the runtime's registered
Record types.

### Decisions (agent proposals)

- **Owner.** The store is `ProjectDecisions` in `tarav.l2.project`, a Project
  feature. `DecisionStore` is removed from `tarav.l1.decisions`, so that
  workflow owns the type and no storage.
- **Layout.** One JSON file per record, named by its identity, written
  exclusively and never rewritten. Parallel agents and worktrees never write
  the same file. The directory is meant to be committed with the Project.
- **Types.** Records are resolved through the registered Record types, not a
  caller-supplied list. `snapshot(decision_type=...)` returns records whose type is the
  given class or a subclass; the default is `Decision`.
- **Unknown and foreign records.** A record whose type is not registered is
  kept on disk and reported as a finding. A registered record that is not a
  Decision is skipped without a finding; this is what lets assessment records
  sit beside the blessings they belong to.
- **Blessings.** `ProjectDecisions.blessings()` returns a `BlessingStore` over
  the same directory, so standing, `bless` and `assess` work unchanged.
  `BlessingStore` learns to skip registered Decision types that are not
  blessings instead of reporting them.
- **Board.** `Project.poi_board()` uses this store for both blessings and
  other Decisions by default, and counts each Decision once.

### Open questions

- Should the older `BlessingAssessmentRecord` keep travelling with blessings,
  or be retired in favour of the scoring workflow's results? Not settled here.
- md-library's typed Project is its code repository while its decisions are
  about the corpus depot. Which root owns the store there is for the md-library
  request.

## Impl.Req.Wiki

Product owner: `tarav-py`.
Wiki owner/root: `tarav-md/notes/wiki`.
Relevant context: `tarav-md/notes/wiki/decisions.md`, `projects.md`; requests
854 and 856.
Supporting chat: claude-code session `8c55cc60-f28a-439f-a6a0-0521567e600e`.
Capture status: completed in `tarav-md/notes/wiki/decisions.md` and `daily/2026-10-03.md`.

## Execution.Plan

1. **Store.** Add `tarav.l2.project.decisions.ProjectDecisions` (`add`,
   `snapshot(decision_type=Decision)`, `load`, `blessings()`), and `Project.decisions()`.
   Check: any registered Decision subtype round-trips; a Type filter returns
   subtypes; an unregistered type is a finding; a second write of one identity
   fails.
2. **Blessings in the same place.** Let `BlessingStore` skip non-blessing
   Decision records it is told about.
   Check: a blessing made through `project.decisions().blessings()` appears in
   `snapshot(decision_type=BlessingRecord)` and in `snapshot()`, gives `blessed`
   standing, and produces no finding beside another Decision type.
3. **Remove the old store; rewire the board.** Delete `DecisionStore`; the
   board accepts the Project store and does not double-count blessings;
   `poi_board()` defaults to it.
   Check: `tests/decisions`, architecture tests, the full suite, ruff.
4. **Guidance.** Update `ARCHITECTURE.md` and `AGENTS.md`.

Risk: other agents are working in this repository. Keep commits scoped and
short-lived; recheck the worktree before each commit.

## Impl.Log
- Start checkpoint 9f50eca.
- Slice 1: `src/tarav/l2/project/decisions.py` adds `ProjectDecisions` (`add`,
  `snapshot(decision_type=Decision)`, `load`, `blessings()`); `Project.decisions()`
  opens it. Types come from the current Record registry, or from an explicit
  `record_types` argument. The filter parameter is named `decision_type`
  because `type` would shadow the builtin.
- Slice 2: `BlessingStore` takes `other_decision_types` and skips those
  records; `ProjectDecisions.blessings()` passes every registered non-blessing
  Decision type. Blessing behaviour is otherwise unchanged.
- Slice 3: `DecisionStore` deleted from `tarav.l1.decisions`, which now owns no
  storage. The board accepts any object with `snapshot()` as `decisions` and
  counts a blessing found in both views once. `Project.poi_board()` defaults
  both to the Project store.
- Slice 4: `ARCHITECTURE.md` (two places) and `AGENTS.md` (Project model).
- Tests: two new tests cover round trip, exclusive write, subtype filtering,
  blessing standing from the shared directory with no findings, an unregistered
  type as a finding, and single counting on the board. `uv run pytest -q`: 164
  passed. `tests/test_architecture.py` with `tests/decisions`: 48 passed. Ruff
  clean on `src` and `tests`.
- Observation: a test needs an explicit `record_types`, because
  `current_records()` reads the process-wide runtime, not one created locally
  with `create_runtime`.
- Breadcrumbs: three on product code and tests, one on `AGENTS.md`; shifted
  positions in the edited files re-recorded; all audits clean.
- Not done, by design: no migration of existing blessing stores; no CLI; SKW
  skills and md-library still use their own blessing directories.
- Product commit 9f58050. Wiki captured; audits clean.
