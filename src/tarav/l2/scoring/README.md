# Assertions and scoring

`AssertionsWorkflow` owns the shallow `TaravAssertion` root and `Assertable`
capability. `ScoringWorkflow` owns its identified, case-producing `Assertion`
subtype, the label-addressed `.assertions` namespace, `AssessmentCase`, and a
shallow `Score` root. An Assertion
declares supported case Types and can close one from supplied material. Each
case retains the Assertion reference, a question, and a complete presentation;
the scorer consumes that snapshot without seeking more material. Unsupported
case Types and incomplete scope are distinct errors. Subtypes own their payload
schema, so no universal evidence format is imposed. The Line grounding
Assertion demonstrates grounding and support-inventory cases while retaining
its existing identity and ranking adapter.
<!-- tarav.breadcrumb 7b05d770fd43 -->
`LinesWorkflow` owns `LineGroundingAssertion(Assertion)`: the claim that a
particular Line edition is supported by its declared Support.Set.

```python
from tarav.lines.assertions import LineGroundingAssertion
from tarav.scoring.tasks import DEFAULT_ASSERTION_RANKING_REGISTRY

assertion = LineGroundingAssertion.from_line(
    line_ship=line_ship, namespace_id=projection.namespace_id, projection=projection,
)
runtime.context(assertion).open("subject")
runtime.context(assertion).open("evidence")
support = assertion.evidence(projection=projection, evidence=chatlas_evidence)

enrollment = runtime.records.from_record(enrollment_record)
edge = runtime.context(enrollment).open("assertion_ref")
same_assertion = edge.resolve(assertions=DEFAULT_ASSERTION_RANKING_REGISTRY)
pool = runtime.context(enrollment).open("pool_ref").resolve(repository=repository)
```

Assertion identity derives from its Type Ship and exact subject coordinate.
A new subject edition creates a different Assertion. Evaluators and scores do
not affect that identity. Assertions round-trip through ordinary Tarav Records;
existing embedded `*.Assertion.Reference` records keep their previous shape.
Subtypes own subject validation and Context/evidence semantics; the base does
not prescribe one evidence format or evaluation method. Common traces can
address other typed subjects, while the existing grounding pool/task remains
a Line-specific ranking implementation.

The retained graph uses the existing concrete records:

```text
PoolEnrollmentRecord → pool + assertion
GroundingRankingTaskRecord → pool + enrolled candidates
RankingRunRecord → task
RankingResultRecord → run
ScoringTraceRecord → assertion
ScoringEventRecord → trace
```

These are now identified Tarav entities. Their Context exposes named reference
edges and the full Record. `ScoringReference.resolve()` preserves repository
hash checks and requires explicit resolution dependencies. Derived win-rate
scores remain derived; a high relative ranking is not proof of correctness.
The legacy Line ranking does not impose an automatic low-score threshold.

`RankingWorkflow` is a Scoring child and Python subtype. Its pairwise path uses
`PairwiseRankingCase`, a registered singleton `Tribunal` entity, and
`enroll_case` → `prepare_pair` → `judge_pair` or `submit_judgment`. The
Tribunal's Type Ship identifies its class; its separately declared Ship
identifies the singleton object. Existing `tribunal_type_id` fields still
identify the class.
Each case keeps its Assertion reference and closed packet. The tribunal supplies
the common question and admission decision; the ranker supplies the same
A/B/tie/abstain procedure for every tribunal. The prompt and each attributed
judgment are retained under the existing `ScoringRepository` Git root.
`tribunal_scores` derives typed, ephemeral `RankingScore` objects with relative
win/tie support and shows comparison count,
abstentions, opponent count, and coverage separately. One case has no relative
score. `TribunalScoreCheck` surfaces unassessed, sparse, or weak support as POIs
without treating low relative rank as a falsity verdict.
<!-- tarav.breadcrumb 964976f03c0e -->

Blessing Records expose the same Assertable interface through a lower-layer
capability and a runtime-composed Blessings producer. Their `main` Assertion
claims that a continuing POI situation can be accepted for now. An optional
`grounds` Assertion addresses offered source support. A case carries the
retained POI and grounds; unresolved source references yield incomplete scope.
`blessing.score_vector(repository)` reads named tribunal assessments from
ScoringRepository by Assertion reference, without copying scores into the
Blessing. Detection remains unchanged.
<!-- tarav.breadcrumb 5a29a5247ba8 -->


The prior `IndexLineGroundingAssertionType` adapter was replaced by the actual
`LineGroundingAssertion` class. Pool operations are class methods;
`from_line()` / `from_reference()` produce assertion objects whose `candidate()`
method supplies a ranking presentation. Import ranking adapters and registries
from `tarav.scoring.tasks`; the package root exposes only the shared scoring
foundation. No compatibility aliases or retained-data rewrites are needed.
