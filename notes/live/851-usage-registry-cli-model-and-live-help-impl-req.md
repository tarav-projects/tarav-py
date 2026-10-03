# 851 — Usage Registry, CLI model, and Live Help

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Execute complete.
Status: implemented and verified; the selected seven-day default and separate
Live Help workflow are provisional design choices.

Add a Usage Registry workflow where any workflow can leave traces of how it
was used, model the `tarav` command line as Tarav objects that register each
call there, and add a Live Help workflow
that makes a reactive section a standard part of every `--help`: where the
command's source is, how it was recently used, and a hint for its history.
<!-- tarav.breadcrumb eefda0f30a44054db611f85bbf620cb401bb140a461362d5e6ace5dd6068e0d0 -->

Non-goals: instrumenting workflows other than the CLI in this request;
recording non-`tarav` shell commands; a Git query workflow;
documentation staleness checks; any ranking or interpretation of recent uses;
changing existing command behavior, arguments, or exit codes.

## Design narrative

### Why

Modifying a skill in this session cost far more in learning the mechanics than
in writing content. The User's diagnosis: Tarav is developed without a minimal
contextualization path for understanding how Tarav itself works.
<!-- tarav.breadcrumb 9e8227d724114acba647438fa631a2a646215b70bbf0547a6f585518e87ee8d4 -->
<!-- tarav.breadcrumb 610ee664e5aaf45f42b2b9acc1fde7a9385a1557f51d8263efb17ee10922e754 -->

Contextualization paths are workflows, and several can exist. The User's
preferred one is to learn from live material: go to the source code, and to
active examples, meaning data recently used by that code, not samples dumped
into a skill that go stale. Written documentation is a last resource because
nothing yet raises a POI when the code it describes changes.
<!-- tarav.breadcrumb 8a365623e707d8112efd0a6ca0fd2ec76f0ffabb3496d687e3f893adc66efea9 -->

The code must stay dumb. Agents are smart; Tarav's job is to remove the
unprofitable work of searching a large code base and to hand over leads:
here are the declarations, here are recent uses and their paths. The Agent
navigates from there.
<!-- tarav.breadcrumb 29edd53063647765391efbc6602a63147c5eac8d5cbd02f68eb9ebf85df14cd0 -->

### CLI as Tarav objects

The User asked to model the CLI in Tarav so there is something typed to attach
tests, checks, and other workflows to, without being pedantic: the command
line as a workflow, and commands as objects that can be referred to. This is
how Tarav grows: type things, then hook workflows to each other.
<!-- tarav.breadcrumb c5553fcc1a424cfea73c9591350f9e02e87b8651aaa5e573a9b24e47f65689fa -->

Current code (inspected): all commands pass through `main()` in
`src/tarav/l3/cli/cli.py`. `build_parser()` composes one argparse tree via
`runtime.register_commands`; leaves set `handler` with `set_defaults` (about
138 handlers, 204 parsers). `main()` parses and calls `handler(args)`.

Agent proposal:

- `CliWorkflow`, a `TaravWorkflow` with its own `WorkflowShip`.
- `Command`: one object per parser in the tree, derived mechanically by
  walking the built argparse tree; never declared by hand, so it cannot drift.
  It holds the command path (`skw document record`), help text, and handler.
  The command path is its readable key. Its Ship is derived deterministically
  from that key, so nothing is stored (see Review decisions).
- Checks on `Command` through the existing Checks workflow, raising POIs such
  as missing help text or a handler whose source cannot be located. The User
  named missing help as an example of what the model should let us detect.
<!-- tarav.breadcrumb dea81d367d616c86b877b4d15f763cfc9702a28d755b22cea286d565cf6e92fc -->

### Usage Registry

Earlier in the discussion the registry was a CLI invocation log: every `tarav`
command stored with its arguments, queryable, keeping only a recent window
whose length is a parameter, in the central storage partition of its owning
workflow (`ArchivePartition(root, workflow_ship)` in
`src/tarav/l1/archive/records/navigation.py`, rooted at
`~/Documents/tarav/archive/<workflow-ship>/`).
<!-- tarav.breadcrumb 37cbdfc3fdd868f7927aa3560a609467aae9438b16ba8c464fa28c9f6b7a2d16 -->
<!-- tarav.breadcrumb 7f23ddd8cd4c44a51a4d9e625819a28e79e27832f0fa9ecb202ff3a0412b457d -->
<!-- tarav.breadcrumb 18dab50bc9bd2d818bed4d77b591ad1eb2af6e7becd4f90e5344fddbfc3dc3e9 -->

The User then generalized it. The registry is its own workflow with one clear
semantic: a place where you put your usage trace so Agents can discover fresh
examples of how Tarav is being used. It is like a logging system with a
specific meaning, which is why it is a workflow. It does not care what is
registered. Each workflow is responsible for knowing what to store so an Agent
can see how it was used; the registry provides only the minimal shape, handles
storage, and provides the query.
<!-- tarav.breadcrumb 41cfc576f94ac8ee2e3b6b7c5a11327a1f66e5eb3837c2225dc804ae3572f90d -->

It is not tied to the CLI. Tarav's main interface is the library and the CLI
is only a consumer, so a trace can be left from inside any method. A CLI
command is an obvious good point, since a public command marks a typical or
important path, but it is one client among others.
<!-- tarav.breadcrumb 0178c821187df29350b75528dad7385100e4b854a237bf2c5efae38c0af153b0 -->

Organization is minimal: each registering workflow may have its own partition
inside the registry. General metadata such as the project and the workflow of
the call lets Agents query back by those native Tarav objects; those queries
are built in. Beyond them, Agents send a general query: Tarav databases are by
default a set of JSON records, so the model is to iterate the records and
query their JSON.
<!-- tarav.breadcrumb 1d4db68395b52f43f2ef65dd4585e93b8c05f83e91f07661cbf20a89f9c4b005 -->

Agent proposal:

- `UsageRegistryWorkflow` owns one Archive partition. Each registering
  workflow gets one typed Archive folder in it, holding one JSON-lines file
  per day as plain workflow-owned files (see Review decisions).
- One library call, `record_usage(workflow, subject, payload, project=None)`,
  appends a `LiteRecord` with time, workflow, subject, project, harness
  session when cheaply resolvable, and the caller's free payload. It never
  changes the caller's result when a write fails: failures are swallowed and
  logged. Disk I/O remains synchronous and may add latency.
- Read side: iterate records filtered by workflow, project, subject, and
  time, plus an optional JMESPath expression over each record. `jmespath` is
  already a declared dependency of `tarav-py` and is currently unused.
- One CLI leaf, `tarav usage query`, exposing those filters.
- The rolling window and its trimming are declared in this workflow's
  constitution; trimming deletes day files older than the window.
- The CLI model is the first client: `main()` records each command call with
  subject = command path and a safe payload: outcome, duration, cwd, and
  supplied option names, never arbitrary values or the raw argument list
  (see Review decisions).

### Live Help

The help in Tarav is reactive, not static. A standard part of every help tells
the Agent where to find things. The User accepted this output shape:

```text
command:  skw document record
source:   src/tarav/l2/skw/document.py:412  (handler _record)
recent uses (3 of 17 in the last 7 days):
  2026-10-03 13:10  exit 0  options --source --generation
                    cwd tarav-md/skills/tarav-hugentics
history:  git -C <repo> log -5 -L412,450:src/tarav/l2/skw/document.py
```
<!-- tarav.breadcrumb 384234849baa7e56e61562e91f5890fbe816cd2f88309b4ad2e07fc4cc0099fd -->

Git is not integrated. The history line is a printed, ready-to-run command
built from the source location. A Git query workflow that objects hook into
was considered and deferred.
<!-- tarav.breadcrumb f0e947dddb6bc5e514b169b79d18aa55a44e90ebb1b51492a714b83f1cb074fc -->

Live Help is a contextualization workflow of its own. It exposes types that
the CLI workflow subtypes to declare that it takes part. Its working name
moved from "live context" to "live help".
<!-- tarav.breadcrumb 3069ba74a2b8c02ffc0a00bf59d29ab6d225b4aee375902ffbbb210eb893c780 -->
<!-- tarav.breadcrumb aa9560e5f28922fc2c963129e4b224f7cb5d252289a127689025a373e0b4720f -->

Agent proposal: `LiveHelpWorkflow` defines one small capability type, a
provider that returns a source location, a Usage Registry subject, and
plain-text hint lines, plus the renderer for the section above. Recent uses
are read from the Usage Registry. `Command` implements it. The section is produced only when help is
requested, through the parser's help formatting (see Review decisions), so
ordinary commands pay nothing.

Relevant existing design (inspected, not discussed with the User):
`TaravType.help()` in `src/tarav/l0/kernel/records.py` already returns a
class's `source_path` and `source_line` mechanically, and the Wiki's
`context-graph.md` describes static `help()` as the Type-level entry point
with reactive `context()` as the expandable route. Live Help should reuse
that source-location mechanism for handlers and stay consistent with it.

### Review decisions

A cold review of this request raised four specification gaps. The claims were
checked against the code and the User asked for these resolutions to be
written here.
<!-- tarav.breadcrumb 19e2cde98cbab2c39464d5804bfb343541e582d9a426f84ff4e187751fd7af8c -->
<!-- tarav.breadcrumb 67faff12225e18b121735bc9247249fed6eae258667edda05d4be2f3dde0f378 -->

1. Safe CLI trace. Raw arguments must not be retained or shown in help:
   `tarav run -- ...` can carry arbitrary code. The CLI client stores the
   command path, exit code, duration, cwd, and supplied option names. Words
   after a `--` separator and argparse remainder arguments are dropped. Named
   option values may themselves be credentials or arbitrary code, so they are
   absent from the default trace. A command-specific producer can later supply
   selected safe values. This follows the registry rule that the registering
   workflow decides what to store.
2. Help integration point. `argparse` prints help and raises `SystemExit`
   inside `parse_args()`, before `main()` reaches a handler, so a hook around
   the handler never sees `--help`. Use one `ArgumentParser` subclass for the
   root parser that appends the Live Help section when formatting help.
   Subparsers inherit the root parser's class, so the whole tree is covered,
   and exit behavior is unchanged.
3. Storage shape. `ArchivePartition.ls()` lists only child directories, so
   bare day files in a partition are not navigable Archive objects. Each
   registering workflow's space is one typed Archive folder created through
   the partition; its day files are plain workflow-owned files inside it,
   read by the registry's own query. Trimming is therefore maintenance of
   files inside a folder, not deletion of Archive records. The window is
   still declared in the `UsageRegistryWorkflow` constitution.
4. Command identity. A `TaravEntity` id must be a Ship. The command path is
   the readable key and the Usage Registry subject; the `Command` Ship is a
   UUIDv5 of that path under a fixed CLI namespace. A renamed command gets a
   new Ship and its old usage records keep the old key. Aliases are out of
   scope.
<!-- tarav.breadcrumb b7b856bc84ed9afe6f93384724dad9b935a8c54a4e1ddce569fb499df9817a53 -->
<!-- tarav.breadcrumb 2947768d6ca6eea25c3d93446ed31a9951f9973d33e554e527dac0355198b64c -->

### Trace content, superseding review decision 1

The first implementation recorded option names only, which made a recent use
too thin to serve as an example. The User decided to remove any truncation
and not to weigh privacy or security in this feature: the traces are local to
`~/Documents/tarav` and so already private, and the ruling principle is that
each workflow is responsible for what it stores for an Agent to see how it
was used. The CLI client now records the complete argument list, including
words after `--`, and Live Help prints it as a runnable `tarav ...` line.
<!-- tarav.breadcrumb aa143a761a6a4adf921983801203f19a870fa2e011e095fa6a4507ecb124bf2a -->
<!-- tarav.breadcrumb 56067a441a0b08a4b102d6e65800ab5db654e58a9cdbf4a83884a1a4251f3666 -->

### Provisional follow-ups

1. Live Help currently has its own workflow. Integration with a Command's
   reactive `context()` remains a later design choice.
2. The retention window defaults to seven days and can be configured in code.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant
notes: `context-graph.md` (progressive discovery, `help()` and `context()`),
`checks-workflow.md`, `poi-system.md`, `record-archive.md`, and the capture of
this design in `live-help.md`. Supporting chat: session `f5845518` above.

## Execution.Plan

1. Scoped start evidence checkpoint.
2. `tarav.l1.usage`: `UsageRegistryWorkflow`, `record_usage`, the filtered
   and JMESPath read, trimming, and `tarav usage query`. Tests: append then
   read round-trips; filters by workflow, project, and subject; a JMESPath
   query; trimming removes only files outside the window; a failing write
   does not raise.
   `tarav.l1.cli`: `CliWorkflow` and `Command` derived from a built argparse
   tree. Test on a small synthetic parser: every leaf yields one `Command`.
3. `tarav.l1.live_help`: the provider type and the section renderer. Tests
   with a fake provider.
4. `tarav.l3.cli`: in `main()`, record each call's safe trace in the Usage
   Registry after the handler returns or raises; build the root parser from
   the Live Help `ArgumentParser` subclass. Tests: a failing registry write
   does not change the exit code; `--help` of a leaf shows `source:` pointing
   at the handler's file and still exits 0; words after `--` never reach the
   registry; two builds of the tree give each command the same Ship.
5. Checks on `Command` for missing help text and unlocatable handler source;
   run them over the real tree and record the POI count, without fixing them.
6. Register the workflows in runtime, extend `tests/test_architecture.py` for
   the new packages, and update `ARCHITECTURE.md`.
7. Inlined Capture on each implemented surface, Wiki capture, completion
   commit.

Acceptance: `tarav <any command> --help` ends with the Live Help section;
after running a command, its help lists that use and `tarav usage query`
returns it; the registry sits in the `UsageRegistryWorkflow` Archive
partition; a non-CLI caller can record and query a trace; the configured suite passes.

## Impl.Log

- 2026-10-03 Design: note written from the discussion in session `f5845518`.
  Code inspected: `l3/cli/cli.py`, `l3/runtime.py` (`register_commands`),
  `l0/kernel/records.py` (`help()`), `l0/kernel/lite_records.py`,
  `l1/archive/records/navigation.py` (`ArchivePartition`),
  `l2/context/storage.py`, `l1/checks/__init__.py`. No product code changed.
- 2026-10-03 Design revision: the registry became the general Usage Registry
  workflow with the CLI as its first client, following the User's correction.
- 2026-10-03 Review decisions recorded: safe CLI trace, help integration via a
  parser subclass, typed folder with plain day files, UUIDv5 command Ships.
- 2026-10-03 Execute: the request was rechecked against current code. The
  default CLI trace was narrowed from truncated option values to option names
  because truncation can still retain secrets. The window defaults to seven
  days, matching the example. Registry, command projection, live help, and
  integration work is in progress; focused tests passed. A concurrent commit
  included the architecture paragraph and its test while this execution was
  running. Those changes remain in the intended product scope.
- 2026-10-03 Execute verification: the full configured suite passed (153 tests),
  Ruff passed, and the reinstalled `tarav` command showed the Usage Query help,
  recorded a call, and displayed it as a recent use. A full-suite failure first
  exposed a real Record loading mismatch: parser-derived `Command` and its
  bound Check cannot be reconstructed from a retained Record. They now remain
  runtime-derived Tarav Objects with stable Ships and inspectable projections,
  outside the dynamic Record registry. The corrected suite passed.
- 2026-10-03 Command metadata checks over the built tree inspected 213 parser
  nodes and surfaced 19 missing-help POIs and no unavailable-handler-source
  POIs. These findings were left for subsequent command owners.
- 2026-10-03 Product capture: new Breadcrumbs were submitted on the usage,
  CLI, Live Help, runtime, tests, and architecture surfaces. Existing moved
  positions were refreshed append-only. Wiki capture updated the daily note
  and `live-help.md`; their Breadcrumbs submitted and audited. Scoped completion
  commits are reported in the execution handoff.
- 2026-10-03 Trace content changed by User decision (commit `719b7d9`):
  `l3/cli/cli.py` records full `argv` and the option-name filter is removed,
  `l1/live_help` renders it, and `tests/test_usage_live_help.py` asserts that
  values and the Python remainder are kept. Focused tests (5) and the
  configured suite (156) passed.
