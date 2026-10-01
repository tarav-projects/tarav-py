# 832 — Neutral POIs, Checks, and Breadcrumb audits

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
1f561f5d = codex:01a0b984-4664-7871-934a-89cf92595b64 @1f561f5d8db849a3a445b83a91a5e94acbb80927f9c332d45322ac70f8705a74
-->

## Impl.Abstract

Knowledge.Surface: wiki.
Alignment.Mode: Interactive.
Status: implemented.

Integrate Breadcrumb audit warnings and refresh notifications into the shared
Checks/POI contracts, co-developing those WIP foundations. Keep the base POI
almost empty. NotificationPOI belongs to the POI workflow; CheckPOI belongs
to Checks. This request covers Breadcrumb audits and minimal shared-consumer
adaptation. The User deferred migration of SKW's finding model to another run.
<!-- tarav.breadcrumb 6fbf723b71c1035940b4a8c8acce1b2bb5d7c0002fddf864141d6bbd4d16d06d -->
<!-- tarav.breadcrumb 33bf30bbef04eb67ae5e2dd98a6957b1588fc429eb8286a2a905bc2f8473f08d -->
<!-- tarav.breadcrumb e92387dd92b3e8612133bff440107b94b8638676fc544a5eb7ed89bbd8273010 -->

Non-goals: mandatory CheckProvider adoption; automatic fixing inside a Check;
new notification persistence or logging framework; mandatory stack capture;
new blessing policy; Wiki restructuring; unrelated diagnostic migrations.

## Design narrative

A POI is a point-of-interest claim, not inherently negative and not itself
evidence of failure. Check code raises failure POIs by default, but that
convention does not prohibit positive or informational POIs.
<!-- tarav.breadcrumb c0ec70fe97110d9ff0ed02c475d942e1851f994f7e2633506017bdc9109922d8 -->
<!-- tarav.breadcrumb c5193360cd63707b7c21f7a803807036aef5a62aed7861b83a58ba7cc16d2836 -->

CheckPOI couples an occurrence to its bound Check object. Checks may
be instantiated directly by the audit: the optional provider interface is
for exposing checks from objects, not a prerequisite for running them.
NotificationPOI reports an operation worth making visible, such as appending
a Breadcrumb position observation, without fabricating a Check.
<!-- tarav.breadcrumb ba42b5bd22dd88d2238b5a196d3b8f2f2d2ae627f97f75ec43b51c5b39532845 -->
<!-- tarav.breadcrumb b10de143a269f2e7931cd6d6410799c0977a92b419f657308642d33549ad8827 -->
<!-- tarav.breadcrumb f5ba63037754ac8df27df5d7f3663580d0bb2db67f4685bffc167c7f37e10c39 -->

Keep the shared POI base almost empty: ordinary Tarav object/entity facilities
and the minimum shared handling contract demonstrated by these consumers.
Do not make Check references, check versions, evidence fingerprints, blessings,
severity, timestamps, location capture, or retained storage mandatory base
fields. NotificationPOI is owned by the POI workflow itself for now.
<!-- tarav.breadcrumb 812ade2fbd26d7ee133fb03902709579bae565a00447b81eea964cb51269b623 -->
<!-- tarav.breadcrumb c8f3081c55a6ac4748a185a5a2a3e307f149172e670125e3891cb3bb395c0325 -->

### Inspected implementation and proposed adaptation

These are implementation observations and agent proposals, not additional
user requirements. Reinspect before execution because this worktree is shared.

- src/tarav/l1/poi/primitives.py currently defines POI as a POICheck
  declaration subclass, not the desired neutral occurrence base. POIInstance
  requires a POICheck and derives identity/state from check, subject and evidence.
  Do not merely insert NotificationPOI under this check-bound constructor.
- The same module's collector requires POIInstance and assumes identity/state
  and blessing-related presentation. Keep check-specific behavior specialized;
  collecting a notification must not require invented check or blessing data.
- src/tarav/l1/checks/__init__.py has independently runnable Check and
  CheckResult, whose pois() exposes POIInstances. Its execution status is
  completed/incomplete/failed, not a success/failure judgment of the subject.
  Preserve that distinction; decide the smallest explicit outcome signal
  needed by the audit instead of using bool(result.pois()).
- src/tarav/l1/breadcrumbs/auditing.py has a separate BreadcrumbAuditFinding
  based on the older TaravPOIInstance marker. BreadcrumbAuditResult has findings
  and plain update mappings; ok currently means no findings.
- src/tarav/l2/breadcrumb_workflows/chatlas_context/ adds evidence checks;
  Git commit audits also consume the Breadcrumb finding contract. Include
  those direct consumers in the adaptation.
- src/tarav/l2/skw/reading_checks.py already produces shared CheckResults
  using POICheck declarations from pois.py. Adapt affected imports, constructors,
  registration and tests without expanding reading-path semantics.

The execution proposal is a neutral POI occurrence base and a bound CheckPOI.
Existing POICheck/POIInstance declarations stay operational until SKW's separate
migration. Resolve the POI declaration-name collision through explicit imports;
do not add aliases or silently reinterpret old Records.
<!-- tarav.breadcrumb 97c7272a55d020325c35bf98d9c8b6caf4a3fb8ce99ab4702005c898060da049 -->
Preserve existing Type Ships and concern/state identities where semantics
remain unchanged. Inspect retained Record impact before changing schemas;
if a retained migration is necessary, document and implement an explicit,
bounded migration rather than a reader fallback. No blanket data rewrite.

Audit orchestration may refresh positions before running read-only Checks.
Keep audit_annotations and the current CLI as the entry points. Successful
refresh produces NotificationPOI; unresolved validation concerns produce
CheckPOI. Failures of the refresh operation may be reported as contextual POIs
without pretending a successful mutation occurred. Keep notifications visible
in text and JSON; they alone must not cause a nonzero audit exit.
Default audits remain read-only, refresh remains opt-in and append-only,
and repeated runs do not create redundant position observations.

## Impl.Req.Wiki

Product: tarav-py.
Wiki owner/root: tarav-md/notes/wiki.
Context: poi-system.md, checks-workflow.md, breadcrumbs.md.
Supporting session and exact User Turns are embedded above. The note carries
the bounded design itself; Wiki links supply broader history, not missing
implementation requirements.

## Execution.Plan

1. Inventory direct POI/Check consumers, Record registration, blessings,
   collector rendering, and file/commit audit callers. Establish baseline tests.
2. Introduce the almost-empty neutral base and POI-owned NotificationPOI;
   move Check-coupled occurrence semantics into Checks-owned CheckPOI.
   Keep dependencies acyclic; inspect ARCHITECTURE.md before moving ownership.
3. Adapt shared result/collector contracts. Keep SKW's current findings
   operational with only the necessary declaration import change.
   Do not infer failure solely from POI presence. Preserve explicit emission
   and exception behavior rather than automatically raising during construction.
4. Implement a bound Breadcrumb Check. Replace audit-result finding
   representations with POIs; transient concerns may feed the Check.
   Keep mutation in audit orchestration, separate from Check execution.
5. Adapt file/commit audit output, runtime registrations, and focused tests.
   Retain surface/occurrence/context links and inspectable Check documentation.
6. Capture implemented surfaces through Breadcrumbs, run validation, update
   this log, and complete scoped evidence commits and selective Wiki capture.

### Acceptance and verification

- Instantiate a neutral POI/NotificationPOI without a Check or check metadata.
- A CheckPOI exposes its explaining Check class and occurrence evidence.
- Direct Check execution works without any CheckProvider.
- A completed Check can report failure POIs; completion is not validation success.
- Positive/informational POIs do not inherently fail an audit.
- A stale position without refresh yields a contextual CheckPOI and no writes.
- Refresh appends one observation and emits a NotificationPOI; unchanged rerun
  adds no observation. Surface text, identity, attachments and old observations
  remain intact. Ambiguity still requires attention rather than guessing.
- Mixed notification/failure output preserves both; exit status reflects failure.
- Commit audits and Chatlas attachment checks retain existing behavior.
- Existing POI identity/state, record round trips, collector and blessing tests,
  SKW reading checks (without migrating their finding model), Breadcrumb tests
  and architecture tests pass after
  deliberate contract updates. Run Ruff and git diff --check.
- Reinstall the editable CLI after changing installed command behavior.

## Impl.Log

Design prepared from inspected code and the linked discussion. No product
code changed. Existing unrelated dirty implementation files are outside this
Design pass. Notification fields and exact outcome representation are bounded
implementation choices: choose the minimum needed, not a new general schema.
The latest user clarification arrived after the initial Chatlas refresh;
an additional exact-session refresh captured that new evidence.

2026-09-30 execution: User clarified that CheckPOI couples to a bound Check
object and deferred the SKW finding migration. The neutral POI base,
NotificationPOI, and CheckPOI are implemented. File and commit audits now
expose mixed POIs; refresh remains opt-in and append-only. Old POICheck and
POIInstance identities, records, and blessing mechanics remain intact. A
bounded search of current Archive roots found no retained Records with the
former Tarav.POI declaration label or Tarav.POIInstance label. Focused POI,
Checks, SKW, Breadcrumb, and architecture tests pass (66). The full suite has
88 failures from an unrelated, currently disconnected Models worktree, with
1,341 tests passing. Ruff passes. Product capture and evidence closure remain.

Product capture completed on the POI base, CheckPOI, Breadcrumb audit Check,
ARCHITECTURE.md, and this request. New Breadcrumbs are
`68dda606d6ef2ed5711488bb952bbcacf278c1c2b6c1252738e0665c6885b48e`,
`0fbb6aeabe9a6b2dfb9a5f0b09d35e49a271b44f1cce37d88557bf09e452092f`,
`43e2d650575b47a3589da47e2f062ae65d74c9238883b59137993caa52c4f0fd`,
`28df20317b527872af6eb271a0ede8e2a1c30d0b8fc98201f63e8cb564ec6183`,
`ba42b5bd22dd88d2238b5a196d3b8f2f2d2ae627f97f75ec43b51c5b39532845`,
and `97c7272a55d020325c35bf98d9c8b6caf4a3fb8ce99ab4702005c898060da049`.
All audits resolved after the explicit position-refresh path appended updated
observations for older labels displaced by documentation edits. Wiki capture
updated the POI topical note and 2026-09-30 daily narrative; both audits pass.

A final regression review found that POI diagnostic fields named `context`
shadowed `TaravObject.context()`. They now use `details` or `audit_context` and
publish those values through `obj_context`; `CheckPOI` also publishes its bound
Check there. Regression tests exercise the normal context explorer. The new
Breadcrumbs are `462d77217023b71b5716e1fe68c4e3111cebca14f5df880365651773e88b2e59`,
`98efb14446fdafc5cbb4a98e2d0d162e31638150e69ea0198d0c4c6c3e0f7cd9`,
`596b1161c0983854154effc76ffa82d48ca21c56785d6915423fe9d12ff196cf`,
`e73444ba05e865201671436a374aa312fd999aa1cf64d4b89f76f2f60138980b`,
and `7d1653f323416c4b29b1ac815541cc406ae9051d39be08c3c8c8229fa63bfea1`.
All resolve cleanly. Wiki follow-up Breadcrumbs are
`ce67a9ca6579a653135e5c1873ca487a4bf48d575d50020541f07e4bb2c33137`
and `ccd1a91e24c36316b7f2574224d3906043d74bc3606b06c72459c9756bcce272`.
The final expanded focused suite passes 95 tests; Ruff and both repository diff
checks pass.
