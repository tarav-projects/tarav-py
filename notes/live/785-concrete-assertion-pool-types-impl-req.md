# 785 — Concrete Assertion Pool Types

Status: Ready for execution

## Impl.Abstract

Reimplement the current Assertion Pool boundary so each Pool Record declares
its concrete Pool Type directly. Remove the redundant `Assertion.Pool` plus
`pool_class` discriminator representation while preserving explicit
enrollments, Pool-owned storage, assertion-owned candidate adaptation,
Pool-owned Task assembly, frozen Runs, Results, and live scoring traces.

The first vertical slice remains intentionally specific to
`Index.Line.Grounding.Ranking.Pool`, but repository and dispatch mechanics must
recognize registered concrete Pool Types without grounding-specific type tests.
There is no retained production Pool data to migrate.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Assertion.Scoring.And.Continuity.Controls` — `e22e51cc-bf92-4369-9b2c-36a6c990ffd2`
- Collection: `785.Impl.Req` — `7e778021-8cb0-4fa4-b57d-e7ade52d6594`
- Draft: `33980e87-f7e9-45cf-9e67-52b40b581b19`
- Authorization Gate: `8f7d4ed8-0093-42b1-b396-51f6cb8b9933`

## Execution.Plan

1. Make the concrete Pool Type the top-level Record `type`; let its registered
   class create and validate Pool instances. Check: focused model and
   repository tests cover concrete references and Pool-owned paths.
2. Replace string/`isinstance` dispatch leaks with the general ownership path:
   an Assertion class produces candidate material and the registered Pool
   class assembles the comparative Task. Check: an incompatible enrollment is
   rejected through contracts rather than concrete Python type checks.
3. Update CLI output, repository traversal, exports, architecture text, and
   tests; run a two-Line end-to-end manual-Runner simulation. Check: focused
   tests, architecture tests, full suite, Ruff, installed CLI, and shell helper
   smoke checks pass.

Risks and deviation triggers: stop and record a deviation if concrete Pool
typing requires a second retained discriminator, if generic repository
discovery cannot remain registry-driven, or if exact historical references
become weaker. Pre-existing unrelated View-scope and Diagram POIs do not block
the product work.

## Impl.Log

- Alignment.Mode: Autonomous.
- Chatlas session: `01a05752-fa8d-7c62-abb2-5ff20c8260da`
  (`91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`).
- The sole session View currently targets `Pdf.Readings`; Tarav Model
  contextualization therefore used the Project Model directly and retains the
  mismatch as a View-scope POI.
- The previous scoring request `784` is Closed; this request owns the concrete
  Pool Type refactor.

