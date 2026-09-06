# 790 — Record Ships and Type Resolution PATH

Status: Ready for execution

## Impl.Abstract

Implement the reviewed follow-up to the Ship-aware Harness Record Types work:
replace path-bearing `ShipOccurrence` discovery with the semantic
`TaravRecordType.ships()` projection, and make Type lookup use the one
Harness-defined `Type.Resolution.PATH`. Diagram is the first consuming
application.

This is deliberately bounded. It does not settle the final serialized Type
value, remove legacy label resolution, rewrite the retained corpus, add a
Record-construction protocol, or begin PaperSON integration. The uncommitted
789 implementation is the direct baseline for this work and must be evolved in
place without discarding any existing changes.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` —
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Blocks:
  - `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
  - `Ship.Identity` — `87654e2d-6ebe-4b1f-8753-6cf5b99fe935`
- Reviewed design source: Diagram commit `f5bf71d`
- Collection: `790.Impl.Req` —
  `0a4f6a8c-f190-48ed-a101-79317ac23903`
- Draft: `b80cf5a9-32f4-449f-9c60-6e426e998611`
- Design authorization gate: `78bfb2d8-98dd-4625-bc3e-e6f692d15dfa`

The retained Session View is scoped to PaperSON rather than Tarav and remains
stale after synchronization. Grounding therefore uses the freshly resolved
Tarav Project Model directly; the View mismatch is retained as a POI.

## Execution.Plan

1. **Harness Ship projection.** Remove `ShipOccurrence` and
   `ship_occurrences()`. Add `TaravRecordType.ships() -> tuple[Ship, ...]`,
   whose default returns the Type Ship. Application classes may inherit or
   extend it with Ships they semantically recognize. The API exposes no
   serialized paths, and generic UUID-shape scanning remains forbidden.
2. **Universal Type resolution.** Define the single non-configurable ordered
   path `(("__tarav__", "type"), ("type",))` in Harness. Select the first
   key path that exists, including when its value is null or empty. Parse and
   resolve only that value; invalid or unregistered values raise without
   falling through. Diagnostics identify the selected path and value.
3. **Diagram adoption.** Replace every Diagram Ship-occurrence override and
   path helper with `ships()` implementations returning concrete Ships. Route
   Diagram Type-reference reads through the Harness Record resolver so Diagram
   does not independently assign semantics to root `type`. Keep existing root
   `type` Records readable and add synthetic coverage for `__tarav__.type`.
4. **Documentation and verification.** Update Harness exports and
   `ARCHITECTURE.md`; replace path-bearing tests with semantic Ship projection
   tests; cover path priority, key existence, malformed shadowing, unknown
   Types, and non-configurability. Run focused tests, the full suite, Ruff, the
   installed CLI smoke test, and live-corpus read/specialization checks.

Acceptance requires no maintained source, export, or test use of
`ShipOccurrence`/`ship_occurrences`; one Harness-owned resolution path; strict
first-present behavior; unchanged retained-corpus readability; and successful
Diagram specialization through both supported locations.

Deviation triggers: stop and record a deviation if execution requires choosing
the final serialized Type representation, rewriting retained Records, adding
configurable resolution paths, introducing Record construction semantics, or
discarding/reconstructing the uncommitted 789 baseline.

## Impl.Log

- Alignment.Mode: Autonomous.
- Chatlas session: `01a07228-313a-7ab3-b6e0-aedcb5216b3c`
  (`33afe59c2f13ac5d4b59e56f7a3761d3d91c1206a1b6287b0872036739b370fd`).
  The explicit design authorization is User Turn `6a5a516d8dab0a1f`.
- Question: turn the reviewed `ships()` and `Type.Resolution.PATH` decisions
  into the next bounded implementation slice.
- Discussion: the current 789 baseline localizes the work: Harness still
  exposes `ShipOccurrence`, Diagram specializes it in a finite set of methods,
  and `RecordTypeReference.from_record()` reads only root `type`.
- Consolidation: the four execution slices above preserve representation
  privacy, semantic ownership by the registered class hierarchy, and the
  deliberately dumb/transparent PATH behavior.
- Autonomous assumptions: base `TaravRecordType.ships()` returns its Type Ship;
  tuple order carries no new domain semantics; resolution errors retain the
  chosen path and value for diagnosis. These follow the reviewed design but
  remain explicit implementation choices.
- Worktree baseline: HEAD `7c18408`; completed 789 product changes remain
  uncommitted. Design made no product edits and created no checkpoint commit.
- The Design Draft remains Open and unapplied. Product implementation requires
  a later execution authorization.
- Draft check: no authorization, support, host, or continuity failures. Local
  findings are three `semantic-record-unasserted` and one
  `archive-grounding-unassessable`; the overlay also reports the pre-existing
  corpus-wide Type, staleness, and closed-Impl.Req findings.

### POIs

- The current Session View targets the PaperSON Model and omits the mentioned
  `Tarav.Record` and `Ship.Identity` Blocks; direct Tarav Model grounding was
  used instead.
- Draft checks may surface the expected unasserted semantic scores,
  unassessable Archive grounding, and pre-existing corpus-wide Type/staleness
  findings. These do not expand this implementation request.
