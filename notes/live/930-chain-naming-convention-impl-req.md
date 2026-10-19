# The chain naming convention — implementation request

<!-- tarav.sessions
3537df0a = claude-code:2bff854f-66a0-4e8c-8f96-9078af34c479 @3537df0a6015d884a94e9594478f971cb92e38df63776b87b5eea38741740d8a
-->

## Impl.Abstract

Status: ready, 2026-10-19.
Knowledge.Surface: wiki.
Alignment.Mode: interactive.

Name every Type of a Situation Chain after the chain, and end the name on
what the Type is: `<Chain>.<Extras>.<Kind>`, with `<Kind>` one of `Chain`,
`Check`, `POI`, `Action`. A helper builds these names, so the convention is
written in the code for the next chains, and defining a chain refuses links
whose names break it. The Gitleaks (4) and Skillware (19) chains are renamed;
the stored action records are migrated so nothing reopens or is lost.
<!-- tarav.breadcrumb e131043cd14d -->

Non-goals: Python class names; suite names (`Tarav.SKW.Suite.Skill` is part
of a suite's identity, which says when a situation is gone); POI Types that
belong to no chain outside Skillware (`Tarav.Git.Hooks.NotInstalled`, the test
workspace); shortening problem names; rewriting earlier live notes and Wiki
notes, which record the names as they were.

## Design

### Current behavior (inspected)

- Three styles coexist. Gitleaks is kind-last without a chain prefix:
  `Tarav.Git.Gitleaks.FindingChain`, `.FindingCheck`, `.Finding` (POI),
  `.Finding.Resolution` (Action); the Binary chain's POI is `.Missing` and the
  Scan chain's `.NeverScanned`. Skillware is kind-first:
  `Tarav.SKW.Chain.Source`, `Tarav.SKW.Check.Source`,
  `Tarav.SKW.POI.InvalidSource`, and the Action `Tarav.SKW.POI.InvalidSource.Resolution`
  (`SkwPOI.__init_subclass__`, `src/tarav/l1/skw/pois.py`).
- `SituationChain.__init_subclass__` (`src/tarav/l1/checks/chains.py`) binds
  `chain` on the Check and POI Types; it reads no name.
- Identities hash Type ids, never names: a check's
  (`SituationCheck.identity`), a POI's (`POI.identity`, class id) and an
  action's (`action_id`: Action Type id and POI identity). Renaming keeps
  them. Suite identities do use the name (`CheckSuite.identity`), hence the
  non-goal.
- Action Types are resolved by name (`resolve_action(run.data["action"])`).
  Stored action records hold names in `action`, `event.poi.type`,
  `event.poi.check` and `event.check.type`. 68 records of the shared store
  `~/Documents/tarav/records/8f3394a6-…` carry chain names: 62 Skillware
  (tarav-md) and 6 Gitleaks (tarav-py, tarav-md, taravangian-project).
  Without migration a renamed Action Type no longer resolves and
  `ProjectActions.refresh` silently skips the action.
- `Tarav.SKW.POI.ContextUnobserved` belongs to no chain; only the analysis
  `lint()` reports it (the agents-file path).
- Outside code, `tarav-md/.tarav/skillware/skills/tarav-hugentics/AGENTS.md`
  names `Tarav.SKW.POI.MissingMarkdownLink` for agents (a plain file in that
  depot, no source compiles it).

### Evidence and decisions

- The User asked to homogenize the names of a chain around one prefix, as
  `<Same.Prefix>.POI` and `<Same.Prefix>.Check`.
  <!-- tarav.breadcrumb 98867b7da022 -->
- It is a formalism for readability, not a behavior change.
  <!-- tarav.breadcrumb 6763a307a794 -->
- The name ends on the kind of Type, so it says what it is; extras, between
  the chain and the kind, are optional. `.Resolution` goes: an Action ends in
  `Action`.
  <!-- tarav.breadcrumb 9ce627ca8b41 -->
- A helper in the code builds the names, so the convention is communicated
  to further Types.
  <!-- tarav.breadcrumb 686319b45e6c -->
- Agent (accepted with the convention, not separately decided by the User):
  a POI and its Action always carry the problem as their extra, also in a
  one-POI chain, so a chain gains a second POI without a rename; the shared
  problem pairs a POI with its one Action Type. A chain and its Check have
  no extras.
- Agent: the problem is the POI's current short name (`InvalidSource`,
  `SkillMarkerMissing`), so the rename is mechanical and the Python class
  name stays searchable. For Gitleaks: Binary `Missing`, Scan `NeverScanned`,
  Finding and Staged `Reported` (what gitleaks reported; the hook may be
  overruled, so the staged report does not always block).
- Agent: defining a chain checks the names (chain ends in `.Chain`; its Check
  is `<prefix>.Check`; each POI is `<prefix>.<problem>.POI` and names
  `<prefix>.<problem>.Action` as its action). A chain that breaks the rule
  fails where it is written; no test has to remember it. This also enforces
  one Action Type per POI Type in every chain (the generic
  `Tarav.Actions.POI.Resolution` default cannot pass).
- Agent: `ContextUnobserved` becomes `Tarav.SKW.ContextUnobserved.POI`, so
  every Skillware POI derives its Action by the same rule (`.POI` →
  `.Action`).
- Agent: the records are migrated by a one-shot script outside Tarav, after
  the precedent `~/Documents/tarav/migrations/20260907-type-reference/`
  (script, `before.tar.gz`, mapping): exact old-name strings in action
  records become the new names, and the store's Git commits the result.
  Deleting them instead would drop their tapes and closings (56 are
  StaleContext actions, blessable) and reopen the open ones as new runs.

## Impl.Req.Wiki

Product project: tarav-py. Wiki: `notes/wiki/` in this repository
(`situation-chains.md`, daily `daily/2026-10-19.md`). Companion edit:
tarav-md's hugentics depot `AGENTS.md` (one name). Capture: pending.

## Execution.Plan

Data shape (`src/tarav/l1/checks/chains.py`):

```python
CHAIN_KINDS = ("Chain", "Check", "POI", "Action")

def chain_type_name(chain: str, kind: str, *extras: str) -> str:
    """<chain>.<extras>.<kind>; raises ValueError for another kind."""
```

`SituationChain.__init_subclass__` validates a concrete chain's names with
it, after the one-chain binding check.

| Chain prefix | POI problems |
|---|---|
| `Tarav.Git.Gitleaks.Binary` | Missing |
| `Tarav.Git.Gitleaks.Scan` | NeverScanned |
| `Tarav.Git.Gitleaks.Finding` | Reported |
| `Tarav.Git.Gitleaks.Staged` | Reported |
| `Tarav.SKW.<Chain>` (19, the chain's current short name) | the POIs' current short names |
| `Tarav.Test.Chains.Lamp` (test) | On |

1. **Refactor — the helper and the Gitleaks names.** `chain_type_name`;
   the 4 Gitleaks chains, Checks, POIs and Actions renamed with it. Check:
   `test_git_gitleaks.py` with its literal names updated, test_situation_chains.
   Status: pending.
2. **Refactor — the Skillware names.** 19 chains and Checks
   (`l2/skw/chains.py`), 42 POIs (`l1/skw/pois.py`), Actions derived
   (`SkwPOI.__init_subclass__`; `l2/skw/pois.py` uses `poi_type.action`
   already). Check: SKW tests with literal names updated; default suite.
   Status: pending.
3. **Migration — the stored records.** Mapping old → new name by Type id
   (old names from HEAD before slice 1, new from the code); backup; rewrite;
   commit in the records store. Check: 0 records with an old name;
   `tarav status` for tarav-py, tarav-md, taravangian-project: nothing
   opened or gone, same open counts (tarav-md 68 → 68; tarav-py 3).
   Status: pending.
4. **Feature — the chain checks its names.** Validation in
   `SituationChain.__init_subclass__`; the test chain's POI declares its
   Action. Check: new tests, a chain with a misnamed Check, a POI without a
   problem, and a POI naming another Action each fail at definition with a
   literal message; default suite. Status: pending.
5. **Docs.** The convention in the chains design note, the
   `SituationChain` docstring, the tarav-md depot `AGENTS.md` line. Status:
   pending.

Deviation triggers: an identity that changes with a name; a name consumed
somewhere this note does not list; a migrated action that opens, reopens or
closes on the next check run.

## Impl.Log

- Design: inspected `l1/checks/chains.py`, `l1/checks/__init__.py`
  (identities), `l1/actions/{__init__,pois,project}.py` (resolution by name),
  `l1/git/gitleaks.py`, `l1/skw/pois.py`, `l2/skw/{chains,pois}.py`,
  `tests/test_situation_chains.py`, the records store (68 records with chain
  names) and the migration precedent. Printed every chain's Check and POI
  names from the runtime; `ContextUnobserved` is the only Skillware POI
  outside a chain. Request 929 (another session) had removed the Publication
  chain: 19 Skillware chains.
