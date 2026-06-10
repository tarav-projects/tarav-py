# Agent Session Copy Command - impl-req

## Impl.Abstract

- **scope:** add an `agentos agent sessions copy` command for copying a provider-native chat session between provider homes, starting with Claude Code project transcript files.
- **status:** ready for implementation.
- **source:** user wants to test moving one Claude Code chat from `~/.claude-br` into `~/.claude` so the destination home/account can load or resume the session. The accepted command shape is:

```sh
agentos agent sessions copy \
  --provider claude-code \
  --from-home ~/.claude-br \
  --to-home ~/.claude \
  --session 67b706eb-d233-446f-96ce-926f52560eab \
  --check
```

- **goal:** provide a safe, inspectable Agentos command for copying native session artifacts without mixing account credentials or live process state.
- **target repository:** `/Users/pereiro/projects/agentos-project/agentos-py`

## Impl.Index

### Current.State

- `src/agentos/agent/commands.py` owns the `agentos agent` argparse namespace. It currently exposes `list`, `accounts`, `profiles`, `run`, and `ping`, but no `sessions` namespace.
- `src/agentos/agent/sessions.py` already provides provider-neutral session discovery and resolution concepts:
  - `list_chat_sessions(...)`
  - `find_chat_session(...)`
  - `resolve_chat_sessions(...)`
  - provider session URI and backing artifact summaries.
- `src/agentos/claude/session.py` already understands Claude Code project sessions:
  - transcript artifacts live under `projects/<encoded-cwd>/<session-id>.jsonl`
  - `find_claude_session_ref_by_id(...)` can locate a session id under target paths
  - `ClaudeSession.sources()` currently reports the transcript as the primary source.
- Claude home research confirmed that the primary transcript JSONL is the minimal artifact needed for a first portability test. The transcript has no obvious credential binding; resuming from the destination home should use destination auth.

### Accepted.Command.Surface

Add:

```sh
agentos agent sessions copy \
  --provider claude-code \
  --from-home <path> \
  --to-home <path> \
  --session <session-id> \
  [--check] \
  [--force] \
  [--json]
```

Initial implementation supports `--provider claude-code` only.

Semantics:

- `--check` plans and reports without mutating.
- without `--check`, copy the source transcript into the equivalent destination project path.
- preserve file metadata where reasonable, especially mtime.
- refuse to overwrite a different destination file unless `--force`.
- allow a byte-identical existing destination file as an idempotent no-op.
- emit JSON via `--json` and a concise human summary otherwise.

### Claude.Path.Mapping

For Claude Code, the copy plan should:

- find the source session by id under `<from-home>/projects`.
- require the source artifact to be a project transcript JSONL.
- compute the destination transcript path by preserving the path relative to `<from-home>`:

```text
<from-home>/projects/<encoded-cwd>/<session-id>.jsonl
  -> <to-home>/projects/<encoded-cwd>/<session-id>.jsonl
```

This avoids parsing or re-encoding cwd during the first slice and matches Claude's existing storage layout.

### Safety.Boundary

Do not copy account/auth state.

Do not copy live process descriptors:

```text
sessions/<pid>.json
```

Do not copy whole homes, global settings, plugins, cache, history, or keychain material.

Do not copy companion directories by default. Companion state can be added later behind explicit flags after the transcript-only behavior is proven.

### Future.Companion.State

Keep the implementation shaped so a later slice can add optional includes, but do not implement them unless explicitly requested:

```sh
--include file-history
--include session-env
```

`tasks/` should remain excluded until there is evidence that copying it is useful and safe. It may contain state that should not be treated as portable session content.

### No.Legacy.Allowed

Do not add compatibility aliases or old command paths.

Do not hide this under `agent accounts`; sessions are provider-native chat artifacts, not account credentials.

Do not route this through Chatlas. Chatlas archives/exports sessions; this command mutates provider homes so the provider CLI can load native state.

## Execution.Plan

### Slice 1 - Add Core Copy Planner

Status: pending.

Create a small core module, expected path:

```text
src/agentos/agent/session_copy.py
```

Responsibilities:

- define request/result dataclasses or simple typed payload builders for session copy.
- dispatch by provider.
- implement `check` and real copy behavior.
- provide byte comparison and overwrite policy helpers.
- return a stable payload containing:
  - `status`
  - `command`
  - `provider`
  - `session_id`
  - `from_home`
  - `to_home`
  - `actions`
  - `warnings`

Observable result:

- a direct Python call can produce a dry-run plan for a Claude session without mutating files.

Check:

- unit test creates a temporary Claude-like source home with `projects/<encoded>/<id>.jsonl` and verifies `check=True` reports the expected destination path without creating it.

### Slice 2 - Implement Claude Transcript Copy

Status: pending.

Add Claude-specific copy planning either inside `agentos.agent.session_copy` or in an adjacent `agentos.claude.session_copy` helper.

Behavior:

- locate source transcript by session id under `<from-home>/projects`.
- error clearly when the session is missing or ambiguous.
- create destination parent directories on real copy.
- copy the transcript preserving metadata.
- if destination exists:
  - byte-identical -> no-op action
  - different and no `--force` -> `CliError`
  - different and `--force` -> overwrite action

Observable result:

- real copy creates `<to-home>/projects/<encoded>/<id>.jsonl`.

Check:

- unit tests cover missing source, dry-run no mutation, real copy, idempotent existing copy, overwrite refusal, and forced overwrite.

### Slice 3 - Add `agentos agent sessions copy`

Status: pending.

Update `src/agentos/agent/commands.py`:

- add `sessions` under `agentos agent`.
- add `copy` under `agentos agent sessions`.
- parse:
  - `--provider`
  - `--from-home`
  - `--to-home`
  - `--session`
  - `--check`
  - `--force`
  - `--json`
- call the core copy function.
- format human output with planned/copied/no-op action lines.

Observable result:

```sh
agentos agent sessions copy --provider claude-code --from-home SRC --to-home DST --session ID --check
```

prints a dry-run plan.

Check:

- CLI tests assert help wiring and dry-run JSON/human output.

### Slice 4 - End-To-End Smoke Against Real Homes

Status: pending.

After unit tests pass, run a real dry-run against the user's current test case:

```sh
agentos agent sessions copy \
  --provider claude-code \
  --from-home ~/.claude-br \
  --to-home ~/.claude \
  --session 67b706eb-d233-446f-96ce-926f52560eab \
  --check
```

If the dry-run plan is correct and the user approves or the execution request permits mutation, run the same command without `--check`.

Validation commands:

```sh
uv run pytest tests/test_agent_session_copy.py -q
uv run pytest tests/test_agent_session_copy.py tests/test_agent_account_registry_commands.py -q
uv run ruff check src/agentos/agent src/agentos/claude tests/test_agent_session_copy.py
git diff --check
```

Refresh installed CLI after implementation:

```sh
uv tool install --reinstall --editable .
```

## Acceptance Signals

- `agentos agent --help` lists `sessions`.
- `agentos agent sessions copy --help` documents the accepted command surface.
- `--check` reports the source and destination transcript path without mutating.
- real copy places only the Claude transcript JSONL in the destination home.
- existing different destination files are protected unless `--force`.
- no account registry, credentials, keychain state, settings, or live process descriptors are copied.
- targeted tests and Ruff pass.

## Impl.Log

- 2026-06-09: Created from the accepted command proposal for moving a Claude Code native session transcript between homes. The first implementation is intentionally transcript-only so the portability test is small, reversible, and easy to inspect.
