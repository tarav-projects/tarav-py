# Situation Chains — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: needs-alignment, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Model Situation → Check → POI → Action → Closing as one thing, a Situation
Chain: a class that groups the Types of those links and states how they
relate. Blessing is one Closing of a chain's Action, not a general model. A
Suite knows how to find situations and run Checks; Checks are atomic. External
tools follow the Gitleaks template: run the tool natively, keep its report,
and let a Suite find situations in it.

This request adds the chain base, gives every POI Type its own Action Type,
moves "may be blessed" from the POI to the Action Type's exits, and regroups
Gitleaks as the first chain. The other checks are regrouped by later requests.

Non-goals: changing Check Suites' role (they stay as they are, one consumer of
chains); the Project (left out of the chain); making the remaining
non-atomic checks atomic; a general positive-result POI (see Open questions).
<!-- tarav.breadcrumb f057195d5280 -->
<!-- tarav.breadcrumb 8284a2d3c8ea -->

## Design

### Why

Today the links exist but only implicitly: `CheckPOI` (`l1/checks`),
`ActionablePOI`/`BlessablePOI` (`l1/poi/actionable.py`),
`POIResolutionAction` with its `GoneClosing` and `Blessing` exits
(`l1/actions/pois.py`, `l1/actions/blessing.py`). Each looks general on its
own: `BlessablePOI` sits beside every POI as if any POI could be blessed, and
`Closing.reopens(record, poi)` is an open predicate on every exit (it invited
request 925's rejected pinning). The User's reading is that they are one model
whose Types are integrated, and that POIs have no evident use outside it.

### Decisions (User)

- Blessings model the Check → POI → Action chain only; it is one closing path
  of the actions. Do not overgeneralize; Tarav may provide several
  POI/Check/Action primitives.
  <!-- tarav.breadcrumb 2c07b9b3786e -->
- The chain is Situation → Check → POI → Action → Bless (or another Closing
  Type), called a Situation Chain: a set of Types implementing their
  relationships. Not every POI needs to scale to an action.
  <!-- tarav.breadcrumb 8a59b44133c0 -->
- `SituationChain` is a class; the Checks, POIs and Actions of a chain are
  modeled inside it. It encapsulates their Types; consumers decide what they
  instantiate.
  <!-- tarav.breadcrumb 68336e556533 -->
- All the POIs of one chain belong to it. Links are bound by a field. Chains
  may be instantiated, and an instance's identity is defined by its
  situation. Check Suites are not changed: they are one consumer of chains.
  The Project is left out for now. Existing Types are a regrouping, not a
  migration.
  <!-- tarav.breadcrumb fd8ed4dc6bde -->
- A chain works with one situation. Identity of its objects is
  hash(type, hash(situation)). A Check may produce several POIs, but there is
  one Action per POI and one POI per Action: a Type relationship, not an
  obligation to instantiate. Actions are their own objects and exist outside
  chains too; the chain is for modeling.
  <!-- tarav.breadcrumb fcab1b585ab7 -->
- Many situations of one kind are many instances of the same Chain Type.
  Every POI Type has its own Action Type, like Checks; there is no generic
  Action Type.
  <!-- tarav.breadcrumb a93b3bdfad15 -->
- The caller creates the situation and passes it to the Check. A Check must be
  atomic; one that reads a whole package and finds many problems is
  ill-conditioned.
  <!-- tarav.breadcrumb 1f0e715db2f1 -->
- A Suite knows how to run Checks; Checks are atomic. Suites nest, have
  names, and the Suite can be a generic Type.
  <!-- tarav.breadcrumb 0eeff34bfc3a -->
- External tools follow Gitleaks: run the tool's native checks, store its
  report as natively as possible, and let Tarav find situations by revisiting
  that report.
  <!-- tarav.breadcrumb a8113d3447d6 -->

### Current implementation observations

Inspected 2026-10-19:

- `l1/checks/__init__.py`: `Check` (identity None by default), `Situation`
  (`LiteRecord`), `CheckPOI(SituationPOI, ActionablePOI)`, `SituationCheck`
  (built with its situation; identity `fingerprint([type id, situation])`;
  `poi()` raises with exactly that situation and `run()` enforces it),
  `CheckSuite` (`produce()` yields Checks, nested Suites or results; `name`,
  `key`; `conclusive_for` decides "gone").
- `l2/skw/pois.py:freshness_checks` already works the chain way: the Suite
  side computes `current_context` and builds the whole situation; the
  `SituationCheck` only compares.
- `l1/poi/actionable.py`: `ActionablePOI.action` names an Action Type, default
  `Tarav.Actions.POI.Resolution`; `BlessablePOI` is a marker. Used by
  `_event()` (`"blessable"`) and `BlessingInputCheck`.
- `l1/actions/pois.py`: `action_id(poi)` = hash(Action Type id, POI identity);
  `POIResolutionAction.exits` = gone (`GoneClosing`) and blessed (`Blessing`).
- `l1/git/gitleaks.py`: native report in a depot (`GitleaksRun`,
  `GitleaksDepot`); one non-atomic `GitleaksCheck` raises `GitleaksMissing`,
  `GitleaksNeverScanned` and one `GitleaksFinding` per finding still in
  history; `GitleaksFindingResolution` writes the fingerprint to
  `.gitleaksignore` when blessed. `GitleaksStaged` is raised by the hook.
- About 22 modules define Checks; 4 are `SituationCheck`s (two Skillware
  freshness, `TestMarkerCheck`, `BlessingInputCheck`).
- Action store: 177 actions, all `Tarav.Actions.POI.Resolution`, none
  blessed.

### Agent decisions (proposals)

- `tarav.l1.chains` holds `SituationChain`, a Type whose class fields name its
  links: `Situation` (a `Situation` subtype), `Check` (a `SituationCheck`),
  `POIs` (its `CheckPOI` Types) and one Action Type per POI Type. Its
  instance holds one situation; identity hash(chain Type, hash(situation)).
  It imports Checks and Actions, so it sits above both.
- A POI Type's Action Type is declared by its chain. When a chain declares
  none for a POI Type, it derives a `POIResolutionAction` subtype whose
  TypeShip is derived from the POI Type's, named `<POI name>.Resolution`.
- Blessing becomes an exit an Action Type allows. `BlessablePOI` is removed;
  `Closing.reopens` becomes a fixed property of each Closing Type (gone
  reopens, blessed does not), not a predicate on the POI.
- Gitleaks: a Suite reads the latest report and produces one atomic
  `SituationCheck` per finding (situation `{repository, fingerprint}`) and one
  per repository for the binary and the scan (`{repository}`). Chains:
  Finding, NeverScanned, Missing, Staged.

### Open questions

1. Action ids change for every existing action when Action Types become
   per-POI-Type. No action is blessed; proposal: let them close as gone and
   reopen once (or delete the 177 records). Which?
2. Scope: this request = chain base, per-POI Action Types, blessing as an
   Action exit, Gitleaks as the first chain. The other ~20 checks later. OK?
3. The general positive-result POI ("checked and found fine", no Action):
   this request or a later one?

## Impl.Req.Wiki

- Product project: `tarav-py`. Wiki: `tarav-py/notes/wiki/`.
- Relevant notes: topical `situation-chains.md` (new), daily `2026-10-19.md`.
- Supporting chat: the session declared above.
- Capture status: see Impl.Log.

## Execution.Plan

Core data shape: `SituationChain` with class fields `Situation`, `Check`,
`POIs`, `actions` (POI Type → Action Type); instance = one situation.

1. Refactor — `SituationChain` base and its binding; a test chain (lamps) in
   `tests/test_situation_chains.py`. Check: a chain instance's Check, POI and
   Action identities follow hash(type, hash(situation)); a POI Type finds its
   chain and Action Type. Status: pending.
2. Feature — per-POI Action Types; blessing as an Action exit;
   `BlessablePOI` and `Closing.reopens(record, poi)` removed. Check: Actions
   workflow tests (blessing allowed only where the Action Type has the exit;
   gone reopens, blessed does not). Status: pending.
3. Refactor — Gitleaks as chains: a Suite over the native report producing
   atomic Checks. Check: `tests/test_gitleaks*.py` behaviour unchanged except
   identities; real `tarav status` on a repository with a scan. Status:
   pending.
4. Docs — ARCHITECTURE (Checks, POIs, Actions, Blessings rows),
   `l1/poi/README.md`, AGENTS POI bullets. Status: pending.

Deviation triggers: a link that cannot be bound without import cycles; a
check of the Actions workflow that depends on the generic Action Type name.

## Impl.Log

- 2026-10-19: request designed in the session above; needs alignment on the
  open questions.
