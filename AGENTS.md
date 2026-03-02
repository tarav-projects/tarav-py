# AGENTS.md

## Python Tooling Preference

- Use `uv` as the default Python environment and package management system.
- Prefer `uv sync`, `uv run`, and `uv tool install` over direct `pip`/`venv` workflows.

## Run agentos cli
- check `agentos --version` to confirm that it is installed on the system.
- run `agentos` to see the available commands and options.
- Prefer direct `agentos ...` shell commands over `uv run agentos ...` when `agentos` is already installed.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Markdown Block Scanning Preference

- When a task requires extracting markdown blocks, use `agentos mdblocks blocks` first.
- Use `agentos mdblocks links` when you need companion `path#Lline` references for those blocks.
- Use `agentos mdblocks find --query ...` for deterministic block retrieval by text/regex.
- Prefer these commands over ad-hoc manual block parsing from raw file reads.
