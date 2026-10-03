# 855 — Typed usage traces with owner rendering

<!-- tarav.sessions
6734aba0 = codex:01a0d86c-9538-7be1-af96-014cd4203d61 @6734aba0b9204f614baf3987604865fa85146495877841244ad7fe1efce4104b
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Execute.
Status: implemented and verified; capture closure in progress.

Follow-up to [851](851-usage-registry-cli-model-and-live-help-impl-req.md)
and [853](853-caller-declared-usage-descriptors-impl-req.md). Give every
usage trace a type. The Usage Registry workflow owns a base trace type that
others subtype, and each type's owner renders its own traces. Live Help
selects traces by type and subject and prints only what a type renders.
Deploy it to the Tarav CLI: a CLI trace type, and descriptors on a few
commands.
<!-- tarav.breadcrumb 5211296600238f305dedc0b841cf9cf90562ee4e57fe1afd4ee510d90be95220 -->

Non-goals: help for methods or classes; any non-CLI trace type; descriptors
for every command; session ids in traces; changing storage or the window.

## Design narrative

### The problem

After 853 the Agent reported that the code was not fully aligned with the
design: Live Help's renderer reads the specific fields the CLI writes and
labels every subject "command", so a trace left by another workflow would
show almost nothing.
<!-- tarav.breadcrumb a152fedef0809e61e5cb0a057e56a06957a5ac92a3c863e0f9b6ae50977374e8 -->

Current code (inspected): `render_live_help` in
`src/tarav/l1/live_help/__init__.py` reads `payload["exit_code"]`,
`payload["use"]`, and `payload["cwd"]` and prints `command:`. The CLI adapter
writes those keys in `src/tarav/l3/cli/cli.py`. `UsageRegistry.record` in
`src/tarav/l1/usage/__init__.py` stores `recorded_at`, `workflow`, `subject`,
`project`, and a free `payload`, with no type.

### Typed records, rendered by their owner

The emitter should not need to know its consumers; it knows only the
semantic, that the trace will contextualize Agents. So the record must be
typed, and the type must have a render method, so that the type's owner does
the rendering.
<!-- tarav.breadcrumb 12c4b3131c269fa2622ab1e4462de5863d68b2c32f6d9a11a209a5610887f447 -->

Help filters by type. When the command line recorded a command, the
command's help shows the most recent traces of that nature. A trace recorded
inside a method, describing how that method was called, is a different type
and belongs to that method's help, which is a later topic. Types give a known
rendering that makes sense for each case.
<!-- tarav.breadcrumb 75f4f064a2642862338577f0a110ed0b46898fff78b7dbef22cd2f70b888a47b -->

Help must not print whatever blob it finds. If nothing of the right type was
recorded, it shows nothing of that kind.
<!-- tarav.breadcrumb 0008cb614877a3c4c89488438290e3c0883598c7bea68471b359ca3f03e99af2 -->

Subtyping carries it: a base type describes the base record of the usage
registry, and everybody can subtype it, the command line records among them.
The minimum viable product is the command line: before any other user of the
registry exists, deploy it in the Tarav CLI on at least a few commands.
<!-- tarav.breadcrumb b45dcb58686b25f2f7338c44006f304f95bfe36d4e236c4e5956e78c5d0e89f4 -->

### Agent proposal

- `tarav.l1.usage`: `UsageTrace`, a `TaravType` owned by the Usage Registry
  workflow. It names the base fields (`type`, `recorded_at`, `workflow`,
  `subject`, `project`) and declares one classmethod,
  `render_trace(row) -> Sequence[str]`. The base rendering prints the time
  and subject only.
- A trace stays a plain JSON row carrying its type name. Reading does not
  rebuild Tarav objects. The consumer's provider already declares the trusted
  trace class that renders matching rows; retained data never selects Python
  code. 851 found that command objects cannot be reconstructed from Records,
  and `--help` should stay cheap.
- `UsageRegistry.record` takes the trace type and stores its name;
  `query` gains a `type` filter beside workflow, project, and subject, and
  `tarav usage query` gains `--type`. The registry still stores any payload.
- `tarav.l1.cli`: `CommandUse(UsageTrace)`, owned by the CLI workflow. Its
  envelope is exit code, duration, cwd, and the command's own descriptor from
  853, which stays free. Its `render_trace` prints the envelope and then the
  descriptor's fields.
- `LiveHelpProvider` states its trace type and its own heading. Live Help
  queries by that type, workflow, and subject, then calls the declared class's
  `render_trace`. Other and legacy untyped rows are outside that view; there
  is no skipped count. Live Help no longer mentions any CLI field. This is the
  User's explicit clarification during execution.
<!-- tarav.breadcrumb ac61c5ca4c30c57ad56ea108ea8c2b0780084c78468419500e9f6cc9fe106242 -->
- Rows written before this change have no type. They remain queryable without
  a type filter and age out of the seven-day window; new writes require a
  trace type. No migration.
- Descriptors for the commands the registry shows are used most:
  `breadcrumbs submit chatlas-context`, `breadcrumbs audit chatlas-context`,
  `chatlas render`, `chatlas query`, `chatlas update`, beside the existing
  `run`, `git commit`, and `usage query`.
- In the `run` descriptor, a short code string is recorded as it is and only
  a long one is summarized, so the trace is informative as well as small.
  `describe_text` gains a threshold for that.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Notes:
`live-help.md`, `caller-declared-identity-inputs.md`. Supporting chat:
session `f5845518` above.

## Execution.Plan

1. Scoped start evidence checkpoint.
2. Usage: `UsageTrace`, the stored type name, the `type` filter, `--type`.
   Tests: a typed row round-trips; the filter selects by type; a retained
   legacy untyped fixture remains queryable without new untyped writes.
3. CLI: `CommandUse` and its rendering; `main()` records with that type.
4. Live Help: provider trace type and heading; query only matching rows and
   render through the provider's trusted class. Tests with a fake provider and
   a fake trace type prove Live Help renders a non-CLI type and ignores other
   types even under the same workflow and subject.
5. Descriptors for the five commands above and the `run` threshold. Test one
   breadcrumbs descriptor and the short-code case.
6. Add `tests/test_usage_live_help.py` to the configured test paths if it is
   still absent. Lint, installed-CLI check, Inlined Capture, Wiki capture,
   completion commit.

Acceptance: `tarav breadcrumbs audit chatlas-context --help` lists recent
uses with their surfaces; `render_live_help` contains no CLI field name;
traces outside a provider's declared type are absent from its view.

## Impl.Log

- 2026-10-03 Design: note written from the discussion in session `f5845518`.
  Inspected `l1/live_help`, `l1/usage`, `l1/cli`, `l3/cli/cli.py`, and
  `l0/kernel/types.py`. Command frequencies came from `tarav usage query`
  (416 traces today). No product code changed.
- 2026-10-03 Execute: start checkpoint `5125d2d`. Added typed rows and
  type-filtered queries while retaining read access to old untyped rows.
  `CommandUse` owns CLI payload rendering; `LiveHelpProvider` supplies the
  trusted class and heading, and Help sees only matching rows. Added five
  command descriptors and the short/long code threshold for `tarav run`.
  The focused usage/architecture suite passed 48 tests, the configured suite
  passed 164, and Ruff passed. Reinstalled the editable CLI; one real
  `breadcrumbs audit chatlas-context` call then appeared in that command's
  `--help` with its surface path. Product Breadcrumbs were submitted beside
  the Type, renderer, and selection boundaries; shifted older position
  observations were appended. Wiki capture updated the daily and Live Help
  notes after scoped Wiki checkpoint `27300f6`. Final configured suite:
  164 passed; Ruff and diff checks clean.
