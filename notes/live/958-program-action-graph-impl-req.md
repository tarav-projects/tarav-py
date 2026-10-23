# Programs as graphs of Actions

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: complete. Execute the accepted refinement of
request 955. Remove the explicit State concept. A Program defines a graph of
NodeActions and EdgeActions; runs retain active Action occurrences and their
tokens. Reuse ordinary Action registration, tapes, Project integration and
external Program storage. The User requests this new request and execution.
<!-- tarav.breadcrumb a4cd728e4440 -->
<!-- tarav.breadcrumb ec7c72b740f3 -->

## Design

The Program owns its Actions, Check definitions and check-selection policy.
NodeAction and EdgeAction describe graph roles, without mandatory ownership or
semantics for checks. A Program can reuse any Check classes across Actions.
In particular, the runner must not automatically rerun source-node status
checks at departure or destination-node status checks at arrival. A concrete
Program may select those same checks explicitly when that is its policy.
<!-- tarav.breadcrumb 96754536e38d -->

Mandatory mechanics: tokens identify current Action occurrences in the right
run and Project. A valid node token cannot enter an undeclared or unavailable
edge. An edge occurrence retains its selected connection and can only proceed
to that connection's destination. Each accepted move replaces its occurrence
and token; old tokens cannot be replayed. Status chooses checks from the actual
active Action, including during an edge, with contextual results.
<!-- tarav.breadcrumb d837ea9e0636 -->

### Implementation choices

Data shape first: delete states.py and the State/StateAction/StateReached API.
actions.py defines ProgramAction(Action), NodeAction, EdgeAction, the existing
ProgramExecutionAction and immutable Transition(source, action, target).
Node/edge closures use the existing basic Closing Type. ProgramRun replaces
state/arrival/pending/token fields with active: a list of typed ActiveAction
values carrying occurrence Ship, Action TypeShip, token and optional edge
source/target TypeShips. Retain Program identity, Project, JSON data, snapshots,
history, phase and timestamps. The overall Program remains a registry Action.

Program.initial is a nonempty tuple of NodeAction Types. This permits a set of
active branches without introducing fork/join mechanics. A move consumes just
the selected occurrence, preserving the others. Program.terminal explicitly
names terminal NodeAction Types. A terminal node remains a visible Action until
step completes it; the overall Program closes only when no active Action remains.

One author hook, Program.checks(run, occurrence, operation=...), returns a
CheckSuite. Operations are enter, status and complete: lifecycle slots, not
fixed meanings for checks. Defaults are empty. Start gates initial entries;
choose gates source completion and edge entry; step gates edge completion and
target entry, or completion of a terminal node. The hook receives the actual
Action occurrence and the run context for that side. The candidate context
replaces that active occurrence and contains updated input data. Status never
advances, rotates tokens or writes run state. Evidence identifies occurrence,
Action Type, role and operation. Failed/incomplete gates retain the original
active occurrence/token and record the attempt. Invalid graph/token operations
fail before mutation. Normal Project status still does not claim another
unselected token context was checked.

Program.available(run, occurrence) filters declared outgoing connections.
Program and Project Type identities stay unchanged. New Action role Types get
their own identities. ProgramRun uses its existing Type with the new strict
schema: no compatibility aliases, automatic stored-run migration or guessing.
Old unsupported run Records fail explicit parsing; Git retains the old schema.
The prior implementation started no production Program runs. No real Program
is started or migrated by this work. Project Monitor changes, fork/join APIs,
per-run code snapshots and external script loading remain outside scope.

## Current mechanics inspected

l1.programs currently defines State(CheckProvider), StateAction(Action), a
Transition whose target is action.State, and ProgramRun with one state/pending
pair and a token that survives selection. Runner chooses only after State
status checks pass and automatically checks destination States on step.
l2.project.programs contextualizes status through StateIncoherent POIs.
l3.programs and l3.status expose the installed harness commands. These callers,
tests and operating documentation must move together. Record Registry and Action
projection recovery remain shared infrastructure. Baseline core/CLI/Record
verification: 19 passed before edits.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki; bounded append to programs.md
and daily/2026-10-23.md, preserving the earlier design as dated history.
Companion: ../../../tarav-md/notes/live/880-program-action-graph-wiki-impl-req.md.

## Execution.Plan

- [x] Feature, one vertical runtime slice: replace the core model, Project/CLI
  consumers and test fixtures together. Verify actual node→edge→node tokens,
  shared Program checks with different lifecycle policy, terminal completion,
  multiple active occurrences, graph/token isolation, failure/no-write behavior,
  external Action visibility, roundtrip, recovery and concurrency. Rewrite old
  behavior assertions only where the accepted design changes them.
- [x] Documentation and integration closure: revise operating guide and
  architecture; capture supported surfaces and the Wiki; refresh installed CLI;
  run focused tests, whole-source Ruff, default discovery and Project --all;
  inspect all failures, then close evidence commits and this request.

## Impl.Log

- Execute / Wiki / Interactive. Constitution and local guidance read; no child
  agents used. Preserved pre-existing Chatlas Typesense work as found at the
  start: Python 721cb46e, Markdown d90be816. Those commits carry unknown-session
  evidence gaps, since their originating discussion was outside this task.
  Shared architecture/runtime/test files may retain later concurrent edits;
  own diffs will preserve them. Current chat refreshed once for this pass.
- Request reloaded and checked against target code. Removed explicit State and
  StateReached; NodeAction/EdgeAction are ordinary Actions and use basic Closings.
  No old API aliases or run migrations. Program.checks owns lifecycle selection.
- Runtime verification: 20 core/real-harness/Record-interface tests passed;
  another 111 architecture/Action/Project/CLI integration tests passed. Measured
  node→edge→node token replacement, optional departure/entry policy, distinct
  status/completion checks, terminal NodeActions, multiple active occurrences,
  concurrent consumption, same-run status isolation and projection recovery.
- Project checks also retire warnings for closed occurrences from recorded
  closure facts. This runs without consumed tokens and does not check another
  active occurrence. A terminal completion test covers the case where no token
  remains. Whole-source Ruff passed. Documentation/capture closure follows.
- Runtime slice committed as 8517607f after all changed surviving source/test
  surfaces passed Breadcrumb capture/audit and Python compilation/Ruff.
  states.py was removed rather than annotated. tests/test_architecture.py also
  retained the concurrent Typesense agent's Breadcrumb submission as found.
- Guide and architecture now describe Action-owned graph roles, Program check
  policy, terminal completion and active collections. Installed CLI refreshed;
  a real Project listing returned no Programs or runs, without starting one.
  Default discovery collects 669 tests and includes both Program test files.
  Documentation and Wiki capture/audits passed. Shared architecture/daily Notes
  retain concurrent Typesense edits; no external work was discarded.
- Documentation slice committed as 15ab6232; Wiki capture as a936ba6f. Commit
  Breadcrumb audits passed for these and runtime 8517607f. All own surviving
  surfaces audited clean; deleted State surfaces remain in Git history.
- Full root `tarav status --project ... --all --json` completed all 1,351
  checks, with 70 completed pytest file checks and zero pytest findings,
  incomplete checks or skipped suites. Exit 1 represents the existing 67
  maintenance POIs (Git setup/scans, review coverage/test markers and
  Skillware/Wiki freshness). Its remaining provisional Wiki markers are on
  other Notes. Report: /tmp/actiongraph-full-status.json. Ruff and default
  discovery passed; no further source changes followed this verification.
- Both repositories were clean before this completion-log update. All active
  Program test data lived in disposable registries; no production run or
  migration was performed. Start external-work snapshots retain their honest
  unknown-session evidence marker; own implementation/capture has no gap.
