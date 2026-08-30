# Promote Tarav2 Into Tarav

## Impl.Abstract

- **Status:** Executing
- **Source session:** `01a02f8b-8c36-7123-ba70-1a217b776e28`
- **Objective:** Promote the mature Tarav2 Archive, Diagram, and hosted
  Bloberia implementation into the normal Tarav package and command surface.
- **Boundary:** Preserve the older Index stack as a frozen compatibility
  island while its corpus and live consumers still depend on it.
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
   names and depot defaults. **Pending.**
2. **Normal CLI promotion** — register `tarav archive`, `tarav diagram`, and
   hosted `tarav bloberia` through `TaravRuntime`; remove the `tarav tarav2`
   branch and experimental isolation rule. **Pending.**
3. **Predecessor boundary** — remove Anchory's public command only after
   confirming no maintained consumer requires it; retain IndexLab, Skillware,
   Wayfinder, Index.Model, and their adapters as a compatibility island.
   **Pending.**
4. **Current consumers and guidance** — update maintained imports, tests,
   architecture guidance, and current Tarav skills to the promoted names.
   Historical notes and deprecated snapshots remain unchanged. **Pending.**
5. **Verification** — reinstall the editable CLI, run focused promotion and
   architecture tests, then Ruff and the complete maintained suite. **Pending.**

## Impl.Log

- The execution invocation selected Autonomous alignment.
- Direct-input bootstrap used the ordinary Capture workflow and introduced one
  `Impl.Req.Block`; no reviewed Gate was manufactured.
