# Index Linter POI Class Review - impl-req

## Impl.Abstract

- **scope:** establish the new `POI.Instance` runtime model, then accumulate the accepted semantics, current Tarav-Py evidence, and possible implementation for every POI class emitted by `tarav index linter`
- **status:** design in progress; not ready for execution
- **design session:** `notes/live/743-index-linter-poi-class-review-design-session.md`
- **current implementation:** `src/tarav/index/linter.py`
- **primary tests:** `tests/index/test_linter.py` and `tests/index/test_linter_report.py`
- **current review position:** the `POI.Instance` diagnostic model, `Index.Linter/Anchor.Collision`, and `Index.Linter/Gate.Validation` are aligned; 16 classes pending
- **out of scope until consolidation:** changing classes that have not completed their individual review

## Impl.Index

### POI.Class.Review.Accumulation

- [DC] one cumulative Impl.Req collects the possible implementation for every current `tarav index linter` POI.Class as its definition and Tarav-Py POI.Instance population are reviewed. ^c20260821-66u

### POI.Instance.Diagnostic.Model

- [DC] implementation replaces public `Finding.operands` with a POI.Instance model carrying class, subject, status, structured cause (`code + message`), and structured evidence. ^c20260821-73u

### Index.Linter/Anchor.Collision

- [DF] for one anchor, `Index.Linter/Anchor.Collision` forms the set of unique `Line.Type + Index.Line.Body` projections; a set with more than one member produces one POI.Instance whose evidence maps every projection to all observed locations. ^c20260821-67u

## Execution.Plan

### Review inventory

| Order | POI.Class | Review state | Implementation state |
|---:|---|---|---|
| 1 | `Index.Linter/Anchor.Collision` | aligned | candidate below |
| 2 | `Index.Linter/Gate.Validation` | aligned | candidate below |
| 3 | `Index.Linter/Landing.Unevidenced` | pending | pending |
| 4 | `Index.Linter/Landing.Unhonored` | pending | pending |
| 5 | `Index.Linter/Line.Drift` | pending | pending |
| 6 | `Index.Linter/Line.Unanchored` | pending | pending |
| 7 | `Index.Linter/Line.Unrecorded` | pending | pending |
| 8 | `Index.Linter/Line.Untyped` | pending | pending |
| 9 | `Index.Linter/Materialization.Standing` | pending | pending |
| 10 | `Index.Linter/Record.Unplaced` | pending | pending |
| 11 | `Index.Linter/Record.Untyped` | pending | pending |
| 12 | `Index.Linter/Review.EvidenceLost` | pending | pending |
| 13 | `Index.Linter/Review.SupportUnseen` | pending | pending |
| 14 | `Index.Linter/Scope.KindMismatch` | pending | pending |
| 15 | `Index.Linter/Scope.Unresolved` | pending | pending |
| 16 | `Index.Linter/Support.Unreachable` | pending | pending |
| 17 | `Index.Linter/Support.Unresolved` | pending | pending |
| 18 | `Index.Linter/Trace.Forked` | pending | pending |

### Foundation slice — `POI.Instance` diagnostic model

- **dependency:** execute after all class reviews are consolidated but before every class-specific slice; each migrated check should target the final model once.
- **candidate runtime model:** `POI.Instance` carries `class`, `subject`, `status`, `cause`, and `evidence`; `cause` carries a stable machine-queryable `code` plus a diagnostic `message`, while `evidence` carries arbitrary JSON-serializable values and references.
- **public vocabulary:** remove `operands` from the public model and render structured `evidence` directly.
- **identity:** cause code, message, evidence, and status do not silently redefine instance identity; identity remains based on the stable affected relationship chosen by each class.
- **single run model:** checks produce the model once; text and JSON renderers consume the same object without reconstructing causes or evidence.
- **messages:** checks author immediate mechanical diagnostics at the emission site; messages explain what happened but are neither identity nor authoritative class semantics.
- **evidence:** preserve enough structured material for an agent to reproduce the computation and verify the message independently.
- **migration:** replace every `Finding(..., operands=...)` emission and every renderer/test expectation in one bounded model migration; do not retain a compatibility alias for `operands`.
- **RED behavior:** JSON exposes structured `cause.code`, `cause.message`, and `evidence`, including nested arrays and objects.
- **RED behavior:** text rendering makes the message visible while keeping class, subject, status, and instance identity unambiguous.
- **RED behavior:** changing diagnostic wording or evidence does not create a different POI identity.
- **checks:** focused linter model/report/renderer tests, every check constructor test, CLI text and JSON E2E coverage, Ruff, then the proportional Index suite selected during consolidation.
- **acceptance:** every emitted POI instance conforms to the new model and no public `operands` field remains.
- **status:** aligned candidate; execution remains deferred until all POI classes are reviewed.

### Slice 1 — `Index.Linter/Anchor.Collision`

- **current evidence:** the 2026-08-21 Tarav-Py run reports 80 pairwise findings but only 27 distinct anchor subjects; `_check_anchor_collision()` retains the first occurrence and emits against each later disagreement.
- **candidate implementation:** collect all labelled surface occurrences by anchor, group them by the unique `(Line.Type, Index.Line.Body)` projection, and emit nothing for a one-member projection set or exactly one finding for a larger set.
- **instance subject:** the anchor.
- **instance evidence:** a deterministic structured collection of unique projections, each carrying its complete deterministic location list.
- **instance location:** do not select one conflicting surface as the instance target; individual surfaces belong to evidence because the defective state belongs to the anchor-wide set.
- **annotation change:** preserve the existing class block but state explicitly that projection membership is deduplicated and that one colliding anchor produces one instance.
- **RED behavior:** two different projections, with either projection repeated on several surfaces, produce exactly one finding.
- **RED behavior:** the finding evidence contains each unique projection once and retains every observed location.
- **existing behavior:** repeated occurrences of one projection produce no finding; differing line types remain distinct projections.
- **checks:** focused `tests/index/test_linter.py`, structured-evidence coverage in `tests/index/test_linter_report.py`, Ruff on touched Python, then `tarav index linter --project . --check anchor-collision --limit 0`.
- **acceptance:** the current corpus reports one `Anchor.Collision` instance per colliding anchor, with no loss of projection or location evidence.
- **status:** candidate; execute only after the accumulated class review is consolidated.

### Slice 2 — `Index.Linter/Gate.Validation`

- **current evidence:** Tarav-Py reports 1,644 review-gate instances: 1,630 missing legacy user-message coordinates and 14 resolved proposals that do not contain the gated line.
- **candidate class:** replace `Index.Linter/Gate.Evidence.Invalid` and `Index.Linter/Gate.Evidence.Unavailable` with one `Index.Linter/Gate.Validation` class whose instance status distinguishes failed from blocked.
- **candidate causes:** stable codes distinguish unavailable session, missing user message, user message without touch, missing user token, missing proposal message, missing proposal token, and proposal line mismatch; each carries an immediate message.
- **status boundary:** an unavailable archive, session, or required message is blocked; a resolved value that falsifies a mechanical gate assertion is failed.
- **evidence:** carry the gate reference, record and relationship identity, expected line or token where applicable, and the resolved references needed to reproduce the validation.
- **subject:** one instance represents one particular gate relationship rather than collapsing every gate on a record; settle the canonical gate-subject reference during final consolidation.
- **annotation change:** replace the bare old declarations with one reviewed SKW class block describing the validation family, status boundary, and cause/evidence contract.
- **RED behavior:** a missing referenced message emits blocked `Gate.Validation` with its missing-message cause.
- **RED behavior:** a resolved proposal missing the line emits failed `Gate.Validation` with its line-mismatch cause.
- **RED behavior:** independent invalid gates on one record remain independently addressable instances.
- **acceptance:** the current corpus separates the 1,630 unavailable legacy references from the 14 mechanically contradicted gates without losing their exact causes.
- **status:** aligned candidate; execute only after the accumulated class review is consolidated.

### Consolidation and execution

After all 18 reviews, reconcile cross-class overlaps, order the accepted vertical slices, name the proportional final suite, and change `Impl.Abstract` to execution-ready only when no class decision remains hidden in a pending row.

## Impl.Log

- 2026-08-21: created one cumulative implementation request instead of implementing `Anchor.Collision` immediately.
- 2026-08-21: promoted the new `POI.Instance` diagnostic shape from an open `Finding.operands` question into the cross-cutting foundation slice.
