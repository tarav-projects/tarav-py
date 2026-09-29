# Assertions and scoring

`ScoringWorkflow` owns `Assertion` and shared evaluation mechanics.
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
No new automatic low-score threshold or POI emission policy is imposed.

The prior `IndexLineGroundingAssertionType` adapter was replaced by the actual
`LineGroundingAssertion` class. Pool operations are class methods;
`from_line()` / `from_reference()` produce assertion objects whose `candidate()`
method supplies a ranking presentation. Import ranking adapters and registries
from `tarav.scoring.tasks`; the package root exposes only the shared scoring
foundation. No compatibility aliases or retained-data rewrites are needed.
