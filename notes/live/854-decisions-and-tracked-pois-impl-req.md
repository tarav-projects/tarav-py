# 854 — Decisions as the root type, and tracked POIs on a board

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
64298cbc = claude-code:9da4cef5-68b7-4d17-8a06-1351ca51e82f @64298cbc8db2e7aa971e0828653c07bcb483cfed40931fdf87d5abe7ce1c60b3
-->

## Impl.Abstract

Knowledge.Surface: wiki
Alignment.Mode: Interactive
Status: implemented (first slice; attention policy and g70203 adoption deferred).

Establish the scaffolding for two generalizations learned while redesigning
g70203 on Tarav:

1. **Decision** becomes the root type for the interventions users and agents
   make in a Tarav system. The existing Blessing becomes one Decision subtype;
   Order and Reported action are the first siblings.
2. **Tracked POIs**: a POI that a workflow chooses to record, with a
   lifecycle, on a **board** that any workflow can filter. Decisions attach to
   tracked POIs.

Non-goals: users as scorers; a final attention policy for orders or reported
actions; replacing the 849 attention report; migrating retained blessing data;
making tracking mandatory for any POI; g70203's own adoption (a separate
g70203 request will pilot this).

## Design narrative

### Origin

The User asked that what was learned in the g70203 redesign be documented in
Tarav and turned into an implementation request here.
<!-- tarav.breadcrumb 46f4dc0b62ef196cebeea8c75cb944ddb21efeeaf2d913f82d8a28ff7f0be7dd -->

A Tarav system is a superposition of workflows, each aimed at one problem,
sharing a significant amount of primitives. md-library's lint and co-reading
passes are the reference: both express their work to the agent as POIs.
<!-- tarav.breadcrumb caf30a4893ac78cb1cc5493eb1b8e0e40ad71f064b2655f627cf93923d06cb72 -->

### Decisions are never permanent

A system that asks a user to decide fails if decisions become permanent: a
mistaken decision would never resurface. Detection is separated from
decision, and every recorded decision is re-evaluated at different
priorities (the User's example: about a month, then three months after a
reapproval, up to about a year).
<!-- tarav.breadcrumb d950a736331552c0cd83c1a6599b9568db012da4029814431ca6814f978adf9e -->

### Blessing is one kind of Decision

A blessing is the decision that suppresses a POI. Decisions are broader: the
interventions made to modify the system, collected and continuously asserted.
Some are only reported, so an action can be traced later; such a decision
captures its context, for instance the Git commits and the diffs they
produce. Like the blessing implementation, a decision is assertable and can
hook into automatic scoring.
<!-- tarav.breadcrumb 3f422eee5ff2a2809b34b50d500461e423b36bc18e8f20e03132db48ca9a00c7 -->

```text
Decision: an intervention in the system, recorded and asserted over time
├── Blessing: suppresses (defers) a still-detected POI
├── Order: changes the data; its consequences are public
└── Reported action: captured for tracing (context, commits, diffs)
```

### Orders and blessings are asymmetric

An order's consequences live in the data, which is public and used by every
other check and consumer, so a wrong order is likely to be discovered; a POI
it causes is not suppressed by it. A blessing recognizes a live POI and
suppresses it. Decisions without a live POI need their own priority policy,
to be worked out later. Decisions are typed so each situation can be handled
differently by scheduling; when some show up too early, more workflows can
modify the order. The present work defines the main scaffolding.
<!-- tarav.breadcrumb 81a84025363bf7c71791ec088f15e861f4559f294217bddea0e01c7d02926cb0 -->

### Decisions are not scores

Scoring is the automatic, agent-evaluated path that assigns numbers to
assertions. A user decision is not a score: the user can be wrong, as an
agent can. The system that orders reassessment and spends resources (user
attention, agent tokens) may still give user decisions more authority than
agent decisions, quantitatively. Users as judges of a scoring system is a
separate conversation.
<!-- tarav.breadcrumb e92c30715b294644db3a98b39d967d098d9db69e8ea055235a76a69106920189 -->

### Tracked POIs, the board, and attention

"Attention" names the workflows that rank and sort POIs. The engine produces
POIs; recorded ones are like GitHub issues: explicit, and they need resolving
(closed, ignored, and so on). Some come from checks outside agent control,
others are introduced by agents. A board lets agents and any workflow see and
filter POIs, e.g. the unresolved POIs of their own workflow. Decisions attach
to recorded POIs. Generating POIs and prompting agents to resolve them is
already a driving force; with scoring the system starts to run by itself.
<!-- tarav.breadcrumb 1051e9b40278b4ac7c5ca5d091d32f149bbf335dde427ab33f7bdb749f2ba6eb -->

Not every POI is recorded; that is the workflow implementer's choice.
Notifications, for example, still use the POI system for contextualization
and Diagram integration. The recorded ones are **tracked POIs**, a name the
agent proposed and the User chose.
<!-- tarav.breadcrumb 4d9962d2349678fb3168941878047b566842d0e9b2b21c924128309e62bfbb6c -->
<!-- tarav.breadcrumb a962a28a157ce334f78f1bd3564f2fc173c15230aced274123be3523c705e6a9 -->

POIs are typed and can express any axes. `CheckPOI` forces a companion Check
class; `NotificationPOI` is raised text; more types will come. Being tracked
is an axis independent of those types.
<!-- tarav.breadcrumb 94a31d633228e327eb64243b8f60259266329497e242c05014052fab0adf87cf -->

### Current behavior (inspected 2026-10-03)

- `tarav.l1.blessings.store.BlessingRecord(TaravEntity, FileRecord,
  Assertable)` — Type Ship `1c218c7c-…`, name `Tarav.Blessings.Record`,
  fields `created_at`, `actor`, `rationale`, `support`, `poi` (a snapshot of
  the blessed POI). It already carries Assertions and a score vector (847).
- `BlessingStore` is an append-only file store (`add`, `bless`, `snapshot`,
  `load`); `BlessablePOI` is the opt-in POI capability.
- `tarav.l2.blessings.attention.attention_report` (849, commit `e419920`)
  pages current detections from a `POICollector` with blessing standing via
  a blessing-specific `BlessingAttentionPolicy`.
- POIs (`tarav.l1.poi.primitives`): `POI`, `IdentifiedPOI` (identity from
  Type and situation), `NotificationPOI`; `POICollector` is per-evaluation
  and in memory. There is no persisted POI registry, lifecycle, or board.

### Agent proposals (not User-approved)

- **Decision base, almost empty**, like the base POI: identity, `created_at`,
  `decider` (today's `actor`), `rationale`, `support`, and its subjects
  (tracked POI ids, records, surfaces). Assertable. Behaviour, including
  scheduling, lives in subtypes.
- **Re-parent `BlessingRecord` under Decision without changing its Type Ship
  or Record schema**, so retained blessings load unchanged.
- **Order** records what was changed and on whose authority; **Reported
  action** may wrap the existing commit-evidence record rather than define a
  new one.
- **Tracked POI** as a persisted Record holding the POI snapshot, owner
  workflow and history, with two independent dimensions (amended after
  review, see Impl.Log):
  - **detection**: `detected` / `not detected`, set only by evaluations whose
    declared scope covers the POI;
  - **disposition**: derived from the attached Decisions, which stay
    revisable and are scheduled by attention. It is never a terminal stored
    state, so a still-detected POI cannot quietly become permanently done.
  "Resolved" just means not detected. Re-detection is the same POI by
  situation identity.
- **Evaluation scope**: reconciliation consumes an evaluation that declares
  its scope (which Checks, which subjects) and signals completion. Only a
  completed evaluation covering a tracked POI may mark it not detected;
  absence from a partial or failed run changes nothing.
- **Storage root is separate from ownership.** The owning workflow is a
  field on the record and a board filter. Files live under whatever root the
  caller supplies: `BlessingStore` already supports an Archive partition
  (`from_archive`, under the POI workflow) and a Project-local root (SKW's
  `.skw/blessings`, `l2/skw/skills.py:159`).
- **Board** = a store plus filters (workflow, type, detection, disposition,
  subject), reusing
  the 849 paging conventions; attention ranks the board.
- Attention dispatch by Decision type (a policy method on each subtype) is the
  follow-up, not this request.

### Open questions for alignment

1. Is the first slice scaffolding only (Decision base, three subtypes, tracked
   POI store and board query), with attention dispatch left to a follow-up?
2. Re-parent `BlessingRecord` in place (keeping its Type Ship), or introduce
   Decision beside it and migrate later?
3. Is detection plus derived disposition the right model, and which
   Decision subtypes define the first dispositions?
4. Storage root: Archive partition (as `BlessingStore.from_archive`), a
   Project-local root, or caller-supplied with one default?
5. Ownership: is the owning workflow a required field on every tracked POI,
   and can a POI be shared by several workflows?

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant
notes: `decisions.md` (new, from this discussion), `poi-system.md` (section
"Tracked POIs, the board, and attention"), `checks-workflow.md`,
`assertions-scoring.md`. Related requests: 833–835 (POIs, situation
identity), 847 (Blessing assertions), 849 (blessing attention). Pilot
consumer: g70203 (`g70203-project/g70203-md/notes/wiki/attention-and-decisions.md`).
Supporting chat: Claude Code session `9da4cef5-68b7-4d17-8a06-1351ca51e82f`
(alias `64298cbc`). Wiki capture: done in tarav-md commit `8658372`.

## Execution.Plan

Executed as a bounded first slice after the User authorized execution and
asked the Agent to resolve the remaining alignment choices.
<!-- tarav.breadcrumb d76d35ebf17aba06251e4499b41155382039db71dbef26e8e004b38cb8d7dabb -->

1. Cold-read `l1/poi`, `l1/blessings`, `l1/scoring`, `l2/blessings` and
   their tests; confirm Record loading of retained blessings.
2. Add `tarav.l1.decisions`: `Decision` base (Assertable) and `Order`,
   `ReportedAction` subtypes; re-parent `BlessingRecord` per question 2.
3. Add tracked POIs: Record, store, and attaching Decisions. Add a scoped
   evaluation (declared Checks and subjects, completion signal) and reconcile
   detection only within a completed evaluation's scope: emitted → detected;
   covered but not emitted → not detected; outside scope or incomplete →
   unchanged. Disposition is computed from Decisions, not stored.
4. Add the board query (filters, paging) and expose it through the Project.
5. Tests: retained blessings load unchanged; each Decision subtype
   round-trips; detection reconciliation (including a partial run that must
   not resolve uncovered POIs, and a failed run that changes nothing); a
   still-detected POI with a Decision stays visible and revisable; board
   filters; both storage roots.
   Run focused and configured suites.

## Impl.Log

- 2026-10-03 Design: note written from the g70203 discussion; code inspected
  as listed under Current behavior. No product code changed.
- 2026-10-03 Design amended after an external review relayed by the User:
  (1) absence from one `POICollector` run is not resolution, so
  reconciliation needs a scoped, completed evaluation; (2) the
  `open/resolved/closed/ignored` states mixed detection with disposition and
  let a still-detected POI become permanently closed, contradicting the
  never-permanent decisions requirement, so detection and disposition are
  now separate; (3) storage root and workflow ownership are separate
  decisions. All three points were checked against the code and accepted.
<!-- tarav.breadcrumb f1b000250df40c007fd11d821f4c81350786e29699299c10cc4124333c4deaff -->
<!-- tarav.breadcrumb 5fc8429030c9375526217ab5c30104679e989f3b0e991448495161e4a8da23ec -->
- 2026-10-03 Execute: chose in-place `BlessingRecord` inheritance from
  `Decision`, preserving its Type Ship and stored schema. The shared role is
  still stored as `actor`, with `decider` as an accessor. `Order` and
  `ReportedAction` retain optional POI links and typed subjects. A generic
  main Assertion is inspectable but has no scoring case yet.
- Tracking is opt-in and caller-rooted. `TrackedPOIStore.reconcile` treats only
  completed evaluations with an *exact* caller-declared scope as evidence of
  absence; another scope or an incomplete run changes nothing. The board
  derives the first disposition (`blessed` or `unreviewed`) from attached
  Blessing Records, includes other Decision references, and never lets that
  disposition alter detection. `Project.poi_board()` uses local tracking and
  Decision roots; callers may supply an existing BlessingStore. The POI's
  concrete Type declares the owning workflow. These are first-slice choices,
  not a new universal attention policy.
- Verification: `uv run pytest -q` passed 156 tests; `uv run ruff check src
  tests` and `git diff --check` passed. Product Surface Breadcrumbs were
  submitted in the Decision and POI foundations, Blessing inheritance,
  assertions, board, Project entry, and focused tests; audits passed after
  refreshing three older stale locations in `blessings/store.py` and eleven
  older locations in `ARCHITECTURE.md`. Pure registration and import adapters
  had no additional justified annotation position. Wiki capture updated the
  2026-10-03 daily note and topical Decisions/POI notes; audits passed after
  refreshing older Decisions-note positions. Completion commit identities
  are reported in the execution handoff; they cannot be recorded in their
  own committed note without another commit.
