# Global CLI command router

<!-- tarav.sessions
0d8af26c = codex:01a168fe-92d6-7410-a7f7-7c15cf921b95 @0d8af26c5b8dff7be764aac420b13df80bb530919d551881ae7d1afcc2400744
-->

## Impl.Abstract

Knowledge.Surface: wiki. Status: executing. Develop / Wiki /
Interactive. Implement a global configuration mapping selected Tarav command
paths to external invocations, forwarding remaining arguments. Always show the
actual invocation before running it. The immediate use case is a future Chatlas
vector command running through `ssh studio-pereiro`. User requested both the
implementation request and execution through Hugentics.
<!-- tarav.breadcrumb 4cbbec55a76c -->
<!-- tarav.breadcrumb 6eda35a35bba -->

Scope excludes vector storage, SSH workflow primitives, run profiles, Project
routes, remote installation and data transfers. Do not enable an actual Studio
route: the vector command and remote installation do not exist yet.
<!-- tarav.breadcrumb d0f98279a55c -->
<!-- tarav.breadcrumb e18fa3fce9a4 -->

## Design

The requested router recognizes a command and launches another invocation;
initial SSH use needs only an external command, without an SSH subsystem.
The mandatory banner includes SSH and the actual arguments. Use stderr for
this banner, preserving stdout for command data and pipelines.
<!-- tarav.breadcrumb b6ea278d3558 -->
<!-- tarav.breadcrumb f21aade20ed0 -->

Inspected `src/tarav/l1/cli/__init__.py` (CLI Workflow and runtime-derived
Command objects), `src/tarav/l3/cli/cli.py` (main currently constructs the whole
runtime/parser before parsing), `_core/home.py` (TARAV_HOME and global paths),
`tests/test_usage_live_help.py`, `tests/cli/test_import_guard.py` and
`tests/test_architecture.py`. CLI architecture is documented in ARCHITECTURE.md;
the relevant Wiki context is live-help.md. No routing exists at present.

Implementation choices (Agent decisions): a separate `cli-routes.json` under
the existing Tarav home, absent by default and never created by reads. A typed
CommandRouter holds CommandRoute values: `command` tokens excluding `tarav`,
target `argv`, and optional `shell_command` tokens. The longest exact leading
token match wins. Remaining tokens are opaque forwarded arguments; there is no
local parsing of the routed command. Duplicate or malformed routes fail clearly.
Literal token matching intentionally requires command tokens before options.

Ordinary routes append the remaining arguments directly to argv. With
`shell_command`, append one POSIX-shell-quoted string constructed from those
tokens plus the forwarded arguments. This generic serialization lets SSH
receive one properly quoted remote command; the router does not interpret SSH.
No local shell, interpolation, eval, or template language is needed.

The l1 CLI workflow owns configuration, matching and argv construction. The l3
process adapter owns subprocess execution, inherited streams/cwd, the flushed
stderr banner and exit status (including signal normalization). Dispatch occurs
before runtime/parser construction; local behavior is retained on a miss.
`TARAV_CLI_NO_ROUTE=1` bypasses routing and is inherited by routed local children
to prevent self-routing. SSH configuration explicitly includes
`env TARAV_CLI_NO_ROUTE=1` in shell_command because SSH does not forward this
variable automatically. This also offers an escape from malformed route files.

Data shape first: frozen CommandRoute and CommandRouter values, validated once
at the JSON boundary. Boundary discipline: reject unknown fields, empty command
tokens/executables, non-string arguments, NUL bytes and duplicate matches;
preserve empty forwarded argument strings and all shell metacharacters.
Subtract before adding: nothing is obsolete; retain parser and usage mechanics
and insert only one pre-dispatch hook. No compatibility aliases or migrations.

## Impl.Req.Wiki

Product: tarav-py. Wiki owner: tarav-md/notes/wiki. Read live-help.md for CLI
context. Capture this discussion in cli-routing.md and daily/2026-10-23.md.
Companion request: ../../../tarav-md/notes/live/878-global-cli-routing-wiki-impl-req.md.
Exact User Turns resolved once from the session declared above; submission and
audit pending. Backend capture is bounded to router decisions and measured code
behavior, with no claim that the vector workflow is already implemented.

## Execution.Plan

- [x] Feature: implement global router and installed CLI pre-dispatch together.
  Prove through real CLI subprocesses: local and SSH-shaped routes, remote-only
  commands, longest/exact-token matching, quoted/empty arguments, stdin/stdout/
  stderr, exit status, local fallback, invalid config and loop bypass. Check
  existing CLI/live-help/import tests and architecture; document actual config.
- [ ] Documentation/capture: submit/audit all implemented Product.Surfaces,
  update architecture and default pytest discovery, reinstall the editable CLI,
  run focused checks and root Project status --all, then close Wiki capture and
  evidence commits. Use temporary fake SSH, not a live remote install.

Dependencies: Python slice before Wiki behavior capture. No unresolved User
decision blocks implementation. Risks: quoting across SSH, recursion and early
dispatch changing ordinary commands. A mismatch requiring broader SSH or run
profile design is an Interactive deviation checkpoint; do not expand scope.

## Impl.Log

- Read applicable project instructions, Constitution and Hugentics Develop
  modules. Both owning worktrees were clean. Start evidence checkpoints are
  recorded in /tmp/cli-router-start-{py,md}-result.json; no external changes.
- Todo list is Execution.Plan above. No delegation requested or used.
- Cold-reloaded both requests before code edits. Start checkpoints: Python
  620d92b6; Markdown 459cfa51. Request Breadcrumb submission/audits succeeded.
- Baseline real CLI routing suite: 15 failed, 2 passed before product edits.
  Post-change: 88 routing, existing CLI/live-help/import and architecture tests
  passed in 45.58 seconds. Focused Ruff and diff whitespace checks passed.
- Implemented CommandRoute/CommandRouter and pre-parser process dispatch. Tests
  use executable fake SSH plus a real POSIX shell to prove remote quoting,
  preserving spaces, empty strings, quotes, dollar signs and newlines; also
  verified inherited streams/cwd, exact matching, remote-only command paths,
  malformed config, child signal status and explicit/inherited loop bypass.
- Refreshed installed entrypoints with `uv tool install --reinstall --editable
  .`. Default discovery now collects 650 tests, including the 17 new router
  cases and architecture boundary check. Whole-source Ruff passed.
- A real installed CLI invocation using temporary configuration routed over
  SSH to studio-pereiro's `/usr/bin/printf`. Exact output preserved a spaced
  argument, an empty argument, literal `$HOME` and a semicolon. No files or
  installation on the Studio were changed; no production route was created.
- Inlined Capture submitted all eight implemented code/test/config/guide
  surfaces (10 new Breadcrumbs). Audits resolved the retained attachments;
  moved existing labels received refreshed positions, with no unresolved POIs.
  Wiki topical and daily capture submitted/audited with zero POIs. Full root
  Project status --all is running, with output retained under /tmp/cli-router-*.
