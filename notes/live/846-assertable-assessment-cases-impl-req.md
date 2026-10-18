# 846 — Assertable objects and closed assessment cases

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: implemented and captured. Phase: Execute.

Introduce the smallest Tarav contract by which an `Assertable` object exposes labeled, identified Assertions and each Assertion can produce typed assessment cases for compatible scoring workflows. A case is the complete, bounded input to one scorer. The scorer judges it without searching for missing evidence. This is Tarav infrastructure, not an md-library specialization.

Non-goals: a universal case schema, one scalar truth score, automatic external research, implementation of the pairwise ranker, migration of every existing semantic Record, and product-code execution in this design phase.

## Design narrative

The user selected the chain `Blessing → Assertions → Cases → Scoring workflows`, with one object potentially exposing many labeled Assertions and each Assertion potentially producing several case types. `Assertable` should provide an `.assertions` capability namespace and a way to enumerate and address Assertions by durable label; indices may help display but are not identity. An Assertion has an exact claim/subject identity. A scoring workflow asks an Assertion for its supported case type. Unsupported type and insufficient material for a supported case are distinct outcomes. The produced case owns a closed scope: claim, question, and supplied material sufficient for the consuming scorer's declared task. An agent scorer may return insufficient scope, but must not expand the packet by independent research. The assertion producer can then enrich its case construction and retry. The case's internal schema belongs to its producer and consumer; Tarav supplies only the common exchange contract. Preserve separate scoring results and vectors; no score is embedded as unquestioned truth in the Assertion.
<!-- tarav.breadcrumb d236f517970d -->
<!-- tarav.breadcrumb 11bcb04aced8 -->
<!-- tarav.breadcrumb 1806e9cf35fc -->
<!-- tarav.breadcrumb 29bf2ca91815 -->

This is a design requirement from the current user conversation, not a claim about current code. The user explicitly said “blessing ... can have many assertions” and “each ... assertion ... can have ... many cases,” and proposed `.assertions` as a namespace gained through an `Assertable` type. They also required the scorer's scope to be complete and prohibited making the scorer a researcher.

Current code already has `tarav.l2.scoring.assertions.Assertion`, whose identity derives from Type Ship and exact subject coordinate, and a Lines-owned grounding subtype with an older ranking adapter. Reconcile this request with those contracts instead of adding a second Assertion ontology. Read `tarav-py/ARCHITECTURE.md`, `src/tarav/l2/scoring/README.md`, and requests 779 and 815 before edits. Preserve retained Record identity when semantics agree; surface any material migration separately.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant current notes: `poi-system.md`, `lines-workflow.md`, and Tarav's candidate `tarav-semantic-calculus.md`. Supporting chat: Codex native session `01a0ff32-0ec2-7b72-8850-fa795135f3c9`; exact User Turns are attached through retained `chatlas-context` Breadcrumbs.

## Execution.Plan

1. Cold-read current Assertion, Lines ranking adapter, registry, tests, and layer boundaries. Select the smallest compatible `Assertable`/`.assertions` and case protocol, with one labeled `main` assertion example.
2. Implement one complete producer/consumer demonstration using an existing concrete Assertion. Demonstrate multiple case types without requiring their payloads to share one schema.
3. Distinguish unsupported case type, incomplete case scope, and scorer judgment in public behavior. A scorer sees only the supplied case.
4. Test stable assertion lookup, case production, unsupported/incomplete behavior, persistence or round-trip where applicable, and import direction. Capture justified Product.Surface Breadcrumbs during Execute; run focused and proportional checks.

Acceptance: another workflow can expose named Assertions through `.assertions`; a scorer can request a typed closed case; failure modes remain distinguishable; existing Line assertion identity and ranking behavior are not silently changed. Handoff to request 847.

## Impl.Log

- Design only. No product code, tests, or retained scoring data changed.
- The Tarav source tree has substantial concurrent uncommitted work; execution must recheck it and avoid overwriting it.
- Recovery: moved from temporary staging into this product repository as request 846; Chatlas and Breadcrumb evidence now live in Tarav's durable data depot. Project.Wiki capture remains pending.
- 2026-10-03 Execute: scoped start checkpoint `984791d5d60464f0264573505f57f5744b6abdc1`. Added `Assertable`/label-addressed `AssertionNamespace`, typed closed `AssessmentCase` snapshots, distinct unsupported/incomplete errors, and two Line-owned case producers. Registered case Types in the runtime; existing Line Assertion identity and ranking adapter were preserved.
- Product.Surface Breadcrumbs were submitted and audited clean on the assertion and Line producers, case tests, architecture document, and scoring README. Runtime registration and exports are mechanical and had no separately justified conversational annotation.
- Verification: `uv run pytest -q tests/scoring tests/test_architecture.py` (47 passed), `uv run ruff check src tests`, and `git diff --check` passed. A Pydantic forward-reference failure in the first test run was corrected by moving the reference interface before case declarations.
- Product completion commit: `230b98a93a582994c11760348bd871bfcbd42058`; commit-message Breadcrumb audit clean. Wiki daily and new `assertions-scoring.md` topical capture committed as `3d559c51b9c4a5d0ab93f7ac746574a2d2e69c1d`, with file and commit Breadcrumb audits clean. A detached clean Tarav CLI snapshot was used for the Wiki commit because unrelated in-progress request 851 temporarily made the shared editable CLI fail runtime registration; no 851 files were changed here.
