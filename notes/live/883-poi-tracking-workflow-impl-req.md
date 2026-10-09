# 883 — POI tracking workflow and trackable check POIs — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive (the User is working elsewhere; ordinary ambiguities are resolved as recorded agent choices). Status: implemented. Phase: Develop; Design and Execute complete.

Give `tarav-py` a POI tracking workflow: a durable record of every tracked POI and of how its status changes over time. Every check POI is trackable and tracked by default. A check run hands its results to the tracker, which records both that a POI was raised and that its owning check finished without raising it. The status of a record is a set of independent axes, not one value. Two axes exist in this version: observation, written from check results, and blessing, read from the existing blessing store. Records can be listed with filters over axis values through a named POI renderer, and each one opens through `tarav context`.

Non-goals: a manual disposition axis; a discussion thread on a record; links between records; a scoring axis; automatic coupling between axes; retirement rules; migrating the blessing store; repairing any POI raised on a Project; changing any POI Type's situation; the Diagram `Finding` family (Impl.Req 881); other repositories.

## Design narrative

### What the User decided

Tracking is a capability. There is no reason not to track every check POI by default, because a check POI is defined by its situation. The trackable class has a setting that can disable a particular instance. POI tracking is its own workflow; the name "POI tracking workflow" is provisional.
<!-- tarav.breadcrumb f09275f080616b61f08ebcb87ebf32339076ac490536593fc176251fb1ae48e0 -->

The check run is the place where tracking integrates. A run starts from the beginning each time, so it gives the tracking system a new data point. It must register the positive sign, a POI was raised, and the negative sign, the owning check finished and did not raise that POI: "the check passed". The thing is not a board; it is a record system that tracks the state of POIs.
<!-- tarav.breadcrumb aaff7c9b610c0a61487576c2a54f442b792712022e1f6139b215bfae528ecc5b -->

Status must not collapse into a single value. It is a vector of statuses on separate axes. "Passed" is one status on one axis; it does not prevent closing a POI or saying more about it. The system is a database of every POI that has ever been tracked, like the issues of a GitHub repository: records stay for documentation and reference, and can be discussed indefinitely.
<!-- tarav.breadcrumb 2e8b8e8b0e514d03ad489e8db54445bc520ece4b7f59079425b76ff671265e5f -->

The existing tracking code is inspiration only. It may be redesigned from the ground up when that gives a better product.
<!-- tarav.breadcrumb ebb857740a54d4f2143f3bbe804a73075a8bff3ff1427e74fb2db02e284883dc -->

Blessing fits into the status as an axis. Workflows can add their own axes, more than one axis may speak about related things, and that overlap is allowed. The priority is a system flexible enough to express everything; it can be formalized and simplified later.
<!-- tarav.breadcrumb 2ab0227a441da56b2a9eaf33bef2377d03d527e47adb84e7a2ab2776331a9567 -->

The User asked for this request to be designed and executed.
<!-- tarav.breadcrumb b85ec1ab8ba2588a007571f916ee431640aec8553255d910934af7663582d81d -->

### First version the User accepted

The agent proposed this content and the User accepted it ("Nice"):

1. **Check identity.** A check can state who it is across runs. A `SituationCheck` gets identity from its Type and situation. A plain `Check` may declare one. Without identity, an absent POI is "not evaluated" and never "passed".
2. **Trackable capability.** A class that `CheckPOI` extends, with a `tracked` setting, default true, through the settings capability of Impl.Req 878. The Type declares; an instance may switch it off.
3. **Track record.** One record per POI identity, kept forever, with the POI snapshot, the owning check identity, and a set of axes. An axis is a named, typed entry with an owner workflow, a current value, and its own history of changes with when and by what. The core does not interpret what an axis means. Each axis Type declares the values it accepts. Any workflow can contribute one.
4. **Two axes.** Observation: active, passed, not evaluated; written only from check results; keeps the last time the POI was active and the last time it was evaluated. Blessing: read from the existing blessing store, which is not migrated.
5. **Hook.** Each `CheckResult` is one data point. The run hands its results to the tracker; checks only emit. On by default in `tarav check`; a script decides for itself. A check that failed, was incomplete, or did not run gives no evidence.
6. **Reading.** Filter by axis values; render through the renderer registry of Impl.Req 879 as a named renderer; open a record through `tarav context --id … --view …`. Keyed command options only.

### Agent proposals, not User decisions

- **Store location.** Records live inside the Project, in `.tarav/poi-tracking/`, one JSON file per POI identity, so that they travel with Git.
- **Write by default.** `tarav check` writes tracking by default; `--tracking skip` leaves the store untouched.
- **Relation to the check-report cache of Impl.Req 876.** The home cache `~/.tarav/check-reports/` stays. It answers a different question: what a surface last showed on this machine, so that a printed identifier can be opened, including for commands that have no Project. The tracking store is durable Project state. The `reported-poi` view gains one entry that names the command opening the track record.

### Agent choices made during design

- **Module.** A new package `tarav.l1.poi_tracking` owns the workflow, the capability, axes, the record, the store, the tracker, the context view and the renderer. `tarav.l1.checks` imports it for the capability and the data point; it does not import checks. The blessing axis lives in `tarav.l2.blessings.tracking` and the Project accessor in `tarav.l2.project.tracking`, so that the collapsed import graph in `tests/test_architecture.py` stays acyclic.
- **Removed.** `tarav/l1/poi/tracking.py` (`TrackedPOI`, `TrackedPOIStore`), the package `tarav/l2/poi/` (`TrackedPOIBoard`), `Project.poi_board()`, and their tests. No alias is left. `Project.poi_tracking()` replaces the accessor.
- **Per-instance switch and the explicit settings rule.** The settings capability includes another Type's partition only when a Type lists it in `settings_include`; that was a User decision in 878. So every check POI is trackable and tracked, and a POI Type that wants the per-instance switch lists `TrackablePOI` in `settings_include`. An instance of a Type that does not include the partition cannot be switched off. This is the reading of "the Type declares, the instance may switch off where the Type allows". See open question 1.
- **Whole run.** `not evaluated` for a record no data point touched is written only when the caller says the data points are the provider's whole suite. `tarav check` says so. A script handing a partial run leaves untouched records as they were.
- **Derived axes.** An axis may derive its value from its own source. The tracker writes derived values, with history, when it observes a run. A read overlays the current derived value without writing, so a listing is accurate between runs and reading never changes files.
- **Unreadable record files.** They are reported as a notification POI Type and skipped; they do not stop an observation.
- **Context resolution.** A track record resolves only for queries that ask for the `tracked-poi` view, so the general view of a POI identifier stays unambiguous. `ContextQueryService.open()` keeps only the candidates the requested view supports.
- **Timestamps in the record.** The two times of the observation axis are stored in the record, so every run rewrites every evaluated record. See open question 2.

### Identity drift

A POI whose situation contains volatile details, such as a line number or a count, gets a new identity when the detail changes. The old record then reads "passed" and a new one reads "active". That is mechanically correct and will look like churn. This request does not change any POI situation; Impl.Log lists the examples seen on the root Project.

### Current behavior this replaces

- `tarav/l1/poi/tracking.py`: `TrackedPOIStore.reconcile(collector, scope=, completed=)` compares one whole evaluation under one scope and one completion flag, keeps one `detected` boolean and one mixed history, and raises when a POI appears under another scope. Nothing calls it outside tests.
- `tarav/l2/poi/board.py`: `TrackedPOIBoard.report()` joins tracked records with blessings and decisions.
- `tarav/l2/project/__init__.py`: `Project.poi_board()` opens that board at `.tarav/tracked-pois`.
- `tarav/l3/check.py`: `report_project_checks()` runs the suite, retains the reported POIs in the home cache and renders through `tarav.l1.poi.rendering`.
- `tarav/l1/checks/__init__.py`: `Check` has no identity; `SituationCheck` holds a situation; `CheckPOI` extends `IdentifiedPOI`.
- `tarav/l1/settings/__init__.py`: `SettingsProvider` with nested `SettingsInterface` and `settings_include`.
- `tarav/l1/blessings/store.py`: `BlessingStore.snapshot()` and `standing()`; a blessing record carries `poi.id`.

### Public shape to build

```text
tarav.l1.poi_tracking
  POITrackingWorkflow
  TrackablePOI(POI, SettingsProvider)   setting: tracked (default true); tracking_enabled()
  TrackAxis(TaravType)                  key, accepted values, optional derive(record), caller_writable
  ObservationAxis(TrackAxis)            active | passed | not-evaluated; tracker only
  CheckObservation                      one data point: check type, check identity, status, POIs
  TrackRecord                           Record Type Tarav.POI.Tracking.Record
  TrackRecordStore(root)                one file per POI identity
  POITracker(store, axes=())            observe(points, whole=, at=), set(...), records(...), report(...)
  TrackRecordUnreadable(NotificationPOI)
  TrackedPOIContext, TrackRecordResolver, view name "tracked-poi"
  renderer "Tarav.POI.Tracking.Renderer"
tarav.l1.checks
  Check.identity -> str | None          SituationCheck: fingerprint of Type and situation
  CheckPOI(IdentifiedPOI, TrackablePOI)
  CheckRun.observations(), CheckRun.track(into=, whole=, at=)
tarav.l2.blessings.tracking   BlessingAxis(store)   blessed | unblessed, derived
tarav.l2.project.tracking     open_tracker(project)
tarav.l2.project.Project.poi_tracking()
tarav check --project [PATH] --tracking {write,skip}
tarav poi tracking list --project [PATH] [--axis KEY=VALUE]... [--type T] [--check C]
                        [--limit N] [--offset N] [--renderer NAME] [--level L] [--json]
tarav context --id <poi-id> --view tracked-poi
```

Observation rules, per data point merged by check identity:

| Situation | Value written |
| --- | --- |
| A trackable, enabled POI was emitted | `active` |
| Record owned by this check identity, check completed, POI not emitted | `passed` |
| Record owned by this check identity, check not completed, POI not emitted | `not-evaluated` |
| Record not touched by any data point, caller declared the whole suite | `not-evaluated` |
| Record not touched, partial run | unchanged |

A history entry is appended only when a value changes.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`, `capabilities-by-subtyping.md`, `settings-capability.md`, `checks-workflow.md`, daily `2026-10-08.md`. Related requests: 854 (old tracked POIs), 876 (context command and reported POIs), 877 (atomic POI Types), 878 (settings capability), 879 (renderer registry). Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Open questions for the User

1. Should every check POI instance be switchable without its Type listing `TrackablePOI` in `settings_include`? That needs an exception to the explicit-inclusion rule of the settings capability.
2. The record stores the last-active and last-evaluated times, so each `tarav check` rewrites every evaluated record and leaves the Project's Git tree modified. Alternatives: keep those two times in one per-run file, or outside the Project.
3. Is `.tarav/poi-tracking/` inside the Project the right place, and should a child Project checked through its root be tracked in the root's store, as now, or in its own?
4. Names: `tracked-poi` for the view, `Tarav.POI.Tracking.*` for the Types, `tarav poi tracking list` for the command, `--tracking write|skip` for the switch.

## Execution.Plan

Each slice ends with its focused tests passing; the executor may stop between slices and must log done, partial and next.

1. **Core.** `tarav/l1/poi_tracking/`: workflow, capability, axes, record, store, tracker. Tests: positive, negative, no evidence, identity-less check, disabled instance, axis from another workflow, caller cannot write observation.
2. **Checks hook.** `Check.identity`, `SituationCheck` identity, `CheckPOI` extends `TrackablePOI`, `CheckRun.observations()` and `track()`. Tests through a real `CheckSuite`.
3. **Blessing axis and Project accessor.** `tarav/l2/blessings/tracking.py`, `tarav/l2/project/tracking.py`, `Project.poi_tracking()`. Remove `l1/poi/tracking.py`, `l2/poi/`, `Project.poi_board()` and their tests; update runtime registration and the record-contract test list.
4. **Reading.** Renderer, context view and resolver, the view filter in `ContextQueryService.open()`, the `reported-poi` pointer entry, `tarav poi tracking list`.
5. **`tarav check`.** `--tracking write|skip`, the tracking line in text output and the `tracking` key in JSON.
6. **Guidance and verification.** `ARCHITECTURE.md` and the agents-file source; full suite and Ruff; reinstall the tool and resync the root harness; run `tarav check --project` at the root twice and record what was written.

Stop rule: a slice whose tests cannot be made to pass is reverted to the previous slice's state, for the executor's own hunks only, and logged as partial with the failing test.

## Impl.Log

- 2026-10-09 Design written from the discussion in the supporting session. Inspected: `l1/poi/{primitives,tracking,reporting,rendering}.py`, `l2/poi/board.py`, `l1/checks/__init__.py`, `l1/settings/__init__.py`, `l1/blessings/{capability,store}.py`, `l2/project/{__init__,decisions}.py`, `l3/check.py`, `l3/cli/cli.py`, `l1/context/query.py`, `tests/test_architecture.py`, `tests/decisions/test_decisions_and_tracking.py`.
- Files the plan touches that carry someone else's uncommitted edits: `src/tarav/l3/check.py`, `src/tarav/l3/runtime.py`, `tests/kernel/test_object_record_contract.py`, `tests/test_architecture.py`, `ARCHITECTURE.md`, `AGENTS.md` and its Skillware source. Only this request's hunks are to be staged there.
- No `tracked-pois` folder exists in the workspace, so the removed Record Type has no retained data to migrate.
- 2026-10-09 Start checkpoint `8fb8efa` (empty). All six slices done.
- Slices 1 to 3: `src/tarav/l1/poi_tracking/__init__.py`, the hook in `src/tarav/l1/checks/__init__.py`, `src/tarav/l2/blessings/tracking.py`, `src/tarav/l2/project/tracking.py`, `Project.poi_tracking()`. Removed `src/tarav/l1/poi/tracking.py`, `src/tarav/l2/poi/`, `Project.poi_board()` and five old tests in `tests/decisions/test_decisions_and_tracking.py`.
- Slice 4: `src/tarav/l1/poi_tracking/views.py` (renderer `Tarav.POI.Tracking.Renderer`, view `tracked-poi`, resolver), the view filter in `ContextQueryService.open()`, the `track-record` entry of the `reported-poi` view, `src/tarav/l3/poi_commands.py`. `POISelection` gained `context_view`, so the default and JSON-lines renderers print the right context command for tracked records.
- Slice 5: `tarav check --tracking write|skip`; one "POI tracking:" line in text output and a `tracking` key in JSON. A tracking failure prints to standard error and never changes the check's exit code.
- Changes outside the plan, each needed by it: `contribute_settings` adds the `settings` Context entry only for Types that declare or include settings, since every check POI is now a settings provider; the command module is named `l3/poi_commands.py` because the import-graph test collapses layers by module name; the POI snapshot in a record drops `help`, which holds machine-local source paths.
- Tests: `tests/test_poi_tracking.py`, 10 tests (positive and negative, no evidence, identity-less check, disabled instance, axis from another workflow, blessing axis, unreadable file, rendering and context, hand-built data point). Shared worktree: 232 passed, Ruff clean. Exact commit tree exported alone: 222 passed, Ruff clean.
- Product commit `0d524e2`, built from a temporary index so that other people's uncommitted hunks in `src/tarav/l3/check.py`, `src/tarav/l3/runtime.py`, `ARCHITECTURE.md` and `pyproject.toml` stay out. It therefore has no commit-message Breadcrumb evidence. One line of this request stays uncommitted: the rename of the removed Record Type inside someone else's uncommitted list in `tests/kernel/test_object_record_contract.py`.
- Inlined Capture: ten Breadcrumbs across `l1/poi_tracking/__init__.py` (6), `l1/poi_tracking/views.py`, `l2/blessings/tracking.py`, `l3/check.py`, `tests/test_poi_tracking.py`; audits clean after a position refresh in `l3/check.py`.
- Tool reinstalled and root harness resynced. `tarav check --project` at the root, twice: 365 checks, 151 POIs; first run wrote 149 records to the root's `.tarav/poi-tracking/` (898 KB), second run created none and rewrote all 149 for the evaluation time. All 149 read `observation=active`, `blessing=unblessed`. `tarav poi tracking list` and `tarav context --id <id> --view tracked-poi` were exercised on them.
- Finding from that run: 135 of the 149 records belong to checks that state no identity (`Tarav.Checks.POIGuidance` 98, `Tarav.SKW.Check.ReadingDeclarations` 16, `Tarav.SKW.Check.ReadingCoverage` 12, `Tarav.Project.Dev.ProvisionalMarkers` 9). They can never read `passed`. Only `Tarav.SKW.Check.ContextFreshness` (14) states one. Follow-up: give those checks an identity that does not contain a machine-local path.
- Identity drift: no situation on the root contains a number. `Tarav.Project.Dev.ProvisionalMarker` keeps its count in the message and not in the situation, so its identity is stable while the count changes.
- Wiki capture: `tarav-md/notes/wiki/poi-system.md` (new section) and `daily/2026-10-08.md`, ten Breadcrumbs, audits clean, commits `be8686e` (start) and `342c32d`.
- Follow-ups: identities for the four checks above; a manual disposition axis; a discussion thread on a record, probably in the Project's Decisions store; links between records; a scoring axis; a notification when axes disagree, such as a closed POI turning active; retirement rules; the four open questions above.
