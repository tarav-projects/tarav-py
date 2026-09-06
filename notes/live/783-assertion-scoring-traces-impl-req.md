# 783 — Assertion scoring traces

Status: In Progress

## Impl.Abstract

Reshape the Assertion Scoring proof of concept around Pool-owned storage and
live score computation. A Pool is the default comparability boundary and owns
its Enrollments, Tasks, Runs, and Results. Ranking Results remain retained
evaluation evidence; scores are cheap interpretations computed live.

Replace `Score.Definition` and standalone `Assertion.Score` records with one
small `Assertion.Scoring.Trace` directory per Assertion instance. Its stable
JSON metadata identifies the Assertion and its JSONL stream records explicit
scoring executions with Pool scope, Results commit, code provenance, values,
and statistics. Passive score reads remain read-only. Renderers may present
current standing or historical trends without performing Agent interpretation.

No default scoring repository exists yet, so the proof-of-concept layout can
be replaced directly without a compatibility migration.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Assertion.Scoring.And.Continuity.Controls` — `e22e51cc-bf92-4369-9b2c-36a6c990ffd2`
- Collection: `783.Impl.Req` — `037a6c8b-12d9-47ea-bd5f-816c2fd6e540`
- Draft: `9d3bee78-8c0f-4bea-a2bd-c54657f214d3`
- Authorization Gate: `cab0070e-b868-40bd-a675-d41ece2f75d0`

## Execution.Plan

1. Restructure the scoring repository so each Pool directory owns its Pool
   record, Enrollments, Tasks, Runs, and Results.
2. Remove `Score.Definition` and standalone `Assertion.Score` records; compute
   scores live through code-owned, versioned score methods.
3. Add one Assertion Scoring Trace directory per Assertion instance, with
   stable JSON metadata and an append-only typed JSONL scoring-event stream.
4. Record compact Pool scope, Results commit, code provenance, value, and
   statistics for explicit scoring executions while keeping passive reads
   read-only.
5. Add current/history renderers, update commands and documentation, run the
   focused and complete suites, then initialize the real scoring repository.

Risks: treating cached score events as evaluation evidence; silently writing
during contextual reads; losing exact Pool boundaries when moving records;
or presenting scores across code/scope changes as one uninterrupted series.

Acceptance signals:

- A Pool is independently inspectable as one directory.
- Ranking records resolve and traverse correctly under Pool-owned storage.
- Current scores are computed without creating records.
- An explicit recording action appends one typed scoring event to the correct
  Assertion trace.
- Trace history exposes code and Results evolution to renderers.
- Focused tests, Ruff, architecture checks, installed CLI smoke tests, and the
  full maintained suite pass.

## Impl.Log

- Interactive Execute workflow bootstrapped from the explicit User request.
- Chatlas session: `01a05752-fa8d-7c62-abb2-5ff20c8260da`
  (`91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`).
- The previous scoring Impl.Req 782 is Closed; this request owns the subsequent
  storage and trace redesign.

