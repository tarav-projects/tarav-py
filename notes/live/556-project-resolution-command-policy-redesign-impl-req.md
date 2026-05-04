# Project Resolution Command Policy Redesign - impl-req

## Impl-Req State

Implemented in the Python CLI. Full tests pass; `ruff` could not be run because the project environment does not currently include the executable.

## User Intent

Make project resolution coherent across `agentos` commands.

Project-aware commands must use explicit project targeting. The minimal explicit project target is bare `--project`, which means the current working directory is the intended project target. Commands should not silently target an `Agentos.Project` through omitted `--project` unless they are explicitly declared read-only discovery or diagnostic surfaces.

The redesign should also add a project name assertion mechanism:

```txt
project=<project-name>
```

This assertion must verify the project already resolved by discovery or explicit targeting. It must not become global project search.

## Why This Exists

`Agentos.Project` discovery is now a named protocol in the markdown design surface, but the Python CLI still wires command project policy one command at a time.

The core mechanics exist in `src/agentos/_core/project.py`, but commands differ on whether `--project` is optional, exact, parent-walk based, diagnostic-only, initialization-capable, logging-enabled, or forbidden with headless roots.

This caused a real workflow error: an artifact was created under `agentos-md` without first resolving the intended project through `agentos prefix`. The deeper issue was not only one command; the CLI currently makes it too easy for nested workspaces to resolve a parent project silently.

## Current Situation

Shared project helpers currently include:

- `find_agentos_project(...)`
- `find_agentos_project_root(...)`
- `normalize_project_target(...)`
- `resolve_agentos_project(...)`
- `require_agentos_project(...)`
- `require_agentos_project_root(...)`
- `resolve_scope_agentos_dir(...)`
- `resolve_scope_storage_paths(...)`
- `resolve_project_tape_dir(...)`

Current command behavior is inconsistent:

- `agentos init` currently defaults `--project` to `.` and can initialize through omitted `--project`.
- `agentos rev-parse` is a read-only discovery command and parent-walks from `--path`.
- `agentos doctor` is diagnostic and can parent-walk from a target path without requiring an existing project.
- `agentos prefix next --target` already requires explicit `--project` and records project command activity.
- `agentos skills` requires an existing project but still allows omitted `--project` parent-walk.
- `agentos mission` requires an existing project but still allows omitted `--project` parent-walk and does not record project command activity.
- `agentos utils tmp-folder new` allocates project-local state but still allows omitted `--project`.
- `agentos tape --tape` requires an existing project but still allows omitted `--project`; `--root` is headless and rejects `--project`.
- `agentos forum` writes require a project, but `--project` is optional; `feed` and `thread` are headless reads; `history` can use `--project-id` or implicit local project.
- `agentos agent` and chat account commands use `--project` as a config-resolution start path and do not require an existing project.

Project command activity logging is partial:

- logged: `skills`, `prefix`, `utils tmp-folder`
- not logged: `mission`, `forum` writes, `tape --tape`

## Requested Change

Implement a coherent project resolution and command policy system for `agentos` commands.

### Core Policy Layer

Add a small project policy/resolution layer instead of repeating ad hoc decisions in every command.

The exact module name can be chosen during implementation, but likely candidates are:

- `src/agentos/_core/project.py`
- `src/agentos/_core/project_policy.py`
- `src/agentos/_core/project_resolution.py`

The layer should provide explicit helpers for common policies:

- existing project, explicit `--project` required
- existing project, discovery diagnostic allowed
- project creation target, explicit `--project` required
- headless-or-project target, where project mode requires explicit `--project`
- config-resolution start path, for commands that may load project config but are not project commands

Suggested helper shape:

```py
resolve_required_project(args_or_project, *, start_path, command_name)
resolve_explicit_project(args_or_project, *, command_name)
resolve_project_creation_target(args_or_project, *, command_name)
resolve_project_diagnostic_target(args_or_project, *, start_path)
resolve_project_config_start(args_or_project, *, start_path)
assert_project_name(project, expected_name)
```

Do not overbuild the abstraction. The goal is consistent behavior and help text, not a large framework.

### Project Name Assertion

Add support for a project name assertion after project resolution.

Design:

- assertion verifies the resolved project
- assertion does not search globally
- assertion should match a project name declared in `.agentos/project.json` when available
- if no marker project name exists, assertion should match the basename of the resolved project root
- mismatch should fail clearly and include the resolved root

Marker schema note:

- existing markers currently require `class` and `project_id`
- add optional `project_name` or equivalent only if implementation keeps backward compatibility
- do not break existing project markers that lack a name field

Possible CLI spelling:

```sh
agentos <command> --project agentos-py ...
agentos <command> --project /path/to/project --project-name agentos-py ...
```

The final spelling should be chosen consistently. The accepted design concept is `project=<project-name>` as assertion, not global search.

### Shared `--project` Parser Behavior

Create shared parser helpers for project-aware commands so help text and argparse behavior stay consistent.

For project-aware commands:

- `--project` must be present
- bare `--project` means current directory
- `--project <path>` means exact intended project target
- omitted `--project` is an error unless the command is explicitly diagnostic/read-only or config-resolution-only

Recommended behavior:

```txt
error: <command> requires --project
```

For read-only discovery or diagnostic commands, use clear wording in help text that omitted project targeting is allowed by command policy.

### Command-Specific Redesign

#### `agentos init`

Change project initialization so project scope requires explicit `--project`.

Expected valid forms:

```sh
agentos init --project
agentos init --project /path/to/project
agentos init --scope global
```

Expected invalid form:

```sh
agentos init
```

`agentos init` must not silently initialize the current directory through omitted `--project`.

#### `agentos rev-parse`

Keep this as a read-only discovery command.

It may continue to parent-walk from `--path` because its purpose is discovery inspection. It should not create or mutate a project.

#### `agentos doctor`

Keep this as diagnostic.

It may inspect a target without requiring an existing project, but help text and JSON output should make clear whether the target is:

- explicit target path
- discovered project root
- no project found
- effective storage scope

If name assertion is supported here, it should verify the discovered project when one exists.

#### `agentos prefix next --target`

This command already follows the new explicit-project rule.

Keep:

- target mode requires `--project`
- existing project marker required
- project command activity logging
- no implicit parent-walk when `--project` is omitted

Add project name assertion support when the shared mechanism exists.

#### `agentos skills`

Change project-aware skills commands to require explicit `--project`.

Affected subcommands:

- `skills list`
- `skills import`
- `skills status`
- `skills path`

Keep existing project marker requirement and command logging.

#### `agentos mission`

Change mission commands to require explicit `--project`.

Mission data is project-scoped, so omitted `--project` should fail.

Also add project command activity logging for project-affecting mission commands.

At minimum, log commands that create or mutate mission state:

- `mission new`
- `mission activate`
- `mission done`
- `mission park`
- `mission help-set`
- `mission todo add`
- `mission todo done`
- `mission note`
- `mission fork`

It is acceptable to also log read commands if the command logger is intended as general project activity.

#### `agentos utils tmp-folder new`

Change project-local tmp-folder allocation to require explicit `--project`.

This command allocates project-local state under `.agentos/tmp`, so it should use the same safety rule as other project-aware allocators.

Keep command logging.

#### `agentos tape`

Keep the existing headless-or-project split:

- `--root` remains explicit headless mode and must reject `--project`
- `--tape` is project mode and should require explicit `--project`

Add project command activity logging for `--tape` mode if the command touches or reads project tape state as project activity.

Do not require `--project` for `--root`.

#### `agentos forum`

Keep the conceptual split:

- writes are project-authored and should require explicit `--project`
- `feed` and `thread` are headless reads and should not require `--project`
- `history` should require either `--project-id` or explicit `--project`

Remove implicit local-project fallback for `forum history`.

Add project command activity logging for project-authored writes:

- `forum post`
- `forum reply`
- `forum react`

#### `agentos agent` and chat account config resolution

These commands are not project commands in the same sense as `skills`, `mission`, `prefix`, `forum`, or `tape`.

They may continue to support config resolution from `cwd`, but the policy should be named and documented as config-resolution behavior, not project targeting.

Recommended cleanup:

- keep omitted `--project` as `cwd` config start path
- keep `--project` as an explicit config start path
- do not require an existing project marker
- avoid wording that implies `--project` is an `Agentos.Project` target when the command does not require a marker
- if a project marker is discovered from the config start path, project-local config may be loaded

If this feels too confusing after implementation starts, consider renaming future option shape to `--config-project` or `--config-start`, but do not rename in this change unless the blast radius stays small.

## Constraints And Invariants

- Do not remove read-only discovery behavior from `agentos rev-parse`.
- Do not remove diagnostic behavior from `agentos doctor`.
- Do not require `--project` for explicit headless `--root` modes.
- Do not turn project name assertion into global project search.
- Do not break existing `.agentos/project.json` markers without a name field.
- Do not initialize projects except through `agentos init`.
- Do not silently create `.agentos/project.json` from any project-aware command other than `init`.
- Keep bare `--project` as current-directory target.
- Keep explicit `--project <path>` as exact intended project target for project-aware commands.
- Keep project command logging best-effort.
- Preserve JSON outputs where commands already support them, updating payloads only where useful for project resolution clarity.

## Out Of Scope

- Full project registry
- Global lookup by project name
- Migration tooling for existing project markers
- Renaming every `--project` option across non-project config commands
- Changing skill routing source semantics beyond project resolution requirements
- Redesigning command logger storage format unless needed for command coverage
- Implementing `agentos prefix doctor`
- Implementing `agentos project doctor`

## Acceptance Signals

- `agentos init` without `--project` fails unless `--scope global` is used.
- `agentos init --project` initializes the current directory.
- `agentos init --project /path/to/project` initializes the explicit path.
- Project-aware mutating or allocating commands fail without `--project`.
- `agentos prefix next --target notes/live` continues to fail without `--project`.
- `agentos skills list` fails without `--project`.
- `agentos mission status` fails without `--project`.
- `agentos utils tmp-folder new` fails without `--project`.
- `agentos tape <subcommand> --tape <name>` fails without `--project`.
- `agentos tape <subcommand> --root <path>` remains valid without `--project`.
- `agentos forum post "..."` fails without `--project`.
- `agentos forum history` fails unless `--project-id` or `--project` is provided.
- `agentos rev-parse --show-toplevel --path <path>` still supports parent-walk discovery.
- `agentos doctor` still produces diagnostics outside an initialized project.
- Project name assertion verifies the resolved project and fails on mismatch.
- Existing project markers without project names continue to load.
- Tests cover exact explicit target behavior, bare `--project`, omitted-project failures, diagnostic exceptions, headless `--root` exceptions, and project name assertion.

## Relevant Files Or Surfaces

- `src/agentos/_core/project.py`
- `src/agentos/_core/project_command_log.py`
- `src/agentos/project/commands.py`
- `src/agentos/system/commands.py`
- `src/agentos/prefix/commands.py`
- `src/agentos/skills/commands.py`
- `src/agentos/skills/routing.py`
- `src/agentos/mission/commands.py`
- `src/agentos/utils/commands.py`
- `src/agentos/tape/commands.py`
- `src/agentos/forum/commands.py`
- `src/agentos/forum/core.py`
- `src/agentos/agent/commands.py`
- `src/agentos/chat/commands.py`
- `src/agentos/chat/providers.py`
- `tests/test_prefix_commands.py`
- `tests/test_skills_commands.py`
- `tests/test_tape_project_resolution.py`
- `tests/test_forum_commands.py`
- `tests/test_system_commands.py`
- `tests/test_project_command_log.py`
- `agentos-md/notes/index/105-Agentos.Project.md`
- `agentos-md/notes/index/ontology.md`

## Open Questions

- What exact CLI spelling should expose project name assertion: `--project-name`, `--project-is`, `--assert-project`, or a structured `project=<name>` argument?
- Should project name assertion be available on every project-aware command immediately, or only on commands with the highest nested-workspace risk first?
- Should read-only project commands such as `mission status` be logged, or only mutating commands?
- Should `agentos doctor --project <path>` treat the path as exact diagnostic target or as a parent-walk start path? Current behavior parent-walks, which is useful but should be explicit.
- Should `agentos agent --project` eventually be renamed because it is a config-resolution start path rather than a required project target?

None of these block the first implementation pass if the core rule is enforced: project-aware commands require explicit `--project`, and declared diagnostic/headless/config-resolution exceptions are documented in code and tests.

## Related Impl-Reqs

- `notes/live/552-project-command-logger-impl-req.md` - project command activity logging foundation.
- `notes/live/555-project-aware-prefix-next-impl-req.md` - existing explicit-project allocator precedent for `agentos prefix next`.

## End Log

- 2026-05-04: Created after reviewing current command project-resolution behavior and adding `Project.Discovery.System` plus explicit `--project` command policy to the Agentos markdown index.
- 2026-05-04: Implemented explicit project targeting for project-aware commands, project-name assertion, project command logging coverage for mission/forum/tape project modes, and related tests. Verified with `uv run python -m pytest -q` (`299 passed`). `uv run ruff check .` could not run because `ruff` is not installed in the project environment.
