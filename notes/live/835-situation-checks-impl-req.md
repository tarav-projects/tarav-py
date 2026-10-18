# 835 — Situation-based Checks

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented.

Introduce SituationCheck as an optional specialization of Check. It evaluates
only a supplied Situation snapshot and constructs CheckPOIs using that same
situation for identity. Retain the current CheckProvider.checks property.
Use SKW generation freshness as the first bounded application.
<!-- tarav.breadcrumb dd35e70d6289 -->
<!-- tarav.breadcrumb bbd656c86733 -->

Non-goals: replacing every Check; named check selection; a new provider registry;
sandboxing Python; automatic blessing; semantic correctness scoring; Models
revival; legacy-data migration; adopting the pattern in all surveyed workflows.

## Design narrative

### Situation → Check → POI

SituationCheck must perform its evaluation using only its situation. If it
needs additional data, that data belongs in the situation prepared before
evaluation. This couples the information used for detection with the information
used to identify the resulting POI, rather than independently constructing two
potentially inconsistent descriptions.
<!-- tarav.breadcrumb dbd1a9499f71 -->

Use a shared Situation based on LiteRecord. Do not require a GenerationSituation
class for the first example. A specialized check may optionally declare its own
SituationType with application-specific validation. This is the explicit-input
mechanism, not a demand that every caller hand-build a dictionary.
<!-- tarav.breadcrumb e0b7f1e87142 -->

Checks can be attached to objects when that is a useful organizational choice.
The object constructs the situation and exposes a bound check. Checks/POIs are
workflows that can integrate in other ways too: direct construction, explicit
pools and multi-subject orchestration remain valid. No universal requirement
that a check be owned or exposed by its subject is introduced.
<!-- tarav.breadcrumb aee891fb1f1f -->

Keep the existing property interface: `run_checks(obj.checks)` or iteration
over `obj.checks`. Do not add `obj.checks("name")` in this request.
<!-- tarav.breadcrumb c2e96d2827b4 -->

### Proposed minimal mechanics

The following are agent implementation proposals for the accepted model:

- Place Situation and SituationCheck in `tarav.l1.checks`; Situation derives
  from the existing l0 LiteRecord value contract, not a second serializer.
- SituationCheck inherits Check and accepts keyword `situation`. Its default
  SituationType is Situation; a subtype can provide a validated specialization.
- Snapshot and expose the situation read-only. Preserve existing LiteRecord
  encoding when accepting an already constructed record; do not double-encode
  native tags. Specialized validation must run for supplied records too.
- A `finding(poi_type, *, code, message, ...)` helper binds `check=self` and
  the captured situation. Optional explanatory details do not change identity.
  Do not accept a situation override through this helper.
- Reuse Check.run(), CheckResult and its POI-provider interface. The result
  retains its bound Check, through which the evaluated situation is inspectable.
  Avoid duplicating the snapshot in multiple mutable fields.
- Make the helper the normal production path; reject a returned CheckPOI whose
  situation differs from the evaluated snapshot at the SituationCheck boundary.
  This enforces identity coupling, not the absence of arbitrary Python I/O.
- Keep ordinary Check behavior unchanged. No live subject, resolver, current
  clock or runtime query should be needed during SituationCheck evaluation.
  Code-defined algorithms are allowed; mutable external inputs are not.

A Situation defines the scope of acceptance: changing any of its fields may
produce a new identity and require another blessing. Extra fields are valid
when conservative resurfacing is intentional; Situation descriptions need not
be minimal. Choose granularity deliberately and use the whole situation without
subset projection or a second state fingerprint. Repeated same-situation
emissions retain 834's collector indexing semantics.
<!-- tarav.breadcrumb 87386b4de7ea -->

Generation freshness and context freshness are independently assessable
concerns, so implement them as separate bound checks. The generation Situation
contains its baseline and current generation-input fingerprints; the context
Situation contains its baseline and current tracked-context fingerprints.
Each also carries the subject coordinate needed to distinguish its occurrence.
<!-- tarav.breadcrumb 83c87cc71208 -->

### Illustrative public usage

```python
check = GenerationFreshnessCheck(situation=Situation({
    "block": block_id,
    "baseline_inputs": baseline_hash,
    "current_inputs": resolved_inputs_hash,
}))
result = check.run()

# A provider can build that same bound check for callers:
results = run_checks(provider.checks)
```

The example expresses the approved shape, not currently available classes.
Concrete Tarav Check/POI types still declare their ordinary class entities.
<!-- tarav.breadcrumb 6d52be0dbade -->

### Current code and the motivating defect

Inspected implementation facts:

- `src/tarav/l1/checks/__init__.py` supplies Check, CheckResult, CheckPOI,
  CheckProvider and run_checks, but no SituationCheck. CheckProvider.checks
  is an iterable property; CheckPOI already requires situation.
- `src/tarav/l0/kernel/lite_records.py` provides detached canonical values and
  controlled serializers. 834 made IdentifiedPOI identity depend on its
  concrete class Ship plus its explicit situation.
- `src/tarav/l1/skw/document.py`: AgentGenerationBlock.output_findings compares
  `Document.inputs()` with its recorded baseline. Context freshness similarly
  compares a resolved context fingerprint with retained baseline data.
- `src/tarav/l2/skw/pois.py` `_analysis_pois` computes resolved input/context
  fingerprints but stores them in evidence only. Its situation contains subject
  and surface_state, which need not cover external dependencies.
- `src/tarav/l2/skw/skills.py` SkwSkill.evaluate invokes this adapter and its
  existing reading checks. Its CLI blessing path is active; disconnected Model
  publication is not required for this defect.

Prior read-only reproduction used a controlled document resolver: changing its
resolved dependency changed evidence but not POI identity; an existing blessing
still matched. This demonstrates the adapter problem, not a claim that retained
user blessings were affected. Detection still fires: the old generation baseline
remains unchanged by blessing. The incomplete POI situation is the problem.

### Bounded SKW integration

Agent plan: build separate generation-input and context-freshness checks. Build
each concern's baseline/current fingerprints and subject coordinate before
evaluation. Include relevant revision inputs explicitly, not by automatically
hashing all evidence. No dependency resolution after a check has begun.

Current blocks obtain environment and lock information through Document; they
are not autonomous file-resolving objects. Do not invent ambient runtime access
just to reproduce `block.checks` literally. Let the existing document/package
composition supply collection context to a builder, and expose bound checks
through the current provider property where practical. Direct checks must work
without a package. Preserve existing reading checks and reporting behavior.

Ensure current package/CLI evaluation consumes the SituationCheck-produced POI,
not an old raw finding rewrapped later with a smaller situation. Avoid duplicate
freshness emissions. Legacy-shaped lint presentation may adapt from the same
result, but must not independently repeat detection or reconstruct identity.
Missing input/baseline handling must preserve current reporting semantics;
capture observable failure data before evaluation or report collection failure
explicitly, rather than inventing a successful empty situation.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner/root: `tarav-md/notes/wiki`.
Relevant notes: `checks-workflow.md`, `caller-declared-identity-inputs.md`,
`poi-system.md`; mandatory daily capture: `daily/2026-10-01.md`.
Request 834 is the implemented identity foundation, not authority to redesign
all checking. This note retains the bounded design and exact User-Turn evidence
needed by another implementation session.

## Execution.Plan

1. Recheck current code and concurrent edits, especially SKW document/reading
   work. Add Situation/SituationCheck without changing the general Check contract.
2. Add focused tests of snapshot construction, optional specialization, the
   POI helper and mismatch rejection. Keep inherited validation usable.
3. Implement the SKW snapshot builder and freshness check; route active package
   evaluation through it. Preserve ordinary provider and direct-use paths.
4. Add an integration contract test using a real external dependency: baseline v1,
   current v2, bless the v2 POI, change only dependency to v3, build a new check.
   The v3 POI must have a different identity and be unblessed.
5. Update relevant architecture/API docs, capture supported product Breadcrumbs,
   run focused and integration tests, update this log and close scoped commits.

### Acceptance checks

- Same snapshot yields the same outcome/POI identity; changed relevant data
  changes the situation identity. No separate POI state field.
- Changing source files after check construction does not change that check's
  result. A newly built check sees the change. Test evaluation with external
  readers disabled to detect accidental reads in the migrated path.
- The check actually compares fields from its snapshot; no separate cached
  detection result or live subject is consulted during evaluation.
- The POI snapshot exactly matches the evaluated situation, including supported
  native values. Caller mutation cannot modify the bound snapshot.
- Direct construction and `run_checks(provider.checks)` both work. Ordinary
  Checks, notifications, blessing matching and collector indexes still work.
- Native-type encoding and specialized validation do not bypass one another.
- Run the maintained foundational contract suite and Ruff. Workflow-specific
  validation can be invoked directly while implementing its surface.

## Impl.Log

2026-10-01 — Design only. Reviewed 834 and current Checks/SKW interfaces.
No product code or blessing data changed. Start checkpoints: Python `742e142`,
Wiki `f38a124`. Wiki capture and exact-turn Breadcrumbs accompany this request.
Implementation proposals above remain distinguishable from User decisions.

2026-10-01 — Implemented `Situation`, `SituationCheck`, and separate SKW
generation/context freshness checks. Active SKW evaluation consumes those bound
checks without reconstructing their identities. The retained contract test
proves that evaluation uses the captured snapshot and that independently
changed generation/context inputs resurface independently. The default
foundational suite passes 150 tests in 12.71 seconds; focused Ruff checks pass.
Product Breadcrumb submission completed for the new surfaces. Audit resolves
the new Breadcrumbs and reports stale position observations for older labels
whose source lines moved; those retained audit POIs remain explicit.
