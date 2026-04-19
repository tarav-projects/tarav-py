# Project Command Enforcement - impl-req

## Impl-Req State

Implemented in the current branch for the intended project-local command surfaces.
The `Agentos.Project` contract now has an index note, shared project-target helpers are in
place, and the targeted enforcement/tests are green. Remaining follow-up is docs/help
cleanup and optional triage of unrelated `chat debug` / `chat extract` test failures.

## User Intent

Strengthen the `Agentos.Project` contract so commands that depend on project-local state
require a real local project marker at `<project>/.agentos/project.json`.

When such a command runs outside an initialized project, it must error and suggest running
`agentos init`.

## Why This Exists

`agentos` is accumulating subsystems that write or manage data relative to the current
project. The project boundary needs to be explicit and consistent so agents and humans do
not operate on project-local state without a valid project anchor.

## Current Situation

The core project contract now exists both as code and as an index note:

- local project marker: `<project>/.agentos/project.json`
- parent-walk discovery from `cwd`
- explicit project targeting via `--project`, including bare `--project` meaning current
  directory
- git-like introspection commands
- shared helpers for resolving a `project target` and requiring an `existing project`
- index note: `notes/index/004-Agentos.Project.md`

The command surface is now better classified as:

Commands that resolve a `project target` and require an `existing project`:

- `agentos skills list`
- `agentos skills import`
- `agentos skills status`
- `agentos skills path`
- `agentos mission ...`
- `agentos utils tmp-folder new`
- `agentos tape ... --tape <name>`

Commands that resolve an explicit `project target` and may auto-init:

- `agentos init --scope project`

Commands that inspect project state:

- `agentos rev-parse --is-inside-agentos-project`
- `agentos rev-parse --show-toplevel`
- `agentos doctor`

Project-aware but not project commands:

- `agentos agent ...`
- `agentos chat ...`
- `agentos chat accounts ...`

True non-project/global/headless commands:

- `agentos chatlas ...`
- `agentos tara-tapes ...`
- `agentos tape ... --root <path>`
- `agentos prefix ...`
- `agentos mdblocks ...`
- `agentos git-refs ...`
- `agentos test`

The main design drift that existed before implementation is now removed:

- `agentos skills ...` no longer uses standalone `.agents` discovery as a public project
  anchor
- routed skills now require an `existing project`
- `mission`, `utils tmp-folder new`, and `tape --tape` now support explicit `--project`
  targeting while preserving implicit parent-walk behavior
- `agentos init` now uses `--project` for project scope instead of `--root`

## Requested Change

Implement command-surface enforcement around the canonical project marker.

Commands that resolve a `project target` and require an `existing project`:

- `agentos skills list`
- `agentos skills import`
- `agentos skills status`
- `agentos skills path`
- `agentos mission ...`
- `agentos utils tmp-folder new`
- `agentos tape ... --tape <name>`

Commands that resolve an explicit `project target` and may auto-init:

- `agentos init --scope project`

Commands that inspect project state:

- `agentos rev-parse --is-inside-agentos-project`
- `agentos rev-parse --show-toplevel`
- `agentos doctor`

Project-aware but not project commands:

- `agentos agent list`
- `agentos agent run`
- `agentos chat debug list`
- `agentos chat debug find`
- `agentos chat debug extract`
- `agentos chat accounts stats`

True non-project/global/headless commands:

- `agentos test`
- `agentos tape ... --root <path>`
- `agentos tara-tapes ...`
- `agentos chatlas ...`
- `agentos prefix ...`
- `agentos mdblocks ...`
- `agentos git-refs ...`

Implementation expectations:

- make `agentos skills ...` require the nearest valid agentos project root
- stop treating bare local `.agents` discovery as sufficient for public routed skills
- preserve the explicit-root escape hatch for commands that already support headless mode
- preserve global-config-backed behavior for `agent` and `chat`
- make project-required errors consistently mention the missing marker and suggest
  `agentos init`
- add or update tests for each project-required surface

## Constraints And Invariants

- The canonical local project marker is `<project>/.agentos/project.json`.
- Commands that manage project-local state must not silently operate without that marker.
- Commands that operate on an explicit external root/path must remain usable without an
  agentos project.
- Global and diagnostic surfaces must not become project-required by accident.
- Do not add compatibility aliases or fallback behavior that weakens the contract.

## Out Of Scope

- Redesigning the top-level CLI namespace into `agentos project ...`
- Reworking global/project config precedence for provider instances
- Broader `Agentos.Project` specification work outside command enforcement
- Changing the tape explicit-root model
- Changing `chatlas`, `tara-tapes`, `prefix`, `mdblocks`, or `git-refs` into
  project-bound tools

## Acceptance Signals

- Running any project-required command outside an initialized project fails with a clear
  error that mentions missing `.agentos/project.json` and suggests `agentos init`.
- `agentos skills ...` no longer succeeds based only on local `.agents/` discovery.
- `agentos init --scope project` uses `--project` targeting semantics.
- `agentos mission ...`, `agentos utils tmp-folder new`, and `agentos tape --tape ...`
  enforce project mode consistently and accept explicit `--project` targeting.
- `agentos agent ...` and `agentos chat ...` still work in global-only environments when
  their configuration is available globally.
- `agentos tape ... --root <path>` remains usable without an agentos project.
- Tests cover the enforced project-required behavior and the preserved non-project paths.

## Relevant Files Or Surfaces

- `src/agentos/_core/project.py`
- `src/agentos/project/commands.py`
- `src/agentos/skills/commands.py`
- `src/agentos/skills/routing.py`
- `src/agentos/mission/commands.py`
- `src/agentos/utils/commands.py`
- `src/agentos/utils/tmp_folder.py`
- `src/agentos/tape/commands.py`
- `src/agentos/agent/commands.py`
- `src/agentos/chat/providers.py`
- `notes/index/004-Agentos.Project.md`
- `notes/live/508-agentos-project-local-global-design.md`
- `notes/live/530-local-skills-context-routing-design.md`
- `tests/test_skills_commands.py`
- `tests/test_mission_commands.py`
- `tests/test_tmp_folder_commands.py`
- `tests/test_tape_project_resolution.py`
- `tests/test_tape_lint_command.py`
- any new tests added for project-required command enforcement

## Open Questions

- None for the implemented contract. One residual repo issue remains outside this request:
  the full suite still has failing `chat debug` / `chat extract` tests unrelated to the
  project-target rollout.

## Related Impl-Reqs

- None.

## End Log

- 2026-04-19: Designer created this impl-req after scanning the current CLI surface and
  classifying commands by project anchoring behavior.
- 2026-04-19: Implementation completed for the intended project-local surfaces. Added the
  `Agentos.Project` index note, shipped shared project-target helpers, changed project init
  to `--project`, made routed skills require an existing project, added `--project` to
  `mission`, `utils tmp-folder new`, and `tape --tape`, and updated the targeted tests.
- 2026-04-19: Targeted validation passed for `skills`, `mission`, `tmp-folder`, and tape
  project resolution. Full suite still shows unrelated `chat debug` / `chat extract`
  failures.
