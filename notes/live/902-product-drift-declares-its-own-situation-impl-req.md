# 902 — Product drift declares its own situation — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

A product drift POI says that a compiled file differs from what its source
produces. Its situation today is the place of the finding plus the content
hash of every file of the package, so an edit of any file of the package
ends its action and opens another. This request gives this one Type the
situation it means.

1. The situation of `Tarav.SKW.POI.ProductDrift` is three fields: the
   compiled file, the hash of its text on disk, and the hash of the text
   its source produces.
2. Its message is a sentence that names the file; its details hold a count
   of the difference.
3. Its Type notes say that the compiled file may be the newer side.

Non-goals: every other Skillware Type, which keeps the package snapshot;
the drift POI of the Agents file (`AgentsMdProductDrift`); the row format
of the status; repairing the drift that is open in `tarav-hugentics`.

## Design narrative

### User decisions

The user pasted the status row of an open product drift action and asked to
discuss it.
<!-- tarav.breadcrumb e16e6bb243fb -->

The user asked what is in the situation field.
<!-- tarav.breadcrumb f057d65565f8 -->

The user asked why the situation holds a snapshot of the whole package.
<!-- tarav.breadcrumb 255fb87c0805 -->

A blessing targets a situation. The situation is the declared state: the
state that is blessed and that the POI represents. This is a simple POI: it
only means that the compiled file differs from what compiling produces.
<!-- tarav.breadcrumb 1062a9d74841 -->

A situation of three fields is sufficient: the product, the hash of the file
on disk, and the hash of the text the source produces.
<!-- tarav.breadcrumb 242301eb3285 -->

Write the request and build it for this Type only.
<!-- tarav.breadcrumb 2411ac1c1d3c -->

Change the code of the POI; do not repair the Skillware mismatch that the
open action reports.
<!-- tarav.breadcrumb ce613a2486c3 -->

A good heuristic for defining a situation is to see what the check
actually uses.
<!-- tarav.breadcrumb 3c42d2998fe3 -->

### Current behavior (inspected)

- `Document.lint()` (`l1/skw/document.py`) compares the text the source
  produces with the text of the compiled file and reports the bare kind
  `product-drift`, with an empty detail.
- `_analysis_pois()` (`l2/skw/pois.py`) gives every Skillware finding the
  same situation: `subject` (package root, source path, block) and
  `surface_state`, the hash of every source, compiled file, `main.json`,
  loading file and lock file of the package. The details repeat the
  snapshot.
- A code comment gives the reason for the snapshot: an acceptance must not
  keep applying after later edits. The findings do not say what content they
  depend on, so the whole package was taken.
- The real case: the open action in `tarav-hugentics` holds 51 hashes. Its
  message is `product-drift in .skw/src/references/inline-capture.skw.json`.

### Proposals of the agent

**Finding.** The drift finding carries what was compared: the hash of each
text, and a count of the places and lines that differ. Its detail is that
count in words.

**Situation.** `{"product", "actual", "expected"}`. The expected side is the
hash of the produced text and not of the source file, since the produced
text also depends on other inputs, such as the loading model.

**Path.** The agent first proposed a path relative to the Project. A
package does not know a Project: it can be checked alone with
`tarav skw skills check`. The product is therefore named by its full path,
as the package root already was in the old situation; the identity is the
same whether a Project runs the check or the package is checked alone.
The message names the package and the path inside it.

**Where the choice lives.** `SkwPOI.from_finding(check, raw, state)` builds
the POI of one finding and holds the general Skillware line. `ProductDrift`
overrides it. Another Type is given its own situation the same way.

**Consequences.** An edit elsewhere in the package leaves the action as it
is. An edit that changes either text is a different drift: the action ends
and another opens. The open action of `tarav-hugentics` gets a new identity
once; nothing is migrated.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md`, root
`tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`daily/2026-10-13.md`. Supporting chat: session `abd0372d` above.
Capture status: done (`poi-system.md`, section "Product drift declares
its own situation"; daily 2026-10-13).

## Execution.Plan

1. `Document.lint()`: the drift finding carries the two hashes and the count.
2. `SkwPOI.from_finding`; `ProductDrift` overrides it; Type notes.
3. Test: the situation, and that an edit of another file of the package
   keeps the identity while an edit of the compiled file changes it.
4. Full suite and Ruff; a real status run.
5. Wiki capture.

## Impl.Log

- Design written from the discussion of 2026-10-13.
- The check uses two texts, and the situation holds exactly those two plus
  the file they belong to; the heuristic the user gave during the build
  confirms the choice and is the rule for the next Types.
- The finding carries the product path, so the POI does not rebuild the
  document to find it. The drift POI of the Agents file reads the same
  finding and now shows the count as its detail; nothing else changes there.
- The path is the full path, not relative to the Project as first proposed;
  the reason is in the design above.
- Checks: Ruff clean; `uv run pytest` 294 passed.
- Real run: `tarav status --project .` closed the old drift action as gone
  and opened one with the three-field situation; a second run changed
  nothing. The count stays at 30 open actions.
- Not done, as instructed: the drift itself in
  `tarav-hugentics/references/inline-capture.md` is left as it is.
- Breadcrumbs: submitted and audited on the request, `l2/skw/pois.py`,
  `l1/skw/document.py`, `tests/test_skw_poi.py` and both Wiki notes; all
  audits are ok after the recorded positions were refreshed.
