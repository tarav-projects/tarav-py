# 660 — Global capture (sweep all homes)

## Impl.Abstract

- **Scope:** Add **global capture** — a sweep that captures the `Auth.Data`
  present in *every* home, building on the singular per-home capture primitive.
  It is the write-mirror of the `status` scan: same home source, but it archives
  instead of just reporting. Surfaced as a `--global` flag on the existing
  `agent accounts capture` subcommand (no new subcommand). Capture never rejects
  — known artifacts file under their account/method, identifiable orphans under
  `Unknown.Account` (`_unknown`), per req 659.
- **Status:** READY (not started).
- **Source context:** Design discussion (this session). Builds directly on req
  659 (`auth_registry.capture_target` / `UNKNOWN_ACCOUNT` / singular capture) and
  reuses `account_status_report.collect_home_targets` (the home scan `status`
  uses). Index grounding: `Auth.Data.Capture` ("classifies, never rejects"),
  `Unknown.Account`, `Capture.Over.Materialization` (capture always-safe).
- **Out of scope:** activation/materialization of swept artifacts (capture only);
  the adoption move for orphans; any change to `status`; capturing homes that are
  not in any profile (profile homes are the authority, same as `status`).

## Impl.Index

### Block: global capture reuses the status scan as its home source
- Evidence: `account_status_report.collect_home_targets(provider)` returns the
  deduped union of all profile homes for a provider (`:30`). `status` already
  sweeps this. Global capture is the write-mirror — same homes, archive instead
  of report.
- Decision: global capture reads each home's `.home` only; it does **not** need
  the candidate sets (capture resolves identity itself via `capture_target` and
  files orphans to `_unknown`). Profile homes are the authority — homes outside
  every profile are not swept (matches `status`).

### Block: "global uses the singular one" — one shared per-home primitive
- Evidence: prior user constraint (req 659 discussion) — "the global capture use
  the singular one ... I do not want the scanning machinery inside the current
  capture primitive."
- Current state (`Hard.Evidence`): `_cmd_agent_accounts_capture`
  (`commands.py:301`) inlines the per-home body (loop auth-methods, first readable
  wins, `capture_target` → `store_artifact` → `is_captured`/`append_capture`) and
  ends with `raise CliError` when nothing reads.
- Decision: extract the per-home body into a provider-agnostic module
  `src/agentos/agent/capture.py`: `capture_home(provider, home) -> CaptureResult
  | None` (None = no readable Auth.Data — the scan machinery is *not* in here) and
  `capture_all_homes(provider) -> list[CaptureResult]` that loops
  `collect_home_targets`. Both the `--home` and `--global` CLI paths call
  `capture_home`. `CaptureResult` carries `provider, home, account, method,
  artifact_id, is_new` (`is_new` = a fresh `append_capture` vs already-present,
  from the existing `is_captured` gate).

### Block: `--global` sweeps every provider; copilot has no auth-method
- Evidence: `_METHODS` registers only codex + claude-code
  (`auth_method_registry.py`); copilot has no `AuthMethod`, so every copilot home
  reads nothing and is skipped. `_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES =
  ("codex", "claude-code", "copilot-cli")` (`commands.py:30`).
- Decision: the global provider set = providers that have a registered
  auth-method (derive from `_METHODS`, via a new
  `auth_method_registry.providers_with_auth_methods()`), so adding an `AuthMethod`
  later auto-joins the sweep and copilot is not swept for nothing. With
  `--provider` given, scope to that one; without it, sweep all-with-methods —
  mirroring the existing optional-`--provider` pattern in the `status` handler
  (`commands.py:415`).

### Block: CLI — `--global` flag, mutually exclusive with `--home`
- Current state: the `capture` subparser requires both `--provider` and `--home`
  (`commands.py:656-660`).
- Decision: add `--global` (store_true) to the `capture` subparser; relax
  `--provider` and `--home` to not-required at the parser level and validate the
  combination in the handler:
  - `--global` + `--home` → `CliError` (mutually exclusive).
  - `--global` without `--home`: sweep; `--provider` optional (scopes if given).
  - single (no `--global`): `--home` **and** `--provider` both required (preserve
    today's behavior, incl. the "no Auth.Data → CliError" on an empty home).
- Decision: a home with no readable Auth.Data is **skipped** (recorded) in the
  global sweep — never aborts the sweep — while the single `--home` path keeps
  raising. Output: global prints one line per swept home (home, account/method,
  artifact, `new`/`already`, or `skipped`) plus a tally; `--json` → list of
  per-home results. Idempotent: re-running captures nothing new (`is_new=False`
  everywhere on the second pass).

## Execution.Plan

Ordering: build the shared primitive (`capture.py`) first so the singular path is
green on it, then the global sweep, then the CLI wiring. `RED.GREEN.Test.Suite`
drives each slice test-first.

### Slice 1 — extract `capture.py` with `capture_home`, singular path uses it
- Changes: new `src/agentos/agent/capture.py` with `CaptureResult` +
  `capture_home(provider, home) -> CaptureResult | None` (the lifted per-home
  body). Rewrite `_cmd_agent_accounts_capture` to call `capture_home` and raise
  the existing `CliError` when it returns None; keep identical output.
- Path: `agent accounts capture --provider <p> --home <home>` (unchanged surface).
- Observable result: single capture behaves exactly as before — known home files
  under account/method, orphan under `_unknown`, empty home errors.
- Check (RED→GREEN): the existing `tests/test_agent_accounts_capture_activate.py`
  cases (`test_capture_files_by_identity`, `test_capture_orphan_to_unknown_account`)
  must stay green; add a direct unit test of `capture_home` returning a
  `CaptureResult` for a readable home and `None` for an empty one (RED before the
  module exists).

### Slice 2 — `capture_all_homes` sweeps one provider's homes
- Changes: add `capture_all_homes(provider) -> list[CaptureResult]` to
  `capture.py`, looping `collect_home_targets(provider)` and calling
  `capture_home` per home (skips Nones).
- Path: programmatic sweep of a provider.
- Observable result: given two profile homes (one known, one orphan), the sweep
  returns two results filed correctly; an empty/non-existent home contributes no
  result; a second call returns results with `is_new=False`.
- Check (RED→GREEN): unit test seeding a profile with two homes (via
  `_helpers.seed_*` + a profile fixture), asserting the result set, the
  `_unknown` filing of the orphan, and idempotency on the second call.

### Slice 3 — `providers_with_auth_methods` + global CLI handler
- Changes: add `auth_method_registry.providers_with_auth_methods() ->
  tuple[str, ...]`. Add `--global` to the capture subparser; relax `--provider`/
  `--home` required-ness; implement the combination validation + global branch in
  `_cmd_agent_accounts_capture` (loop the provider set, aggregate per-home
  results, print lines + tally, `--json` list).
- Path: `agent accounts capture --global` and `... --global --provider codex`.
- Observable result: `--global` with no provider sweeps codex + claude-code (not
  copilot); `--global --home` errors; single path still requires both.
- Check (RED→GREEN): handler-level tests — (a) `--global --provider codex` over a
  seeded two-home profile captures both and prints a tally; (b) `--global --home X`
  raises `CliError`; (c) single `--home` with no `--provider` raises; (d)
  `providers_with_auth_methods()` returns exactly `("codex","claude-code")`
  (order-insensitive).

### Risks / deviation triggers
- `collect_home_targets` resolves homes with `.expanduser().resolve()`; a profile
  home that does not exist on disk yields a `HomeTarget` whose read returns None →
  skipped. Confirm `capture_home` tolerates a missing home path (no exception).
- If `capture_home` must capture *all* readable methods per home rather than the
  first (today's singular captures only the first readable), that is a semantic
  change — out of scope here; keep first-readable parity with the singular path
  and note it.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `agent accounts capture --global --provider codex` over the live profiles
  reports a per-home tally and files any new artifacts (idempotent on re-run).
- `status` is unchanged; capture and status stay independent.

## Impl.Log

- (empty — not started)
