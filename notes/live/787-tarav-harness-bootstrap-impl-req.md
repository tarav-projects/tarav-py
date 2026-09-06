# 787 — Tarav Harness bootstrap from Diagram

Status: Implemented and verified

## Impl.Abstract

Bootstrap a dependency-clean `tarav.harness` boundary from the working Diagram
application. The first slice introduces small semantic base classes and moves
only the trusted top-level Record Type registry/resolution mechanic into the
Harness. Diagram must continue to work throughout, and PaperSON is explicitly
outside this implementation request.

This is a narrow extraction seam, not a claim that the Harness design is
already universal. Further behavior moves only after another application shows
real duplication.

## Impl.Req.Diagram

- Namespace: `User.Touched.Chatlas.Index` —
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- Model: `Tarav` — `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- Blocks:
  - `Harness.Context.And.POI.Services` —
    `76d5c723-b7b7-467a-bb9a-1f7de15a3e25`
  - `Tarav.Record` — `e63beedb-3007-4391-b339-215dea550cff`
- Collection: `787.Impl.Req` —
  `4765c08b-ce55-4910-bd0c-3eaad39a4613`
- Draft: `ef762eab-c861-4680-9516-6b1150b3fb34`
- Authorization Gate: `44412ef6-6643-46b2-8ed8-f4a665b1ad83`

The sole retained Session.View for this long-running chat remains scoped to
`Pdf.Readings`, so grounding used the documented direct Project Model fallback.
That View-scope mismatch is a POI; it is not silently treated as Tarav context.

## Execution.Plan

1. Add a dependency-clean `tarav.harness` package with schema-neutral semantic
   roles and a trusted Type registry. Check: focused Harness tests prove exact
   registration, duplicate rejection, unknown-Type behavior, and resolution
   from a top-level Record `type`.
2. Adapt Diagram's typed Ship, Annotation, Assertion, and object-Type registry
   surfaces to participate in Harness without changing their schemas or public
   behavior. Check: existing Diagram characterization tests stay green.
3. Document and mechanically enforce the one-way dependency boundary. Check:
   architecture tests reject Harness imports from applications and application
   cross-imports through Harness.
4. Run focused tests, architecture tests, the complete suite, Ruff, installed
   CLI smoke checks, and diff inspection. Reconcile this Draft, close the
   Collection, and apply it once.

Deviation triggers: stop and record a deviation if the shared registry needs
Diagram schemas, if Diagram behavior cannot remain compatible, or if the slice
requires PaperSON changes. Ships, scoring, POI instance/storage mechanics, and
other application behavior remain in their current owners.

## Impl.Log

- Alignment.Mode: Autonomous.
- Chatlas session: `01a05752-fa8d-7c62-abb2-5ff20c8260da`
  (`91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1`).
- Design support is rooted in User Turn `b33dffc75c425b84`; the latest explicit
  workflow authorization is User Turn `fc68f68d2dd5a33e`.
- Workflow checkpoint commit: `1723508`.
- Added dependency-clean `tarav.harness` semantic roles and an explicit exact
  Type registry that reads only a Record's top-level `type`.
- Diagram's Ship and Annotation specialization now composes trusted Harness
  registries. Existing Diagram schemas and specialization errors are retained.
- Diagram typed Ships and Annotations, object Assertions, and finding instances
  now subtype the corresponding schema-neutral Harness roles.
- Architecture documentation and tests enforce `tarav.diagram → tarav.harness`
  and prohibit reverse application imports from Harness.
- Focused Harness, Diagram, and architecture verification: `60 passed`; the
  complete Diagram suite: `76 passed`.
- Complete verification: `1294 passed`; Ruff and targeted formatting checks
  pass; the reinstalled editable `tarav` CLI resolves the Project Model; and
  interactive-shell `fcodex_mm -h` works.
- No PaperSON files or imports were changed. Ships, scoring, storage, and POI
  behavior remain in their existing owners; only the semantic participation
  base for Diagram findings was added.
- The Closed `787.Impl.Req` Draft applied once at Diagram commit `c6fdd35`.
  Its first render exposed an incorrect `-04:00` capture-hour transcription;
  the exact five timestamps were repaired at `bc94ffa` through the Diagram
  repository's retained Git history. The Collection now renders `ok` with no
  lifecycle findings.
