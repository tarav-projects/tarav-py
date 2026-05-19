# Projects CLI List Resolve - impl-req

## Impl.Abstract

- **scope:** add two `agentos projects` commands for Agentos.Project discovery and resolver verification
- **status:** implemented
- **source:** 2026-05-19 CLI design discussion; user accepted `projects list --root <dir>` and `projects resolve --project [PROJECT] --project-base PROJECT_BASE`
- **target project:** `agentos-py`
- **primary surfaces:** `src/agentos/project/commands.py`, `src/agentos/_core/project.py`, `src/agentos/cli.py`, focused CLI tests

## Impl.Index

### Project.Command.Namespace

- `agentos projects` should be a new command namespace, distinct from existing top-level `agentos rev-parse`
- the namespace is for higher-level project operations, not for replacing existing `init` or `rev-parse`
- implementation should register the namespace through the existing argparse command registration path
- keep command wording and help consistent with current Agentos.Project terminology

### Projects.List.Root

- accepted command shape: `agentos projects list --root <dir>`
- `--root` is required and path-valued
- the command should scan under the root for Agentos.Project markers at `.agentos/project.json`
- the observable default output should be one resolved project root path per line, sorted deterministically
- a directory is an Agentos.Project only when its `.agentos/project.json` marker is present; Agentos-looking folders alone are not enough
- the command is a headless discovery operation and should not require `--project`

### Projects.Resolve.Assertion

- accepted command shape: `agentos projects resolve --project [PROJECT] --project-base PROJECT_BASE`
- `--project-base` is required
- `--project` keeps existing Agentos CLI semantics: optional value, bare `--project` targets current working directory, omitted `--project` uses discovery from current working directory
- `--project-base` keeps its existing semantic: assert the resolved project root folder basename, not marker name and not full path
- the command exists as a resolver double-check; on success it should print `true`
- mismatch and resolution failure should be nonzero and consistent with existing project assertion/error behavior unless implementation discovers a stronger local convention

### Project.Flag.Consistency

- existing project-aware commands use `--project [PROJECT]` with `nargs="?"`, `const=Path(".")`, and `default=None`
- existing `--project-base` behavior is implemented by `assert_project_base(...)` in `agentos._core.project`
- `agentos stdlib prefix next` already makes `--project-base` required while keeping `--project` optional; `projects resolve` should follow that pattern
- do not introduce `--expect-base`, `--project-root`, or other new project selector/assertion flags
- do not add backward-compatibility aliases

## Execution.Plan

### Slice 1 - Add project discovery primitive

- add a small reusable function for finding Agentos.Project roots under a supplied root
- path: filesystem root -> descendant `.agentos/project.json` markers -> project root paths
- observable: test fixtures with multiple nested/sibling projects produce sorted project root paths
- check: focused unit/CLI test for `projects list --root`
- status: completed

### Slice 2 - Register `agentos projects list`

- add the `projects` argparse namespace and `list` subcommand in the existing project command module or an adjacent project commands module
- path: `agentos` parser -> `projects` parser -> `list --root <dir>` handler
- observable: `agentos projects list --root <dir>` prints discovered project roots one per line
- check: CLI test calls `main(["projects", "list", "--root", ...])` and asserts output
- status: completed

### Slice 3 - Register `agentos projects resolve`

- add `projects resolve` with `--project [PROJECT]` and required `--project-base PROJECT_BASE`
- reuse existing project resolution and basename assertion helpers rather than inventing another project flag contract
- path: cwd or explicit `--project` -> existing Agentos.Project resolution -> `assert_project_base(...)` -> `true`
- observable: matching basename prints `true` and exits `0`
- check: CLI tests for cwd discovery, explicit project path, bare `--project`, required `--project-base`, basename mismatch, and marker-name mismatch avoidance
- status: completed

### Slice 4 - Verify command surface

- run focused tests for the new project command behavior
- run the broader Python test suite if feasible in the current environment
- refresh the installed executable with `uv tool install --reinstall --editable .` after CLI changes, per `agentos-py/AGENTS.md`
- manually check help output for `agentos projects --help`, `agentos projects list --help`, and `agentos projects resolve --help`
- observable: installed `agentos` exposes the new commands and focused tests pass
- status: completed

## Impl.Log

- 2026-05-19: Created Impl.Req from CLI design discussion. Accepted decisions: add `agentos projects list --root <dir>`; add `agentos projects resolve --project [PROJECT] --project-base PROJECT_BASE`; keep `--project-base` required for `resolve`; reuse existing project flag semantics and avoid new project flags.
- 2026-05-19: Implemented project discovery primitive, registered `agentos projects list`, registered `agentos projects resolve`, and added focused CLI tests covering list output, root requirement, current-directory resolution, explicit `--project`, bare `--project`, required `--project-base`, mismatch failure, and marker-name avoidance. Focused verification: `uv run python -m pytest tests/test_project_commands.py -q` passed (`8 passed`).
- 2026-05-19: Completed verification. Broader suite passed with `uv run python -m pytest -q` (`413 passed`). Touched-file lint passed with `uv run ruff check src/agentos/_core/project.py src/agentos/project/commands.py tests/test_project_commands.py`. Full-repo `uv run ruff check .` remains blocked by pre-existing deprecated/dev lint failures outside this change. Refreshed installed CLI with `uv tool install --reinstall --editable .`. Manual installed-command checks confirmed `agentos --help` lists `projects`, `agentos projects --help` exposes `list` and `resolve`, `agentos projects resolve --project /Users/pereiro/projects/agentos-project/agentos-py --project-base agentos-py` prints `true`, and `agentos projects list --root /Users/pereiro/projects/agentos-project` lists both `agentos-md` and `agentos-py`.
