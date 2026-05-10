# Agent Command Profile And Chat Package Reorg - impl-req

## Impl-Req State

This request has been implemented: agent mechanics moved under `agentos.agent`, `agentos agent run` now uses `--profile`, and the old `agentos.chat` package has been removed.

## User Intent

The user wants the codebase and CLI to reflect the newer Agentos agent model more directly.

The important user-pointed elements are:

- `agentos/chat` is now a legacy package location and should go away.
- Agent-related mechanics belong under `agentos/agent`.
- `agentos agent run` should become the normalized calling surface for provider agents.
- CLI arguments should produce an `AgentConfig`, then build a concrete `<Provider>.Agent`.
- `--instance` should be renamed to `--profile`.
- A profile is not a runtime object. It is only a named config preset.
- Explicit CLI args such as `--home`, `--account`, `--model`, and prompt should override the selected profile.
- Do not introduce an `AgentProfile` runtime object unless a later design explicitly requires it.
- Do not touch or redesign `agentos chatlas` behavior in this pass.

## Why This Exists

The previous refactor removed `LegacyProviderConfig` and moved runtime construction toward:

```text
agent.instances[] / config input
  -> AgentConfig
  -> <Provider>.Agent
```

That improved the model, but the package topology still says the old thing:

```text
agentos/chat/
  providers.py
  core.py
  session_primitives.py
  accounts.py
  commands.py
  extractors/
```

Most of that is no longer "chat" as a domain. It is agent configuration, agent account/status support, live provider session discovery, provider session ref helpers, and provider raw extraction.

The CLI also still exposes `--instance`, which sounds like selecting a runtime object. The user clarified that the command should build a `<Provider>.Agent` from merged configuration. The selected named preset is better called a `profile`.

## Current Situation

Current generic agent surfaces:

```text
agentos agent list
agentos agent run
agentos agent accounts stats
```

Current downstream Chatlas surfaces:

```text
agentos chatlas update
agentos chatlas stats
agentos chatlas query
agentos chatlas export
agentos chatlas raw path
agentos chatlas raw export
```

Current provider-specific Codex mux surface:

```text
agentos codex --account ... --home ... --just-link --dry-run -- <codex args>
```

Current implementation shape:

- `agentos/agent/primitives.py` owns `Agent`, `AgentConfig`, `AgentRunCommand`, and agent identity helpers.
- `agentos/agent/providers.py` builds concrete provider agents from `AgentConfig`.
- Provider packages such as `agentos/codex`, `agentos/claude`, and `agentos/copilot` own concrete `Agent` and `SessionRef` classes.
- `agentos/chat/providers.py` still parses configured agent inputs into `AgentConfig`.
- `agentos/chat/core.py` still owns live session coordination.
- `agentos/chat/session_primitives.py` still owns central provider-session-ref helper dispatch.
- `agentos/chat/accounts.py` still owns agent account/status collection.
- `agentos/chat/commands.py` still owns account stats CLI rendering used by `agentos agent accounts stats`.
- `agentos/chat/extractors/` still owns provider raw extractors used by live session stats and Chatlas.
- `agentos/chatlas` imports from `agentos.chat` and should keep its public behavior unchanged in this pass.

## Requested Change

Implement a package and CLI terminology cleanup that makes `agentos.agent` the owner of agent mechanics.

### 1. Rename CLI `--instance` To `--profile`

Update `agentos agent run` so the user selects named config presets with:

```text
--profile <id>
```

not:

```text
--instance <id>
```

The CLI should treat a profile as a named config preset, not as a runtime object.

The command should resolve:

```text
provider defaults
  < profile config, if --profile is passed
  < explicit CLI args
  -> AgentConfig
  -> <Provider>.Agent
  -> AgentRunCommand
```

### 2. Add Normalized Agent Run Axes

`agentos agent run` should support the important invocation axes:

```text
--provider
--profile
--home
--account
--model
--cwd
--dry-run
prompt
```

Expected semantics:

- `--provider`: provider family to build.
- `--profile`: named config preset for that provider.
- `--home`: provider-home override for the resulting `AgentConfig`.
- `--account`: credential/auth identity axis. This is separate from `--profile`.
- `--model`: model override.
- `--cwd`: subprocess working directory.
- prompt: payload passed to the provider agent.

`--profile tk --home /Users/pereiro/.codex` means:

1. Load the `tk` profile for the selected provider.
2. Override the profile home with `/Users/pereiro/.codex`.
3. Build `AgentConfig`.
4. Build the concrete `<Provider>.Agent`.
5. Resolve and run the command.

`--profile work --account tk` means:

1. Use the `work` config preset.
2. Run with account/auth identity `tk`.

The implementation may initially support `--account` only where the provider has an existing account/mux capability, but the CLI model should keep account separate from profile.

### 3. Move Agent Mechanics Out Of `agentos.chat`

Reorganize the package layout so `agentos.agent` owns the mechanics currently living under `agentos.chat`.

Target layout:

```text
agentos/agent/
  primitives.py        Agent, AgentConfig, AgentRunCommand
  providers.py         load/resolve/build provider agents
  commands.py          agent CLI registration
  config.py            moved from chat/providers.py
  accounts.py          moved from chat/accounts.py
  account_commands.py  account stats CLI/rendering from chat/commands.py
  sessions.py          moved from chat/core.py
  session_refs.py      moved from chat/session_primitives.py
  extractors/          moved from chat/extractors/*
```

Remove `agentos/chat` after imports are updated. Do not keep compatibility aliases unless the implementation discovers an unavoidable transitional need and records it explicitly.

### 4. Keep Chatlas As A Downstream Subsystem

Do not redesign `agentos chatlas` in this pass.

Update Chatlas imports to consume the moved agent modules:

```text
agentos.agent.config
agentos.agent.accounts
agentos.agent.sessions
agentos.agent.session_refs
agentos.agent.extractors
```

Chatlas command behavior should remain unchanged.

## Constraints And Invariants

- Do not recreate `LegacyProviderConfig`.
- Do not add `AgentProfile` as a runtime model.
- A profile is only named configuration input.
- The final runtime object is always a concrete `<Provider>.Agent`.
- Explicit CLI args override profile config.
- `--profile` and `--account` are separate axes.
- `--home` is a config override or ad hoc provider-home input, not a distinct runtime object.
- Keep `agentos chatlas` public commands stable in this pass.
- Keep provider-specific behavior inside provider agents or provider support modules.
- Do not preserve old imports from `agentos.chat` as compatibility shims unless explicitly approved.
- Prefer mechanical moves plus import updates before deeper behavior changes.
- Keep tests green at each vertical slice where practical.

## Out Of Scope

- Redesigning Chatlas commands or Chatlas user-facing semantics.
- Moving Chatlas itself under `agentos.agent`.
- Introducing a durable `AgentProfile` class or runtime profile object.
- Fully normalizing provider `SessionRef` methods in the same pass, unless it is necessary to complete the package move.
- Removing provider-specific Codex mux behavior entirely.
- Changing account storage/auth management design beyond what is necessary for `--account` on `agentos agent run`.

## Acceptance Signals

The implementation is acceptable when:

- `agentos agent run --help` shows `--profile` and no longer shows `--instance`.
- `agentos agent run --provider <provider> --profile <id> --dry-run ...` resolves through `AgentConfig -> <Provider>.Agent`.
- `agentos agent run --provider <provider> --profile <id> --home <path> --dry-run ...` uses the CLI home override in the final agent config.
- `agentos agent run --provider codex --profile <id> --account <account> --dry-run ...` uses existing Codex account/mux behavior where supported, or returns a clear provider capability error if not supported yet.
- `agentos agent list` still works.
- `agentos agent accounts stats --help` still works.
- `agentos chatlas --help` still works.
- Existing Chatlas update/query/export tests still pass.
- No production imports remain from `agentos.chat`.
- The `src/agentos/chat/` package is removed, or only remains if a documented blocker is found and accepted.
- Full test suite passes:

```sh
uv run python -m compileall -q src/agentos tests
uv run python -m pytest -q
```

Additional useful checks:

```sh
rg -n "agentos\\.chat|from agentos\\.chat|import agentos\\.chat" src/agentos tests
rg -n "--instance" src/agentos tests
```

## Implementation Shape

### Slice 1. CLI Terminology And Run Resolution

Goal: make the command surface match the model before moving packages.

Work:

- Change `agentos agent run --instance` to `--profile`.
- Add `--home` and `--account` options to `agentos agent run`.
- Resolve the selected profile from configured agent config.
- Overlay CLI overrides into a final `AgentConfig`.
- Build the concrete provider agent with `agent_from_config()`.
- Keep `--model`, `--cwd`, `--dry-run`, and prompt behavior working.

Validation:

- Tests for `--profile` replacing `--instance`.
- Tests for profile plus `--home` override.
- Tests for missing/ambiguous profile errors.
- Tests for provider/account support behavior.

### Slice 2. Move Config Parsing

Goal: make config parsing live under `agentos.agent`.

Work:

- Move `chat/providers.py` to `agent/config.py`.
- Update imports from `agentos.chat.providers` to `agentos.agent.config`.
- Keep `AgentConfig` itself in `agentos.agent.primitives`.
- Keep provider capability specs available to Chatlas and sessions through the new module.

Validation:

- `agentos agent list --help`
- `agentos agent run --help`
- focused tests for agent commands and config parsing.

### Slice 3. Move Session Primitives And Live Session Coordination

Goal: make live provider session mechanics agent-owned.

Work:

- Move `chat/session_primitives.py` to `agent/session_refs.py`.
- Move `chat/core.py` to `agent/sessions.py`.
- Update imports in Chatlas, tests, and extractors.
- Preserve existing behavior for:
  - session listing
  - session resolving
  - session stats
  - URI parsing
  - provider/session fingerprints

Validation:

- Existing session-related tests.
- Chatlas tests, because Chatlas consumes the same session ref helpers.

### Slice 4. Move Accounts

Goal: make account/status mechanics agent-owned.

Work:

- Move `chat/accounts.py` to `agent/accounts.py`.
- Split account CLI/rendering from `chat/commands.py` into `agent/account_commands.py` or equivalent.
- Update `agent/commands.py` to import account command handlers from `agentos.agent.*`.
- Preserve `agentos agent accounts stats` behavior.

Validation:

- Account stats tests.
- `agentos agent accounts stats --help`.

### Slice 5. Move Extractors

Goal: remove remaining provider raw extraction code from `agentos.chat`.

Work:

- Move `chat/extractors/` to `agent/extractors/`.
- Update imports in session stats and Chatlas session model normalizers.
- Keep extractor behavior unchanged.

Validation:

- Chatlas export tests.
- Session stats tests.

### Slice 6. Delete `agentos.chat`

Goal: remove the old package.

Work:

- Delete `src/agentos/chat`.
- Remove stale `__all__` surfaces.
- Run search for stale imports.
- Update tests and any docs/notes that reference code paths if necessary.

Validation:

- `rg` checks listed above.
- Full compile and full pytest.

## Relevant Files Or Surfaces

Primary code surfaces:

- `src/agentos/agent/primitives.py`
- `src/agentos/agent/providers.py`
- `src/agentos/agent/commands.py`
- `src/agentos/chat/providers.py`
- `src/agentos/chat/core.py`
- `src/agentos/chat/session_primitives.py`
- `src/agentos/chat/accounts.py`
- `src/agentos/chat/commands.py`
- `src/agentos/chat/extractors/`
- `src/agentos/chatlas/`
- `src/agentos/codex/commands.py`
- `src/agentos/codex/agent.py`

Provider model surfaces:

- `src/agentos/codex/agent.py`
- `src/agentos/codex/session.py`
- `src/agentos/claude/agent.py`
- `src/agentos/claude/session.py`
- `src/agentos/copilot/agent.py`
- `src/agentos/copilot/session.py`
- `src/agentos/gemini/agent.py`
- `src/agentos/gemini/session.py`
- `src/agentos/openclaw/agent.py`
- `src/agentos/openclaw/session.py`
- `src/agentos/opencode/agent.py`
- `src/agentos/opencode/session.py`
- `src/agentos/pi/agent.py`
- `src/agentos/pi/session.py`

CLI surfaces:

- `agentos agent list`
- `agentos agent run`
- `agentos agent accounts stats`
- `agentos chatlas ...`
- `agentos codex ...`

Test surfaces:

- `tests/test_agent_commands.py`
- `tests/test_chat_accounts_commands.py`
- `tests/test_chatlas_commands.py`
- any tests importing `agentos.chat.*`

Related design/request artifacts:

- `notes/live/560-agentos-agent-session-model-design-summary.md`
- `notes/live/561-provider-native-agent-session-model-rewrite-impl-req.md`
- `notes/live/562-provider-session-ref-model-cleanup-impl-req.md`

## Open Questions

- Should config file terminology change from `agent.instances[]` to `agent.profiles[]` in the same implementation, or should the first pass only change CLI terminology?
- If config terminology changes, should it be a hard rename with no compatibility, or a staged migration with explicit temporary acceptance of both fields?
- What should `--account` do for providers without account switching support?
  - Recommended initial behavior: accept the axis at CLI parse level, then return a clear provider capability error when unsupported.
- Should the existing top-level `agentos codex` mux remain indefinitely as a convenience, or become a compatibility surface after `agentos agent run --provider codex --account ...` is strong enough?
- Should live session commands be exposed as `agentos agent session ...` in this pass, or only move internal modules first?

## Related Impl-Reqs

- `561-provider-native-agent-session-model-rewrite-impl-req.md` - predecessor for provider-native agent/session model direction.
- `562-provider-session-ref-model-cleanup-impl-req.md` - predecessor for provider session ref cleanup.

## End Log

- 2026-05-10: Created from user-approved refactor plan. Captures the `--profile` CLI terminology decision, the merged CLI/profile-to-`AgentConfig` model, and the package reorganization request to remove `agentos/chat` by moving agent mechanics under `agentos/agent`.
- 2026-05-10: Implemented. Moved config, sessions, session refs, accounts, account commands, CLI common helpers, and extractors from `src/agentos/chat/` to `src/agentos/agent/`; removed `src/agentos/chat/`; updated Chatlas and provider imports; changed `agentos agent run` from `--instance` to `--profile`; added `--home` and `--account` run axes; kept Chatlas commands stable. Verified with compileall, full pytest, stale import/`--instance` searches, and installed CLI smoke checks.
