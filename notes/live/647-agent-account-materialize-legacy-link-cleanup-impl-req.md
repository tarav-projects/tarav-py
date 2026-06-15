# Agent Account Materialize Legacy Link Cleanup - impl-req

## Impl.Abstract

- **scope:** remove active legacy "link" account-auth code and terminology from `agentos-py` after the account command surface moved to `materialize`; keep historical notes untouched unless they are active docs
- **status:** proposed
- **source:** 2026-06-15 `$hugentics-codebase-cleaner` request with `NO.LEGACY.CODE` after implementing `account_policy: "home-current"`
- **owning project:** `agentos-py`
- **primary paths:** `src/agentos/codex/account_registry.py`, `src/agentos/codex/account_reconcile.py`, `src/agentos/codex/agent.py`, `src/agentos/claude/account_registry.py`, `src/agentos/claude/account_reconcile.py`, `src/agentos/copilot/account_registry.py`, `src/agentos/codex/linking.py`, `src/agentos/agent/link_runtime.py`, `tests/`, `README.md`
- **related surfaces:** `notes/live/645-agent-account-auth-interface-redesign-impl-req.md`, `notes/live/646-agent-profile-home-current-account-policy-impl-req.md`

## Impl.Index

### Cleanup.Scope

Active code should speak the current account-auth language: inspect/register/reconcile/materialize/prepare-run.

Hard.Evidence:

- `agentos agent accounts link` was removed from the active command surface in 645.
- Active event payloads now use `account.auth.materialized` and `agent accounts materialize`.
- `src/agentos/codex/account_registry.py` still exposes `link_codex_account_to_home(...)` and `_record_link_failure(...)`.
- `src/agentos/claude/account_registry.py` still exposes `link_claude_account_to_home(...)`.
- `src/agentos/copilot/account_registry.py` still exposes `link_copilot_account_to_home(...)`.
- `src/agentos/codex/linking.py` and `src/agentos/agent/link_runtime.py` are unused by active code according to `rg` and preserve an old link/symlink abstraction.
- `README.md` still documents `agentos agent accounts link`.

Implementation direction:

- Rename active provider helper functions from `link_*_account_to_home` to `materialize_*_account_to_home`.
- Rename internal failure helpers from link terminology to materialize terminology.
- Update active call sites and tests.
- Delete unused legacy link runtime modules.
- Update active docs to use `agent accounts materialize`.
- Do not edit historical live notes except this Impl.Req and its log.

### No.Legacy.Allowed

No compatibility aliases should remain for the replaced link terminology.

Rules:

- Do not keep `link_*_account_to_home` wrappers.
- Do not keep `AgentLinkRequest`, `AgentLinkResult`, or `AgentLinkDryResult` if no active command imports them.
- Do not preserve `codex.linking` as a hidden compatibility surface.
- Do not update historical notes just to erase past design language; they are audit artifacts, not active code.
- Search acceptance should allow only unrelated `skills-routing-links.json`, markdown link concepts, historical notes, or non-account symlink/link wording.

### Integration.Shape

This cleanup must stay mechanical and local.

Implementation direction:

- Provider registries remain the owner of materialization mechanics.
- Reconcile and run-preparation continue to call provider registry materialization helpers.
- Tests should assert behavior, not old names.
- README should present the current CLI surface.

## Execution.Plan

### Slice 1 - Rename Active Provider Materialization Helpers

- Rename:
  - `link_codex_account_to_home` -> `materialize_codex_account_to_home`
  - `link_claude_account_to_home` -> `materialize_claude_account_to_home`
  - `link_copilot_account_to_home` -> `materialize_copilot_account_to_home`
- Update imports, call sites, tests, and `__all__`.
- Rename `_record_link_failure` to `_record_materialize_failure`.
- Do not add compatibility wrappers.

Observable result:

- Active account registry/reconcile/run code no longer imports or calls `link_*_account_to_home`.

RED.GREEN.Test.Suite:

```bash
uv run pytest tests/test_agent_run_account_preflight.py tests/test_codex_account_reconcile.py tests/test_claude_account_registry.py tests/test_claude_account_reconcile.py tests/test_agent_profiles.py -q
```

### Slice 2 - Remove Dead Link Runtime Modules

- Delete `src/agentos/agent/link_runtime.py`.
- Delete `src/agentos/codex/linking.py`.
- Verify no imports remain.

Observable result:

```bash
rg -n "agent\\.link_runtime|codex\\.linking|AgentLink|link_codex_account\\(|link_codex_account_dry|link_codex_auth_for_account" src/agentos tests
```

returns no active-code matches.

Validation:

```bash
uv run ruff check src/agentos/agent src/agentos/codex src/agentos/claude src/agentos/copilot tests
```

### Slice 3 - Active Docs And Final Search

- Update `README.md` account command example from `accounts link` to `accounts materialize`.
- Run focused search for active account-link remnants.

Search:

```bash
rg -n "agent\\.accounts\\.link|agent accounts link|link_codex_account_to_home|link_claude_account_to_home|link_copilot_account_to_home|_record_link_failure|AgentLink|codex\\.linking|agent\\.link_runtime" src/agentos tests README.md
```

Expected result: no matches.

Final validation:

```bash
uv run pytest -q
uv run ruff check src/agentos tests
```

## Risks And Deviation Triggers

- If an external package imports these link helpers, do not add wrappers by default; record it as a breaking cleanup consistent with `NO.LEGACY.CODE`.
- If `codex.linking` is discovered to back an active CLI command, stop and narrow the cleanup to provider account-registry naming only.
- If search results are historical notes only, leave them unchanged.

## Acceptance.Signals

- No active code/test/README references remain for `agent accounts link`.
- No active provider account registry helper uses `link_*_account_to_home` naming.
- Dead `agent.link_runtime` and `codex.linking` modules are removed.
- Focused and full tests pass.
- Ruff passes.

## Impl.Log

- 2026-06-15: Created from codebase-cleaner scan. Scope is deliberately narrow: remove active legacy link naming and dead link runtime modules without broad account-auth redesign.
