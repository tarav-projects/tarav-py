# 876 — Context command and reported POIs — Impl.Req

<!-- tarav.sessions
abd0372d = claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a @abd0372dd06ffeef10c625e3f68354a234a91e4992b67406f075d93ccb20f4d4
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Status: ready. Phase: Develop (Design).

Give agents one general entry point for asking Tarav about an identifier: `tarav context --id <identifier> [--view <view>]`. It builds a typed context query, finds the object behind the identifier, and opens the same navigable Context that scripts reach through `.context`. Use it to improve the POI life cycle: a check report shows POIs compactly and opens with one header telling the agent to open a POI's context before acting, with the exact command, an example and a pointer to help. A dedicated view for a POI that has been reported to the agent answers what it is, where it came from, what was found, what to read first and what may be done. Two checks keep the connection honest.

Non-goals:

- Repairing any POI currently reported on the Taravangian projects. They are the test bench for this life cycle.
- A general Entity Registry. Only identifiers that can already be found are resolved.
- Guards that refuse to act on a POI whose context was not opened.
- Changing `tarav skw skills poi --id`; it is a later caller of this command.

## Design narrative

### Why

Reviewing today's bootstrap POIs showed that `tarav check` prints one-line summaries and an identity hash that no command accepts; the full record was only reachable by writing a script. The User took this as evidence that any presentation of data must give the agent a clear way to escalate to full context, because an agent should not act on limited context, and that guards may come later.
<!-- tarav.breadcrumb c91750dd57a92f4f60ebfb88c0daec7eb947cccd32ff273984675a17a7ca0a1e -->

The User wants this centralized instead of each surface implementing its own expansion, with the check output advertising it, and wants the connection itself to be checkable: when it is missing, that is a POI.
<!-- tarav.breadcrumb d07ce6a95ac583d38948b5237833bbaf2352ebf1f9079f4167a87881a9aedada -->

### Decisions by the User

It is not a POI-only command. An agent holding an identifier asks Tarav for its context through one common entry point. This is the existing `.context` system: the CLI finds the identity and lets the agent navigate, and search may be what finds it. The context can be qualified, so that a surface which showed the identifier can recommend the view suited to how the agent arrived there.
<!-- tarav.breadcrumb 1e90a92dfe28965823e9fa95072b1702e5690743f132cd709e4d5ed72e53be52 -->

The request is a query object, similar to Search: by default an identifier is looked up as the identity of something, with a typed and extensible query system that can start basic. It hooks into `.context`; scripts and the CLI are two doors to the same mechanic.
<!-- tarav.breadcrumb 6df009889260c62d9ec18aaef7f1d3ee1b8ec53760d78f8122000de7cdd2c13f -->

The qualifier is a context view type. For POIs the life cycle is: the POI is shown with its identifier and a small message, and the agent is told explicitly that before doing anything with any POI it must check its context, and how.
<!-- tarav.breadcrumb b2b8ae97c2c4b859279a7280ab1441488e3044fed1b8e8afc7f320aacd9ad89d -->

The instruction is stated once per output, as a header or footer, with the explicit command using placeholders, usage examples, and a prompt to read the command's help.
<!-- tarav.breadcrumb 6f5fca28e62ce06d5c6a7ce040b650ce8086a4963a319ef02c29f6637cb4174d -->

Tarav CLI arguments are always explicit key/value, so the identifier has a key. The view needs a clearer name than "poi": it is a POI that has been presented. Context may be added to POI instances and classes as needed. None of the POIs currently reported is to be repaired. The work follows the implementation Develop path.
<!-- tarav.breadcrumb 535e09c3f02fb5d5be89756f0ffc00356e0e5c1d4d72562f41247da685a7afb9 -->

### Current behavior (inspected 2026-10-08)

- `tarav.l1.context.explore(subject, type=...)` opens the general view or a typed `Context` subclass through `for_subject()`, which rejects unsupported subjects. `ContextExplorer` lists, selects and follows entries. There is no CLI over it.
- `tarav.l1.search` has `SearchQuery`, `SearchEngine` with `accepts()` and incremental hits, and `SearchService`, a registry-backed meta engine. The runtime owns one `SearchService`.
- `IdentifiedPOI` computes its identity from its Type and situation; `CheckPOI` binds the producing Check and contributes `check` and `details` to Context. `TaravType.help()` gives the class source path and line.
- `CheckRun.report()` groups POIs and `render_check_run()` prints the grouped report. Grouping by type, the default, prints no identifiers at all; only `--by identity` does. POIs exist only during the run.
- `tarav check --project` runs `report_project_checks()` inside the Project's harness environment, where Project-specific Types exist; the installed CLI process may not have them.
- Blessings apply to `BlessablePOI` only, which check POIs are not, so there is no cheap history of earlier actions for them.

### Design (agent proposal under the decisions above)

**Query.** `tarav.l1.context.query` adds `ContextQuery` (a `SearchQuery` carrying the requested view name and a navigation path) and `IdentityContextQuery` (adds the identifier). Resolution reuses Search: resolvers are `SearchEngine`s registered in a `ContextQueryService`, each accepting the queries it understands and yielding candidate subjects. One match opens; several are listed as candidates; none is reported with a hint. Unique prefixes are accepted.

**Views.** The service keeps named views: a name bound to a `Context` subclass. The general view is the default. The CLI prints which named views support the resolved subject.

**CLI.** `tarav context --id <identifier> [--view <name>] [--path <a/b>] [--json] [--limit <n>]`. Without `--path` it lists the entries of the opened context with their descriptions. `--path` walks entries; a container is listed and anything else is printed as its record, bounded by `--limit` lines. The command is a thin adapter over the service.

**Reported POIs.** A check run started by `tarav check --project` retains its POIs, best effort, in a machine-local store, one file per Project id under `~/.tarav/check-reports/` (`TARAV_CHECK_REPORTS` relocates it for tests). Each retained record is written in the harness process, so it carries what only that process knows: the POI's record with details, the POI class description and source, the Check class and source, the class's declared guidance, the Project, and the time. A resolver finds retained POIs by identity or prefix and yields a `ReportedPOI` object (`Tarav.POI.Reported`).

**View name.** `reported-poi`, Type `Tarav.POI.Reported.Context`. Its entries are `poi-type`, `raised-by`, `finding`, `read-first` and `may-do`. An entry for earlier actions is left out because no store records them for check POIs.

**Guidance on POI types.** `POI` gains two class-level declarations, what to read first and what may be done, empty by default, and one function that produces the instruction header. The four `Tarav.Project.Agents` POI types and the three skill bootstrap POI types are filled in as the worked example.

**Header.** `CheckRun.report()` adds the identity of its first identified POI, and `render_check_run()` prints, after the totals line, the instruction, the command with placeholders, one example built from that identity, how to list identifiers, and the help pointer.

**Checks.** `POIGuidanceCheck` walks the loaded POI types defined under a Project's root and raises one reminder POI per type that declares neither reading nor actions. `POIContextRoundTripCheck` renders a sample report, takes the example command from its header, and resolves it through the service; a missing header, an unparsable example or a failed resolution is a POI. A `PythonPackageProject` includes both when the POI base type's source lies under its root, which is true only where Tarav itself is developed.

**System prompt.** One sentence in the shipped Tarav System Prompt says to open a POI's context before acting on it; `tarav-py`'s agents file is produced and compiled again.

### Agent choices

The view name, the retention place, reusing Search for resolution, resolving Tarav Types by name or Ship as a second identifier kind, the condition under which a Project runs the two new checks, and leaving out the earlier-actions entry are agent choices made while the User was occupied, under the instruction to use common sense.

## Impl.Req.Wiki

Product: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant notes: `context-graph.md`, `poi-system.md`, `checks-workflow.md`, `agents-bootstrap.md`, daily `2026-10-08.md`. Supporting session: `claude-code:d82f1801-d3f2-4deb-9c95-297028a54b7a`. Capture status: see Impl.Log.

## Execution.Plan

1. Query service, identity query, named views, and a Type resolver; tests with stub resolvers for one match, several, none, and prefixes.
2. POI guidance declarations and header function; retained check reports; `ReportedPOI`, its resolver and view; tests with a temporary store.
3. Report example identity and the rendered header; retention from `report_project_checks`; the `tarav context` command; tests through the CLI.
4. The two checks and their inclusion; guidance for the seven bootstrap POI types; tests.
5. System prompt sentence, agents file recompiled, `ARCHITECTURE.md`; full suite, Ruff, isolated commit tree, CLI reinstall, harness sync; real use on the Taravangian root as listed in Verification; captures and scoped commits.

Verification on the root: the header appears with a working example; the example opens the view and two entries can be navigated; the general view opens for the same identifier; an unknown identifier and an ambiguous prefix are reported clearly; the earlier 64 POIs are unchanged apart from new reminders.

## Impl.Log

- Design inspection (2026-10-08): `l1/context/__init__.py`, `l1/search/__init__.py`, `l1/poi/primitives.py`, `l1/checks/__init__.py`, `l3/check.py`, `l3/runtime.py`, `l1/blessings/store.py`, `l2/project/decisions.py`, `l1/project/agents.py`. The shared worktree has unrelated edits, including `l3/runtime.py`; Execute stages only its own hunks.
