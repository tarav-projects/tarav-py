# Chat Archive Command TODO

## Goal
- Add `agentos chat archive`.
- Move the archive/checkpoint behavior from `trackagents/scripts/track.jl` into `agentos`.
- Store the git-tracked archive repo at `~/.agentos/chat-archive`.
- Use a family/instance config model aligned with `agentos chat session`.

## Checklist
- [x] Inspect `trackagents` behavior and existing `agentos chat` config patterns.
- [x] Define archive config shape and runtime model.
- [x] Implement archive family/instance loading with built-in defaults.
- [x] Implement sync + git checkpoint behavior.
- [x] Wire `agentos chat archive` into the CLI.
- [x] Add tests for default behavior.
- [x] Add tests for configured extra instances.
- [x] Add tests for include/exclude handling.
- [x] Run targeted tests.
- [x] Refresh installed `agentos` CLI.

## Progress Notes
- Confirmed old behavior: mirror configured homes into one git repo, skip missing sources, commit only on changes with `checkpoint: <timestamp>`.
- Confirmed current `agentos chat session` config uses provider instances with default families plus configured extras from `config.json`.
- Implemented `agentos chat archive` with built-in families `claude-code`, `copilot-cli`, `codex`, `gemini-cli`, `agents`, and `openclaw`.
- Archive repo root is now `~/.agentos/chat-archive`.
- Config lives under `chat.archive.provider_instances` and supports `provider`, `home`/`homes`, `instance`, `includes`, and `excludes`.
- Verified with the full `agentos` test suite and refreshed the installed `agentos` executable.
