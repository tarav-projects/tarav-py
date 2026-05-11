# Agent Link Command Surface - impl-req

## Impl-Req State

Implemented: Codex account linking now lives under `agentos agent link` without profiles, and the legacy top-level `agentos codex` command is no longer registered.

## User Intent

Add the `agentos codex --just-link` functionality into the normalized `agentos agent` surface.

The target command surface is intentionally simple:

```sh
agentos agent link \
  --provider codex \
  --home /Users/pereiro/.codex \
  --account tk
```

Dry-run should be:

```sh
agentos agent link \
  --provider codex \
  --home /Users/pereiro/.codex \
  --account tk \
  --dry-run
```

Do not include `--profile` for this command. Linking is an account/home mutation, not selection of a configured runnable agent profile.

The end state should remove the legacy top-level `agentos codex` command implementation. Do not leave two maintained command surfaces for the same behavior.

## Why This Exists

`agentos codex` is now a legacy mux surface relative to the provider-native `agentos agent` model, and should be removed after its useful account-linking behavior has a normalized replacement.

Current legacy command:

```sh
agentos codex --account tk --home /Users/pereiro/.codex --just-link
```

It exists outside the normalized agent command group and keeps Codex-specific behavior in a top-level provider command. The new model should surface agent-related operations through `agentos agent`, with provider-specific behavior owned by provider modules/capabilities rather than by generic command code.

## Current Situation

`agentos codex` is registered as a top-level command in `src/agentos/cli.py`.

Its implementation in `src/agentos/codex/commands.py` owns:

- `codex.mux` config parsing.
- default Codex executable/home/base args.
- `CODEX_HOME` env handling.
- managed account auth path resolution.
- Codex auth symlink mutation.
- raw Codex arg passthrough.
- `--just-link`.
- dry-run printing.
- subprocess execution.

`agentos agent run --provider codex ...` now uses provider-native `CodexAgent.run(...)` and `CodexAgent.run_dry(...)`, but Codex account linking still reuses private helpers from `agentos.codex.commands`.

This means the implementation direction is partly migrated:

- Good: `agentos agent run` is the normalized run surface.
- Bad: standalone account-home linking still only exists as `agentos codex --just-link`.
- Bad: reusable Codex link/account primitives are trapped inside a legacy command module.

## Requested Change

Add a new normalized command:

```txt
agentos agent link
  --provider <provider>
  --home <provider-home>
  --account <account>
  --dry-run
```

Initial supported provider:

```txt
codex
```

For Codex, this command should perform the same observable mutation as:

```sh
agentos codex --account <account> --home <home> --just-link
```

Dry-run should perform the same observable preview as:

```sh
agentos codex --account <account> --home <home> --just-link --dry-run
```

The generic command layer should only:

- parse CLI args
- select the provider capability
- pass `provider`, `home`, `account`, and `dry_run`
- print provider dry-run lines
- return success/failure

Provider-specific path layout and symlink behavior must stay provider-owned.

## Target Runtime Shape

Use a small provider-owned link capability surface.

Suggested shared request/result objects:

```py
AgentLinkRequest
  provider: str
  home: Path
  account: str

AgentLinkResult
  exit_code: int = 0

AgentLinkDryResult
  lines: tuple[str, ...]
```

Exact names are flexible. The important boundary is:

- `agentos.agent.commands` does not know Codex auth file layout.
- `agentos.agent.commands` does not call private `agentos.codex.commands` helpers directly.
- Codex owns how account auth source and provider-home auth destination are resolved.

Possible provider API:

```py
CodexAgent.link(request) -> AgentLinkResult
CodexAgent.link_dry(request) -> AgentLinkDryResult
```

However, because `agent link` deliberately has no `--profile`, it may be cleaner to use provider-module capability functions instead of requiring a configured `CodexAgent` instance:

```py
link_codex_account(request) -> AgentLinkResult
link_codex_account_dry(request) -> AgentLinkDryResult
```

Either shape is acceptable if the provider ownership boundary is preserved.

## Command Semantics

### Required Flags

`--provider` is required.

`--home` is required for the first implementation. Do not default to `~/.codex` yet; implicit mutation of a provider home is too easy to misread.

`--account` is required.

### Dry Run

`--dry-run` prints the link action and does not mutate the filesystem.

For Codex, the expected dry-run output should remain compatible with current `agentos codex --just-link --dry-run` style:

```txt
link /Users/pereiro/.codex/auth.json -> /.../accounts/codex/tk/auth.json
```

### Unsupported Providers

If a provider does not support linking, return a clear provider capability error.

Example:

```txt
error: agent link is not supported for provider claude-code
```

Do not fake support with a generic fallback.

## Constraints And Invariants

- Keep the new surface simple: no `--profile`, no `--model`, no prompt, no raw provider args.
- Keep `--home` explicit in this pass.
- Keep current Codex symlink safety behavior:
  - missing managed auth file is an error
  - managed auth path must be a file
  - existing matching symlink is accepted
  - non-symlink destination auth file is refused
  - mutation uses the existing safe symlink replacement behavior
- Keep current managed account storage convention unless separately redesigned:
  - default source remains under `AGENTOS_HOME/accounts/codex/<account>/auth.json`
  - existing `codex.mux.accounts_root` may still be honored if it remains the only configured source root
- Do not redesign `agentos agent run`.
- Do not redesign `agentos agent accounts stats`.
- Do not redesign Chatlas or sessions.
- Do not add compatibility aliases.
- Remove the legacy top-level `agentos codex` implementation in this pass after the normalized replacement is implemented and verified.
- Do not keep `agentos codex` as an alias or compatibility wrapper unless the user explicitly reverses this decision. The project preference is clean replacement, not compatibility layers.

## Out Of Scope

- Raw Codex passthrough under `agentos agent`.
- `agentos agent exec`.
- `agentos agent unlink`.
- Account creation/import.
- Renaming config fields.
- Removing `codex.mux` entirely.
- Deprecation warnings for `agentos codex`; the command should be removed rather than warned.
- Preserving `agentos codex` as a compatibility alias.

## Acceptance Signals

- `agentos agent link --provider codex --home <home> --account <account>` creates or updates `<home>/auth.json` as a symlink to the managed Codex account auth file.
- `agentos agent link --provider codex --home <home> --account <account> --dry-run` prints the link action and does not mutate `<home>/auth.json`.
- The command rejects missing `--home`.
- The command rejects missing `--account`.
- The command rejects unsupported providers with a clear capability error.
- `agentos.agent.commands` does not import `_link_codex_auth_for_account` or other private Codex command helpers.
- Codex auth/link primitives are moved out of `agentos.codex.commands` into a provider-owned runtime/account module, or otherwise exposed through a provider-owned non-command surface.
- The top-level `agentos codex` command is no longer registered after the replacement surface is implemented.
- `src/agentos/codex/commands.py` is deleted, or reduced only to provider-owned non-CLI primitives if the file is renamed/re-scoped; there should not be a legacy top-level Codex command module.
- Tests no longer assert `agentos codex` behavior; useful coverage is moved to `agentos agent link` and provider-owned Codex primitive tests.
- Focused tests cover the new command and Codex behavior.

## Implementation Shape

Implement in vertical slices.

### Slice 1. Extract Codex Link Primitive

Move reusable Codex account-linking behavior out of `src/agentos/codex/commands.py`.

Suggested target module:

```txt
src/agentos/codex/linking.py
```

or, if the account/auth model is already being centralized:

```txt
src/agentos/codex/accounts.py
```

Observable check:

- Existing `tests/test_codex_commands.py` still pass.
- Static search shows `agentos.codex.commands` can call the extracted provider primitive, not own the primitive itself.

### Slice 2. Add `agentos agent link` Parser

Add the command under `register_agent_commands`:

```txt
agentos agent link --provider ... --home ... --account ... [--dry-run]
```

Keep parser choices consistent with existing provider family choices.

Observable check:

- `agentos agent link --help` shows only the intended flags.
- No `--profile` appears in link help.

### Slice 3. Implement Codex Provider Link Capability

Route `agentos agent link --provider codex ...` to the Codex-owned link behavior.

The command layer should stay thin:

- build request
- call provider capability
- print dry-run lines
- return exit code

Observable check:

- New test proves dry-run prints the expected `link destination -> source` line and does not create the symlink.
- New test proves normal run creates the symlink.

### Slice 4. Unsupported Provider Error

Add a narrow unsupported-provider test.

Observable check:

- `agentos agent link --provider pi --home <home> --account tk` returns error with a clear unsupported-provider message.

### Slice 5. Remove Legacy `agentos codex`

Remove the top-level `agentos codex` registration after `agentos agent link` covers account-home linking.

Work:

- Remove `register_codex_commands` from `src/agentos/cli.py`.
- Remove `src/agentos/codex/commands.py` as a command module, or rename/extract any remaining provider primitives into provider-owned non-command modules.
- Update `src/agentos/codex/__init__.py` so it no longer exports command registration.
- Move or replace `tests/test_codex_commands.py` coverage with `agentos agent link` tests and provider primitive tests.
- Search docs/notes/tests for active references to `agentos codex` and update current implementation surfaces. Archived notes do not need rewriting.

Observable check:

```sh
agentos codex --help
```

Expected result:

- argparse rejects `codex` as an invalid top-level command.
- no active tests depend on `agentos codex`.

### Slice 6. Cleanup Static Coupling

Remove direct use of private command helpers from provider agents where possible.

In particular, `CodexAgent.run(...)` should not need to import `_link_codex_auth_for_account` from `agentos.codex.commands` after the extraction.

Observable check:

```sh
rg "_link_codex_auth_for_account|_load_codex_mux_config" src/agentos
```

Expected result:

- no references from `src/agentos/agent/commands.py`
- no references from `src/agentos/codex/agent.py`
- no references to `src/agentos/codex/commands.py`
- if still present, references should be confined to the new provider-owned module

### Slice 7. Final Verification

Run focused and import-level checks.

Suggested commands:

```sh
uv run ruff check src/agentos/agent src/agentos/codex tests/test_agent_commands.py
uv run pytest tests/test_agent_commands.py -q
uv run python -m compileall -q src/agentos/agent src/agentos/codex
rg "register_codex_commands|agentos codex|\\[\"codex\"" src tests README.md notes/live
```

The `rg` command may still find archived notes if included broadly; active code/tests should not reference the removed CLI.

## Relevant Files Or Surfaces

- `src/agentos/agent/commands.py`
- `src/agentos/agent/run_runtime.py`
- `src/agentos/codex/agent.py`
- `src/agentos/codex/commands.py`
- `src/agentos/codex/accounts.py`
- possible new `src/agentos/codex/linking.py`
- `src/agentos/cli.py`
- `tests/test_agent_commands.py`
- `tests/test_codex_commands.py` as a migration/deletion target
- `notes/live/572-provider-native-agent-run-capability-impl-req.md`

## Open Questions

- Should the shared link request/result types live in `agentos.agent.run_runtime`, a new `agentos.agent.link_runtime`, or provider-local code?
- Should `codex.mux.accounts_root` remain the source of managed auth paths, or should this move into a normalized account config surface later?
- Should `agentos agent link` eventually default `--home` from configured provider homes when unambiguous?
- Are there any non-test users of raw Codex passthrough that need a different normalized command later, such as `agentos agent exec`? This impl-req does not preserve raw passthrough.

## Related Impl-Reqs

- `572-provider-native-agent-run-capability-impl-req.md` - introduced provider-native `agent.run` / `agent.run_dry`.
- `570-provider-agent-account-capability-refactor-impl-req.md` - moved account stats behavior toward provider-agent capabilities.
- `565-agent-command-profile-and-chat-package-reorg-impl-req.md` - raised the question of whether top-level `agentos codex` should become compatibility surface after normalized agent run is strong enough.

## End Log

- 2026-05-10: Created after agreeing that the replacement for `agentos codex --just-link` should be `agentos agent link --provider codex --home <home> --account <account>`, without `--profile`.
- 2026-05-10: Updated to make removal of the legacy top-level `agentos codex` command an explicit implementation requirement, not a deferred compatibility question.
- 2026-05-10: Implemented. Added `agentos agent link`, moved Codex auth-linking/config primitives to `src/agentos/codex/linking.py`, added shared link request/result types, removed top-level `agentos codex` registration and legacy command module, migrated useful coverage to `tests/test_agent_commands.py`, and refreshed the installed CLI.
