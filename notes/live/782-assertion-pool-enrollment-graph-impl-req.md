# 782 — Assertion Pool enrollment graph

Status: Completed

## Impl.Abstract

Replace selector-owned Assertion Pools with explicitly enrolled populations.
Assertion classes continue to own their supported Scoring Methods and Task
construction; Assertion instances may enroll in several named Pools. Pools may
validate an enrollment, but do not discover participants.

Retain every enrollment as its own typed scoring Record so Pool membership,
Tasks, Runs, Results, and Scores form one navigable provenance graph. A Ranking
Task pins the exact enrollment editions used. Score computations remain
independent of Pools and may select Results from several Pools.

This request migrates the temporary scoring proof-of-concept schema directly;
no compatibility with its unpopulated default repository is required.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Assertion.Scoring.And.Continuity.Controls` — `e22e51cc-bf92-4369-9b2c-36a6c990ffd2`
- Collection: `782.Impl.Req` — `a5401ff5-b12a-4333-b4d3-81078c332bbd`
- Draft: `03faf906-2a65-4d37-ab0c-f201bbaa366f`
- Authorization Gate: `9c520a99-9aca-4ea2-9831-79e1ab08a462`

## Execution.Plan

1. Redefine `Assertion.Pool` as a named population and add an
   `Assertion.Pool.Enrollment` Record referencing one exact Pool edition and
   one Assertion instance. Check duplicate enrollment and class-owned method
   compatibility.
2. Make Pool Task construction read explicit active enrollments, resolve each
   Assertion through its class, and retain exact Enrollment references as Task
   provenance. Keep Runner semantics-free.
3. Make score selection accept Results from multiple Pools and expose
   assertion-centric forward and reverse graph navigation without authoritative
   backlink duplication.
4. Reshape the compact CLI around Pool creation, enrollment, Pool Task
   production, independent score computation, and graph tracing. Update docs
   and public exports.
5. Run focused scoring and architecture tests, reinstall the editable CLI, run
   the full maintained suite, smoke-test the retained graph, reconcile the
   Draft, and apply it once.

Risks: treating admission checks as participant discovery; storing mutable
Pool membership without exact enrollment provenance; duplicating graph
backlinks; or letting the Pool replace Assertion-class scoring semantics.

Deviation triggers: Assertion references cannot be resolved independently from
their original CLI arguments; exact enrollment editions cannot be recovered;
or multi-Pool score selection requires copied ancestry rather than references.

Acceptance signals:

- An Assertion instance enrolls explicitly and may belong to several Pools.
- A Pool cannot silently discover or score unenrolled Assertions.
- Assertion classes own the methods that admit and present their instances.
- Tasks pin exact Enrollment editions and trace through them to Pool and
  Assertion references.
- One named score can consume Results from several Pools.
- An Assertion reference can discover its enrollments, Results, and Scores.
- Focused tests, Ruff, architecture checks, and the full maintained suite pass.

## Impl.Log

- Autonomous alignment selected by the explicit `--AUTO` invocation.
- Grounded through Chatlas session `01a05752-fa8d-7c62-abb2-5ff20c8260da`
  (`91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`)
  and the Tarav Model's `Assertion.Scoring.And.Continuity.Controls` Block.
- Existing request 781 product changes were committed at the User's explicit
  `commit all` instruction before this request began product mutation.
- Workflow checkpoint: `cc9582c`.
- `Assertion.Pool` is now a named population organized around one class-owned
  Scoring Method. `Assertion.Pool.Enrollment` retains each explicit
  many-to-many membership and its exact Pool/Assertion references.
- Pool Task construction reads only retained enrollments. Every Task candidate
  references its exact Enrollment edition; the Assertion class resolves and
  presents the exact asserted Line edition.
- `tarav scoring pool create|enroll|show|run` provides the normal workflow.
  Standalone `task`, `render`, `run`, `submit`, `show`, and `assertion` commands
  preserve inspectable debugging and navigation.
- Replaced aggregate `Score.Computation` records with independent
  `Assertion.Score` records. One score computation may consume Results reached
  through several Pools, while each retained Score directly references its
  Assertion, Definition, and contributing Results.
- Graph traversal derives inbound edges by scanning authoritative outgoing
  references. No backlink database or duplicated ancestry was introduced.
- Live installed-CLI smoke repository:
  `/tmp/tarav-scoring-782.ABLtPB/scoring`. It exercised create, multi-enroll,
  Pool Task/Run preview, Result submission, scoring, and assertion-centric
  graph traversal over real Tarav Diagram Lines.
- Verification: 23 focused scoring/architecture tests passed; all touched
  Python files pass Ruff lint and format checks; repository-wide Ruff lint
  passed; the complete maintained suite passed with 1,289 tests. The global
  Ruff format check remains non-clean on 238 pre-existing unrelated files.
- Reinstalled the editable `tarav` CLI and verified `pool run` plus multi-record
  score output through the installed executable.
- Product.Surface generation context has no current code-edition Annotation
  path, so exact code references remain in this live note for later
  reconciliation rather than manufacturing unsupported Diagram data.
- Applied the closed `782.Impl.Req` Draft once. Diagram receipt commit:
  `ef478b421ecc13b5035693fe60f09ab37b2492be`.
- Expected landing POIs remain: the new semantic records are unscored,
  Chatlas-to-Archive grounding is not yet mechanically assessable, and
  Collection-hosted Lines surface Model-staleness opportunities. Existing
  legacy Type/lifecycle POIs were not changed by this request.
