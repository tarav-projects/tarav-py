# 797 — Skillware retirement — Impl.Req

- **Status:** complete; product changes remain uncommitted for review.
- **Scope:** retire the obsolete Skillware compiler and the old code-annotation
  and Wayfinder/POI integration. Keep the current SKW document, generation,
  and context-role work under `tarav.skw`.
- **Alignment:** autonomous, bounded to the current retirement; this note does
  not authorize a broader POI redesign.

## Impl.Abstract

The user directed the team to deactivate old paths before reimplementation,
using old Skillware as the first target, then specifically directed removal of
the old code-annotation and Wayfinder/POI integration. Retire and preserve the
disconnected legacy material in Attic; retain the current SKW engine and make
only fresh, currently needed replacements.

## Impl.Req.Diagram

- **Namespace:** `User.Touched.Chatlas.Index`
  (`1c99092c-ba46-4006-adc3-9ada50c00abd`)
- **Model:** `b7b78eab-e5c2-4610-9bf5-1b704a106f34`
- **Collection:** `f3553af7-ff4e-4ec8-8978-3b4de264a541`
  (`797.Impl.Req`, Closed after final reconciliation)
- **Draft:** `1b970b90-02d9-4c99-9400-6de67c91e231`
- **Capture receipt:** Diagram commit `886a33bb25c8049846a385ab56d21a85a6ec109e`
  (base `bc9c663fe7471b33e6f69363aa5f0db42720d2d5`)
- **Capture authorization:** user turn `c0de582f6eac1c69`; exact turn and
  producer references are in the applied Draft.

## Execution.Plan

1. Preserve legacy material in Attic before removal.
2. Move the current SKW document, generation, and context-role implementation
   to `tarav.skw`; disconnect the obsolete Skillware compiler and commands.
3. Retire the old code-annotation and Wayfinder/POI integration without
   retaining a compatibility path.
4. Verify current SKW behavior and the affected runtime boundaries; report
   remaining POIs and capture gaps.

## Evidence

- User turn `cb162edf8eeb4036`: deactivate old paths before reimplementation
  and archive them, naming old Skillware as the first target.
- User turn `c0de582f6eac1c69`: old code-annotation discovery and
  Wayfinder/POI integration “must go”; fresh implementation is preferred.
- Producer turn `af13d361810caed8` reports that the retirement scope includes
  the runtime/Anchory Wayfinder–POI dependency.
- Attic deposit `cb30d730-f14a-46fd-b7f4-efa268a2b309` preserves the legacy
  Skillware and related code surfaces. Deposit
  `b114cab9-3fcc-4cd7-9d2c-c98ebb1d5624` preserves legacy Chatlas and lab
  surfaces while retaining the current Chatlas skill.

## Verification

- Full suite: `1196` tests passed.
- Scoped Ruff and diff review passed.
- Reinstalled CLI exposes the current `skw document` and `skw skills`
  surfaces only.
- Navigation's `ProviderError` now uses `tarav.poi`; the former POI
  catalog/model/runtime/linter/renderer/commands and orphan SKW network have
  been retired.

## Impl.Log

- Subsequent audit cleanup authorized by the user: conserved `index_model`,
  its dedicated tests, the obsolete Index test-isolation fixture, and ignored
  `index`/`chatlas2` bytecode remnants in
  `~/Documents/tarav/attic/deposits/20260918T214725Z-index-model-retirement/`.
  Removed those active paths and the retired grammar ownership test; corrected
  README and Architecture claims about removed commands. `stdlib.refs`, project
  Index metadata, and external data remain unchanged. Runtime smoke check passes.

- Follow-up authorization: the user explicitly requested moving the remaining
  Wayfinder and Anchory cores to Attic. Deposit
  `84a1ec27-5341-43a6-bfc0-cd78d89739f9` conserves their code and dedicated
  tests. This follow-up removes the obsolete top-level `reference` command
  and runtime type registration while retaining `tarav.references` and
  Archive reference operations. Follow-up verification: 1,155 tests passed;
  scoped Ruff and diff checks passed; the installed CLI was reinstalled and
  verified without the retired commands. Historical user data depots remain
  untouched. Product changes remain uncommitted.

- **Deviation:** Python edits began before the workflow checkpoint pause became
  effective. No retrospective checkpoint was created; the pre-change material
  is preserved by deposit `cb30d730-f14a-46fd-b7f4-efa268a2b309` and Chatlas
  checkpoint `a1917ec` predates this work.
- The three unresolved Hugentics type-definition links remain existing POIs.
- The final Draft application created the retirement Block, closed Collection,
  one supported Decision Line, and one authorization Gate. Its retained POIs
  are one archive-grounding-unassessable and five unasserted records, plus
  pre-existing model staleness, missing type, and closed-collection findings.
