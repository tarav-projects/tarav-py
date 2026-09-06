# 784 — Frozen unresolved Ranking Runs

Status: In Progress

## Impl.Abstract

Refine Assertion Ranking around explicit Assertion and Pool ownership, then
make manual evaluation a two-step protocol. Task preparation registers one
compact, frozen `Ranking.Run` and prints its full blinded prompt. Any Agent may
act as an unknown Runner and submit exactly one structured Result against that
Run UUID.

The Run avoids duplicating data recoverable from exact references, registered
Types, and Git provenance. It retains only the information required to freeze
the experiment and validate its later Result.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` — `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Block: `Assertion.Scoring.And.Continuity.Controls` — `e22e51cc-bf92-4369-9b2c-36a6c990ffd2`
- Collection: `784.Impl.Req` — `24af26f3-bb85-44a8-b2ba-7b7018c8b502`
- Draft: `95f53ce3-b89c-4df4-9c59-58346efc24b8`
- Authorization Gate: `71cd0711-cef7-41df-8b6e-e011533f5e1d`

## Execution.Plan

1. Separate Assertion-owned candidate adaptation from Pool-owned comparative
   Task assembly in the public code model.
2. Make `Ranking.Run` a compact frozen preparation record: exact Task
   reference, opaque label map, renderer/code provenance, prompt hash, and
   known or unknown Runner provenance without retained prompt duplication.
3. Make the manual Task CLI create the Task and unresolved Run together, print
   the full prompt, and embed submission commands targeting the Run UUID.
4. Make Result submission accept only a registered eligible Run and preserve
   the frozen Run while recording the Result separately.
5. Update documentation and run focused, architecture, lint, installed-CLI,
   and full-suite verification.

## Impl.Log

- Direct implementation input was bootstrapped into a dedicated Impl.Req at
  the User's request.
- Chatlas session: `01a05752-fa8d-7c62-abb2-5ff20c8260da`
  (`91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`).

