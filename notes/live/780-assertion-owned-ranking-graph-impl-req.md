# 780 — Assertion-owned ranking and provenance graph

Status: Completed

## Impl.Abstract

Reimplement the first Assertion.Scoring proof of concept so semantic
compatibility and Ranking.Task production belong to Assertion Types, while an
Assertion.Pool is only a typed selector over Assertion instances. Normalize
the retained experiment provenance into a navigable Tarav.Record graph:
Result → Run → Task → Assertions → Diagram/Evidence. Each Record references
its direct dependencies instead of copying transitive ancestry.

The exact experimental stimulus remains retained where it was observed. A Run
therefore keeps the exact rendered prompt, candidate-label mapping, runner
configuration, and prompt hash even though its semantic ancestry is reached
through references. Ranking.Task.Runner remains semantics-free.

No compatibility is required with the temporary scoring schema checkpointed
by this workflow. No production scoring repository has been initialized.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Assertion.Scoring.And.Continuity.Controls` — `e22e51cc-bf92-4369-9b2c-36a6c990ffd2`
- View: `73303608-fe4f-4e8a-a9d5-0917298eea86`
- Collection: `780.Impl.Req` — `d031c530-0e94-4c14-b11e-be3caba6a85c`
- Draft: `d09e365b-64bb-405d-b3db-e94eb5bd1c48`
- Authorization Gate: `2102455f-7cea-4e00-add8-5e8643525b14`

## Execution.Plan

1. Replace Pool-owned Task compatibility with typed Assertion selectors and an
   Assertion-Type registry that owns supported Task producers and candidate
   presentation.
2. Replace duplicated `*_id` ancestry with typed direct references between
   Pool, Task, Run, Result, Score Definition, and Score Computation Records.
3. Preserve exact experiment-specific stimulus in the Task/Run boundary and
   keep the Runner ignorant of Assertion semantics.
4. Add graph expansion to the existing debug surface so a Result or Score can
   be followed through its direct dependencies to Assertion references.
5. Update docs and tests, reinstall the editable CLI, run focused and full
   verification, then close and apply the Diagram Draft once.

Risks: confusing Pool membership with comparison compatibility; treating live
Diagram state as the historical stimulus; hiding duplicated ancestry in helper
payloads; or introducing a general Reference framework inside this focused
slice.

Deviation triggers: exact Diagram Line editions cannot provide stable
Assertion references; graph traversal requires a second authority; or a
semantics-free Runner cannot reproduce the retained Task stimulus.

Acceptance signals:

- Pools answer membership through registered selector Types.
- Assertion Types own their supported Ranking.Task producers.
- Results contain only a direct Run reference; Runs contain only a direct Task
  reference for semantic ancestry.
- `tarav scoring show <record> --trace` exposes the retained dependency graph.
- Exact rendered stimuli remain reproducible and inspectable.
- Focused tests, Ruff, architecture checks, and the full maintained suite pass.

## Impl.Log

- Autonomous alignment selected by the explicit `--AUTO` invocation.
- Grounded through the current Chatlas Normal Model and the Tarav Model's
  `Assertion.Scoring.And.Continuity.Controls` Block.
- The Project Diagram.View creation outlived its initial command yield. A query
  issued while it was still materializing temporarily found no `view.json`;
  after completion the View resolved and listed normally. No View defect was
  reproduced.
- Workflow checkpoint: `8f720ee`.
- Replaced `Assertion.Ranking.Pool` with `Assertion.Pool` containing a typed
  `Assertion.Type.Selector`. Pool membership is checked independently of Task
  compatibility.
- Added an Assertion Ranking registry. `Index.Line.Grounding.Assertion` now
  owns its supported Task producer and the Diagram-to-candidate presentation;
  the generic Agent Runner only executes the rendered Task.
- Scoring Records now carry typed, content-addressed direct references. Exact
  older editions resolve through the scoring repository's non-rewritten Git
  history, including when the Record's current edition has changed.
- Removed transitive Pool/Task IDs from Runs and Results, the resolved-candidate
  duplicate from Results, the Result back-reference from completed Runs, and
  the Definition-name duplicate from Score computations. Score aggregation
  resolves opaque result labels through each exact referenced Run.
- Added `tarav scoring show <record> --trace`, which walks scoring Record
  dependencies and exposes Diagram Assertion references as external leaves.
- Live smoke experiment over two real Tarav Diagram Lines created a Pool, Task,
  preview Run, Result, Score computation, and complete trace successfully in a
  temporary Git-backed repository.
- Verification: 22 focused scoring/architecture tests passed; Ruff and format
  checks passed; the complete maintained suite passed with 1,279 tests; the
  editable `tarav` CLI was reinstalled and its live scoring workflow passed.
- Applied the closed `780.Impl.Req` Draft once. Diagram receipt commit:
  `ce67863d1ae1f48dbca70fa93541cfc3d7d48f91`.
