# AgentOS CLI current interface & capabilities (tutorial)

This is about the **AgentOS CLI**, whose executable is **`agentos`**.

Verified from current code/help in this repo (`agentos` v0.1.0).

## 1) What is the CLI entrypoint?

- Package: `agentos`
- Script entrypoint: `agentos = "agentos.cli:main"`
- Alternate invocation: `uv run python -m agentos ...`

## 2) Quick start

```sh
uv sync
agentos --help
```

Sanity checks:

```sh
agentos doctor
agentos test --json
```

## 3) Current top-level interface

`agentos` currently exposes these command groups:

1. `agent` — configured agent-provider resolution and execution
2. `init` — initialize project or global Agentos storage
3. `rev-parse` — inspect Agentos.Project resolution state
4. `doctor` — environment and Agentos.Project diagnostics
5. `test` — smoke test for CLI wiring
6. `chat` — provider-facing live chat discovery, extraction, and account status
7. `chatlas` — dataset-facing chat archive/query/export surface
8. `tara-tapes` — Tara spec-first JSONL tape operations
9. `tape` — folder-backed JSONL tape operations
10. `git-refs` — git-grounded line-span reference tools
11. `skills` — project-local routed skills control
12. `prefix` — allocate numeric file prefixes
13. `utils` — small agent-facing helpers
14. `mdblocks` — markdown block extraction/search/lint tools
15. `mission` — project-scoped mission tracking

## 4) Capability walkthrough by command group

### Project targeting

`agentos` now distinguishes between:

- `project target` — the root selected by implicit discovery or `--project`
- `existing project` — a project target with `.agentos/project.json`

Shared targeting rules:

- implicit discovery parent-walks from `cwd`
- `--project <path>` explicitly selects a target
- bare `--project` selects current `pwd`

Surface policy is command-specific:

- `doctor` can inspect a project target without requiring an existing project
- `agent ...` and the relevant `chat ...` leaves use `--project` for config resolution only
- `skills ...`, `mission ...`, `utils tmp-folder new`, and `tape --tape ...` require an existing project

### `init` / `rev-parse`

```sh
agentos init --scope project --project .
agentos rev-parse --is-inside-agentos-project
agentos rev-parse --show-toplevel
```

Capabilities:
- initialize an explicit project target or the global `~/.agentos` home
- inspect whether the current directory is inside an Agentos.Project
- resolve the nearest project root without mutating anything

### `doctor`

```sh
agentos doctor
agentos doctor --project
agentos doctor --project /path/to/repo
```

Capabilities:
- print structured environment info plus Agentos.Project resolution state
- inspect `project`, `global`, or `auto` effective storage scopes
- inspect an explicit project target without requiring that it already be an existing project

### `agent`

```sh
agentos agent list
agentos agent list --project
agentos agent run --provider codex --instance work --project /path/to/repo --cwd /tmp/work -- prompt text
```

Capabilities:
- list configured provider instances from global and selected project config
- run one resolved provider instance with model and prompt overrides
- separate config resolution (`--project`) from launched process working directory (`--cwd`)

### `test`

```sh
agentos test --json
```

Returns machine-readable smoke-test status.

### `chat`

```sh
agentos chat debug list --provider codex --output json
agentos chat debug find session-id-or-query --project
agentos chat debug extract session-id-or-query --project /path/to/repo
agentos chat accounts stats --project /path/to/repo --output usage
```

Capabilities:
- inspect live provider sessions directly from configured or default provider homes
- resolve a provider-agnostic session query and extract dialog from live artifacts
- query configured account status and usage across supported providers
- use `--project` for config resolution without becoming a project-required surface

### `skills`

```sh
agentos skills list --json
agentos skills path --depot
agentos skills path todo-miner
```

Capabilities:
- list routed skills for the resolved existing project
- inspect configured depot roots or one routed skill path
- sync and audit project-local routed skills depots

### `prefix`

```sh
agentos prefix next --root . --include notes/live --min 500 --width 3
```

Capabilities:
- scans files for used numeric prefixes
- supports include/exclude, custom width/min floor, JSON mode

### `mdblocks`

```sh
agentos mdblocks blocks notes --json
agentos mdblocks links notes --json
agentos mdblocks lint notes --fail-on error
agentos mdblocks find notes --query "tape" --top-k 10 --json
```

Capabilities:
- deterministic heading-block extraction
- line-link companion output
- structural linting with configurable failure policy
- query/regex block retrieval

### `tape`

Subcommands: `init`, `append`, `append-batch`, `consolidate`, `query`, `verify`, `config`, `doctor`.

Core capabilities:
- initialize and write folder-backed JSONL tapes
- support project mode (`--tape`) and headless explicit-root mode (`--root`)
- query committed or best-effort views and inspect tape config/health

### `git-refs`

Subcommands: `from-span`, `from-text`, `list-text-matches`, `resolve-batch`, `from-markers`.

Core capabilities:
- produce formal git-aware references from exact spans/text/markers
- enumerate all text matches with references
- resolve batches of references back into extracted text (optionally strict, commit-aware)

## 5) Interface patterns to expect

- Built on `argparse` with nested subcommands.
- Several commands provide `--json` for automation pipelines.
- Project targeting is explicit and command-specific rather than inferred from ad hoc local folders.
- Most commands are deterministic/data-oriented (good for scripting and agent tooling).
