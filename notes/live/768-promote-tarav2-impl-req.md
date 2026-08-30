# Promote Tarav2 Into Tarav

## Impl.Abstract

- **Status:** Implemented
- **Source session:** `01a02f8b-8c36-7123-ba70-1a217b776e28`
- **Objective:** Promote the mature Tarav2 Archive, Diagram, and hosted
  Bloberia implementation into the normal Tarav package and command surface.
- **Boundary:** Archive, Diagram, and hosted Bloberia become the maintained
  surfaces; predecessor systems do not remain as compatibility commands.
- **Data rule:** Preserve the existing Archive and Diagram roots and stored
  schemas; this is an implementation and command-surface promotion, not a data
   migration.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index`
- **Model:** `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Impl.Req.Block:** `768.Impl.Req` / `bf6e8bd8-5cf2-42bb-9e19-cce9108572c2`
- **Capture commit:** `5ffd3491abdc91a9b61a080ac3c011da15da4ade`
- **Capture standing:** six records landed; expected unasserted and Archive
  grounding POIs remain nonblocking.

## Execution.Plan

1. **Normal domain ownership** — move Archive and Diagram implementation,
   rendering, and command ownership out of `tarav.tarav2`; move hosted
   Tarav.Bloberia into the existing Bloberia domain. Preserve stored class
   names and depot defaults. **Complete.**
2. **Normal CLI promotion** — register `tarav archive`, `tarav diagram`, and
   hosted `tarav bloberia` through `TaravRuntime`; remove the `tarav tarav2`
   branch and experimental isolation rule. **Complete.**
3. **Predecessor boundary** — remove predecessor public commands and disconnect
   Index-specific adapters from retained consumers. **Complete.**
4. **Current consumers and guidance** — update maintained imports, tests,
   architecture guidance, and current Tarav skills to the promoted names.
   Historical notes and deprecated snapshots remain unchanged. **Complete.**
5. **Verification** — reinstall the editable CLI, run focused promotion and
   architecture tests, then Ruff and the complete maintained suite.
   **Complete:** the post-cleanup maintained suite and Ruff pass.

## Impl.Log

- The execution invocation selected Autonomous alignment.
- Direct-input bootstrap used the ordinary Capture workflow and introduced one
  `Impl.Req.Block`; no reviewed Gate was manufactured.
- `tarav.archive` and `tarav.diagram` now own the promoted implementation and
  domain command adapters.
- `tarav.bloberia` owns only the hosted global registry. Its opaque JSON storage
  is private infrastructure; there is no second Bloberia CLI or public API.
- The `tarav tarav2` and `tarav anchory` public command branches are removed.
- IndexLab, Mission, Canvas, and the generic Bloberia CLI are absent from the
  maintained runtime. Index-specific Skillware and Wayfinder adapters were
  removed rather than retained behind compatibility aliases.
- Current Tarav package and Hugentics skills use the promoted command surface.
- Editable installation, focused promotion tests, architecture tests, Ruff,
  and the full maintained suite pass.
- Slice-close capture found no additional qualifying User-Touched requirements.
  The Block renders with five expected `line-unreviewed` POIs because this was
  an automatic capture and no Verbatim.Gates were manufactured.
- Exact Product.Surface/Production.Context Annotations are not yet represented
  by current Diagram mechanics; the verified files and checks remain recorded
  here for later reconciliation.
