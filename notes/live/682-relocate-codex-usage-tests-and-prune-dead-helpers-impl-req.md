# 682 — relocate codex usage tests to agentos-py, prune dead test helpers

## Impl.Abstract

- **Scope:** follow-ups recorded in agentos-cli `notes/live/001` Impl.Log:
  1. The 3 codex usage tests in agentos-cli `tests/test_e2e_agent_usage.py`
     are library-level (they call `CodexAgent.account_status()` directly, no
     CLI parser involved) — move them into agentos-py as
     `tests/test_codex_usage_records.py`, delete the agentos-cli file.
  2. Delete the dead `register_codex_args` from agentos-py
     `tests/_helpers.py` (asserted dead by grep: definition only).
  3. Prune agentos-cli `tests/_helpers.py` helpers left dead by the move.
- **Status:** COMPLETE.
- **Source context:** `agentos-hugentics-codebase-cleaner --AUTO`; tree prep
  committed the pending 681 monitor cleanup (`6672e02`) and the 001 e2e
  realignment (`09113cd`).
- **Constraints:** pure move + delete; no behavior or assertion changes beyond
  dropping unused `capsys` fixtures and switching to agentos-py's own helpers
  (`seed_codex_account`, `codex_auth_json`, `write_text_file`,
  `read_jsonl_file` — all already present there).

## Execution.Plan

### Slice 1 — move the tests into agentos-py
- Create `agentos-py/tests/test_codex_usage_records.py` with the 3 tests and
  their `_codex_usage_payload` / `_failed_app_server_result` /
  `_seeded_codex_agent` helpers; imports from agentos-py `tests/_helpers.py`.
- Delete `agentos-cli/tests/test_e2e_agent_usage.py`.
- Check: new file green in agentos-py; agentos-cli suite green.

### Slice 2 — prune dead helpers
- agentos-py `tests/_helpers.py`: delete `register_codex_args`.
- agentos-cli `tests/_helpers.py`: delete helpers with no remaining users
  (verify by grep after slice 1).
- Check: both suites green; ruff clean in both repos.

### Acceptance signals
- agentos-py: full suite green (255 expected: 252 + 3 moved).
- agentos-cli: full suite green (49 expected: 52 − 3 moved).
- `register_codex_args` gone from both repos.

## Impl.Log

- 2026-07-04: Impl.Req created (cleaner, autonomous).
- 2026-07-04: Executed both slices. Checkpoints: agentos-py `574dd62`,
  agentos-cli `1521016`. One addition beyond the named helpers: agentos-cli's
  `_jwt`/`codex_auth_json` in `tests/_helpers.py` became dead after the move
  (the accounts test carries its own local `_jwt`) — pruned per slice 2's
  grep-verified rule. Verification: agentos-py 255 passed / ruff clean;
  agentos-cli 49 passed / ruff clean; no `register_codex_args` anywhere.
