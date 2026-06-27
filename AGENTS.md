# AGENTS.md

## Python Tooling Preference

- Use `uv` as the default Python environment and package management system.
- Prefer `uv sync`, `uv run`, and `uv tool install` over direct `pip`/`venv` workflows.

## Run agentos cli
- check `agentos --version` to confirm that it is installed on the system.
- run `agentos` to see the available commands and options.
- Prefer direct `agentos ...` shell commands over `uv run agentos ...` when `agentos` is already installed.
- The `agentos` executable is owned by `agentos-cli`, not this package. After changing CLI entrypoint or command-registration code, refresh the installed executable from `agentos-cli/` with `uv tool install --reinstall --editable .` so `~/.local/bin/agentos` stays in sync.
- Changes limited to library/runtime code in `agentos-py` do not require reinstalling `agentos-cli` unless they affect the installed CLI behavior you are actively testing.

## Compatibility Policy

- Do not add backward-compatibility aliases or compatibility layers unless explicitly requested.
- Prefer clean namespace and interface changes over preserving legacy command paths.

## Markdown Block Scanning Preference

- When a task requires extracting markdown blocks, use `agentos stdlib mdblocks blocks` first.
- Use `agentos stdlib mdblocks links` when you need companion `path#Lline` references for those blocks.
- Use `agentos stdlib mdblocks find --query ...` for deterministic block retrieval by text/regex.
- Prefer these commands over ad-hoc manual block parsing from raw file reads.
