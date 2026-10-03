# 855 — Typed usage traces with owner rendering

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Design only.
Status: ready.

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
  rebuild Tarav objects: the type's class is resolved by name and renders the
  row. 851 found that command objects cannot be reconstructed from Records,
  and `--help` should stay cheap.
- `UsageRegistry.record` takes the trace type and stores its name;
  `query` gains a `type` filter beside workflow, project, and subject, and
  `tarav usage query` gains `--type`. The registry still stores any payload.
- `tarav.l1.cli`: `CommandUse(UsageTrace)`, owned by the CLI workflow. Its
  envelope is exit code, duration, cwd, and the command's own descriptor from
  853, which stays free. Its `render_trace` prints the envelope and then the
  descriptor's fields.
- `LiveHelpProvider` states its trace type and its own heading. Live Help
  queries by that type and subject, resolves the class, and calls
  `render_trace`. Rows that are untyped, of another type, or of an unknown
  type are not printed; help says how many were skipped. Live Help no longer
  mentions any CLI field.
- Rows written before this change have no type. They are skipped and age out
  of the seven-day window; no migration.
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
   Tests: a typed row round-trips; the filter selects by type; an untyped row
   is still stored and queryable.
3. CLI: `CommandUse` and its rendering; `main()` records with that type.
4. Live Help: provider trace type and heading; render through the type;
   skip and count other rows. Tests with a fake provider and a fake trace
   type prove Live Help renders a non-CLI type and prints no unknown row.
5. Descriptors for the five commands above and the `run` threshold. Test one
   breadcrumbs descriptor and the short-code case.
6. Add `tests/test_usage_live_help.py` to the configured test paths if it is
   still absent. Lint, installed-CLI check, Inlined Capture, Wiki capture,
   completion commit.

Acceptance: `tarav breadcrumbs audit chatlas-context --help` lists recent
uses with their surfaces; `render_live_help` contains no CLI field name; a
trace of an unregistered type is counted, not printed.

## Impl.Log

- 2026-10-03 Design: note written from the discussion in session `f5845518`.
  Inspected `l1/live_help`, `l1/usage`, `l1/cli`, `l3/cli/cli.py`, and
  `l0/kernel/types.py`. Command frequencies came from `tarav usage query`
  (416 traces today). No product code changed.
