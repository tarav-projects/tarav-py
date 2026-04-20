---
title: Agent Instance Registry Migration Plan
date: 2026-04-20
status: active
---

# Agent Instance Registry Migration Plan

## Overview

Restructure the live-instance and chat-history surfaces around one canonical
registry at `agent.instances`, move account usage under `agent accounts stats`,
and remove `agentos chat` entirely.

This migration is intentionally breaking. Per repository policy, do not add CLI
aliases, compatibility command paths, or long-lived config fallbacks unless
explicitly requested.

## Goal

Make the product surface and config model line up with actual semantics:

- `agent` is the live runtime surface for runnable machine-local instances
- `agent.instances` is the SSOT for configured live instances
- `agent accounts stats` is the live account/usage inspection surface
- `chatlas` is the archived/queryable chat-history surface
- `chat` is removed instead of remaining a mixed live/runtime/history namespace

## Progress

- Done in worktree: Phase 1 (`agent.instances` canonical registry)
- Done in worktree: Phase 2 (`agent list` / `agent run` on `agent.instances`)
- Done in worktree: Phase 3 (`agent accounts stats`, `agent.accounts`)
- Pending: Phase 4 (`chatlas.instance_ids`)
- Pending: Phase 5 (`chat` removal)
- Pending: Phase 6 (Codex mux alignment)

## Target CLI Surface

Keep:

- `agentos agent list`
- `agentos agent run`
- `agentos agent accounts stats`
- `agentos chatlas update`
- `agentos chatlas stats`
- `agentos chatlas query`
- `agentos chatlas export`
- `agentos codex ...`

Remove:

- `agentos chat debug list`
- `agentos chat debug find`
- `agentos chat debug extract`
- `agentos chat accounts stats`
- the top-level `agentos chat` command registration

## Target Config Model

```json
{
  "agent": {
    "instances": [
      {
        "id": "codex-main",
        "provider": "codex",
        "label": "Codex main",
        "home": "~/.codex",
        "cli_command": ["/opt/homebrew/bin/codex"],
        "run_args": ["--dangerously-bypass-approvals-and-sandbox"]
      },
      {
        "id": "codex-work",
        "provider": "codex",
        "label": "Codex work",
        "home": "~/.codex-work",
        "cli_command": ["/opt/homebrew/bin/codex"],
        "run_args": ["--dangerously-bypass-approvals-and-sandbox"]
      }
    ],
    "accounts": {
      "instance_ids": ["codex-main"],
      "usage_total": {
        "label": "Selected accounts aggregate",
        "limit_class": "usage_over_time",
        "limit_name": "weekly",
        "instance_ids": ["codex-main"]
      }
    }
  },
  "chatlas": {
    "instance_ids": ["codex-main", "codex-work"]
  },
  "codex": {
    "mux": {
      "default_instance_id": "codex-main",
      "accounts_root": "~/.agentos/accounts/codex"
    }
  }
}
```

## Config Semantics

### `agent.instances`

Canonical machine-local runnable instance registry.

Each entry must contain enough data to run independently via `agent run`.

Allowed shape should stay close to current `ProviderInstance` input fields:

- `id`
- `provider`
- `label`
- `home` or `homes`
- `direct_paths`
- `grep_paths`
- `sqlite_db_path` / `sqlite_db_paths`
- `cli_command`
- `run_args`
- `env`
- `timeout_sec`
- `default_model`
- `model_flag`
- `prompt_flag`
- `live_usage_refresh`
- `usage_progression_limit`
- `includes`
- `excludes`

### `agent.accounts`

Surface selection plus account-specific aggregate config.

- `instance_ids` selects which `agent.instances` are used for account/usage
  checks
- `usage_total` replaces the current flat `chat.accounts_usage_total`

### `chatlas`

Use selectors instead of redefining instances:

- `instance_ids` selects which `agent.instances` are mirrored/tracked
- `chatlas.provider_instances` is removed

Chatlas-specific include/exclude/destination policy should be derived from the
selected instance definitions and provider-family defaults, not from a second
full instance registry.

## Core Design Rules

- `ProviderInstance` stays the canonical in-memory semantic object.
- The canonical config source moves from `chat.provider_instances` to
  `agent.instances`.
- Surfaces do not implicitly consume all configured instances unless that is
  their explicit design.
- `agent.accounts.instance_ids` and `chatlas.instance_ids` are selectors over
  `agent.instances`.
- No command alias is kept for removed `chat` surfaces.
- No config namespace alias is kept for old `chat.*` instance config once the
  migration lands.

## Migration Phases

## Phase 1. Introduce `agent.instances` As The Canonical Registry

### Purpose

Move the base instance registry out of `chat.*` so the live-instance model is no
longer anchored to a chat-specific namespace.

### Code Changes

- Add a new config source in `src/agentos/chat/providers.py`:
  - object path: `("agent", "instances")`
  - field prefix: `agent.instances`
- Replace the current `CHAT_PROVIDER_INSTANCE_CONFIG_SOURCE` usage with the new
  canonical source name and helper.
- Rename or replace `load_configured_provider_instances()` so it reads from
  `agent.instances`.
- Keep the canonical `ProviderInstance` type unchanged if possible.

### Notes

- This phase is structural only. It should not yet remove any command surfaces.
- Do not add a compatibility reader for `chat.provider_instances`.
- Update tests and fixture writers to emit `agent.instances` immediately.

### Expected Files

- `src/agentos/chat/providers.py`
- any tests that currently write `chat.provider_instances`

## Phase 2. Move `agent list/run` To The New Registry

### Purpose

Make the live runtime surface consume the new canonical registry directly.

### Code Changes

- Update `src/agentos/agent/commands.py` to read instance config from the new
  canonical loader.
- Keep CLI shape stable:
  - `agentos agent list`
  - `agentos agent run`
- Keep runtime behavior stable:
  - provider filtering
  - `--instance`
  - `--model`
  - `--project`
  - `--cwd`
  - `--dry-run`

### Test Changes

- Rewrite `tests/test_agent_commands.py` config fixtures from `chat` to `agent`
- Preserve current behavior expectations after the config move

### Expected Files

- `src/agentos/agent/commands.py`
- `tests/test_agent_commands.py`

## Phase 3. Move Account Usage To `agent accounts stats`

### Purpose

Promote account/usage inspection into the `agent` namespace and decouple it from
all-instance implicit consumption.

### Code Changes

- Move the account-stats command registration out of `src/agentos/chat/commands.py`
  into `src/agentos/agent/commands.py`
- Add nested subcommands:
  - `agent accounts stats`
- Reuse the existing rendering and collection logic from
  `src/agentos/chat/accounts.py` rather than rewriting provider adapters
- Update `configured_account_provider_instances()` to:
  - source base instances from `agent.instances`
  - filter them by `agent.accounts.instance_ids`
  - validate that every referenced id exists
  - validate that selected providers are supported by account handlers

### Config Changes

- Move `chat.accounts_usage_total` to `agent.accounts.usage_total`
- Add `agent.accounts.instance_ids`

### Validation Rules

- `agent.accounts.instance_ids` must be a non-empty JSON array when present
- entries must be unique
- every id must exist in `agent.instances`
- `agent.accounts.usage_total.instance_ids` must be a subset of
  `agent.accounts.instance_ids`

### Test Changes

- Move or replace `tests/test_chat_accounts_commands.py`
- New target test module should cover:
  - `agent accounts stats`
  - config validation under `agent.accounts`
  - usage total subset validation
  - provider-specific collection behavior

### Expected Files

- `src/agentos/agent/commands.py`
- `src/agentos/chat/accounts.py`
- `tests/test_chat_accounts_commands.py`
- possibly rename to `tests/test_agent_accounts_commands.py`

## Phase 4. Make Chatlas Select From `agent.instances`

### Purpose

Stop Chatlas from maintaining a second instance registry and make it explicitly
select from the canonical live-instance registry.

### Code Changes

- Update `src/agentos/chatlas/core.py` so `configured_chatlas_settings()`:
  - loads from `agent.instances`
  - applies `chatlas.instance_ids` as a selector
  - stops reading `chatlas.provider_instances`
- Remove `_CHATLAS_PROVIDER_INSTANCE_CONFIG_SOURCE`
- Remove config-entry-to-instance expansion for Chatlas-specific instance defs
- Keep provider-family filtering and raw archive behavior intact after selection

### Validation Rules

- `chatlas.instance_ids` must reference existing `agent.instances`
- ids must be unique
- selected providers must be supported by Chatlas

### Notes

- This phase intentionally removes the current inheritance model where Chatlas
  starts with shared instances and then extends them.
- Chatlas should now have one input: selected canonical instances.

### Test Changes

- Rewrite `tests/test_chatlas_commands.py` fixture config from:
  - shared `chat.provider_instances`
  - optional `chatlas.provider_instances`
  to:
  - `agent.instances`
  - `chatlas.instance_ids`
- Preserve behavior around:
  - multiple Codex homes
  - archive destination naming
  - include/exclude filtering
  - normalized/query/export behavior

### Expected Files

- `src/agentos/chatlas/core.py`
- `src/agentos/chatlas/raw.py`
- `tests/test_chatlas_commands.py`

## Phase 5. Remove `agentos chat` In One Cut

### Purpose

Delete the mixed live-provider namespace once both replacement surfaces are in
place.

### Code Changes

- Remove `register_chat_commands()` import/registration from `src/agentos/cli.py`
- Delete or retire `src/agentos/chat/commands.py`
- Remove `chat` exports from `src/agentos/chat/__init__.py`
- Delete the live debug surfaces:
  - list
  - find
  - extract
- Delete the old `chat accounts stats` command path

### Secondary Cleanup

- Remove chat-surface docs/help text across the repo
- Remove tests for `chat debug` and old `chat accounts`
- Update any project/live notes that describe `chat` as an active public surface

### Expected Files

- `src/agentos/cli.py`
- `src/agentos/chat/commands.py`
- `src/agentos/chat/__init__.py`
- `tests/test_chat_commands.py`
- `tests/test_chat_extract_commands.py`
- old chat account CLI tests

## Phase 6. Align Codex Mux With `agent.instances`

### Purpose

Reuse the canonical instance registry for Codex launcher defaults.

### Code Changes

- Teach `src/agentos/codex/commands.py` to resolve
  `codex.mux.default_instance_id` through `agent.instances`
- If `default_instance_id` is present:
  - use that instance's `home`
  - use that instance's `cli_command`
  - use that instance's `run_args`
- Keep explicit `--home` and explicit Codex mux config overrides authoritative
  when passed

### Notes

- This phase is logically downstream from the registry migration.
- It can ship in the same branch after Phase 1 if helpful, but it should not
  block the core `agent`/`chatlas` migration.

### Expected Files

- `src/agentos/codex/commands.py`
- `tests/test_codex_commands.py`

## Deletion Policy

Delete old surfaces and config paths instead of shadowing them:

- delete `chat.provider_instances`
- delete `chat.accounts_usage_total`
- delete `chatlas.provider_instances`
- delete `agentos chat`

Do not add:

- `agentos chat` aliases to `agent accounts`
- dual-reading config helpers that quietly support both old and new namespaces
- silent migration behavior inside runtime commands

If migration assistance is needed, do it with:

- explicit repo config edits
- explicit test fixture rewrites
- explicit doc updates

## Implementation Order

Recommended branch order:

1. Phase 1: canonical config source rename to `agent.instances`
2. Phase 2: keep `agent list/run` green on the new registry
3. Phase 3: move `accounts stats` under `agent`
4. Phase 4: make Chatlas select from `agent.instances`
5. Phase 5: delete `chat`
6. Phase 6: align Codex mux defaults with `agent.instances`

This order minimizes time spent with broken or doubled public surfaces.

## Test Plan

Minimum command/test checkpoints by phase:

- Phase 1:
  - `uv run pytest tests/test_agent_commands.py`
  - relevant provider/config loader tests
- Phase 2:
  - `uv run pytest tests/test_agent_commands.py`
- Phase 3:
  - `uv run pytest tests/test_agent_commands.py`
  - `uv run pytest tests/test_chat_accounts_commands.py`
  - or renamed replacement module
- Phase 4:
  - `uv run pytest tests/test_chatlas_commands.py`
- Phase 5:
  - full suite covering CLI registration changes:
  - `uv run pytest`
- Phase 6:
  - `uv run pytest tests/test_codex_commands.py`

At the end:

- reinstall the editable CLI:
  - `uv tool install --reinstall --editable .`
- sanity-check public help:
  - `agentos`
  - `agentos agent --help`
  - `agentos agent accounts --help`
  - `agentos chatlas --help`
  - ensure `agentos chat` no longer exists

## Acceptance Signals

- `agent.instances` is the only configured live-instance registry
- `agent list` and `agent run` operate from `agent.instances`
- `agent accounts stats` exists and `chat accounts stats` does not
- `agent.accounts.instance_ids` controls usage/account selection
- `agent.accounts.usage_total` replaces `chat.accounts_usage_total`
- `chatlas.instance_ids` controls which instances are mirrored
- `chatlas.provider_instances` no longer exists
- `agentos chat` is gone from help and parser registration
- tests and docs reflect the new surface and config model

## Risks

- Chatlas currently uses instance materialization paths that assume it can define
  extra archive-only instances. Removing that path may expose hidden reliance on
  Chatlas-specific instance config.
- Some tests likely encode `chat` naming deeply and will need broad rewrites,
  not just fixture changes.
- Removing `chat debug` means losing live provider introspection helpers; be
  sure no remaining code path or docs assume that surface still exists.

## Deferred Items

- introducing a first-class `account` object distinct from `ProviderInstance`
- any compatibility migration command for rewriting old config files
- rethinking provider-family naming such as `provider` vs `family`
- broader product redesign beyond the namespace and registry migration
