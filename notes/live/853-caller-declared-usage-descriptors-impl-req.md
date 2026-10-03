# 853 — Caller-declared usage descriptors

<!-- tarav.sessions
f5845518 = claude-code:4ee3b84e-14fa-4aa9-9c6f-8d139954fe18 @f5845518e808c6cf0496f867fc656fdad9063980a184f7c3f15c54adf8fcb31f
-->

## Impl.Abstract

Knowledge.Surface: wiki. Alignment.Mode: Interactive. Phase: Develop.
Status: implemented and verified.

Follow-up to [851](851-usage-registry-cli-model-and-live-help-impl-req.md).
A CLI usage trace carries a small descriptor of the call that the command
itself declares. The Usage Registry and the CLI adapter impose no
representation. Live Help prints that descriptor.

Non-goals: writing descriptors for every command; a default descriptor;
changing registry storage or query; session ids in traces.

## Design narrative

### What a trace should hold

Review of 851 found that recent uses showed option names only, too thin to be
examples. The User first asked to remove truncation and not to weigh privacy
or security here: the records are local to `~/Documents/tarav`, and the ruling
principle is that each workflow is responsible for what it stores for an Agent
to see how it was used.
<!-- tarav.breadcrumb a80a04653641041da081638d2bbabb76126f406e80bb4de265cb6ae3d847b648 -->
<!-- tarav.breadcrumb ecc56a5586b6825718979d21325a546443209609e9b3fc4810ea599f8bb6c1fd -->

The Agent read that as "store the whole command line" and implemented it
(commit `719b7d9`). The User corrected this: the point is not to pass the
whole command. The caller must know which parts are informative yet
economical. A long file is not wanted, a path is. The trace need not be the
exact command arguments; it is an informative descriptor.
<!-- tarav.breadcrumb 629e12d9f1f43f0afe0e351e355dd026223a7fd99974ec94f7f989190e352d2f -->

### The pattern

The User named this a common Tarav design pattern, already used for POI
instance identity: the shared mechanism does not know what describes the
situation, so the caller provides it, in the least constrained interface as a
JSON record of key-value pairs. The caller is expected to be clever and
brief: for a file, give its path and a hash of the content, not the content.
<!-- tarav.breadcrumb d71d2d7d8614bb1036bc8bb60d9336e9dba0da4bf678219a6bbe9c30831cdd46 -->

Applied here: the registry does not know what a command is or how it wants to
be expressed. It lets the caller say what to record about its command or
method call so Agents get it when they ask for help. The caller has the
responsibility to represent the call, and no mechanics are imposed. A command
that takes a whole file's content understands itself fully, so it can
represent that argument as, for example, its first and last 20 characters and
a hash, and so respect everyone's space. The caller also understands it must
not put random things there: the purpose is to inform an Agent how the
command was used so it is better contextualized to use that workflow.
<!-- tarav.breadcrumb 848e46651c4cced283f634032c1a7f7d2cca5157eb34b83aa6da8dd79303346f -->

Inspected precedent: `tarav-md/notes/wiki/caller-declared-identity-inputs.md`
states the same principle for hashed situations described as a `LiteRecord`.

### Decisions by the Agent

- A command declares its descriptor at registration with
  `set_defaults(usage_descriptor=fn)`, where `fn(args)` returns a mapping.
- There is no default descriptor. A command that declares none records only
  exit code, duration, and cwd, and its metadata check raises the POI
  `cli.missing-usage-descriptor` as a reminder for its owner.
- `tarav.l1.usage` offers two optional helpers matching the User's examples:
  `describe_text` (size, first and last 20 characters, hash) and
  `describe_file` (path, content hash). Nothing requires their use.
- Three commands get descriptors now as worked examples: `run`,
  `git commit`, and `usage query`.

## Impl.Req.Wiki

Product project: `tarav-py`. Wiki owner: `tarav-md/notes/wiki/`. Notes:
`live-help.md` (Usage Registry), `caller-declared-identity-inputs.md` (the
pattern). Supporting chat: session `f5845518` above.

## Execution.Plan

1. Replace the CLI trace's argument list with the command's descriptor.
2. Add the descriptor declaration to `Command`, its check POI, the optional
   helpers, and the Live Help rendering.
3. Declare descriptors for `run`, `git commit`, and `usage query`.
4. Tests, lint, installed-CLI check, Inlined Capture, Wiki capture, commits.

## Impl.Log

- 2026-10-03 The code was written before this note, on the User's correction;
  the User then asked for the full cycle. No start checkpoint was made. The
  preceding commit `719b7d9` (full argument list) is the state this replaces.
- Changed: `src/tarav/l3/cli/cli.py`, `src/tarav/l1/cli/__init__.py`,
  `src/tarav/l1/usage/__init__.py`, `src/tarav/l1/usage/commands.py`,
  `src/tarav/l1/live_help/__init__.py`, `src/tarav/l3/run.py`,
  `src/tarav/l3/git/commands.py`, `tests/test_usage_live_help.py`.
- Checks: focused tests 5 passed; configured suite 156 passed; Ruff passed.
  Over the built tree of 217 parser nodes the metadata check now reports 162
  `cli.missing-usage-descriptor` and 19 `cli.missing-help` POIs, left for
  command owners.
- `ARCHITECTURE.md` was not updated: it holds another Agent's uncommitted
  edits, outside this scope.
