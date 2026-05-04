# Project-Aware Prefix Next - impl-req

## Impl-Req State

Implemented for `agentos prefix next`; diagnostics and full custom prefix config remain deferred.

## User Intent

Redesign `agentos prefix next` from a generic folder scanner into an `Agentos.Project` aware allocator for numbered project surfaces.

The caller should provide the numbered target path, and Agentos should discover the project root, load prefix policy through project config mechanics, and allocate the next prefix from the resolved route.

The first implementation should focus only on `next`. Do not implement `check`, `doctor`, or full custom project prefix config yet.

## Why This Exists

Current `agentos prefix next` requires callers to know scanner internals:

```sh
agentos prefix next --root . --include notes/live --min 500 --width 3
```

That is too low-level for Agentos numbered surfaces. The durable markdown design in `agentos-md` treats file numbers as stable project-surface handles. Numbering should therefore be project-aware, route-based, and policy-driven, not ad hoc per-folder command knowledge.

The desired user-facing shape uses named options:

```sh
agentos prefix next --target notes/live
agentos prefix next --target notes/index
agentos prefix next --project /path/to/project --target notes/live
```

## Current Situation

Current implementation lives in:

- `src/agentos/prefix/commands.py`
- `src/agentos/prefix/core.py`

Current behavior:

- command surface is `agentos prefix next`
- scanner options are `--root`, `--include`, `--exclude`, `--min`, `--width`, `--no-default-excludes`, and `--json`
- prefixes are extracted from filenames matching `^(\d{width})-`
- allocation is append-only within the selected scan result: `max(existing eligible prefixes) + 1`, or `minimum`
- default minimum is `500`
- default width is `3`
- default scan excludes come from `agentos._core.scan.DEFAULT_SCAN_EXCLUDES`
- command is not `Agentos.Project` aware
- command has no route/policy concept
- command has no dedicated tests found for prefix behavior

Existing project helpers are available in `src/agentos/_core/project.py`, including:

- `require_agentos_project(...)`
- `require_agentos_project_root(...)`
- `project_config_path(...)`
- `load_project_config(...)`

Current config files have class guards:

- project config class is `agentos.project.config`
- project config path is `.agentos/config.json`

Relevant design surfaces:

- `agentos-md/notes/index/103-File.Numbering.Protocol.md`
- `agentos-md/notes/index/101-Md.Surface.md`
- `agentos-md/notes/index/104-Maintenance.System.md`
- `agentos-md/skills/agentos-file-numbering-base/SKILL.md`
- `agentos-md/skills/agentos-live-note-base/SKILL.md`
- `agentos-md/skills/agentos-live-scripts-base/SKILL.md`

## Requested Change

Implement a project-aware `agentos prefix next --target <target>` flow.

### CLI Surface

Add a required named target option to `prefix next`:

```sh
agentos prefix next --target <target>
agentos prefix next --project /path/to/project --target <target>
agentos prefix next --project --target <target>
```

Expected examples:

```sh
agentos prefix next --target notes/live
agentos prefix next --target notes/index
agentos prefix next --target dev/live
agentos prefix next --project /Users/pereiro/projects/agentos-project/agentos-py --target notes/live
```

Use the existing project command convention for `--project`:

- optional `Path`
- `nargs="?"`
- `const=Path(".")`
- bare `--project` targets the current working directory
- commands require an existing project marker when operating in project mode

### Project Resolution

For the named target mode:

- resolve the existing `Agentos.Project`
- parent-walk from `cwd` when `--project` is omitted
- use the explicit project target when `--project` is provided
- require `.agentos/project.json`
- do not initialize or create projects
- resolve the target as a normalized project-relative path
- reject absolute targets for v1 unless implementation reveals an existing project command convention that clearly supports them
- reject target paths that escape the project root

### Prefix Policy Loading

Create prefix policy loading mechanics now, even though v1 should use the default policy.

Policy loader behavior:

1. Load `.agentos/config.json` for the resolved project.
2. If the config has no `prefix` field, return the default prefix policy object.
3. If the config has a `prefix` field, fail clearly for v1 unless full custom parsing is implemented intentionally.

Suggested error:

```txt
custom project prefix config is not supported yet
```

This preserves the future config contract without silently accepting a half-implemented shape.

Default policy shape should be represented as data, not scattered constants inside allocator logic:

```json
{
  "scan": {
    "include": ["notes", "dev/live"],
    "exclude": []
  },
  "routes": {
    "__reserved": {
      "fixed": {
        "notes/index/000-index.md": 0,
        "notes/live/010.TODOS.md": 10
      }
    },
    "notes/index": {
      "range": [100, 499]
    },
    "*": {
      "range": [500, 999]
    }
  }
}
```

Important reserved-prefix wording:

- reserved prefixes are manually assigned fixed-role prefixes
- reserved prefixes are part of the numbering system
- reserved prefixes are not allocated by `prefix next`
- reserved route recognition exists to prepare for future `prefix doctor` or equivalent diagnostics

### Route Resolution

Route resolution for `next`:

- `__reserved` is internal and never selected as a user allocation route
- `*` is the fallback route
- path routes match exact paths and descendants
- if multiple path routes match, choose the longest matching route
- target `notes/index` resolves to `notes/index`
- target `notes/index/archive` resolves to `notes/index`
- target `notes/live` resolves to `*`
- target `dev/live` resolves to `*`

### Scan Scope

The command should scan the project-numbered surface, not only the target folder.

Default global scan includes:

- `notes`
- `dev/live`

Default excludes:

- use existing `DEFAULT_SCAN_EXCLUDES`
- also allow explicit command-line excludes if those remain supported

The scanner should ignore missing default include roots. For example, a project may have `notes/` but no `dev/live/` yet.

### Include/Exclude Filters

Keep include/exclude filtering available, but align it with project-aware semantics.

Suggested v1 behavior:

- command-line `--include` values are project-relative scan roots
- command-line `--exclude` values are project-relative exclude patterns
- includes override the policy default scan includes for that invocation
- excludes add to the policy/default excludes for that invocation
- include/exclude do not change route selection
- include/exclude do not change the selected route range

Future policy can support per-route filters:

```json
{
  "routes": {
    "notes/index": {
      "range": [100, 499],
      "scan": {
        "include": ["notes/index"],
        "exclude": ["notes/index/archive"]
      }
    }
  }
}
```

If route-level filters are implemented in v1, use this combination rule:

- effective includes = route `scan.include` if present, otherwise global `scan.include`
- effective excludes = global `scan.exclude` plus route `scan.exclude`

But route-level filters are not required for v1.

### Allocation Behavior

Use the selected route range:

- `notes/index`: allocate in `100-499`
- `*`: allocate in `500-999`
- `__reserved`: never allocated by `next`

Allocation remains append-only:

- scan project scope for `NNN-*` ordinary numbered files
- extract numeric prefixes with width `3`
- consider only prefixes in the selected route range
- return the lower bound if no existing prefix exists in that route range
- otherwise return `max(existing in range) + 1`
- fail clearly if the next value exceeds the route maximum

Examples:

Given:

```txt
notes/index/100-Agentos.Index.Notes.md
notes/live/500-session.md
dev/live/501-probe.py
notes/live/010.TODOS.md
```

Then:

```sh
agentos prefix next --target notes/index
# 101

agentos prefix next --target notes/live
# 502

agentos prefix next --target dev/live
# 502
```

Reserved files such as `notes/live/010.TODOS.md` should be recognized by policy as reserved fixed-role files, but they do not affect ordinary allocation.

### JSON Output

Keep `--json` and update it to describe project-aware allocation.

Suggested fields:

```json
{
  "next_prefix": "502",
  "next_value": 502,
  "project_root": "/abs/path",
  "target": "notes/live",
  "route": "*",
  "range": [500, 999],
  "scan": {
    "includes": ["notes", "dev/live"],
    "excludes": [".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules"]
  },
  "matched_prefix_count": 2,
  "reserved_prefix_count": 2,
  "policy_source": "default"
}
```

`reserved_prefix_count` is useful in JSON, but plain output should remain quiet.

### Legacy Compatibility

Do not break existing callers abruptly if avoidable.

Recommended approach:

- support the new project-aware positional-target mode as the primary path
- keep old scanner mode when `--root` or old scanner flags are used without a target
- do not require project discovery for legacy scanner mode
- make tests cover both paths if legacy mode remains

If keeping both modes complicates argparse too much, prefer a clear compatibility decision and document it in the implementation update.

## Constraints And Invariants

- Implement `next` only.
- Do not implement `prefix check`, `prefix doctor`, or project-wide diagnostics yet.
- Do not implement full custom `prefix` config parsing unless it stays small and well-tested.
- Do not allocate reserved fixed-role prefixes.
- Do not treat reserved prefixes as invalid everywhere; they are manually assigned fixed-role prefixes.
- Do not warn about missing reserved files in plain `next` output.
- Keep plain output machine-friendly: print only the next prefix on success.
- Keep allocation append-only; do not fill gaps.
- Keep three-digit width for the project-aware default policy.
- Keep default scan excludes.
- Do not create or initialize Agentos projects.
- Do not renumber files.
- Do not mutate project config.

## Out Of Scope

- `agentos prefix check`
- `agentos prefix doctor`
- duplicate report command
- range violation report command
- accidental renumbering detection
- full custom project prefix policy support
- project config migration tooling
- automatically creating numbered files
- changing md-surface skills or notes as part of the implementation

## Acceptance Signals

- `agentos prefix next --target notes/live` works inside an existing Agentos project and prints the next `500-999` prefix.
- `agentos prefix next --target notes/index` works inside an existing Agentos project and prints the next `100-499` prefix.
- `agentos prefix next --project /path/to/project --target notes/live` resolves the explicit project target.
- bare `--project` follows existing project command convention.
- project-aware `prefix next` records a project command log event.
- command fails clearly outside an Agentos project when using project-aware target mode.
- `.agentos/config.json` without a `prefix` field uses the default policy object.
- `.agentos/config.json` with a `prefix` field fails clearly if custom parsing is not implemented.
- default scan includes `notes` and `dev/live`, ignoring missing include roots.
- default scan excludes `.git`, `.venv`, `__pycache__`, `.mypy_cache`, `.pytest_cache`, and `node_modules`.
- `notes/index` and descendants resolve to the `100-499` route.
- other targets resolve to the `500-999` fallback route.
- allocation scans across the configured project scan scope, not only the target folder.
- reserved fixed files do not affect ordinary allocation.
- `--json` includes project-aware metadata.
- plain success output remains just the prefix.
- focused tests cover route resolution, project discovery, config fallback, range exhaustion, include/exclude behavior, JSON output, and legacy mode if preserved.

## Relevant Files Or Surfaces

- `src/agentos/prefix/commands.py`
- `src/agentos/prefix/core.py`
- `src/agentos/prefix/__init__.py`
- `src/agentos/_core/project.py`
- `src/agentos/_core/scan.py`
- `tests/test_prefix_commands.py` or a new focused equivalent
- `tests/_helpers.py`
- `.agentos/project.json`
- `.agentos/config.json`
- `agentos-md/notes/index/103-File.Numbering.Protocol.md`
- `agentos-md/notes/index/101-Md.Surface.md`
- `agentos-md/notes/index/104-Maintenance.System.md`
- `agentos-md/skills/agentos-file-numbering-base/SKILL.md`

## Open Questions

- Should legacy scanner mode be preserved indefinitely, deprecated, or moved behind a different command in a later change?
- If a custom `prefix` field exists in `.agentos/config.json`, should v1 fail immediately or parse the exact default-shaped config?
- Should JSON output include reserved path details or only aggregate `reserved_prefix_count`?

None of these block the first implementation if the conservative defaults above are followed.

## Related Impl-Reqs

- `notes/live/552-project-command-logger-impl-req.md` is related only as prior project-command infrastructure context.
- Future follow-up: implement `agentos prefix doctor` or `agentos prefix check` using the same policy object.

## End Log

- 2026-05-04: Created from the converged design discussion for project-aware `agentos prefix next`; scope intentionally excludes diagnostics and full custom config support.
- 2026-05-04: Implemented project-aware `agentos prefix next --target <target>` with default prefix policy loading, route-based allocation, reserved fixed-prefix recognition, project scan includes, `--project`, project command logging, JSON metadata, legacy scanner preservation, and focused tests in `tests/test_prefix_commands.py`. Verified with `uv run python -m pytest tests/test_prefix_commands.py -q` (`16 passed`) and `uv run python -m pytest -q` (`286 passed`). Ruff was not run because the project environment does not currently include `ruff`.
