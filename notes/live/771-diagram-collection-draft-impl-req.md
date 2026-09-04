# Diagram Collection and Draft Vertical Slice

## Impl.Abstract

- **Status:** Ready for execution
- **Source session:** `01a05752-fa8d-7c62-abb2-5ff20c8260da`
- **Objective:** Implement the approved end-to-end path from recursive
  `Diagram.Collection` hosting through durable `Diagram.Draft`, bounded
  `Impl.Req.Collection` lifecycle, `Capture.Authorization.Gate`, and
  collection-aware loading and staleness POIs.
- **Boundary:** Extend the current typed Ship database and capture machinery;
  preserve existing Model, Block, Line, View, Annotation, and receipt behavior.
- **Out of scope:** General Assertion.Scoring and Chatlas-to-Archive grounding;
  those remain independent existing POIs.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` /
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Bootstrap Impl.Req.Block:** `771.Impl.Req` /
  `8cbdf069-55cd-443c-bf00-4fae11d89489`
- **Block edition:** `a4ebf621-08f4-4efe-b201-f0bccbdfd9ea`
- **Capture commit:** `049980da9067baa6f4c4bbaa7cb76dc5cf4d9e38`
- **Capture standing:** one supported automatic Decision Line; expected
  unasserted and Archive-grounding POIs are nonblocking.

The legacy Block is the presently executable Develop handoff. Execution will
introduce `Impl.Req.Collection` as its replacement and use the resulting
mechanics during the final capture audit.

## Execution.Plan

### Slice 1 — Collection hosting and projection

- Add recursive typed Collection Ships and edition-level hosting independent
  of a Line's semantic Block attachment.
- Preserve old records by deriving Model hosting when an edition has no host.
- Observable: a Collection-hosted Line is absent from the primary Model view
  and discoverable through explicit expansion/query.
- Check: focused schema, projection, recursion, and query tests.
- **Status:** Not started.

### Slice 2 — Durable Diagram.Draft

- Introduce a persistent Draft repository and public create/show/check/apply
  workflow over the existing internal Manifest compiler.
- Applying a settled Draft records its Capture.Receipt without making the
  Draft semantic authority.
- Observable: a Draft survives reload, checks as a Model overlay, lands once,
  and becomes applied.
- Check: domain and CLI lifecycle tests.
- **Status:** Not started.

### Slice 3 — Authorization and Impl.Req lifecycle

- Add `Capture.Authorization.Gate`, edition references, and receipt coverage.
- Add Open/Closed `Impl.Req.Collection` state plus reopening-window and
  closed-write findings while preserving the constitutional writable core.
- Observable: authorization evidence is assessable; invalid lifecycle actions
  surface scoped POIs rather than hiding or corrupting data.
- Check: Gate evaluation, receipt, closure, and reopening tests.
- **Status:** Not started.

### Slice 4 — Loading and staleness

- Make primary Model loading exclude Collection-hosted editions by default;
  expose collection expansion and attached-Line queries.
- Produce `Model.Staleness.POI` when a Line has a newer Collection-hosted
  edition than its primary Model edition.
- Observable: default and expanded projections differ predictably and expose
  enough identity to investigate staleness.
- Check: projection, renderer/query, and POI tests.
- **Status:** Not started.

### Slice 5 — Workflow and documentation alignment

- Replace new-write `Impl.Req.Block` and public Capture.Manifest language in
  current package, Hugentics, architecture, and CLI guidance.
- Preserve explicit historical readability without retaining the old workflow
  as current behavior.
- Observable: the documented Develop workflow grounds first, works in a
  durable Draft, lands at completion, and targets `Impl.Req.Collection`.
- Check: architecture/docs tests, Ruff, full maintained suite, and a live
  Draft/Collection smoke test.
- **Status:** Not started.

## Risks and deviation triggers

- The approved Closed-write wording conflicts with the Constitution if read as
  a low-level write prohibition. Normal workflow checks will surface and avoid
  such writes, while the Diagram core remains nonblocking and writable.
- Existing Namespaces explicitly allowlist Ship types; introducing Collection
  requires a current-data migration or an equally explicit policy update.
- If Collection hosting requires rewriting historical Line identities, stop;
  the intended design adds edition-level host data without rebinding UUIDs.
- If Draft persistence starts duplicating semantic authority, keep only the
  proposed delta and receipt in the WIP repository.

## Acceptance signals

- Focused and complete Diagram tests pass.
- Ruff and architecture checks pass.
- The installed editable CLI exposes the new Draft and Collection workflows.
- A live Impl.Req Collection can be opened, populated through a Draft, queried,
  closed, and inspected for authorization and staleness evidence.

## Impl.Log

- The current design is grounded in reviewed Blocks `Diagram.Collection`,
  `Diagram.Draft`, `Impl.Req.Collection`, `Impl.Req.Lifecycle`, and
  `Gates.And.Deferred.Review`.
- Edition-level hosting is selected because organizational location may change
  across one Line lineage while its semantic Block attachment remains stable.
- The execution order follows the User-selected vertical slice.
