# Assertion workflow graph

## Impl.Abstract

Implement Scoring-owned Assertion primitives and a Lines-owned grounding
Assertion, reusing existing ranking Tasks, Runs, Results, traces and scores.
Do not introduce another evaluator or eagerly rename all graph roles.

## Impl.Req.Diagram

Capture remains unreconciled: current-session Chatlas support, Collection,
Draft, and Product Breadcrumbs have not been resolved for this implementation.
This is coordination, not a substitute for supported Diagram capture.

## Execution.Plan

- [x] Add identified Assertion objects and Line grounding specialization.
- [x] Use objects in ranking adapters; preserve retained reference formats.
- [x] Expose existing scoring records and relationships through Context.
- [x] Verify ownership, import directions, round-trips, and ranking regression.

## Impl.Log

- History checkpoint: 6104b84, preserving the POI implementation.
- Existing ranking records remain concrete graph nodes. No replacement engine,
  additional subworkflows, or mandatory new evaluation base classes.
- Ranking adapters now consume Lines-owned assertion objects. Import adapter
  helpers from scoring.tasks, keeping the public foundation import acyclic.
- Focused first verification: 50 tests passed, including exact-hash reference
  resolution, namespace/edition boundaries, custom assertion subjects, Context,
  dynamic Record loading, and import-order regressions.
- Final validation: 1,327 full-suite tests and 50 focused tests passed. Ruff and
  git diff whitespace checks passed. Editable installed CLI refreshed.
- Product implementation complete; Diagram capture remains unreconciled.
