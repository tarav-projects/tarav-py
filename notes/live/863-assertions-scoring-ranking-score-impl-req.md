# 863 — Assertion and scoring roots, ranking workflow, typed scores

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop (Design → Execute). Status: design ready; execution pending.

Separate the generic Assertions and Scoring workflow roots from the existing particular assessment/ranking implementation. Add a minimal `Score` object root and a typed ranking-score subtype around the currently derived tribunal score rows. Keep the current assertion-to-case-to-judgment behavior and scoring arithmetic intact.

Non-goals: redesigning ranking, introducing a universal numeric score, retaining score snapshots, migrating the old Unsorted assessment engine, moving historical scoring repository records, or requiring every Assertion to produce a scoring case.

## Design narrative

The user wants an extensible ontology whose shallow workflow roots do not inherit one current method's details. Types and workflow ownership should let an agent inspect the chain from a Blessing or Line through its Assertions, closed cases, particular scoring method, retained judgments, and derived score. Particular assertions may build typed cases; that is not a universal requirement on the Assertions root. Ranking is one scoring method, not the definition of Scoring. A score should itself be a typed object, but can be ephemeral and recomputed from retained evidence. Common score fields should emerge from multiple applications, not be guessed from ranking alone.

Current code: `l1.scoring.Assertable` is Scoring-owned; `l2.scoring.Assertion` carries subject-addressed identity and case production; `AssessmentCase` is Scoring-owned; `PairwiseRankingCase`, `Tribunal`, pairwise operations and `tribunal_scores()` live in `l2.scoring.tribunals`. The latter returns dictionaries. `ScoringRepository` retains case/pair/judgment Records, while Blessing and Check consumers read derived rows. Existing Type Ships and retained Record labels matter independently of source paths. `ARCHITECTURE.md` and scoring tests enforce the current ownership.

First-slice design: introduce an Assertions-owned shallow assertion root and move the common `Assertable` capability under Assertions ownership. Keep the existing subject-addressed, case-producing `Assertion` as a subtype with its established Type identity and Record schema; concrete producer classes remain its subtypes. Add a shallow Scoring-owned `Score` root and Ranking-owned score subtype wrapping one existing tribunal row. Add `RankingWorkflow` as a Scoring child; pairwise ranking Types belong to it, while Scoring owns generic cases and retains its existing repository paths. The implementation may keep convenient public re-exports, but the canonical source paths should express ownership. Do not make the shallow roots promise reference identity, case construction, one numeric value, or persistence.

Evidence: current conversation's user turns beginning “we cannot handicap the abstract layer by a particular implementation,” “the assertion build the case ... scoring actually run it,” “scorings can be recomputed ... cheap,” and “split the objects ... include the scoring objects ... wrap the dictionaries.” Current native session resolved as `codex:01a0d86c-9538-7be1-af96-014cd4203d61`. Exact Turn hashes and Breadcrumbs are pending: Chatlas refresh failed on the sandbox-denied `/Users/pereiro/Documents/tarav/chatlas/cache/.../sessions.json`; do not invent them. This ordered excerpt locator is temporary evidence, not a Breadcrumb.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner/root: `tarav-md/notes/wiki/`. Relevant topic: `assertions-scoring.md`. Relevant previous requests: 846–848. Supporting current conversation as above; retained Chatlas-backed Breadcrumb capture pending environment access.

## Execution.Plan

1. Recheck current imports, Type/Workflow identities, runtime registration, record schemas, score consumers, and tests. Establish a scoped start checkpoint before product edits.
2. Introduce Assertions workflow/root/capability without adding scoring obligations to the root. Preserve existing identified assertion IDs and schemas; update runtime and ownership tests.
3. Introduce Ranking as a child of Scoring and place pairwise Types/operations under its source namespace. Preserve retained case/pair/judgment schema and repository location.
4. Add `Score` and `RankingScore` as typed Tarav objects. Return typed score rows at the tribunal boundary and adapt Blessing/Check/rendering consumers intentionally; keep computation unchanged and allow explicit conversion to a Record/dict for legacy-shaped output where those interfaces require it.
5. Test class/workflow graph, round-trips, ranking numbers/coverage, no-comparison case, Blessing score view, POIs, retained repository reopening, and architecture boundaries. Run focused suite, broader suite, lint, diff checks. Capture justified Product.Surface Breadcrumbs when the Chatlas workflow is available; log precise gaps otherwise. Commit only declared work scope; capture discussion selectively in Wiki.

Acceptance: generic Assertions and Score roots are shallow; current concrete assertions and ranking Types are subtypes/specializations with discoverable Workflow owners; ranking produces typed score objects without changing numerical results or stored evidence; existing retained scoring records remain usable.

## Impl.Log

- Design pass inspected current source, tests, architecture, and requests 846–848. No product code edited yet.
- Chatlas update unavailable due sandbox permissions outside workspace; exact User-Turn Breadcrumbs pending, with ordered verbatim locators above for recovery.
