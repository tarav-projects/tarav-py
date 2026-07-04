# 679 — cleanup: share the duplicated account-status payload helpers

## Impl.Abstract

- **Scope (cleanup — repeated knowledge / DRY):** the three provider `account_status`
  modules (`claude/`, `codex/`, `copilot/`) each carry private copies of the same
  payload-shaping helpers. Six of them are byte-identical (or identical modulo the
  `datetime.UTC` vs `datetime.timezone.utc` spelling) across their copies. Move those
  six into `agentos/agent/account_status.py` — the existing shared boundary module that
  already owns `AccountLimit` / `AccountIdentity` / `AccountStatusError` and that all
  three providers already import. No new module, no new layer.
- **The six shared helpers** (verified identical by AST-body diff):
  - `limits_summary(limits)` — from `_limits_summary`, 3× (claude:391, codex:391,
    copilot:600). Consumes `tuple[AccountLimit, ...]` — belongs next to `AccountLimit`.
  - `string_or_none(value)` — from `_string_or_none`, 3× (claude, codex, copilot).
  - `iso_from_epoch_seconds(epoch_seconds)` — from `_iso_from_epoch_seconds`, 2×
    (claude:1176, codex:527).
  - `period_bounds_from_reset(*, resets_at_epoch, period_duration_mins)` — from
    `_period_bounds_from_reset`, 2× (claude, codex). Calls `iso_from_epoch_seconds`.
  - `optional_int(value, *, field_name)` — from `_optional_int`, 2× (claude, codex).
    Raises `CliError` — `account_status.py` may import `CliError` (check; add if not).
  - `parse_iso_datetime(value)` — from `_parse_iso_datetime`, 2× (claude, copilot;
    identical modulo UTC spelling — pick one spelling, output identical).
- **Decision:** shared copies become public (no leading underscore) module functions in
  `agent/account_status.py`; provider modules import them and the local `def _*` copies
  are deleted (`No.Legacy.Allowed` — no aliasing shims like `_limits_summary =
  limits_summary`). Call sites switch to the imported names.
- **Status:** COMPLETE.
- **Source context:** `hugentics-codebase-cleaner` scan after 678. No test references
  any of these private helpers (verified by grep over `tests/`), so the move is
  invisible to the suite — existing provider account-status tests are the behavior net.
- **Out of scope (do NOT touch):**
  - The **provider-tuned near-duplicates**: `_identity_match` (each provider compares a
    different identity field), `_setup_errors`, `_account_name`, `_account_timeout_sec`
    (different default constants), `_usage_auth_summary`, `_optional_number`,
    `_required_int`, claude's `_period_bounds_from_reset_iso`. Parameterizing these
    reshapes logic — not this cleanup.
  - The `_datetime_to_iso` one-line wrappers (claude/copilot) — they already delegate to
    `clock.iso_z` (678); an alias is not repeated knowledge.
  - Any behavior, output shape, or parsing semantics.

## Impl.Index

### Block A: the duplication is real and mechanical (`Hard.Evidence`)
- AST-body diff over the three modules: `_limits_summary`, `_string_or_none` identical
  3×; `_iso_from_epoch_seconds`, `_period_bounds_from_reset`, `_optional_int` identical
  2× (claude/codex); `_parse_iso_datetime` identical 2× (claude/copilot) except
  `datetime.UTC` ≡ `datetime.timezone.utc`.
- Call sites (grep): codex 8, claude 14, copilot 5 — all module-internal; zero test or
  cross-module references to the private names.
- `agent/account_status.py` (232 lines) is imported by all three provider
  `account_status` modules already — adding these functions creates no new dependency
  edge.

### Block B: naming and placement
- Shared functions are public names (they cross a module boundary now): drop the `_`.
- Place them together under a short section comment near `AccountLimit` (for
  `limits_summary`) / at the module tail (parsing helpers) — follow the module's
  existing layout.
- `optional_int` needs `CliError`; `iso_from_epoch_seconds` keeps its exact current
  formatting expression (epoch-built, keeps microsecond-free output only because epoch
  seconds have no micros — do NOT reroute through `clock.iso_z`, which would be a
  semantic re-derivation, not a move).

## Execution.Plan

One vertical slice — this is a pure relocation with a single observable boundary:
identical provider behavior with the helper family defined once. Per
`No.Regression.Tests.Allowed`, no new tests: the existing provider account-status suites
are the net. `RED.GREEN` does not apply to a pure move; verification is suite + lint +
a no-duplicates grep.

### Slice 1 — move the six helpers, repoint the three providers
- Changes: add the six public functions to `agent/account_status.py` (bodies verbatim
  from the current copies, one UTC spelling); in each provider module extend the
  existing `from agentos.agent.account_status import …` with the names it uses, delete
  the local `def _*` copies, and rename call sites to the imported names.
- Path: every provider account-status probe (`claude`/`codex`/`copilot`) → shared
  payload helpers.
- Observable result: byte-identical account-status output; each helper has exactly one
  definition; ~60 duplicated lines gone.
- Check: full suite green, `ruff` clean, and grep confirms no `_limits_summary` /
  `_string_or_none` / `_iso_from_epoch_seconds` / `_period_bounds_from_reset` /
  `_optional_int` / `_parse_iso_datetime` definitions remain under `src/agentos/{claude,codex,copilot}/`.

### Risks / deviation triggers
- **Unused-import fallout:** deleting local copies may orphan `datetime` submodule
  imports in a provider — trim only what ruff flags; touch nothing else.
- **Hidden divergence:** if any copy turns out not identical at edit time, that copy is
  out of scope — leave it local and record the finding in `Impl.Log` (cleanup never
  broadens or reinterprets).
- **Scope guard (hard boundary):** no parameterization of the provider-tuned helpers, no
  behavior change, no new module.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- The six helpers defined once, in `agent/account_status.py`; zero copies left in
  provider modules; no aliasing shims.
- Provider account-status behavior byte-identical (existing tests unchanged and green).

## Impl.Log

- Slice 1 done. Suite 247 passed (unchanged — pure relocation, no new tests per
  `No.Regression.Tests.Allowed`); lint clean; grep confirms zero helper copies remain in
  the provider modules. **No deviations.**
- Spelling note: the shared `iso_from_epoch_seconds` / `parse_iso_datetime` use
  `datetime.UTC` (the module's existing spelling; alias of `datetime.timezone.utc` —
  the originals' spelling). Identical object, identical output.
- Unused-import fallout as predicted: codex's `import datetime` orphaned by the
  deletions; removed (ruff-flagged, nothing else touched).
- claude's `_period_bounds_from_reset_iso` (superficially similar name, claude-only
  logic) verified untouched by the word-boundary rename.
