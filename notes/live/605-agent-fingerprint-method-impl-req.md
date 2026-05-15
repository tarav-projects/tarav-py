# Agent Fingerprint Method - impl-req

## Impl.Abstract

- **scope:** move provider-agent identity helpers from free functions to agent instance methods, so callers use `agent.fingerprint()`, `agent.identity_key()`, and `agent.uri_key()`
- **status:** implemented
- **source:** user request on 2026-05-15 after review of `agent_fingerprint(agent)`
- **target project:** `agentos-py`
- **current worktree note:** the worktree already has unrelated edits in `src/agentos/agent/primitives.py`, `src/agentos/codex/agent.py`, and `src/agentos/claude/agent.py` for `account_status(record_usage=...)`; preserve those changes and adapt around them

## Impl.Index

### Agent.Identity.Method.Shape

- the accepted interface target is `agent.fingerprint()`, because the fingerprint is a property of the configured provider agent instance
- `agent_identity_key(agent)` and `agent_uri_key(agent)` are the same category of agent identity behavior and should move with the fingerprint helper
- all concrete provider agents inherit from `AgentBase`, so the behavior belongs in `AgentBase` rather than duplicated per provider class
- the `Agent` protocol must expose the new methods so typed call sites can use them without importing helper functions

### Fingerprint.Field.Name.Conflict

- `AgentBase` and `AgentConfig` currently have a field named `fingerprint: str | None`
- Python cannot support both an instance attribute named `fingerprint` and a method named `fingerprint()` on the same dataclass instance
- rename the internal override field to a non-conflicting name, preferably `fingerprint_override`
- preserve the external config and summary key named `"fingerprint"` unless a separate design decision changes the public schema

### Current.Helper.Surface

- `AgentConfig.computed_fingerprint()` already contains the same conceptual logic as `agent_fingerprint(agent)`
- `AgentConfig.identity_key()` and `AgentConfig.uri_key()` already model the desired method shape for config records
- current free-function call sites are small:
  - `src/agentos/agent/sessions.py` imports and calls `agent_fingerprint`, `agent_identity_key`, and `agent_uri_key`
  - `src/agentos/chatlas/delta_scan.py` imports and calls `agent_fingerprint`
- direct helper tests were not found by `rg` during design; validation should cover session and chatlas behavior instead of only unit-level helper replacement

### No.Legacy.Helper.Layer

- the project compatibility policy says not to add backward-compatibility aliases unless explicitly requested
- after call sites move to methods, remove `agent_fingerprint`, `agent_identity_key`, and `agent_uri_key` from `__all__`
- keep `agent_identity_fingerprint(...)` as the low-level digest primitive unless implementation discovers a cleaner home; it is not the user-facing problem

## Execution.Plan

### Slice 1 - Add agent identity methods without changing behavior

- add `fingerprint()`, `identity_key()`, and `uri_key()` methods to `AgentBase`
- add the same method declarations to the `Agent` protocol
- have these methods preserve the current digest and key behavior exactly
- path: configured `AgentConfig` -> provider agent via `agent_from_config()` -> identity methods
- observable: a provider agent can answer `agent.fingerprint()`, `agent.identity_key()`, and `agent.uri_key()`
- check: focused tests or existing tests that construct configured agents and assert stable identity values
- status: done

### Slice 2 - Resolve the field/method name conflict

- rename the dataclass field currently named `fingerprint` to `fingerprint_override` or another clear non-conflicting name
- update `agent_base_kwargs_from_config()`, `AgentBase.summary()`, `AgentConfig.computed_fingerprint()`, config loading, and any tests that construct `AgentConfig`
- preserve input/output schema key `"fingerprint"` for config documents and summaries
- path: config document field `"fingerprint"` -> `AgentConfig` -> concrete provider agent -> `agent.fingerprint()`
- observable: configured explicit fingerprints still override computed fingerprints
- check: test that a config-level `"fingerprint"` value appears in summary and is returned by `agent.fingerprint()`
- status: done

### Slice 3 - Replace runtime helper call sites

- replace `_dedupe_agents()` in `src/agentos/agent/sessions.py` with `agent.identity_key()`
- replace provider context construction in `src/agentos/agent/sessions.py` with `agent.fingerprint()`, `agent.identity_key()`, and `agent.uri_key()`
- replace chatlas instance selection in `src/agentos/chatlas/delta_scan.py` with `agent.fingerprint()`
- remove now-unused imports
- path: session listing and chatlas update instance selection
- observable: generated provider instance fingerprints and URIs remain byte-for-byte stable for the same config
- check: session/chatlas tests that assert `provider_instance_fingerprint`, `uri`, or raw/index partition paths
- status: done

### Slice 4 - Remove obsolete free-function surface

- remove `agent_fingerprint`, `agent_identity_key`, and `agent_uri_key` from `src/agentos/agent/primitives.py`
- update `__all__`
- run `rg` to prove no imports or call sites remain
- keep `agent_identity_fingerprint(...)` if still used by `AgentConfig` and `AgentBase`
- path: public primitive exports -> codebase imports
- observable: no code imports or calls the removed helpers
- check: `rg "agent_fingerprint|agent_identity_key|agent_uri_key" src tests`
- status: done

### Slice 5 - Validation and CLI smoke checks

- run focused tests for agent sessions and chatlas surfaces
- run lint on touched files
- run `uv tool install --reinstall --editable .` if CLI source changed and the installed `agentos` executable should stay in sync
- suggested checks:
  - `uv run ruff check src/agentos/agent src/agentos/chatlas tests`
  - `uv run pytest tests/test_agent_commands.py tests/test_chatlas_commands.py tests/test_chatlas_views.py -q`
  - targeted tests around any changed config-loading behavior
- status: done

## Impl.Log

- 2026-05-15: Impl designer created this request after the user approved the direction to move `agent_fingerprint(agent)` into the provider agent instance interface as `agent.fingerprint()`.
- 2026-05-15: Codebase scan found current free-function call sites in `src/agentos/agent/sessions.py` and `src/agentos/chatlas/delta_scan.py`; also found existing dirty worktree edits for `account_status(record_usage=...)` that implementers must preserve.
- 2026-05-15: Implemented the identity-method refactor. Added `fingerprint()`, `identity_key()`, and `uri_key()` to `AgentBase` and the `Agent` protocol; renamed the stored override field to `fingerprint_override`; preserved the external config/summary key `"fingerprint"`; updated session and Chatlas call sites; removed obsolete helper functions and exports.
- 2026-05-15: Validation passed with `uv run pytest tests/test_agent_commands.py tests/test_chatlas_commands.py tests/test_chatlas_views.py -q`, `uv run pytest tests/test_agent_commands.py -q`, `uv run ruff check src/agentos/agent src/agentos/chatlas tests/test_agent_commands.py tests/test_chatlas_commands.py tests/test_chatlas_views.py`, and `rg "agent_fingerprint|agent_identity_key|agent_uri_key" src tests -S` returning no matches.
