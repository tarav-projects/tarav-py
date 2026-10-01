# 833 — Workflow-owned POIs and composable blessings

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki.
Alignment.Mode: Interactive.
Status: ready for implementation after reconciling with 832.

Migrate existing active POI-like reporting into workflow-owned types that
subtype the neutral POI base. Establish a separate Blessings workflow with
BlessablePOI. This first pass changes type/ownership infrastructure while
preserving existing detection and operation semantics.
<!-- tarav.breadcrumb f4178f9253ffd731e3cae5f4c0397dc53af7974910859e84ea702a5d4e6e5a67 -->

Dependency: [832](832-neutral-pois-checks-and-breadcrumb-audits-impl-req.md)
is being implemented separately. Re-read its landed code before choosing
imports or changing shared contracts; do not concurrently reimplement its
POI foundation or Breadcrumb migration.
<!-- tarav.breadcrumb e11158fe65b434b1a29f74675836a5a68f9429bbe1486b6b6b4fa27b39ba23de -->

Non-goals: replacing every engine with Checks; requiring CheckProvider;
inventing new checks or notifications; redesigning blessing scoring;
reactivating disconnected Models/Lines; converting search matches into POIs;
changing exception control flow merely to unify reporting.

## Design narrative

The minimum integration is that actual POIs are defined in their producing
workflows and inherit the shared POI base. Existing analysis may remain as
it is. Shared typing makes those outputs part of the same system without
forcing an orchestration or producer abstraction on each caller.
<!-- tarav.breadcrumb 03c4312bac3c7a0e3a4fe52f5cff33f61e69e2efad1598c5448b5c6683394b09 -->

Blessability belongs to another workflow with its own BlessablePOI base.
Ordinary POIs must not acquire required blessing fields or semantics.
Concrete types retain their own workflow ownership even when inheriting
capabilities from Checks and Blessings.
<!-- tarav.breadcrumb c292279b14b06d76bf0031057508c0074441528293259a812bdd2a2185abd72d -->

### Composition

The intended example is a SKW-owned StaleGenerationPOI inheriting both
CheckPOI and BlessablePOI. Checking and blessability are composable aspects,
not competing ownership declarations. The example establishes the pattern;
it does not newly authorize blessing every stale-generation condition.
Existing per-kind blessing policy must be preserved.
<!-- tarav.breadcrumb a6c505e9a81bbcd50d18bc5b3ada8239acaa07f0e180206da4eed04a3af511ec -->

### Current-code survey and proposed migration scope

This inventory records inspected implementation, not additional user claims.
Paths and constructors must be rechecked after 832.

| Area | Current reporting | First-pass scope |
| --- | --- | --- |
| References: l1/references/__init__.py | ReferenceFinding uses the older TaravPOIInstance marker | Workflow-owned POI types; preserve resolution status and target semantics |
| Skills: l1/skills/routing.py and commands.py | String selection warnings; missing/broken/unsynced/conflicting status collections | Expose existing attention-worthy conditions as Skills POIs while retaining useful status data |
| SKW generation: l1/skw/generation.py | Local Finding values from Generation.check() | SKW-owned POIs, retaining current dependency/staleness analysis |
| SKW document/package: l1/skw/document.py, l2/skw/skills.py, pois.py | Dictionaries and a conversion collector; reading Checks already integrated | Adapt remaining public POI outputs; reuse 832's existing adaptations |
| Archive: l1/archive/__init__.py | ArchiveWarning for skipped unsupported/suspicious remote locators | Archive-owned POI for that existing condition; successful capture stays successful |
| Navigation: l1/navigation/__init__.py | ProviderError and NavigationResult.findings already use older POI infrastructure | Adapt only if 832 has not; preserve existing error behavior |
| Blessings: l1/poi/blessings.py | Records/store/assessment findings owned by POI; generic consumers assume blessing fields | Extract to Blessings ownership; use BlessablePOI for optional capability |

The survey also found l0/kernel/types.py TypeReferenceFinding and
l1/surfaces SourceDiagnostic. Do not introduce an upward import from l0.
Keep native diagnostic data where needed; if agent-facing POI exposure needs
an integration adapter, place it at a permitted layer. These boundary cases
are a second slice, not a reason to expand the base POI or relocate Kernel.

ChatlasTurnFinding is a query match, not a diagnostic: leave it alone.
Legacy Lines/Models projections are outside this pass. Do not migrate every
type named Finding merely because the name matches.

### Blessings implementation proposal

BlessablePOI must be an operative contract, not only a marker. The minimal
proposed contract supplies a stable concern/occurrence identity, an identity
for the evidence state being blessed, and a serializable snapshot sufficient
to retain and assess that blessing. Concrete types supply these through
methods/properties; do not require one instance-field layout. A runtime-only
CheckPOI does not already supply them. Implement and test the contract on a
composed concrete type before declaring the extraction complete.

For this pass, preserve existing physical blessing store locations and
identities. Code and semantic workflow ownership can change independently
of physical storage. Do not automatically relocate retained data to a new
Archive partition. If current resolution couples these, expose the conflict
and resolve a bounded migration explicitly rather than silently moving data.

Introduce an independently owned BlessingsWorkflow, ordinarily under
tarav.l1.blessings, with BlessablePOI inheriting the neutral POI base.
Move existing blessing Records, store operations and assessment-specific
mechanics into that workflow. Keep the existing acceptance, assessment,
visibility and stale-state rules; this is not a policy redesign.

Adapt runtime registration, imports, collector presentation and SKW consumers.
Generic POI collection must work without assuming blessing/state attributes.
Blessings consumers can require the BlessablePOI capability. CheckPOI and
BlessablePOI must compose without duplicate initialization or conflicting
required constructors. Avoid adding blanket flags or check-only fields to
the neutral base as a shortcut.

Inspect existing Records and Type Ships before moving ownership. Preserve
identity where meaning remains the same; report any schema/retained ownership
migration explicitly. Do not silently reinterpret old Records, rewrite retained
stores, or add compatibility aliases. If a required data change is material,
resolve its exact scope before mutation. Keep existing output compatibility
where practical, but do not retain a parallel public finding ontology merely
to avoid adapting in-repository consumers.

### Notification emission and existing return contracts

NotificationPOI is the lightweight notification mechanism, analogous to
warnings.warn(): a producer emits a typed notification and continues its
ordinary operation. Delivery belongs to shared POI mechanics, not to an
Archive-specific output protocol. Creating a notification without delivering
it is insufficient.
<!-- tarav.breadcrumb a0cdd483a5acbd138ae4ac17764c97666338f44999d1fbdff65715b86e9151c0 -->

For Archive's existing skipped-remote warning, emit an Archive-owned
NotificationPOI through the shared emission path and continue returning the
artifact. Do not wrap or replace that return value, require a new result
object, or invent a Check merely to announce the event. Preserve the useful
notice rather than silently dropping it when no caller installed a collector.

Implementation proposal: reuse the shared emission mechanism if available;
otherwise add the smallest common path that makes a notice visible by default
and allows explicit collection by a caller. Keep construction distinct from
emission, avoid duplicate delivery, and do not add a logging or persistence
framework. Choose its exact API against the landed POI implementation.
Skills may retain its structured status results and expose typed POIs there;
it need not adopt Archive's return shape or a new checking engine.

## Impl.Req.Wiki

Product project: tarav-py.
Wiki owner/root: tarav-md/notes/wiki.
Relevant notes: poi-system.md and checks-workflow.md.
The preceding narrative and adjacent Breadcrumbs carry the bounded user intent;
Wiki links provide broader context. 832 is the prerequisite implementation
request, not a fixed API specification for this follow-up.

## Execution.Plan

1. Reconcile 832, read current project guidance/ARCHITECTURE.md, inventory
   affected consumers and existing blessing policies. Record the resulting
   bounded file scope and test baseline.
2. Extract Blessings ownership and introduce composable BlessablePOI.
   Implement its identity/state/snapshot contract and exercise a composed
   concrete type with BlessingStore. Preserve storage locations and existing
   blessing permissions.
3. Migrate References and Navigation's remaining older POI reporting.
4. Migrate Skills routing/status attention outputs and remaining SKW
   generation/document POIs without redesigning their engines.
5. Reuse or minimally complete shared POI notification emission, then migrate
   the existing Archive warning path without changing its artifact return.
   Preserve nonblocking capture and observable default delivery.
   Record native Kernel/Surface integration boundaries separately.
6. Verify each slice, attach supported product Breadcrumbs, update this log,
   and close scoped evidence commits plus selective Wiki capture.

## Verification

- Every migrated public POI value is an instance of the neutral base, with
  its concrete class entity owned by the producing workflow.
- BlessablePOI belongs to Blessings; CheckPOI remains owned by Checks.
- A concrete class can inherit both, instantiate successfully, expose its
  Check context, and participate in existing blessing mechanics.
- Non-blessable POIs remain usable without blessing fields or a Check.
- Blessable composition works end to end: the same concern/state resolves its
  existing blessing; changed evidence becomes stale; retained snapshot data
  does not depend on keeping the original runtime Check alive.
- Existing blessing stores remain at their current paths and retain identities.
- Existing blessable/non-blessable choices, assessment/stale-state handling,
  and visibility are preserved. Blessing does not hide a POI.
- No new mandatory CheckProvider, checks engine, or record persistence contract.
- Existing conditions still produce equivalent diagnostic meaning; source
  coordinates and context are not lost in the type migration.
- Archive registration still succeeds when reporting skipped remote locators.
  Notifications alone do not imply failure.
- Archive still returns its artifact. The typed notification is observable
  without custom caller setup and collectable explicitly; no duplicate warning
  or notification is emitted for the same reporting action.
- Lower layers do not import higher layers. Native parser diagnostics and
  Chatlas query matches are not incorrectly replaced with POIs.
- Run affected reference, navigation, skills routing, SKW generation/document,
  POI/blessing and Archive tests, architecture tests, Ruff and diff checks.
  Reinstall the editable CLI if command behavior changes.

## Impl.Log

Design only. No product code changed. Survey inspected the named sources;
shared worktree changes and 832 execution remain outside this documentation
pass. Exact constructors, exported occurrence names and retained-format impact
must be reconciled against 832 rather than guessed now.

2026-10-01 clarification: notification delivery is shared POI infrastructure,
not a reason to redesign Archive's return contract. Expanded the implementation
proposal with the minimal BlessablePOI contract and an explicit no-relocation
storage policy. These are design amendments; no product code changed.
<!-- tarav.breadcrumb 9ae73348c0294cad3fe3e22c656abfd2584930a512275bf433e01ca207c8f040 -->
