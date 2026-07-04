# 683 — shared test fixtures, agent-commands split, monitor test split

## Impl.Abstract

- **Scope:** items 1, 2, 4, 5 of the user-approved cleanup list (this session):
  1. Promote account seed/auth fixtures into `agentos.testing`; delete private
     copies in agentos-py / agentos-cli / agentos-chatlas-py test helpers.
  2. Split `agent/commands.py` (1,128 lines) into a per-domain package.
  4. Split `tests/test_agent_monitor_auto_prime.py` (1,318 lines) by subject.
  5. Bounded look at `skills/routing.py` and `mdblocks/core.py`: small safe
     wins only, else record findings and defer.
- **Status:** PLANNED.
- Item 3 (typed monitor state) gets its own Impl.Req (684) — riskier, distinct
  blast radius. Item 6 (chatlas WIP) untouched by design; item 7 done in tree
  prep (`887aaab`, `20555d1`).
- **Constraints:** no compat aliases; tests import from owning modules (same
  rule as the workflows split); public entrypoint `register_agent_commands`
  stays importable from `agentos.agent`.

## Impl.Index

### Block: fixture promotion (item 1)
- Evidence: `seed_account` duplicated in agentos-py + agentos-cli helpers;
  `codex_auth_json`/`_jwt` duplicated in agentos-py + agentos-chatlas-py;
  `write_claude_home`, `seed_claude_account`, `seed_copilot_account` only in
  agentos-py but belong with the family. chatlas's `codex_auth_json` and
  `register_codex_args` are **dead** there (grep: definition only) — delete,
  don't migrate. `agentos.testing` (171 lines, single module) is the shared
  surface all three packages already import.
- Decision: add to `agentos.testing`: `seed_account`, `seed_codex_account`,
  `seed_claude_account`, `seed_copilot_account`, `codex_auth_json`,
  `write_claude_home` (+ private `_jwt`); extend `__all__`. Delete the copies
  from all three `tests/_helpers.py`; update test imports to `agentos.testing`.
  Generic io helpers (`write_text_file`, `read_json*`, `captured_json`) stay
  package-local — they are not Agentos-state fixtures.

### Block: agent commands split (item 2)
- Evidence: one module holds parsers+handlers for list, profiles, run, ping,
  profile-check, 8 accounts subcommands, monitor, sessions. External surface:
  `agentos.agent.register_agent_commands` (used by agentos-cli); tests import
  `_cmd_agent_accounts_*`, `_cmd_agent_list`, `register_agent_commands`, and
  names from `test_agent_profiles.py` directly from `agentos.agent.commands`.
- Decision: `agent/commands/` package split by command domain:
  - `_shared.py` — provider-choice constants, `_config_start_path`,
    `_add_agent_run_target_args`
  - `listing.py` — `agent list`
  - `profiles.py` — `agent profiles show|new`
  - `run.py` — `agent run|ping|profile-check` + resolve helpers
  - `accounts.py` — list/orphans/capture/activate/rotate/materialize/status
  - `monitor.py` — `agent accounts monitor` + input thread
  - `sessions.py` — `agent sessions copy`
  - `__init__.py` — `register_agent_commands` assembling the `agent` parser
    from per-domain `_register_*` functions.
  Tests updated to import handlers from the owning submodule.

### Block: monitor test split (item 4)
- Evidence: `test_agent_monitor_auto_prime.py` covers monitor config loading,
  limits-tracking refresh/rows, auto-prime triggers/ping/status, loop/display,
  render/payload — under a name claiming only auto-prime.
- Decision: split into `test_agent_monitor_config.py`,
  `test_agent_monitor_limits_tracking.py`, `test_agent_monitor_auto_prime.py`
  (auto-prime only keeps the name), `test_agent_monitor_loop_render.py`.
  Pure moves; shared fixtures duplicated only where trivial, else a
  `tests/_monitor_helpers.py`.

### Block: bounded look (item 5)
- Decision: inspect both files; implement only crisp local wins (dead code,
  obvious duplication); otherwise write findings into this note's Impl.Log
  and stop. No structural rewrites in this run.

## Execution.Plan

- Slice 1 — fixture promotion; check: all three suites green.
- Slice 2 — monitor test split; check: agentos-py suite green, same test count.
- Slice 3 — commands package split; check: agentos-py + agentos-cli suites
  green; `agentos.agent.commands` monolith deleted.
- Slice 4 — routing/mdblocks assessment; check: findings logged; any edits
  covered by existing tests.
- Acceptance: all suites green (py/cli/chatlas), ruff clean in touched repos.

## Impl.Log

- 2026-07-04: Impl.Req created (cleaner, autonomous, from user-approved list).
