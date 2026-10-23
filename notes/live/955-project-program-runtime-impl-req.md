# Project-defined Programs, StateActions and arrival tokens

<!-- tarav.sessions
ec6cf584 = codex:01a1563b-2992-7c62-8a38-05c1cc75b1fe @ec6cf5849bb6c4e66f011b015415da94eeb1a17634872aa4fb9e25d8e065ab53
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: ready. Develop a first working Program runtime
from the accepted discussion. A Program is a trusted Tarav class defined in a
Project, not an injected Python script. Its reusable base owns execution,
persistence and tokens; concrete classes define States, Actions and allowed
connections in ordinary Python. User requests an implementation request and
execution together. Project Monitor reorganization is explicitly deferred.
<!-- tarav.breadcrumb 2ecbcbd42d6e -->
<!-- tarav.breadcrumb 8e62cb2f31b9 -->

## Design

A State is a CheckProvider. A StateAction owns prompting and prerequisites and
uses its destination State's same check-producing object. Successful action
checks establish arrival; contextualized status reruns that State's checks to
find later incoherence. A token is an agent declaration of the State to maintain,
not proof that the product can never change. No manual done path skips checks.
<!-- tarav.breadcrumb 45bbb62f7096 -->
<!-- tarav.breadcrumb 8894fff08e16 -->
<!-- tarav.breadcrumb 4e8900562d23 -->

The Program class defines connections (source State, StateAction; target comes
from the Action), initial State and optional terminal States. Python loops can
construct connection tuples; an availability hook filters them from run data.
The base step controls advancement rather than requiring a dispatch tree in
every author-written step. Program data is explicit persisted JSON, not a
serialized Python stack. Class code is the Project's current trusted code; no
script loader, execution snapshot, sandbox bypass or restored Iterante runtime.
<!-- tarav.breadcrumb fa2abe82f881 -->
<!-- tarav.breadcrumb 55fb46c2dffe -->
<!-- tarav.breadcrumb 71a090eead4a -->
<!-- tarav.breadcrumb 20337a4e9ffc -->

## Current code and implementation choices

Inspected l1.programs (minimal TaravProgram Entity), l2.project.programs (minimal
ProjectProgram), l1.actions (ActionRun, StepRunner, tape, typed Closings),
CheckProvider/CheckSuite, RecordRegistry and l3 Project harness/status launch.
Existing ActionRunStore is outside Projects and Project action listings already
include any run carrying their owner descriptor. Programs and Actions were not
yet related. Retained Iterante supplied evidence for per-invocation persisted
data, not a live dependency.

Data shape first: State and StateAction definitions, immutable Transition
declarations, ProgramRun Record with Program TypeShip, owner Project, current
State TypeShip, arrival number/current token, pending action, JSON data, event
history and canonical ActionRun snapshots. Existing Program identities remain.
Root ProgramExecutionAction and StateActions appear in the existing Project
action registry; StateActions are managed by Program commands rather than the
unrelated operator StepRunner. Each graph-declared action is registered by the
trusted runtime. Concrete Program classes register normally in their harness.

Agent policy: start verifies its initial State before issuing an arrival token;
the default State has no additional conditions. Choose opens one allowed action
under the current token; step runs prerequisites and destination checks. Failure
records the attempt and keeps the action/token. Success closes the action,
records arrival and replaces the token, even on a cycle. Terminal arrival also
closes the root Action. Status never advances or rotates tokens. Input data is
an explicit JSON object. An availability override can only select graph edges.

The Programs Record Registry partition is authoritative and outside the Project.
Action Registry records are projections of retained ActionRun snapshots. A
single Programs lock serializes token consumption. Persist the run before
projecting Actions; explicit recover replays projections after interruption
without changing tokens, checks or history. Reads never initialize or repair.
This avoids pretending independent Git repositories form one transaction.

Boundary discipline: resolve Program identity only through the Project's trusted
registered Types and ownership selection. Tokens include run identity plus fresh
random bytes; only the stored current token is accepted. Bind every operation
to Program and Project identity, reject wrong/stale tokens before mutation, and
keep control fields separate from supplied program data. No security claim that
other agents cannot read the external registry. State checks run in full.

Project.programs owns integration. `tarav program` runs inside the existing
Project harness; `tarav status --program-token` adds a coherence check to the
normal Project loop. A missing/failed scan is incomplete, not proof of coherence.
The monitor and ActionManager ownership stay as they are.

Subtract before adding: replace bootstrap-only docstrings with the implemented
contract; reuse Action tapes, CheckSuites and RecordRegistry. No compatibility
paths, legacy migrations, production Program definitions, real User tokens or
new agent execution service are needed. Old minimal Program Record examples
remain valid. Tests use disposable Projects and registries.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Existing programs.md and
operator-context.md provide context; append the accepted state/token refinement
to programs.md and daily/2026-10-23.md. Companion request:
../../../tarav-md/notes/live/877-project-program-runtime-impl-req.md.

## Execution.Plan

- [x] Feature: definition/State/StateAction models and durable checked execution.
  Verify actual Python start/choose/step/reload, failed/incomplete checks, illegal
  edges, stale tokens, cycles, terminal closure, shared State checks, Action
  projections and explicit recovery. Preserve bootstrap Record roundtrips.
- [x] Feature: Project manager, trusted class resolution, installed program CLI
  and status modifier. Verify a real Project-defined class in its harness, no
  arbitrary source loading, Project isolation, ordinary Action listing and
  later state drift detected without token rotation.
- [ ] Documentation/capture: operating guide, architecture test, contextualized
  request and Wiki capture; reinstall CLI, focused checks, Project --all and
  evidence commits. No live business Program is started by implementation.

## Impl.Log

- Develop / Wiki / Interactive. Todo above. Read code and instructions, checked
  current boundaries and runnable uv tests. Initial worktrees clean; evidence
  start checkpoints retained at /tmp/program-start-{py,md}-result.json.
- Start checkpoints: Python 101068e7; Markdown df428a25. Product request was
  cold-reloaded and code targets checked before execution. No external work was
  present. No subagent work is requested or used.
- Slice 1: 23 Program lifecycle/Record checks passed. Measured real product edits,
  action opening/checked closure, failed and incomplete attempts, cycle freshness,
  stale token rejection, terminal closure, conditional availability, Project and
  Program isolation, exact record roundtrip and explicit projection recovery.
- Recovery test exposed restoration of already committed Action bytes requiring
  no Git commit. Initial comparison incorrectly mixed bytes and text; inspected
  git_result's bytes contract, compared bytes, and reran the regression. Recovery
  now restores the file without a spurious empty commit. Strict ProgramRun
  schema also explicitly declares its type discriminator. Ruff passed.
- Slice 2: real disposable Project environment passed CLI start/list, checked
  action completion, resume/show/recover and stale-token rejection. Source was
  unavailable in the caller environment and loaded through the existing harness.
  Contextual status opened a drift action and closed it only on restoration;
  ordinary status and a different run's token preserved it. Invalid import paths
  and non-object JSON inputs were rejected. Installed CLI was refreshed.
- Added initial-condition/no-storage, undeclared-availability/no-storage and
  concurrent-token regression tests. Two new fixture subclasses initially
  omitted their required class-local identities; corrected the fixtures before
  rerunning. Full verification and documentation closure remain below.
- Slice 2 verification: 126 broader tests passed, with the two newly added
  fixture-identity failures corrected and all 12 core tests then passing. The
  final real-harness suite passed both tests, including incomplete-check
  preservation. Ruff over src/tests/tooling passed. Surface Breadcrumb audits
  passed after separating provisional references into the required individual
  markers. A real Project program listing was checked without starting a run.
