# 851 — CLI model, Live Help, and command invocation registry

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design only.
Status: needs alignment on the open questions below; otherwise ready.

Model the `tarav` command line as Tarav objects, record every `tarav`
invocation in a registry owned by that model, and add a Live Help workflow
that makes a reactive section a standard part of every `--help`: where the
command's source is, how it was recently used, and a hint for its history.
<!-- tarav.breadcrumb eefda0f30a44054db611f85bbf620cb401bb140a461362d5e6ace5dd6068e0d0 -->

Non-goals: recording non-`tarav` shell commands; a Git query workflow;
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
  Identity is the command path, not a UUID, so a removed command leaves
  honest history behind.
- `CommandInvocation`: one record per call.
- Checks on `Command` through the existing Checks workflow, raising POIs such
  as missing help text or a handler whose source cannot be located. The User
  named missing help as an example of what the model should let us detect.
<!-- tarav.breadcrumb dea81d367d616c86b877b4d15f763cfc9702a28d755b22cea286d565cf6e92fc -->

### Invocation registry

Every `tarav` command is stored: which command, its arguments, and so on. The
registry must be queryable and may keep only a recent window (two days, three
days, a week); the window is a parameter.
<!-- tarav.breadcrumb 37cbdfc3fdd868f7927aa3560a609467aae9438b16ba8c464fa28c9f6b7a2d16 -->
<!-- tarav.breadcrumb 7f23ddd8cd4c44a51a4d9e625819a28e79e27832f0fa9ecb202ff3a0412b457d -->

It lives in Tarav's central storage, in the partition each workflow has
there. Inspected mechanism: `ArchivePartition(root, workflow_ship)` in
`src/tarav/l1/archive/records/navigation.py`, rooted at
`~/Documents/tarav/archive/<workflow-ship>/`; Context and the Test workflow
use it today.
<!-- tarav.breadcrumb 18dab50bc9bd2d818bed4d77b591ad1eb2af6e7becd4f90e5344fddbfc3dc3e9 -->

Agent proposal: each invocation is a `LiteRecord` appended as one JSON line to
a per-day file inside the `CliWorkflow` partition, holding command path, argv,
cwd, exit code, duration, start time, and the harness session when
`tarav chatlas current-session` mechanics can resolve it cheaply. Trimming
deletes day files older than the window. The write happens in `main()` and
must never fail or slow the command: errors are swallowed and logged.

### Live Help

The help in Tarav is reactive, not static. A standard part of every help tells
the Agent where to find things. The User accepted this output shape:

```text
command:  skw document record
source:   src/tarav/l2/skw/document.py:412  (handler _record)
recent uses (3 of 17 in the last 7 days):
  2026-10-03 13:10  exit 0  --source SKILL.skw.json --generation 954e…
                    cwd tarav-md/skills/tarav-hugentics  session claude-code:4ee3…
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
provider that returns a source location, recent uses, and plain-text hint
lines for a subject, plus the renderer for the section above. `Command`
implements it. The section is produced only when help is requested, so
ordinary commands pay nothing.

Relevant existing design (inspected, not discussed with the User):
`TaravType.help()` in `src/tarav/l0/kernel/records.py` already returns a
class's `source_path` and `source_line` mechanically, and the Wiki's
`context-graph.md` describes static `help()` as the Type-level entry point
with reactive `context()` as the expandable route. Live Help should reuse
that source-location mechanism for handlers and stay consistent with it.

### Open questions

1. Is `LiveHelpWorkflow` a new workflow beside Context, or should recent uses
   be contributed to a `Command`'s existing reactive `context()`, with Live
   Help only rendering it? The User asked for a workflow; the Agent notes the
   overlap and recommends a small separate workflow that reuses `help()`.
2. A rolling window deletes Archive records routinely. The Constitution allows
   explicit Archive maintenance; the Agent recommends declaring the window in
   the `CliWorkflow` constitution. The User has not answered.
3. Default window length.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Relevant
notes: `context-graph.md` (progressive discovery, `help()` and `context()`),
`checks-workflow.md`, `poi-system.md`, `record-archive.md`, and the capture of
this design in `live-help.md`. Supporting chat: session `f5845518` above.

## Execution.Plan

1. Scoped start evidence checkpoint.
2. `tarav.l1.cli`: `CliWorkflow`, `Command` derived from a built argparse
   tree, and `CommandInvocation` with its append and windowed read. Tests on a
   small synthetic parser: every leaf yields one `Command`; append then read
   round-trips; trimming removes only files outside the window.
3. `tarav.l1.live_help`: the provider type and the section renderer. Tests
   with a fake provider.
4. `tarav.l3.cli`: in `main()`, record each invocation after the handler
   returns or raises, and attach the Live Help section to help output. Tests:
   a failing registry write does not change the exit code; `--help` of a leaf
   shows `source:` pointing at the handler's file.
5. Checks on `Command` for missing help text and unlocatable handler source;
   run them over the real tree and record the POI count, without fixing them.
6. Register the workflows in runtime, extend `tests/test_architecture.py` for
   the new packages, and update `ARCHITECTURE.md`.
7. Inlined Capture on each implemented surface, Wiki capture, completion
   commit.

Acceptance: `tarav <any command> --help` ends with the Live Help section;
after running a command, its help lists that use; the registry sits in the
`CliWorkflow` Archive partition; the configured suite passes.

## Impl.Log

- 2026-10-03 Design: note written from the discussion in session `f5845518`.
  Code inspected: `l3/cli/cli.py`, `l3/runtime.py` (`register_commands`),
  `l0/kernel/records.py` (`help()`), `l0/kernel/lite_records.py`,
  `l1/archive/records/navigation.py` (`ArchivePartition`),
  `l2/context/storage.py`, `l1/checks/__init__.py`. No product code changed.
