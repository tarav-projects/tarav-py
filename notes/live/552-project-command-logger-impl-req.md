# Project Command Logger - impl-req

## Impl-Req State

Implemented and verified; the first project command logger version is wired into representative project-aware commands.

## User Intent

Add an Agentos project command logger that appends an activity record whenever a project-aware Agentos command is called against a valid project.

This is not a project registry in the authoritative sense. A project is still defined only by the project folder and its `.agentos/project.json`. The log is observational command activity and can later be used to derive known Agentos-controlled projects.

## Why This Exists

Agentos should have a global activity trail under `~/.agentos` showing which project-aware commands were run against which projects. This enables future workflows such as listing recently touched projects, deriving known projects, maintenance across seen projects, or project activity inspection.

The design intentionally favors a simple rolling JSONL log over deduplicated registry state.

## Current Situation

Project-aware commands currently resolve projects through helpers in `src/agentos/_core/project.py`, especially root-oriented functions such as `find_agentos_project_root(...)` and `require_agentos_project_root(...)`.

Those helpers primarily return paths. Some call paths may later need both the root and `.agentos/project.json` content. The new logger should avoid reparsing `project.json` when project validation has already loaded it.

## Requested Change

Implement a project command logger subsystem.

Storage:

```text
~/.agentos/projects/activity/YYYYMM.jsonl
```

The filename uses numeric year and month only, for example `202604.jsonl`.

Append one JSON object per logged project-aware command:

```json
{
  "schema_version": 1,
  "timetag": "2026-04-30T...",
  "project_id": "...",
  "project_root": "/abs/project/root",
  "agentos_command": {
    "command": "skills import",
    "argv": ["skills", "import", "--force"]
  }
}
```

Add a class-based project discovery/checking mechanism centered on an `AgentosProjectHandler` object:

- It is not frozen.
- It can be created from only a root path.
- It owns the lifecycle for project validation and project marker access.
- It exposes the normalized project root.
- It can load and cache `.agentos/project.json` lazily.
- It has methods/properties for validation, marker payload, marker path, and project id.

Existing project resolution should move toward using this common handler-based mechanism. Root-only helpers may remain as wrappers, but they should call the handler-based mechanism rather than maintaining separate project checking behavior.

Add a logger API that accepts the handler, not just a root path:

```python
record_project_command(
    *,
    project: AgentosProjectHandler,
    agentos_command: dict[str, object],
) -> None
```

The logger should read `project.project_id` from the handler, using cached marker data if validation already loaded it.

## Constraints And Invariants

- A project remains defined only by the project folder and `.agentos/project.json`; the command log must not participate in project discovery or project validity.
- Logging is command activity, not deduplicated registry state.
- Append on every relevant project-aware command call; do not implement lazy touch or dedupe logic.
- The logger should be explicit. Do not hide command logging inside project discovery as a side effect.
- Project command handlers should call the logger after project resolution/validation succeeds and before the main command work when practical, so failed command attempts are still visible as activity.
- Avoid parsing `.agentos/project.json` multiple times in one command path. Prefer passing or reusing an `AgentosProjectHandler`.
- Keep `agentos_command` lightweight. Record command identity and argv-like command info, but do not record environment variables, command output, secrets, or large config payloads.
- Logger write failures should be best-effort unless they reveal a fundamental project validation error. The command should generally proceed if the activity log cannot be written.
- Use existing Agentos time utilities where available for `timetag`.
- Use `uv` workflows for tests and reinstall the CLI after command changes.

## Out Of Scope

- Implementing a project list command.
- Implementing a deduplicated registry/index.
- Deriving known projects from the logs.
- Backfilling historical activity.
- Recording command outcomes, duration, stdout/stderr, or environment variables.
- Using the log to validate whether a folder is an Agentos project.

## Acceptance Signals

- `AgentosProjectHandler` exists and is the common class-based project checking mechanism.
- Existing root-only project helpers are backed by the handler-based mechanism.
- `record_project_command(...)` appends JSONL events under `~/.agentos/projects/activity/YYYYMM.jsonl`.
- Event records include `schema_version`, `timetag`, `project_id`, `project_root`, and `agentos_command`.
- At least a representative set of project-aware commands logs command activity.
- The implementation avoids duplicate marker parsing where the handler already validated or loaded `.agentos/project.json`.
- Logging does not make the activity log authoritative for project discovery.
- Tests cover log file path rolling by year/month, event shape, best-effort behavior, and at least one project-aware command integration.
- After CLI changes, refresh the installed executable with `uv tool install --reinstall --editable .`.

## Relevant Files Or Surfaces

- `src/agentos/_core/project.py`
- `src/agentos/cli.py`
- `src/agentos/skills/commands.py`
- Other project-aware command modules using `require_agentos_project_root(...)`
- `tests/`
- `~/.agentos/projects/activity/YYYYMM.jsonl`

Related prior work:

- `notes/live/531-project-command-enforcement-impl-req.md`
- `notes/live/551-skills-import-depot-linking-impl-req.md`

## Open Questions

The exact first set of command handlers to wire can be decided during implementation by scanning current project-aware commands. The design intent is to start with the obvious commands that already resolve a project in their command handler.

## Related Impl-Reqs

None directly superseded.

## End Log

- 2026-04-30: Created from design discussion. Accepted semantics: project command logger, rolling monthly JSONL under Agentos home, explicit command-handler logging, and a non-frozen `AgentosProjectHandler` that owns project validation and cached marker access.
- 2026-04-30: Implemented `AgentosProjectHandler`, the rolling JSONL project command logger, CLI argv capture, and explicit logging for `skills` commands plus `utils tmp-folder new`. Verified with `uv run python -m pytest -q` (`261 passed`) and refreshed the installed executable with `uv tool install --reinstall --editable .`.
