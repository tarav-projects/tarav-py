# 838 — SKW reference resolution checks

<!-- tarav.sessions
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented and verified.

Add explicit SKW Checks that surface broken declared references as CheckPOIs.
Reference resolvability is independently assessable: it must not disappear when
freshness evaluation cannot construct its inputs or has no recorded baseline.
This request changes checking/reporting, not generation or retained content.

Non-goals: automatic repair, mandatory successful validation before mutation,
new check engines, broad arbitrary-object crawling, uv/environment changes,
or changes to blessing policy.

## Design narrative

### User direction and evidence

During the read-only review of request 836, the user requested a Check to
evaluate whether connections are resolvable and raise a POI for a broken
reference. The subsequent clarification was explicit: a broken reference
should produce the POI; successful resolution needs no success POI. The user
then requested this implementation request through Tarav Hugentics Design.

Canonical Chatlas resolution is now available. The exact User Turn requesting a
Check for resolvable connections is `e05664dd5124b417`; the clarification that
only a broken reference should produce the POI is `5fe2c051bf36a8b8`.
<!-- tarav.breadcrumb b34495abc255 -->
<!-- tarav.breadcrumb cd7f5eb55298 -->

The User subsequently trusted execution of this request.
<!-- tarav.breadcrumb d4696d4f30a4 -->

### Current implementation observations

Request [836](836-typed-annotated-skw-blocks-impl-req.md) moved SKW to neutral
blocks with typed annotations and a local objects index.

- `src/tarav/l2/skw/skills.py`: `_check_without_reading()` invokes
  `document.lint(freshness=False)`; `evaluate()` and `check()` construct checks
  with `skip_unresolved_freshness=True`.
- `src/tarav/l2/skw/pois.py`: `freshness_checks()` catches resolution errors
  and skips checks in that mode. Context freshness iterates recorded context
  baselines, not every current declaration.
- The comment in `evaluate()` says preliminary document analysis already
  retains resolution failures. That assumption must be revalidated against
  the new structural-only lint path.
- A `ContextUnresolvable` POI already exists; inspect its contract before
  adding another overlapping type.

Execution reproduced both missing paths. A missing external generation-context
file emits no reference POI. A missing local object-index target aborts document
construction and is reduced to `invalid-loading-model`, before an independent
reference Check can exist.

### Proposed bounded contract

Provide an independently runnable SKW-owned Check through the existing Checks
workflow and expose it through the existing iterable `SkwSkill.checks`.
Reuse CheckResult and CheckPOI mechanics. Consumers emit resulting POIs through
the existing collector; do not add a parallel finding model or confuse POI
emission with raising a Python exception.

Enumerate generation-context reference occurrences using the actual typed SKW
contracts: direct typed References, local ObjectIndexReference targets, and an
indexed object that is itself a Reference. Existing loading and reading targets
remain owned by `InvalidBlockReference` and `InvalidContextTarget`; do not
duplicate them. Do not interpret arbitrary strings or Markdown links as typed
graph edges, nor recursively crawl arbitrary referenced content.

For each supported occurrence, successful resolution produces no failure POI.
A resolution failure produces a POI identifying the owning document/block,
annotation or index coordinate, declared target, and available failure reason.
An unavailable or permission-denied target should be reported accurately as
unresolvable in this environment, not asserted to be permanently deleted.
Use the existing explicit situation/identity conventions, not hidden hashing
heuristics or unstable timestamps.

Reference checking does not require a generation baseline. A failure must not
abort evaluation of unrelated valid references or suppress unrelated Checks.
If a prerequisite cannot resolve, dependent freshness is not verified; never
report it as fresh merely because its Check was skipped. Keep independently
resolvable generation/context freshness checks working. Do not introduce a
new universal status framework solely for this integration.

Document loading types context declarations but does not resolve their targets.
In particular, `SkwBlock.bind_registry()` must stop resolving local
ObjectIndexReferences through `GenerationAnnotation.context_objects()`.
Reference resolution belongs to the new Check and to operations that consume
the context.

Check enumeration must remain available when a target is broken. Constructing
`SkwSkill.checks` must not eagerly resolve freshness or loading inputs in a way
that prevents callers from obtaining the reference Checks. Package evaluation
always runs these Checks, even when dependent freshness or reading Checks are
unavailable.

Prefer one resolution observation per evaluation that can feed both the
resolution result and dependent freshness snapshots. If SituationCheck is
used, collect observations before execution and preserve its snapshot-only
contract. This is an implementation proposal, not a requirement for all Checks
to become SituationChecks.

Keep package evaluation, existing CLI reporting, and standalone targeted checks
consistent. Avoid duplicate POIs for the same occurrence from overlapping
structural and resolution paths. Broken inputs must remain visible even when
another malformed input prevents full loading-model construction; retain
existing structural diagnostics rather than assuming all objects can load.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`.
Relevant existing context:

- `tarav-md/notes/wiki/checks-workflow.md`: Check, result POI provider,
  targeted execution, and SituationCheck contracts.
- `tarav-md/notes/wiki/poi-system.md`: POI semantics and identity.
- `tarav-md/notes/wiki/reader-context-path.md`: declared reading relationships.

Capture status: canonical User Turns resolved and attached. The bounded Wiki
capture records the final reference-checking contract and implementation.

## Execution.Plan

1. Reproduce missing external context through public package evaluation;
   compare standalone document lint. Include a block without any baseline.
2. Inventory existing typed reference resolvers and Checks. Select the smallest
   missing resolution Check/POI integration, reusing existing coverage.
3. Implement independent resolution reporting and integrate `.checks`,
   `evaluate()`, `check()`, and current CLI reporting without silent skips.
4. Verify deterministic tests: all references resolve; missing external file;
   missing local index target; resolver failure; no baseline; mixed valid and
   broken references; relevant loading/reading targets; no duplicate reports.
5. Verify unrelated freshness still runs; unresolved freshness is not presented
   as verified; repaired references stop producing broken-reference POIs.
   Use fake resolvers for permission/remote failures, not live services.
6. Run focused SKW/Checks tests, then configured suite and lint. Confirm no
   check repairs sources, refreshes baselines, or changes generated content.
7. Capture supported Product.Surface Breadcrumbs and Wiki updates and complete
   scoped workflow closure; preserve unrelated worktree edits.

Acceptance: a broken supported reference is visible as an inspectable CheckPOI
through normal package reporting and a targeted Check, independently of
freshness baseline presence. Successful resolution produces no failure POI.

## Impl.Log

- 2026-10-02: Resolved the exact User Turns retained by the emergency evidence
  map and replaced the fallback quotations with canonical Breadcrumb markers.
- Added one independently runnable `GenerationContextResolutionCheck` for each
  typed generation-context Reference declaration. It follows direct References,
  local object-index targets, and indexed References through the existing SKW
  resolver and emits the existing `ContextUnresolvable` POI on failure.
- Changed generation annotation binding to type context declarations without
  following them. A missing local index or external file therefore remains
  available to the Check instead of collapsing package loading into
  `invalid-loading-model`.
- Composed reference checks before dependent freshness and reading checks.
  Freshness construction skips an unresolved prerequisite while independent
  reference checks and unrelated Checks remain runnable.
- Added one end-to-end SKW POI test covering a valid direct Reference, a broken
  indexed Reference, repair, and a missing local index. Both failure cases are
  reported as `ContextUnresolvable` rather than `InvalidLoadingModel`.
- Verification: `uv run pytest -q tests/test_skw_poi.py` (2 passed) and
  `uv run pytest -q` (151 passed in 24.13 seconds). `git diff --check` passed.
