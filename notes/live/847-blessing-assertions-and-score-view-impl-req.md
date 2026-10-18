# 847 — Blessing Assertions and score view

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: implemented and verified; Wiki capture closed. Phase: Execute complete.

Make Tarav Blessing Records `Assertable` under request 846. A blessing can expose a stable labeled primary Assertion that the still-detected POI situation is acceptable without immediate action, plus workflow-owned additional Assertions when useful. Let consumers navigate from blessing to its Assertions and their separately stored, named assessments. Do not make a blessing erase a POI or imply certainty.

Non-goals: changing which POIs are blessable, requiring evidentiary perfection before a blessing can be recorded, assigning one canonical scalar strength, scheduling repeat review, and migrating all historical blessings in this slice.

## Design narrative

Detection and acceptance are separate: a check may continue emitting the same POI while a blessing states that the detected situation is currently acceptable. Multiple attributed blessings can accumulate for that exact situation. A blessing is a claim-bearing object, not a truth verdict. Its existing actor, time, rationale, support, and retained POI snapshot remain inspectable. Its `main` Assertion describes the acceptance claim precisely enough for case producers to present the POI, the triggering data edition, and the offered grounds. Other typed Assertions may expose assessable factual grounds; free-text rationale alone must not silently become trusted fact. A blessing with weak or missing evidence can still be recorded, while assessment and POIs surface the weakness. Human authorship is one possible support signal, not 100% certainty.
<!-- tarav.breadcrumb 701f25246e3d -->
<!-- tarav.breadcrumb 357aa9a6bff4 -->

The score view is an aggregation of independent named results retrieved by Assertion identity from scoring workflows. It keeps unscored, weakly scored, and well-supported distinct. Scoring data remains owned by each scorer. The blessing provides navigation; consumers may choose how much attention to give its continuing POI. This request stops before changing the agent-facing attention policy in request 849.
<!-- tarav.breadcrumb 2d70358c7403 -->
<!-- tarav.breadcrumb 744bd0c16366 -->

Current `tarav.l1.blessings.store.BlessingRecord` and `BlessingAssessmentRecord` are append-only, and `BlessingStore.standing()` currently reports blessed/unblessed using POI identity. Reconcile their records and existing assessments with the new Assertion view; do not silently reinterpret retained records or change physical partitions. The user said “blessing ... can have many assertions” and that a later agent should be able to ask the blessing for scores attached directly or indirectly to those Assertions.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `checks-workflow.md`, and candidate `tarav-semantic-calculus.md`. Supporting chat: Codex native session `01a0ff32-0ec2-7b72-8850-fa795135f3c9` through retained Breadcrumbs. Dependency: request 846.

## Execution.Plan

1. Cold-read requests 833–835, current BlessingStore, POI identity, scoring Assertion, md-library's current blessing consumer, and architecture boundaries. Identify any retained-data conflict before code edits.
2. Add the Blessing-owned Assertable specialization and a primary acceptance Assertion linked to the exact blessing and POI situation. Exercise an optional second named Assertion without imposing it on all blessings.
3. Expose a read-only score/assessment vector by Assertion identity. Keep scorer results in scorer-owned storage and distinguish absent evaluation from adverse evaluation.
4. Verify the check still reports the POI, repeated blessings remain distinct and attributed, existing blessings remain readable or a bounded migration is explicitly called out, and old `BlessingAssessmentRecord` behavior does not silently compete with the new view. Capture Product.Surface Breadcrumbs and run focused checks during Execute.

Acceptance: a blessing's Assertions are discoverable by label, their cases can be requested, their available assessments can be navigated without copying them into the blessing, and no score or blessing suppresses detection itself. Handoff to requests 848 and 849.

## Impl.Log

- Design only; no implementation or retained blessing changes.
- Current Tarav worktree has concurrent uncommitted work. Recheck ownership and record compatibility at Execute.
- Recovery: moved from temporary staging into this product repository as request 847; Chatlas and Breadcrumb evidence now live in Tarav's durable data depot. Project.Wiki capture remains pending.
- 2026-10-03 Execute: scoped start checkpoint `c7f084ae5db8f7f867802b995c9074eda596493f`. The direct `BlessingRecord : Assertable` relationship required placing the common capability and Scoring Workflow Ship in `l1.scoring`; identified Assertion and case mechanics remain in `l2.scoring`, and `l2.blessings` supplies the producer functions through runtime composition. This preserves the `l1 → l2` import rule and existing Type Ship identities.
- Each existing BlessingRecord now has a stable `main` acceptance Assertion tied to its own Record ID and retained POI situation. An optional `grounds` Assertion appears when support references exist. The main ranking case includes the POI snapshot, actor, rationale, and resolved source passages; unresolved offered references yield `IncompleteCaseScope`, while no support remains an explicit weak case. Score vectors read scorer-owned tribunal results by Assertion reference, distinguishing unassessed, unscored, and scored, without copying results into blessings or reinterpreting historical BlessingAssessmentRecords.
- Tests cover repeated blessings, optional grounds, source closure, changed POI situation, scorer navigation, retained Record round-trip, unchanged legacy standing and POI detection, and import direction. `uv run pytest -q` passed 154 tests; `uv run ruff check src tests` and `git diff --check` passed. A read-only corpus scan found no persisted md-library blessing JSON files at the expected path, so retained-data compatibility is proven by Record fixtures and existing tests, not a live corpus sample.
- Product.Surface Breadcrumbs were submitted and audited clean on the capability, blessing store and producer, scoring README, architecture, runtime composition, and tests. Identity re-export and package `__init__` files are mechanical; no separate conversational annotations were justified there.
- Product completion commit: `8c1fd6a81afa361429ceb417614161c131523df1`; its commit-message Breadcrumb audit is clean. Wiki daily and `assertions-scoring.md` capture commit: `2e4f20e9652b448bf0bc4818c58590804e7b1f7a`; both file audits and its commit-message audit are clean. No retained blessing records were rewritten.
