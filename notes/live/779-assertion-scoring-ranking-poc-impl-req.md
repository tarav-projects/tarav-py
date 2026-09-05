# 779 — Assertion scoring and ranking proof of concept

Status: Ready

## Impl.Abstract

Replace the maintained legacy Tournament surface with the first coherent
`Assertion.Scoring` implementation. The vertical slice stores typed scoring
Records in a global Git-backed repository, models compatible Assertion pools,
creates and renders typed Ranking Tasks, executes them through a separate Agent
Runner, validates structured ranking submissions, retains inspectable Results,
and derives a simple reproducible score computation.

The first Task specialization is `Index.Line.Grounding.Ranking.Task`. It ranks
how well each declared `Support.Set` supports an exact Index Line edition in its
Block context. Task-level and candidate-level material remain distinct. The
common runner understands only the general Ranking Task protocol and structured
submission boundary.

The previous `tarav tournament` implementation is historical evidence rather
than a compatibility surface. Move its source and tests under `_DEPRECATED/`
and remove its public command registration. Reuse ideas only through the new
contracts; do not import legacy Tournament code.

Large prompt or response payloads ultimately belong behind Archive references.
This bounded POC may retain its compact exact rendered prompt in the Run Record;
Archive payload promotion and Diagram score-vector integration remain explicit
follow-up work.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Collection: `779.Impl.Req` — `06bb862c-77b0-4334-81a1-d0329ecefd30`
- Draft: `f8d24a67-5f63-4782-b6c4-2d75829c95d3`
- Authorization Gate: `6174455a-8148-41b7-9e79-5e18c592e89d`

## Execution.Plan

1. Introduce `tarav.scoring` with a Git-backed repository rooted by default at
   `~/Documents/tarav/scoring/`. Retain one typed JSON Record per Pool, Task,
   Run, Result, Score Definition, and Score Computation. Check initialization,
   exact/prefix identity resolution, type validation, and Git history.
2. Implement the general typed `Ranking.Task` protocol plus
   `Index.Line.Grounding.Ranking.Task`. Create tasks from exact Diagram Line
   editions, preserving Block context, rooted support, Assertion identity, and
   separate task/candidate appendices. Check rendering and candidate blinding.
3. Implement the typed Agent Task Runner, exact Run record, randomized opaque
   labels, preview/debug rendering, and structured `submit` command supporting
   ordered tiers and abstention. Check invalid, duplicate, stale, and unknown
   submissions without spawning real providers in the test suite.
4. Implement a named win-rate Score Definition and retained Score Computation
   over selected Ranking Results. Expose compact list/show/render/debug commands
   that preserve navigation from a score through Results and Runs to exact
   Assertion editions and support.
5. Remove `tarav tournament` from the maintained CLI and architecture, move its
   source and focused tests into `_DEPRECATED/tournament/`, reinstall the
   editable CLI, and run focused, Ruff, architecture, and full-suite checks.

Risks: allowing result records to grow unbounded, confusing Task construction
with Runner execution, treating project/model metadata as compatibility,
silently mixing Task versions in a score, or retaining a hidden dependency on
Tournament internals.

Deviation triggers: the current Diagram APIs cannot resolve exact Line
editions and support without importing command adapters; Agent submission
cannot address an open Run safely; or the global repository cannot provide
recoverable Git history without violating existing data-root ownership.

Acceptance signals:

- `tarav scoring` is the sole maintained comparative-evaluation CLI.
- A real Diagram Line set can produce an inspectable typed grounding Task.
- The exact prompt shown by debugging is the prompt handed to the Runner.
- Agent submission is mechanically validated and retained as a typed Result.
- A named score can be recomputed from retained Results with full provenance.
- No maintained code or test imports `tarav.tournament`.

## Impl.Log

- Autonomous alignment selected by the explicit `--AUTO` invocation.
- Current Tournament is treated only as implementation evidence; the redesign
  does not preserve its public schemas or command compatibility.
- Initial storage keeps compact exact prompts in Run Records. Archive promotion
  is deferred until real payload sizes demonstrate the boundary.
- Existing Model and scoring design were grounded through session View
  `1de9cbc1-3848-4170-bdcb-b121b5863a66` and the
  `Assertion.Scoring.And.Continuity.Controls` Block.
- The pre-edit checkpoint also preserves an unrelated concurrent
  `tarav.reading_club` implementation and its runtime/architecture wiring;
  scoring execution does not modify or depend on those surfaces.
