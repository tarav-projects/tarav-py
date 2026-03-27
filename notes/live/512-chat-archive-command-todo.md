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
- Follow-up fix: `chat archive` now also inherits extra home-based instances from `chat.provider_instances`, so existing session-home config for `~/.codex-jp` and `~/.codex-tk` is archived without duplication.
- Follow-up fix: restored the old `codex-tk` `_auth-tk.json` exclusion and reran the live Codex archive.
- Follow-up change: moved session config from `chat.provider_instances` to `chat.session.provider_instances`, updated the code/tests, and migrated the live `~/.agentos/config.json` to match.
- Follow-up change: archive layout now mirrors homes directly by home-relative path under `~/.agentos/chat-archive`, so `~/.codex-jp/...` archives to `~/.agentos/chat-archive/.codex-jp/...` and the old `provider/instance` folders are migrated away.
