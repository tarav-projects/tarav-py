# 848 — Pairwise tribunal scoring MVP

<!-- tarav.sessions
1ae20f8c = codex:01a0ff32-0ec2-7b72-8850-fa795135f3c9 @1ae20f8c8159f12d2402ea702cf49c876ec46a72f71ce12423ae1dbdf2a91871
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: implemented and captured. Phase: Execute.

Provide Tarav's first reusable comparative scorer: typed ranking cases enter a named tribunal, agents compare two cases at a time using only their supplied presentations, and the scoring workflow retains judgments and derives per-Assertion relative support with an inspectable measure of sampling. This is a minimum usable workflow for arbitrary compatible Assertion types, not a Line-only ranking adapter.

Non-goals: an absolute truth probability, universal semantic comparability, mandatory prompt-version machinery, exhaustive round-robin comparisons, a complex statistical model, or an automatic claim that low rank proves falsity.

## Design narrative

Every ranking case follows the same small exchange protocol, regardless of tribunal or internal payload. The Assertion produces the case, which names its tribunal and can present its bounded claim/evidence. A tribunal may be a typed object or registered type. It supplies the shared comparison question and instructions, and may define admission checks; it need not be predeclared in a central list before compatible cases can be enrolled. The generic ranker supplies the pairwise procedure and constrained outcomes. It must only pair cases inside one tribunal. The scorer receives ranker instructions, tribunal instructions, then two self-contained cases; it may choose A, B, tie, or abstain/insufficient scope. It must not research outside those cases. Preserve the exact presented material and result enough for agent audit, without making prompt versioning a prerequisite for the MVP.
<!-- tarav.breadcrumb 31be72a25f12 -->
<!-- tarav.breadcrumb 989387f3d410 -->
<!-- tarav.breadcrumb 43b14003cfcf -->
<!-- tarav.breadcrumb 9d542c6a7fad -->

When the first case arrives, the tribunal has a population but no relative score. Comparisons begin with at least two. Retain each pairwise result with case/Assertion identities, judge, outcome, and available rationale/evidence. Derive an initial simple relative ranking from retained outcomes and expose mechanical support information such as comparison count and sparse coverage separately from the relative score. Repeated weak ranking or missing assessment can surface scoring-owned POIs; low relative support means weaker support within that tribunal, not falsehood. New tribunals should require a new tribunal type or instance, not a rewrite of the ranker.
<!-- tarav.breadcrumb d9d18ea1b9c2 -->

The user requested “a first kind ... always a ranking process,” comparing equivalent cases in pairs, and emphasized that cases choose their tribunal while the ranker remains generic. The user explicitly rejected premature rigidity and preferred usage data before sophisticated controls.

Current Tarav scoring already has retained Pools, Tasks, Runs, Results, a runner, and a derived win-rate score from request 779; request 815 added Assertion objects and graph navigation. Treat these as inspectable implementation evidence, not a fixed design contract. Cold-review what can be reused. Do not duplicate persistent scoring stores or silently delete retained results. Candidate `tarav-semantic-calculus.md` discusses ranking and inspectable evidence; this request makes the current conversation's cross-workflow tribunal behavior concrete.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `lines-workflow.md`, candidate `tarav-semantic-calculus.md`; current code guide `src/tarav/l2/scoring/README.md`. Supporting chat: Codex native session `01a0ff32-0ec2-7b72-8850-fa795135f3c9` through retained Breadcrumbs. Dependency: request 846; request 847 supplies the first blessing consumer but the ranker must remain general.

## Execution.Plan

1. Cold-read scoring models, repository, runner, registries, Line ranking adapter, tests, and 779/815 history. Choose a bounded reuse/refactor path, preserving retained data or reporting a separate migration need.
2. Implement the shared ranking-case exchange and typed tribunal registration/lookup with optional admission checks. Demonstrate two tribunals with different questions and case payloads but the same ranker.
3. Add pairwise run construction, blinded/ordered presentation where useful, constrained verdict parsing, abstention, and retained comparison evidence. Agent scorer receives a closed case packet.
4. Derive an initial relative score and separate sampling metadata; expose low/unassessed/sparse POIs and navigable results. One-case tribunal remains unscored without failure.
5. Run focused persistence, rendering, comparison, and score tests; perform a small real or fixture-backed end-to-end trial, inspect results with an agent, then capture Product.Surface Breadcrumbs and proportional validation during Execute.

Acceptance: an Assertion can enter a new compatible tribunal without ranker-specific code; only within-tribunal pairs are compared; two cases produce inspectable retained outcomes and a relative score; one case produces no invented score; sparse/weak output is visible as a signal, not a verdict.

## Impl.Log

- Design only; existing scoring code and records untouched.
- No mandatory schema/prompt-version gate in this MVP. Preserve actual run inputs for inspection and evolve controls from observed problems.
- Recovery: moved from temporary staging into this product repository as request 848; Chatlas and Breadcrumb evidence now live in Tarav's durable data depot. Project.Wiki capture remains pending.
- 2026-10-03 Execute: scoped start checkpoint `9c65788d7b24bc930fbaddf1bb8d2e5d858c2505`. The generic path now uses typed `Tribunal` admission and `PairwiseRankingCase`, retained case/pair/judgment Records in the existing scoring repository, frozen prompts, A/B/tie/abstain judgments, and a derived per-Assertion relative score with separate sampling metadata. A scoring Check emits unassessed, sparse, and weak-support POIs; the legacy Line ranking path remains intact.
- Focused library/fixture trial: two tribunals with different questions and case payloads use the same pairwise code; one-case populations remain unscored; abstentions do not invent a score; retained Records reopen from the scoring repository. `uv run pytest -q tests/scoring tests/test_architecture.py tests/test_poi_workflow.py` passed 61 tests, `uv run ruff check src tests` and `git diff --check` passed. Product Breadcrumbs on model, repository, tribunal code, test, README, runtime, and architecture were submitted and audited. Shifted position observations were refreshed; final file audits were clean.
- Architecture contract/tests and default runtime registration are now in place. Concurrent request 851 landed independently while this request was in progress; its files remain outside this request's scoped diff except for the additional scoring lines. Wiki capture follows product completion.
- Product completion commit `bd5be1099ec8bcc8d115e4676842314f0af06980`; commit-message Breadcrumb audit clean. Wiki daily and `assertions-scoring.md` capture committed as `130e44ed652544dbc112cda952917648882cd72f`, with file and commit audits clean. No retained scoring data outside tests was migrated or rewritten.
