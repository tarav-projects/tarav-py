# 908 — The ObjectGroup context view — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented.

The extension's action page shows "Workflows" trees for three Types it picks
by hand (the action's, the POI's, the check's). Nothing in Tarav says why
those three. This request formalizes it: the objects that belong together
form an **ObjectGroup**, a context view any member opens with
`obj.context(type=ObjectGroup)`.

1. `ObjectGroup` (`tarav.l1.context.groups`) is a Context view. Its entries
   are the group's members, in chain order: situation, suites, check, POI,
   action, closing records. The Project is not a member.
2. No method is added to objects. Each workflow registers, for the Types it
   owns, a function naming their direct links; the view follows the links
   until nothing new appears, so every member opens the same group.
3. A member is a typed record (`Tarav.Context.Group.Member`): its role, its
   Type, and its id or key, or its value when it has no Type. A member that
   is not a live object (a check, a suite) is its Type and key, read from
   the records; building a group never runs checks.
4. `tarav context --id <id> --view object-group` shows it.
5. The extension's Workflows box becomes an "Object group" section built
   from the view; `workflows()` in its scripts goes.

Non-goals: groups for other kinds of object (Skillware blocks, Lines) until
one is wanted; following a member's own group from the page beyond one
click; a better name than `ObjectGroup` (the User keeps it for now).

## Design narrative

### User decisions

The Workflows graphs on the extension are ad hoc: why the action and the
POI, and not the check and other objects? Formalize it: an object declares
related objects, through a context view the extension uses, with names and
a proper model.
<!-- tarav.breadcrumb a5479ba1f2864a3ffb0c98d0fe8b6d4a812960ea4a3ae279b58ea43f9785732c -->

No new method on top of objects: it is a Context workflow, reached as
`obj.context(SomeView)`; subclasses still extend through inheritance. The
object returns the whole chain, Situation → Check → POI → Action, peeking
at the other objects as needed. "related" is too broad a word.
<!-- tarav.breadcrumb 53fb923a7236dfdf8ef66a832c2a81b8678003fa52f27e574bc370fdf166d122 -->

The User accepted the agent's model (below: contributors per workflow, the
view closing over direct links, the suites and closing records included,
the Project left out) and named the view `ObjectGroup`, to be renamed later
if a better name comes.
<!-- tarav.breadcrumb 624c46a91638b83f7210395c0d32ec9d5d28ca60502b52ed458415ee51bcfd2d -->

Build it, after the agent's last two points: members are entries named by
role, carrying Type and id; a member that is not a live object is its Type
and key, and a view never runs checks.
<!-- tarav.breadcrumb 70b33a45acc22c713ebf15c4809690037d288a926b05ab7c44699fcef4565bcc -->

### Current behavior (inspected)

- `TaravObject.context(*, type=None)` (`l0/kernel/records.py`) opens a view
  of a given Type through the runtime; `explore(..., type=View)`
  (`l1/context/__init__.py`) calls `View.for_subject(subject)`, which raises
  `TypeError` for a subject the view does not support. Typed views get no
  contributors. The one typed view today is `LineScope` (`l1/lines`).
- `ContextQueryService.register_view(name, view)` (`l1/context/query.py`)
  backs `tarav context --view`; `l3/cli/cli.py` builds the service and
  registers no view. `views_for(subject)` lists the views a subject supports.
- `l1/context` imports only `l0` and `l1.search`, so every workflow may
  import a module of it.
- A stored action (`ActionRun`) keeps `event.poi` (the POI record: Type,
  id, situation, `check` Type name), `event.suites` (`[{type, key}]`, outer
  first) and its tape, whose `Closed` entries hold the closing records. The
  POI record loads as a POI object (`type_named(POI, name)`); its check does
  not (`CheckPOI._from_record` leaves `check=None`, `raised_by` names it).
- A situation is a `LiteRecord`, not a Tarav Type: it has no Type name.
- Registration is explicit and module-level, done by the runtime:
  `register_action(POIResolutionAction)` in `l3/runtime.py`.
- The extension: `workflows(run)` in `scripts/_common.py` builds three
  chains; `pages.ts` `poiHtml(..., workflows, ...)` renders them with
  `workflowTree`.

### Proposals of the agent

**Links, not neighbours lists.** A registered function takes one object
and yields `Link(upstream, downstream)` pairs of members, the object itself
among them with its role. Direction gives the chain order: the view sorts
members so every upstream member comes before its downstream ones, ties in
the order found. So every starting member gives the same order.

**Who declares what.** Each workflow declares the links it owns:
- POI (`l1.poi`): a `SituationPOI` — situation → POI.
- Checks (`l1.checks`): a `CheckPOI` — check (its Type) → POI.
- Actions (`l1.actions.pois`): an `ActionRun` of a POI action — POI → action,
  each suite → the next and the innermost → check, action → each closing
  record; an `ActionablePOI` — POI → its action, when one is registered.

**Closure.** Starting from the subject, the view calls the functions
registered for each Type in the member's class hierarchy, for every member
that has a live object, until no new member appears. Members are the same
when role, Type, id and key are (the situation: role and value).

**Entries.** One entry per member, named by role (`situation`, `suite`,
`check`, `poi`, `action`, `closing`); a role with several members is
numbered in chain order (`suite-1`, `suite-2`).

**Extension.** The script opens the group of the action and gives each
member its Workflow chain, resolved from its Type name; the page shows one
row per member: role, Type, Workflow chain, and the value or id.

## Impl.Req.Wiki

Product project: `tarav-py`; also `vscode-tarav-center`. Wiki owner:
`tarav-md`, root `tarav-md/notes/wiki/`. Relevant notes: `poi-system.md`,
`context-graph.md`, `daily/2026-10-15.md`. Supporting chat: session
`abd0372d`. Capture status: done (`context-graph.md`, section "The
ObjectGroup view"; daily 2026-10-15).

## Execution.Plan

Core data shape: `Member` (role, type, id, key, value; a live object
attached, not recorded); `Link(upstream, downstream)`; a module-level
registry `{Type: [function]}`; `ObjectGroup(ContextFolder)`.

1. Feature — the view (tarav-py). `tarav.l1.context.groups`: `Member`,
   `Link`, `register_links`, `ObjectGroup` with closure and ordering. Check:
   a test with small Types of its own (closure from either end gives the
   same entries; ordering; unsupported subject raises `TypeError`).
2. Feature — the links. POI, Checks and Actions register theirs; the
   runtime registers them; `tarav context --view object-group`. Check: a
   test on a real POI action (the `.tarav/tests` workspace): the action and
   its POI open the same group, situation → suite → check → POI → action →
   closing; the CLI on a live action.
3. Feature — the extension. Script shape 9 gives `group`; the Object group
   section replaces Workflows; `workflows()` goes. Check: compile, script
   tests, the script on a live action, package and install.
4. Docs: `ARCHITECTURE.md` (context section and actions row).
5. Breadcrumbs, Wiki capture, commits per slice.

Risk: Type-name resolution for a member whose Type the running code lacks;
deviation trigger: a member Type unresolvable gives no chain, never an
error. Subtracted: `workflows()` and `workflowTree` in the extension.

## Impl.Log

- Design written from the discussion of 2026-10-15.
- Start checkpoint: skip — tarav-py, tarav-md and the extension were clean
  (only this note was new).
- Slice 1: `tarav.l1.context.groups` with `Member` (`Tarav.Context.Group.Member`;
  the member's Type is the field `member_type`, since `type` is the record's
  own), `Link`, `register_links`, `members()` and `ObjectGroup`
  (`Tarav.Context.ObjectGroup`); both in the runtime's record Types. Ties in
  the order are broken by role, Type, id and key, so the order never depends
  on where the walk began. Test `tests/test_object_group.py` (own small
  Types): the same five entries from either end, `fruit-1`/`fruit-2`; a
  member without a live object is not followed; no links, `TypeError`;
  Member round trip. 4 passed; architecture, record and context tests 142
  passed; Ruff clean. Breadcrumbs: 3 on `groups.py`, audited.
- Slice 2: links registered by the runtime (`l3/runtime.py`):
  `situation_links` (`SituationPOI`, l1.poi, with `poi_member`),
  `check_links` (`CheckPOI`, l1.checks: situation → check → POI),
  `run_links` (`ActionRun`, l1.actions: action → closing records, each after
  the previous), `poi_run_links` (`ActionRun`, l1.actions.pois: POI → action,
  suites outer first → check) and `poi_links` (`ActionablePOI`: POI → its
  registered action). The action member's Type is its Action Type
  (`Tarav.Actions.POI.Resolution`), not the record Type. Closing members are
  their Type and the `at` of their `Closed` entry. `tarav context --view
  object-group` registered in `l3/cli/cli.py`. Test
  `test_an_action_and_its_poi_open_the_same_object_group` (real
  `DocsProject`, opened, gone, reopened): the reopened action and a freshly
  raised POI give the same six entries, and the CLI query opens `closing`.
  Live: `tarav context --id fe1e4dca --view object-group` lists situation,
  suite, check, poi, action, closing. Whole `tests/`: 447 passed, 1 failed
  (`test_scoped_lines`, foreign). Ruff clean. Breadcrumbs on
  `poi/primitives.py`, `checks/__init__.py`, `actions/pois.py`, audited.
- Slice 1 committed `02e3b2e`; slice 2 `9c768e4`.
- Slice 3 (extension `2e8cf7e`, 0.0.19 installed): `group(run)` in
  `scripts/_common.py` opens the view and adds each member's Workflow chain,
  resolving its Type by name among `TaravType` subclasses (the runtime's
  record Types do not include checks, suites or Action Types); script shape
  9 gives `group`; `workflows()`, `workflowTree` and their CSS are gone; the
  page's Object group section is a table (member, Type, Workflows, id, key
  or value). Checks: compile, `test:scripts`, the script on the live action
  `fe1e4dca` (six members, five chains), the page rendered with a vscode
  stub.
- Slice 4: `ARCHITECTURE.md`, a paragraph under "Context queries". Doc and
  architecture tests: 47 passed.
- Breadcrumbs: audited on `groups.py`, `poi/primitives.py`,
  `checks/__init__.py`, `actions/pois.py`, `ARCHITECTURE.md`, this note, the
  extension's `scripts/_common.py` and the Wiki.
