# 863 — Assertion and scoring roots, ranking workflow, typed scores

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop (Design → Execute). Status: implementation verified; Product.Surface and Wiki Breadcrumb submission pending.

Separate the generic Assertions and Scoring workflow roots from the existing particular assessment/ranking implementation. Add a minimal `Score` object root and a typed ranking-score subtype around the currently derived tribunal score rows. Keep the current assertion-to-case-to-judgment behavior and scoring arithmetic intact.

Non-goals: redesigning ranking, introducing a universal numeric score, retaining score snapshots, migrating the old Unsorted assessment engine, moving historical scoring repository records, or requiring every Assertion to produce a scoring case.

## Design narrative

The user wants an extensible ontology whose shallow workflow roots do not inherit one current method's details. Types and workflow ownership should let an agent inspect the chain from a Blessing or Line through its Assertions, closed cases, particular scoring method, retained judgments, and derived score. Particular assertions may build typed cases; that is not a universal requirement on the Assertions root. Ranking is one scoring method, not the definition of Scoring. A score should itself be a typed object, but can be ephemeral and recomputed from retained evidence. Common score fields should emerge from multiple applications, not be guessed from ranking alone.
<!-- tarav.context 6734aba0:434e3f65fc9c6be5 -->
<!-- tarav.context 6734aba0:fbf15ffc7aa9ae0e -->
<!-- tarav.context 6734aba0:33c08d1be038423c -->

Current code: `l1.scoring.Assertable` is Scoring-owned; `l2.scoring.Assertion` carries subject-addressed identity and case production; `AssessmentCase` is Scoring-owned; `PairwiseRankingCase`, `Tribunal`, pairwise operations and `tribunal_scores()` live in `l2.scoring.tribunals`. The latter returns dictionaries. `ScoringRepository` retains case/pair/judgment Records, while Blessing and Check consumers read derived rows. Existing Type Ships and retained Record labels matter independently of source paths. `ARCHITECTURE.md` and scoring tests enforce the current ownership.

First-slice design: introduce an Assertions-owned shallow assertion root and move the common `Assertable` capability under Assertions ownership. Keep the existing subject-addressed, case-producing `Assertion` as a subtype with its established Type identity and Record schema; concrete producer classes remain its subtypes. Add a shallow Scoring-owned `Score` root and Ranking-owned score subtype wrapping one existing tribunal row. Add `RankingWorkflow` as a Scoring child and Python subtype: this particular subtype relationship makes ranking a kind of scoring workflow, but does not impose a universal scoring method yet. Pairwise ranking Types belong to Ranking, while Scoring owns generic cases and retains its existing repository paths. The implementation may keep convenient public re-exports, but the canonical source paths should express ownership. Do not make the shallow roots promise reference identity, case construction, one numeric value, or persistence.

The user clarified that Tribunal belongs to Ranking alone. Each concrete Tribunal class defines one particular comparison question, admission, and presentation policy. It has a separate class representative (`entity(MyTribunal)`, identified by its TypeShip) and one stable Tribunal entity (`MyTribunal()`, identified by its own hardcoded Ship). This mirrors the deliberate class/instance distinction used for Workflows. The Tribunal instance is a singleton; persistence of that instance is independent. Do not collapse the two identities, convert the class entity into the tribunal, or standardize rich case requirements across tribunals. An Assertion can produce different case Types for different tribunals. Existing `tribunal_type_id` fields name the class, not the new singleton object: preserve that interpretation in retained records, make resolution to the singleton explicit, and do not silently relabel old references as object Ships. Adding a direct retained object reference is a distinct schema decision and need not be forced into this slice.
<!-- tarav.context 6734aba0:a37ed4686d740bc3 -->
<!-- tarav.context 6734aba0:b0167f504889a33e -->
<!-- tarav.context 6734aba0:bba1c976c99de9c3 -->
<!-- tarav.context 6734aba0:e3a12d122bc8c5ca -->

Evidence: native session `codex:01a0d86c-9538-7be1-af96-014cd4203d61`. Read-only inspection of its retained raw Chatlas transcript located these User Turns (UTC): `2026-10-06T14:48:03.492Z` (“we cannot handicap the ... abstract layer”), `14:50:42.975Z` (“the assertion build the case ... scoring actually run it”), `15:00:02.920Z` (“scorings can be recomputed”), `15:16:11.162Z` (“split the objects ... include the scoring objects”), `15:34:47.306Z` (Ranking and Tribunal semantics), `15:38:23.044Z` (Tribunal specialization), `15:41:05.480Z` (“we create an instant of a tribunal ... always the same one”), and `15:43:12.384Z` (why class and instance IDs differ). Exact Turn hashes and Breadcrumbs are pending: Chatlas Normal Model refresh failed on the sandbox-denied `/Users/pereiro/Documents/tarav/chatlas/cache/.../sessions.json`; do not invent them. These timestamped locators are temporary evidence, not Breadcrumbs.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner/root: `tarav-md/notes/wiki/`. Relevant topic: `assertions-scoring.md`. Relevant previous requests: 846–848. Supporting current conversation as above; retained Chatlas-backed Breadcrumb capture pending environment access.

## Execution.Plan

1. Recheck current imports, Type/Workflow identities, runtime registration, record schemas, score consumers, and tests. Establish a scoped start checkpoint before product edits.
2. Introduce Assertions workflow/root/capability without adding scoring obligations to the root. Preserve existing identified assertion IDs and schemas; update runtime and ownership tests.
3. Introduce Ranking as a child and Python subtype of Scoring. Place pairwise Types/operations under its source namespace. Make Tribunal a Ranking-owned singleton Entity with separate stable class TypeShip and instance Ship; adapt registration and resolution without changing the meaning of retained `tribunal_type_id`. Preserve retained case/pair/judgment schema and repository location.
4. Add `Score` and `RankingScore` as typed Tarav objects. Return typed score rows at the tribunal boundary and adapt Blessing/Check/rendering consumers intentionally; keep computation unchanged and allow explicit conversion to a Record/dict for legacy-shaped output where those interfaces require it.
5. Test class/workflow graph, round-trips, ranking numbers/coverage, no-comparison case, Blessing score view, POIs, retained repository reopening, and architecture boundaries. Run focused suite, broader suite, lint, diff checks. Capture justified Product.Surface Breadcrumbs when the Chatlas workflow is available; log precise gaps otherwise. Commit only declared work scope; capture discussion selectively in Wiki.

Acceptance: generic Assertions and Score roots are shallow; current concrete assertions and ranking Types are subtypes/specializations with discoverable Workflow owners; `entity(MyTribunal).id` and `MyTribunal().id` are distinct stable identities, with repeated construction returning the same object; ranking produces typed score objects without changing numerical results or stored evidence; existing retained scoring records remain usable.

## Impl.Log

- Design pass inspected current source, tests, architecture, and requests 846–848. No product code edited yet.
- Chatlas raw-source resolution and read-only transcript inspection succeeded. Normal Model update is unavailable due sandbox permissions outside workspace; exact User-Turn Breadcrumbs remain pending, with timestamped verbatim locators above for recovery.
- Scoped start checkpoint `fb600aeae586ef5b06964d93a4ae1710f8f6c4fe` saved the design handoff. Subsequent user clarification changed the Tribunal model before product edits; this note was updated accordingly.
- Execute: added `l1.assertions` with shallow `TaravAssertion` and the existing `Assertable` Type Ship; Scoring's identified Assertion remains a subtype with its existing Ship and Record schema. Registered the new root and AssertionsWorkflow in the runtime.
- Execute: added RankingWorkflow as Python subtype and workflow child of Scoring. Moved the pairwise implementation under `l2.scoring.ranking`, preserving existing pairwise Type Ships, Type names, and retained scoring repository schema. Tribunal is now a `TaravEntity` singleton per class, with a separate class-local Ship declaration. Existing `tribunal_type_id` continues to resolve the class; no retained field was reinterpreted.
- Execute: added shallow Score and derived RankingScore objects. `tribunal_scores()` now returns typed Mapping-compatible RankingScore values. Blessing score vectors and Check evidence explicitly convert those values to detached row dictionaries, preserving their existing output shape. Added class/instance identity, score round-trip, workflow ownership, and no-comparison tests.
- Verification: direct shared project interpreter `../.tarav/env/bin/python -m pytest -q` passed 169 tests; `compileall` and both repos' `git diff --check` passed. `uv run` could not open its cache under `/Users/pereiro/.cache/uv` in this sandbox; the shared interpreter lacks Ruff, so lint remains unrun. Product work remains uncommitted while Breadcrumb submission is unavailable.
- Capture: read-only Chatlas raw-source resolution and in-memory Normal Model construction supplied exact User-Turn hash prefixes. Provisional `tarav.context` markers are placed on justified product and Impl.Req passages; Wiki daily and topical Notes carry corresponding markers. `tarav breadcrumbs submit chatlas-context` on the daily Note failed before mutation because this sandbox cannot create `/Users/pereiro/Documents/tarav/chatlas/normal-model/locks/6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b.lock`. Formal submission and audits remain pending. Do not claim capture closure or a completion commit.
