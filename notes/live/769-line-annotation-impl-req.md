# Line.Annotation Vertical Slice

## Impl.Abstract

- **Status:** Implemented
- **Source session:** `01a05752-fa8d-7c62-abb2-5ff20c8260da`
- **Objective:** Implement the first `Line.Annotation` vertical slice in
  Tarav.Diagram.
- **Boundary:** Introduce only `Line.Annotation`; do not add specialized
  Annotation types.
- **Semantic shape:** A `Line.Annotation` is a free-standing `Index.Line` whose
  context is an explicit `Argument.Set` rather than a containing Block.
- **Edition data:** Retain an `Argument.Set`, a natural-language claim, and
  optional `Support.Set`, producer, Gates, and Assertions.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index` /
  `1c99092c-ba46-4006-adc3-9ada50c00abd`
- **Model:** `Tarav` / `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Impl.Req.Block:** `769.Impl.Req` /
  `f41a486f-d5d0-43a4-9cb5-4651e9297f92`
- **Block edition:** `d5d9e723-1caa-42ce-a8fe-daa528f626ee`
- **Capture commit:** `132c73d1d1b69ad6d8eb08d6c157705b39b3319c`
- **Capture standing:** four automatic Lines landed; expected unreviewed,
  unasserted, and Archive-grounding POIs remain nonblocking.

## Execution.Plan

1. **Contract and persistence** — define the minimal `Line.Annotation` record,
   edition validation, object references, and capture persistence.
   **Complete.**
2. **Reading surfaces** — make `Line.Annotation` renderable and discoverable
   through the maintained Diagram commands. **Complete.**
3. **Verification and guidance** — cover the canonical two-Block example,
   update current package/workflow documentation, and run focused plus
   maintained validation. **Complete.**

## Impl.Log

- Direct-input bootstrap used the ordinary automatic Capture workflow; no
  reviewed Gate was manufactured.
- The bootstrap capture also serves as the first slice-open capture because it
  records the governing implementation constraints immediately before work.
- Product changes after the required execution checkpoint remain uncommitted.
- Required execution checkpoints: `tarav-py@3c56149` and
  `tarav-md@6531013`.
- `Line.Annotation` now retains one stable Annotation UUID and ordered claim
  editions. Each edition has an explicit typed `Argument.Set`, natural-language
  text, and optional producer, support, Gates, Assertions, and score vector.
- Existing one-shot Annotation types remain unchanged; no second semantic
  Annotation.Type was introduced.
- Argument discovery is available through the Python API and
  `tarav diagram annotation list --argument <uuid>`. Model and Block reading
  surfaces expose related Line.Annotations without projecting them as Block
  Lines.
- `Kernel.Writing.Line.Annotation` renders the current claim edition and exact
  navigable arguments; `Diagram.Debug.Annotation` retains the complete raw
  history.
- The canonical test preserves the Block Line “Block Y is superseded by Block
  X” while independently retaining and discovering a `Line.Annotation` from
  both Blocks.
- Focused Diagram validation passes (`67 passed`); Ruff and the complete
  maintained suite pass (`1507 passed`). The editable CLI was reinstalled and
  its Annotation-list surface smoke-tested.
- Slice-close capture found no additional qualifying User-Touched requirement
  beyond the bootstrap Lines. Exact Product.Surface/Production.Context
  Annotations remain unavailable in the current Diagram vocabulary, so the
  verified surface and checks are retained here for later reconciliation.
