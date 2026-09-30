# 832 — Neutral POIs, Checks, and Breadcrumb audits

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
-->

## Impl.Abstract

Knowledge.Surface: wiki.
Alignment.Mode: Interactive.
Status: ready for implementation.

Integrate Breadcrumb audit warnings and refresh notifications into the shared
Checks/POI contracts, co-developing those WIP foundations. Keep the base POI
almost empty. NotificationPOI belongs to the POI workflow; CheckPOI belongs
to Checks. This request covers the necessary existing-consumer adaptation,
not a general redesign of every diagnostic subsystem.
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

CheckPOI couples an occurrence to the Check class explaining it. Checks may
be instantiated directly by the audit: the optional provider interface is
for exposing checks from objects, not a prerequisite for running them.
NotificationPOI reports an operation worth making visible, such as appending
a Breadcrumb position observation, without fabricating a Check.
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

The execution proposal is a neutral POI occurrence base, with CheckPOI carrying
the existing check-specific occurrence semantics where appropriate. Resolve
the existing POI declaration-name collision explicitly across maintained
callers; do not add misleading aliases or silently reinterpret old Records.
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
3. Adapt shared result/collector contracts and affected SKW consumers.
   Do not infer failure solely from POI presence. Preserve explicit emission
   and exception behavior rather than automatically raising during construction.
4. Implement a small number of bound Breadcrumb Checks, grouped by semantics
   and shared inputs. Replace duplicate finding representations with POIs.
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
  SKW reading checks, Breadcrumb tests and architecture tests pass after
  deliberate contract updates. Run Ruff and git diff --check.
- Reinstall the editable CLI after changing installed command behavior.

## Impl.Log

Design prepared from inspected code and the linked discussion. No product
code changed. Existing unrelated dirty implementation files are outside this
Design pass. Notification fields and exact outcome representation are bounded
implementation choices: choose the minimum needed, not a new general schema.
The latest user clarification arrived after the initial Chatlas refresh;
an additional exact-session refresh captured that new evidence.
