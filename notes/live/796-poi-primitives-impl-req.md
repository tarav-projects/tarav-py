# Reusable POI primitives

## Impl.Abstract

Autonomous Develop. Implement application-owned POI subclasses, non-throwing
collection, bounded reporting with class source navigation, and recorded
blessings at an application-selected path. Integrate SKW package checks and
store its blessing actions in `.skw/blessings/`. Existing older POI consumers
are outside this bounded slice; no compatibility adapters or silent migration.

## Impl.Req.Diagram

Project Model: b7b78eab-e5c2-4610-9bf5-1b704a106f34.
Namespace: 1c99092c-ba46-4006-adc3-9ada50c00abd.
Semantic Block: 76d5c723-b7b7-467a-bb9a-1f7de15a3e25.
Draft: 5897080d-687e-49af-8b5a-4301832b7b47 (/Users/pereiro/Documents/tarav/diagram/drafts/5897080d-687e-49af-8b5a-4301832b7b47.json).
Collection: c7f10b8e-f92e-4c90-8bcd-7d4dcbc303f2.
Authorization Gate: 1506cc18-4d4f-45cf-8f59-8459985c0d68.

## Execution.Plan

- [x] Core: typed POI base, immutable finding snapshots, collector, class help.
- [x] Blessings: explicit store, append-only acceptance and assessment records;
  test policy refusal, actor provenance, state changes, missing/low scores.
- [x] SKW: owned classes, complete detection and bounded reporting, explicit
  bless/inspect/score CLI operations with named flags; no automatic blessings.
- [x] Verify third-party subclass use, package checks and installed CLI;
  update documentation and complete Draft audit/apply.

## Impl.Log

Current SKW checks emit dictionaries; existing tarav.poi includes separate
Wayfinder-oriented reports and runtime checks. New primitives belong to
tarav.poi and must not import SKW. Stable occurrence identity is separate from
the accepted evidence-state fingerprint. Default blessability is false.
Assessment is an attributed assertion, not a self-written validity flag.
Missing scores remain visible; no semantic scorer is invented in this slice.
Workflow checkpoint: tarav-py e294cc1; tarav-md 98addcb.
Product-context annotation support will be reported separately from code tests.

## Completion

Status: implemented and verified. 64 focused tests and 10 existing POI tests
passed; Ruff and diff checks passed. Installed CLI reports three unchanged
SKW POIs, all unblessed, with bounded pages and class paths.

Draft applied once; Collection closed. Receipt commit: bc9c663fe7471b33e6f69363aa5f0db42720d2d5.
Grounded View: de862688-19eb-4e4d-80f9-e945a4ea8a47.

Capture POIs: inherited block/line types missing, missing assertion scores,
archive-grounding unassessable, model staleness, and lifecycle findings.
Product-context annotations remain unavailable in this slice; exact code
editions are fingerprinted below rather than claiming Diagram provenance.

- `src/tarav/poi/primitives.py` SHA256 `0cc8050d1077dbcbc6f125c9e0e916ca325f50e79d94037db15552aadca3da46`
- `src/tarav/poi/blessings.py` SHA256 `170519eaafe51397c0834698ffd407d203ab4995ae1ac5ddb46c9e60cb5edeac`
- `src/tarav/skw/pois.py` SHA256 `3d3720883f14c4bff7e2a2d2d436cdb4214be6ef564e2110cdda741dfa9a6a88`
- `src/tarav/skw/skills.py` SHA256 `8fbff23434d8ea2c5093dd5d5be440afe42b07c1310a6bcfd80f65e7411a3e2c`

Assumptions: conservative package-wide acceptance fingerprints; generic actor
references are structurally validated, not semantically resolved. Scores are
attributed retained evaluations, not an invented automatic semantic scorer.
No existing POI was blessed. Post-checkpoint changes remain uncommitted.
