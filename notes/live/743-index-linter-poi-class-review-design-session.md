# Index Linter POI Class Review - design-session

## Session.Abstract

This session revisits every POI class currently implemented by `tarav index
linter` together with its current POI instances on Tarav-Py. The active class is
the proposed `Index.Linter/Gate.Validation`, replacing the unclear
`Index.Linter/Gate.Evidence.Invalid` presentation. Candidate implementation accumulates in
`notes/live/744-index-linter-poi-class-review-impl-req.md` until the complete
class review is ready for execution.

## Design.Index

### POI.Class.Review.Workflow

- [DC] this session reviews every implemented `tarav index linter` POI.Class together with its current Tarav-Py POI.Instance population, one class at a time. ^c20260821-65u

### POI.Instance.Diagnostic.Model

- [DC] one POI.Instance emission carries its stable class, affected subject, and status together with a structured cause and structured evidence. ^c20260821-68u
- [DF] a POI.Instance cause contains a stable mechanical code and an immediate diagnostic message explaining what happened. ^c20260821-69u
- [DF] POI.Instance evidence contains the concrete values and references needed to reproduce the computation; `operands` is not a separate public concept. ^c20260821-70u
- [CT] the exception shape is a data-model analogy only; a linter accumulates POI instances instead of interrupting control flow. ^c20260821-71u

### Index.Linter/Gate.Validation

- [DC] `Index.Linter/Gate.Validation` is the POI.Class for gate validation; each instance cause identifies the exact failed or unavailable assertion while status distinguishes failed from blocked. ^c20260821-72u

## Session.Notes

### Index.Linter/Anchor.Collision

- Current run: 80 failed instances across 27 distinct anchors.
- The implementation emits one instance for each later conflicting occurrence,
  so the instance count is not the bad-anchor count.
- First inspected example: `^c20260724-31u` appears on several distinct
  Bloberia and umbrella-CLI projections.
- Accepted semantics: form the deduplicated set of unique
  `Line.Type + Index.Line.Body` projections for one anchor; more than one unique
  projection produces one anchor-wide POI instance.
- Candidate implementation is recorded in Impl.Req 744.
- Decision: aligned.

### Gate.Validation — review notes

- Current run: 1,644 instances, all attached to review gates.
- 1,239 reference missing legacy ordinal user messages and 391 reference
  missing legacy UUID user messages; these 1,630 instances should be blocked
  rather than failed because required evidence is unavailable.
- The remaining 14 resolve their evidence but reference proposals that do not
  contain the gated line; these are genuine failed validations.
- The class-level name is `Gate.Validation`; the instance cause says which
  assertion failed or was unavailable.
- Decision: aligned; implementation consequences remain to be added to Impl.Req
  744 outside this Design.Session capture transaction.

## Session.Log

- 2026-08-21: opened the class-by-class review and began with
  `Index.Linter/Anchor.Collision`.
- 2026-08-21: aligned `Anchor.Collision` and opened cumulative Impl.Req 744.
- 2026-08-21: aligned the general POI diagnostic model and applied it to
  `Gate.Validation`.
