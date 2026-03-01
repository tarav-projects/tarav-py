# AgentOS CLI current interface & capabilities (tutorial)

This is about the **AgentOS CLI**, whose executable is **`agentcli`**.

Verified from current code/help in this repo (`agentos` v0.1.0).

## 1) What is the CLI entrypoint?

- Package: `agentos`
- Script entrypoint: `agentcli = "agentos.cli:main"`
- Alternate invocation: `uv run python -m agentos ...`

## 2) Quick start

```sh
uv sync
uv run agentcli --help
```

Sanity checks:

```sh
uv run agentcli doctor
uv run agentcli test --json
```

## 3) Current top-level interface

`agentcli` currently exposes these command groups:

1. `doctor` — environment and project diagnostics
2. `test` — smoke test for CLI wiring
3. `tape` — append-only JSONL tape operations
4. `git-refs` — git-grounded line-span reference tools
5. `skills` — inspect bundled skills directory
6. `prefix` — allocate numeric file prefixes
7. `mdblocks` — markdown block extraction/search/lint tools

## 4) Capability walkthrough by command group

### `doctor`

```sh
uv run agentcli doctor
```

Prints structured environment info (version, python, platform, project root, skills path/count).

### `test`

```sh
uv run agentcli test --json
```

Returns machine-readable smoke-test status.

### `skills`

```sh
uv run agentcli skills list --json
uv run agentcli skills path
uv run agentcli skills path todo-miner
```

Capabilities:
- list available local skills
- resolve skills root or one skill path

### `prefix`

```sh
uv run agentcli prefix next --root . --include notes/live --min 500 --width 3
```

Capabilities:
- scans files for used numeric prefixes
- supports include/exclude, custom width/min floor, JSON mode

### `mdblocks`

```sh
uv run agentcli mdblocks blocks notes --json
uv run agentcli mdblocks links notes --json
uv run agentcli mdblocks lint notes --fail-on error
uv run agentcli mdblocks find notes --query "tape" --top-k 10 --json
```

Capabilities:
- deterministic heading-block extraction
- line-link companion output
- structural linting with configurable failure policy
- query/regex block retrieval

### `tape`

Subcommands: `init`, `append`, `append-batch`, `path`, `list`, `summary`.

Core capabilities:
- create metadata-first JSONL tapes
- append single/batch entries with cargo + refs payloads
- generate/select tape paths with rotation/selection strategies
- filter/count/list entries and summarize tape stats

### `git-refs`

Subcommands: `from-span`, `from-text`, `list-text-matches`, `resolve-batch`, `from-markers`.

Core capabilities:
- produce formal git-aware references from exact spans/text/markers
- enumerate all text matches with references
- resolve batches of references back into extracted text (optionally strict, commit-aware)

## 5) Interface patterns to expect

- Built on `argparse` with nested subcommands.
- Several commands provide `--json` for automation pipelines.
- Most commands are deterministic/data-oriented (good for scripting and agent tooling).
