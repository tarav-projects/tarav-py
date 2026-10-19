# Assertions and scoring

`AssertionsWorkflow` owns the shallow `TaravAssertion` root and `Assertable`
capability. `ScoringWorkflow` owns its identified, case-producing `Assertion`
subtype, `AssessmentCase`, and a shallow `Score` root. An Assertion declares
supported case Types and can close one from supplied material. Each case keeps
the Assertion reference, question, and complete presentation; the scorer reads
that snapshot without seeking more material.

`RankingWorkflow` is a Scoring child and Python subtype. Its pairwise path uses
`PairwiseRankingCase`, a registered singleton `Tribunal` entity, and
`enroll_case` → `prepare_pair` → `judge_pair` or `submit_judgment`. Each case
keeps its Assertion reference and closed packet. The Tribunal supplies the
question and admission decision; the ranker freezes a two-case prompt and
retains an attributed A/B/tie/abstain judgment in `ScoringRepository`.
`tribunal_scores` derives ephemeral `RankingScore` objects with relative
win/tie support, comparison count, abstentions, opponent count, and coverage.
One case has no relative score. `TribunalScoreCheck` surfaces unassessed,
sparse, or weak support as POIs without treating a low relative rank as a
falsity verdict.

Blessing Records expose `Assertable` through the lower-layer capability and a
runtime-composed Blessings producer. Their `main` Assertion claims that a
continuing POI situation can be accepted for now. An optional `grounds`
Assertion addresses offered source support. A case carries the retained POI
and grounds; unresolved source references yield incomplete scope.
`blessing.score_vector(repository)` reads named tribunal assessments from
`ScoringRepository` without copying scores into the Blessing.

The former Line grounding assertion and its Diagram-backed pool/task adapter
were retired with the old Diagram implementation. The general scoring and
pairwise Tribunal contracts remain available for new consumers.
