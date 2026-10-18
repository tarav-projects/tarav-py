# 879 — One POI system and POI rendering — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Autonomous (selected on resume). Status: implemented. Phase: Develop; design revision and Execute complete.

Make the things in `tarav-py` that look like POIs be POIs of the core tree, and give POIs one rendering path: a POI renderer type, a registry of named renderers with one default, and command-line surfaces that choose a renderer by name instead of formatting POIs themselves. Remove the word "finding" where the thing is a POI, and rename it where the thing is something else.

Non-goals: tracked POIs and the notification log; repairing any POI raised on a Project; other repositories; a perfect first iteration. Families that cannot be converted safely in this request are listed as deferred with their reason.

## Design narrative

### What the User asked

Tarav grows, becomes somewhat chaotic, and is then formalized and integrated. This request is an integration pass: most POI or POI-like objects and scenarios should converge on fewer primitives and workflows. Everything in Tarav that exposes something that looks like a POI should be revised and implemented as a POI, integrated end to end from the command line to the mechanics. The design does not have to be perfect in the first iteration.
<!-- tarav.breadcrumb 1203b1cc808f -->

"Finding" is a legacy name for POIs and should disappear. All such situations are modelled with the current POI types or subtypes of them, with no `code` field.
<!-- tarav.breadcrumb 931b13db49ca -->

On rendering, the User asked how to formalize the POI life cycle further and named two options: a universal renderer, or at least a universal renderer type that formalizes the visual aspect of POIs, versus independent workflows that render for different consumers, many of which could expose a renderer flag.
<!-- tarav.breadcrumb 759b771a5d80 -->

The agent proposed the middle path below and the User accepted it ("Very nice, yes") while asking for this request.
<!-- tarav.breadcrumb 811913d1c2a6 -->

### Rendering design (proposed by the agent, accepted by the User)

- **Stages.** Collect (a check run or a log produces POIs), Select (filter, group, page), Render (a named renderer lays out the selection), Escalate (the rendering tells the reader how to open the context). `render_check_run` mixes them today.
- **Ownership.** The POI type owns what is said about one POI. The renderer owns the layout of many. Selection happens before rendering; a renderer never selects.
- **One renderer type, named instances.** A registry with one default, as Chatlas and the Diagram already have. A surface chooses with a keyed `--renderer <name>` option. Consumers do not write private POI formatting; a new need adds a named renderer that then exists for everyone.
- **Levels.** `line` (identifier and summary), `record` (bounded detail), `context` (the `tarav context` view). A renderer declares which it supports.
- **Checkable.** A renderer contract, shipped as a reusable test: output for a non-empty selection carries a resolvable identifier and the escalation instruction. A coverage check renders a sample of every loaded POI type with the default renderer and reports types whose line is empty or only a label.

### Agent choices

- A POI type's own summary is optional. `POI.summary()` returns the instance message when there is one and falls back to the type description. The coverage check is what surfaces weak ones.
- `l0` cannot import `l1`. `TypeReferenceFinding` and `RecordDepotCheckFinding` stay plain data, lose the word "finding", and would be converted to POIs at an `l1` boundary when one surfaces them (none does today). Open question for the User: should the root POI type move to `l0`?
- The `context` level is not rendered inline; a renderer satisfies it by printing the escalation instruction. This keeps the context command the single place that opens a POI.
- Renderers receive a `POISelection` (the selected rows plus counts and paging), built from a `CheckRun.report()` or a `POICollector.report()`. The selection is plain data so that a harness process can render what another process collected.
- The view entry `finding` of the `reported-poi` context view becomes `occurrence`.

### Inventory

Decision values: **converted** (now an atomic POI type of the core tree), **renamed** (not a POI; only loses the word), **already** (already an atomic core POI; only its printing moves), **deferred**.

| Object or surface | Where | What it is | Decision |
| --- | --- | --- | --- |
| `BreadcrumbFinding` (`code`, `message`) | `l1/breadcrumbs/store.py` | State of one Breadcrumb's resolution | converted: family `BreadcrumbResolutionPOI` (`IdentifiedPOI`) with one class per case |
| `ReferenceFinding` (`code`, `message`, `hints`) | `l1/references` | State of one Reference's resolution | converted: family `ReferencePOI` (`IdentifiedPOI`) with one class per status |
| `SituationCheck.finding()` and private `_finding` helpers | `l1/checks`, check modules | POI constructors | renamed to `poi()` / `_poi` |
| `reported-poi` view entry `finding` | `l1/poi/reporting.py` | One POI occurrence | renamed `occurrence` |
| `render_check_run` | `l1/checks` | Private POI layout | replaced by the default renderer; `tarav check --renderer --level` |
| `render_poi_report`, `render_poi` | `l1/skw/presentation.py` | Private POI layout for `tarav skw skills check/build/deploy/poi` | moved onto the registry as named renderers |
| `poi: <code>: <message>` lines | `l1/breadcrumbs/commands.py`, `l2/breadcrumb_workflows/chatlas_context/commands.py`, `l2/git/breadcrumbs.py` | Private POI layout | moved onto the default renderer where they print POIs |
| `SkillsStatusPOI`, `GenerationPOI`, `WorkspacePOI`, Breadcrumb audit, tribunal, agents and skills families | several | Atomic core POIs since 877 | already |
| `ChatlasTurnFinding`, `ChatlasQueryResult.findings` | `l1/chatlas/query.py` | A Turn matched by a query | renamed `ChatlasTurnMatch`, `matches` |
| `TypeReferenceFinding` | `l0/kernel/types.py` | Observation about a retained Type reference | renamed `TypeReferenceObservation` (plain data, see choices) |
| `RecordDepotCheckFinding`, `RecordDepotCheckResult.findings` | `l0/_core/record_depot.py` | A record that does not parse | renamed `UnreadableRecord`, `unreadable` (plain data) |
| `Finding` / `Tarav.Diagram.Finding` (74 distinct codes, about 85 construction sites) | `l2/unsorted`, `l2/lines` | Diagram validation states | deferred: the code is nearly untested, one site rebuilds findings from retained records by code, and the split needs 74 types; it needs its own request |
| `store_findings`, `assessment_findings`, `by_assessment_finding` | `l1/blessings/store.py`, `POICollector.report()` | Integrity observations of the blessing store | deferred: retained standing vocabulary; belongs with the tracked-POI work |
| `Document.lint()` findings (dictionaries with `kind`) | `l1/skw/document.py`, `l1/skw/presentation.py` | Producer-side lint results, mapped to atomic POIs in `l1/project/agents.py` and `l2/skw` | deferred: the mapping to POIs exists; renaming the producer vocabulary touches Skillware JSON output used by skills |
| `SourceDiagnostic` | `l1/surfaces` | Parser diagnostics of a native model | deferred: not surfaced as such; its consumers already raise typed POIs |
| search "findings" | `l1/agent/sessions.py` | Search hits over session artifacts | deferred: not POIs; rename belongs to that subsystem |

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `checks-workflow.md`, `context-graph.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. **Renderer.** `tarav.l1.poi.rendering`: `POISelection`, `POIRenderer`, `POIRendererRegistry`, the default renderer, levels, `POI.summary()`. A reusable contract test in the library. `tarav check` renders through the registry and gains `--renderer` and `--level`. The round-trip check follows every registered renderer.
2. **Vocabulary in the core.** `SituationCheck.poi()`, `_poi` helpers, the `occurrence` view entry.
3. **Conversions.** Breadcrumb resolution POIs; Reference POIs. One family per slice with tests.
4. **Renames of non-POIs.** Chatlas Turn matches; the two `l0` data classes.
5. **Other surfaces.** Skillware skill POI reports and the Breadcrumb command lines render through the registry.
6. **Coverage check.** Sample every loaded POI type through the default renderer and raise a typed POI for an empty or label-only line; add it to the development checks.
7. Guidance (`ARCHITECTURE.md`, agents file source where they name changed surfaces), verification (focused tests, suite, Ruff, CLI reinstall, root `tarav check --project` runs), Inlined Capture, scoped completion commit, Wiki capture.

## Impl.Log

- Design inspection (2026-10-08): class list of POI-like types, counts of "finding" per file, the Chatlas renderer registry as precedent, `render_check_run`, the Skillware presentation module, and the construction sites of each coded class.
- Design note capture: four User-Turn Breadcrumbs submitted in this note; design commit `4a21875`, which is also the scoped start state (no product file was edited).
- Stopped after Design (2026-10-08) at the User's request, because of quota. No source, test or guidance file was changed by this request. Wiki capture is pending: nothing was written to `tarav-md/notes/wiki/` for this request.
- Findings of the inspection that the executing agent should know:
  - Callers of `render_check_run`: `l3/check.py`, `l1/checks/poi_contract.py`, `tests/test_checks_workflow.py`, `tests/cli/test_context_command.py` (which asserts that lines 3 to 5 of the output are the context instruction).
  - Construction sites: `BreadcrumbFinding` 4, `ReferenceFinding` 8, `TypeReferenceFinding` 11, `RecordDepotCheckFinding` 5, `ChatlasTurnFinding` 8 (readers of `result.findings` in `l1/chatlas/rendering.py` and `l2/breadcrumb_workflows/chatlas_context`), private `_finding` helpers 33.
  - POIs printed by `tarav skw skills check` are not retained in the reported-POI store, so the escalation instruction would not resolve for them until that surface retains what it prints.
  - Files in the plan that carry someone else's uncommitted edits: `l2/skw/pois.py`, `l2/skw/skills.py`, `l3/runtime.py`, `tests/test_architecture.py`, `ARCHITECTURE.md`, `AGENTS.md` and its Skillware source. Stage only this request's hunks there or leave them uncommitted and report it.
  - Only the files listed in `pyproject.toml` `testpaths` run by default; the Diagram code has almost no tests.
- Next step for a resuming agent: cold-read this note and `AGENTS.md`, then start Execution.Plan step 1 (`tarav.l1.poi.rendering` and `tarav check` on the registry).

## Open questions for the User

1. Should the root POI type move to `l0`, so that the two `l0` data classes can be POIs themselves?
2. The Diagram `Finding` family (74 codes) is deferred to its own request. Is that acceptable, or should it be split here despite the missing tests?
3. Is `occurrence` the right name for the view entry that replaces `finding`?
4. A second named renderer is not required by any consumer yet. The plan adds a JSON-lines renderer for scripts; say if another layout matters more.

<!-- tarav.sessions
473c89a0 = codex:01a1176b-f14c-7fd0-a97c-b22279c3f8c8 @473c89a00e2367fb827193af74a6375c60a96b0be110f21df0aff49360ca972f
-->

## Develop revision — 2026-10-08

The User resumed this request through Develop with autonomous alignment and sharpened the order: establish the shared primitives first, then visit as many POI-like Tarav systems as practical and unify their producers and presentations. The existing Diagram `Finding` family is therefore an integration target to inspect and attempt, rather than a blanket deferral. The earlier non-goals on tracked POI policy, notification-log redesign, repairing reported POIs and other repositories still stand. The User also required visits to the exact User Turns behind referenced design; the three distinct Turns already attached above, and the related context and atomic-POI Turns in the Wiki, were rendered before this revision.
<!-- tarav.breadcrumb e857fcaeeed0 -->

Revised order: (1) one POI renderer interface, registry, selection value and default/JSON-lines instances, with check-report integration and a resolvable context instruction; (2) Breadcrumb and Reference resolution POIs and the common command presentation; (3) migrate remaining POI-shaped SKW and Diagram outputs through those primitives, including their retained/context paths where a command exposes them; (4) rename data that only resembles a POI without forcing an `l0` to `l1` dependency; (5) test each integration slice, perform a fresh whole-library inventory, and record any cases that cannot be safely integrated in this pass with a concrete reason. The renderer selects no POIs; the POI Type owns its one-line meaning. The old plan above is provenance where this revision changes it.
<!-- tarav.breadcrumb 98855066aa88 -->

Bounded implementation choices under autonomous alignment: keep the POI root in `l1`; `l0` observations become POIs when an `l1` consumer actually surfaces them. Use `occurrence` for the reported-POI view. A JSON-lines renderer is the second named layout because scripts can consume it; `--json` continues to produce structured records independently. A family parent may group atomic cases but must never be raised. Changing a retained record schema or dynamically allocating POI Types from observed codes would need a compatibility design, so inspect those boundaries before converting the Diagram cases.
<!-- tarav.breadcrumb aed0ab0d58c1 -->

Start checkpoint for this resumed Develop pass: `141da47307f4e48e6ad641eeb9b7373095255753`. No product source had been changed by request 879 at this point; the shared worktree carries unrelated edits across Tarav layers. Inlined Capture and commits must stay scoped to this request.

## Execution observations — 2026-10-08

- Shared `POISelection`, named `POIRenderer` registry, default and JSON-lines renderers, and `line`/`record`/`context` levels now drive `tarav check` and Skillware POI output. `POI.summary()` supplies instance meaning with a Type-description fallback. The renderer receives an already selected page. `POIContextRoundTripCheck` exercises every registered renderer; `POIRenderCoverageCheck` samples loaded leaf POI Types.
- Breadcrumb and Reference resolution now return atomic `IdentifiedPOI` families instead of code-bearing data. Breadcrumb file and commit audits and resolve output use the common renderer and retain displayed identified POIs for `tarav context`. `SituationCheck.poi()` and its callers replace the POI constructor named `finding`; the reported context entry is `occurrence`.
- Chatlas query results now report `matches` of `ChatlasTurnMatch`, since a matched Turn is not a POI. The two `l0` record/type inspections now report plain observations or unreadable records; neither creates an upward dependency. The Project agents unknown-lint-kind POI loses `Finding` in its Type name.
- Diagram was inspected down to its retained boundary: about 85 `Finding(...)` constructions, roughly 74 coded cases, and 50 retained Drafts under the local Diagram data root with Capture Receipt `findings[]` rows. Those rows persist `type=Tarav.Diagram.Finding`, `code`, `path`, and `message`; `CaptureReceipt` rehydrates them by code. A safe atomic-Type conversion needs a typed case catalog, a receipt schema/version migration for those real records, and targeted tests of read/write/replay. This pass leaves Diagram's coded class as a concrete exception and records the migration as follow-up work. The user-facing SKW `Document.lint()` dictionaries already map to typed POIs at their consumers; blessing-store standing findings and tracked POI policy remain outside this request.
- Verification: 222 Python tests passed in the shared worktree; 212 passed in a scoped clean checkout that excludes concurrent work. Ruff passed on `src` and `tests`, including that checkout. A malformed Breadcrumb audit produced a JSON-lines POI, and its advertised short ID opened the `reported-poi` context view. The installed CLI was rebuilt. `tarav check --project --json` completed 11 checks with 98 pre-existing missing-guidance POIs and none from the new render-coverage or context-round-trip checks.
- Product Inlined Capture submitted one context Breadcrumb on each of 36 changed Python surfaces and two on `ARCHITECTURE.md`; audits on all 37 surfaces finished `ok` (31 informational position-refresh notifications, no failing POIs). A current-source Skill routing change is intertwined with a separate uncommitted relocation; the scoped clean checkout applies its Type-summary addition at the old path while the shared worktree retains the captured new-path edit. The renderer and POI changes are otherwise isolated from those unrelated edits.
- Wiki capture updated `tarav-md/notes/wiki/poi-system.md` and `daily/2026-10-08.md`, with exact Turn Breadcrumbs; scoped Wiki completion commit `03e29e41b7c1db5e0cebb61e34b2eb3c1ab86c31` and its commit audit are clean. Product scoped completion commit `ee0d8b37546290d8418e7583ad48a10fa5302fc8` passed its evidence audit. The remaining uncommitted worktree edits belong to concurrent requests and were preserved.
