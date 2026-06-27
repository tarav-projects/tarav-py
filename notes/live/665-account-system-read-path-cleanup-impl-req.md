# 665 — account system: dedup read paths + fix two read oddities

## Impl.Abstract

- **Scope (cleanup):** remove duplicated read logic in the account/auth system and
  fix two correctness/doc oddities it exposed. Three narrow, coherent themes:
  - **A. One capture-log iterator.** `auth_registry.is_captured`,
    `orphan_captures`, `captures_for` each re-implement the same
    `captures.jsonl` open→splitlines→skip-blank→`json.loads`→`isinstance`
    scan. Centralize into one private `_iter_capture_records(provider)`.
  - **B. One home auth-reader.** `capture.capture_home`,
    `materialization._home_target_account_method`, and
    `account_status_report.status_for_home` each re-walk "the first provider
    `AuthMethod` that reads this home, plus its extracted identity" — three
    divergent copies. Centralize into
    `auth_method_registry.read_home_auth(provider, home)`. This also fixes
    `status_for_home`'s method-name oddity: it currently derives the method name
    by string-matching profile candidates rather than routing by the class
    actually read (a latent mislabel for a multi-method account). Behaviour-
    preserving today (one `AuthMethod` per provider), correct for the future.
  - **C. Stale doc.** `claude/auth_method.py` module docstring claims
    `materialize` is "intentionally unimplemented / read-only"; it is fully
    implemented and `materializable=True`. Correct the docstring.
- **Status:** COMPLETE.
- **Source context:** `hugentics-codebase-cleaner` scan of the account system
  (this session), after the 659–664 rebuild. Cleanup constraints: stay narrow,
  module-local helpers, no new frameworks, replace (don't wrap) the duplication.
- **Out of scope:** any change to the registry on-disk format, the capture/rotate/
  activate/materialize semantics, CLI surfaces, or provider credential parsing.
  No new modules beyond the two helper functions in existing files.

## Impl.Index

### Block A: a single capture-log iterator
- Current state (`Hard.Evidence`): `auth_registry.py` — `is_captured` (238-248),
  `orphan_captures` (270-285), `captures_for` (288-304) all open
  `captures_path(provider)`, guard `is_file`, `splitlines`, skip blank lines,
  `json.loads` each, and (mostly) `isinstance(record, dict)`-check. `pool_for`
  (307) and `auth_data_for_ref` (251) already consume `captures_for`.
- Decision: add private `_iter_capture_records(provider) -> Iterator[dict]` that
  yields each parsed dict record (skipping blanks/non-dicts). Rewrite the three
  readers as filters over it. `is_captured` keeps its tuple-equality test;
  `orphan_captures`/`captures_for` keep their account/method filters. No format,
  ordering, or signature change.

### Block B: a single home auth-reader, routing by the read class
- Current state (`Hard.Evidence`):
  - `capture.capture_home` (`capture.py:42-49`): `for auth_method in
    auth_methods_for_provider(provider): auth = read_auth_data(home); if None
    continue; identity = extract_identity(auth); …` then `capture_target`.
  - `materialization._home_target_account_method`: the same loop, then
    `resolve_account_by_identity` + candidate check + `method_for_class`.
  - `account_status_report.status_for_home` (`:50-85`): a *different* loop over
    `target.candidates` using `method_class`, then derives `method_name` by
    string-matching candidates (`:71-74`) — not by the class actually read.
- Decision: add `read_home_auth(provider, home) -> HomeAuth | None` to
  `auth_method_registry.py` (a small frozen `HomeAuth(method, auth, identity)`):
  the first provider `AuthMethod` whose `read_auth_data` is non-None, with its
  `extract_identity`. All three call sites consume it and keep their own
  account-policy tail (capture → `capture_target`/orphan bucket; materialize/
  status → `resolve_account_by_identity` + candidate gate + `method_for_class`).
- Decision (oddity fix): `status_for_home` resolves its reported method via
  `method_for_class(provider, account, found.method.name)` (route by the read
  class), replacing the candidate string-match. Single `AuthMethod` per provider
  today ⇒ identical output now; removes the latent multi-method mislabel.

### Block C: correct the claude docstring
- Current state (`Hard.Evidence`): `claude/auth_method.py` docstring (10-12) says
  materialize is "intentionally unimplemented — observed read-only", but
  `ClaudeAuthMethod.materialize` (137-148) writes secure storage + `.claude.json`
  and `materializable = True`; the live `rotate --materialize` writes claude homes.
- Decision: reword the docstring to state the credential spans two home locations
  and is both read and materialized (write both halves back). `No.Legacy.Allowed`
  — misleading doc removed.

## Execution.Plan

Verification is the existing suite (the account read paths are well covered:
`test_agent_auth_registry`, `test_agent_capture`, `test_agent_materialization`,
`test_agent_accounts_list/status/rotate`, provider auth-method tests). Each slice
is a behaviour-preserving refactor, so the gate is "full suite stays green +
lint clean" rather than a new RED test. No new behaviour ⇒ `No.Regression.Tests`:
do not add tests for unchanged behaviour.

### Slice 1 — `_iter_capture_records` (Block A)
- Changes: add the private iterator in `auth_registry.py`; rewrite `is_captured`,
  `orphan_captures`, `captures_for` over it.
- Observable result: identical records/order from all three; callers (`pool_for`,
  `auth_data_for_ref`, rotation, list) unaffected.
- Check: `uv run pytest tests/test_agent_auth_registry.py tests/test_agent_capture.py
  tests/test_agent_accounts_list.py -q` green; then full suite.

### Slice 2 — `read_home_auth` shared reader (Block B)
- Changes: add `HomeAuth` + `read_home_auth` to `auth_method_registry.py`. Rewire
  `capture_home`, `_home_target_account_method`, and `status_for_home` onto it;
  fix `status_for_home`'s method-name to `method_for_class(... found.method.name)`.
  Drop now-unused imports (`auth_methods_for_provider` in capture/materialization,
  `auth_method_for_class`/`method_class` path in status where superseded).
- Observable result: capture/materialize/status behave exactly as before for the
  current one-method-per-provider providers; the three read loops are now one.
- Check: `uv run pytest tests/test_agent_capture.py tests/test_agent_materialization.py
  tests/test_agent_accounts_status.py tests/test_agent_accounts_rotate.py -q`
  green; then full suite. Live spot-check: `agent accounts status --provider
  claude-code` and `rotate --provider claude-code --materialize --dry-run` read
  identically to before (read-only / dry-run).

### Slice 3 — claude docstring (Block C)
- Changes: reword `claude/auth_method.py` module docstring.
- Check: `uv run ruff check src/ tests/`; full suite green (docs-only).

### Risks / deviation triggers
- If any provider gains a second `AuthMethod` before this lands, `read_home_auth`'s
  "first method that reads" changes which class a home resolves through vs the old
  candidate-driven `status` path — still the intended unified behaviour, but flag
  it. (None today.)
- `read_home_auth` must preserve "first non-None read wins" ordering
  (`auth_methods_for_provider` order) so capture/status pick the same method as
  before. Do not sort or change the iteration source.
- Keep capture's orphan policy intact: `read_home_auth` returns identity possibly
  None; `capture_target` still files None/unmatched under `_unknown`. The shared
  reader must not apply any account policy itself.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `auth_registry` has one capture-log scan; `auth_method_registry` has one
  home-reader consumed by all three call sites; no duplicated read loops remain.
- `claude/auth_method.py` docstring matches the implemented `materialize`.

## Impl.Log

- All three slices applied as behaviour-preserving refactors. Full suite stayed
  green throughout (189 passed), lint clean. No new tests added (`No.Regression`).
- Block B confirmed zero behaviour change live: `agent accounts status --provider
  claude-code` and `rotate --provider claude-code --materialize --dry-run` produced
  identical output to pre-cleanup (same drift/aligned per home; same 2-home
  materialize preview). The `status_for_home` method-name fix is latent-only today
  (one `AuthMethod` per provider) — no observable diff now, removes the multi-method
  mislabel for the future.
- `auth_method_registry` gained `account_status` (`AccountIdentity`) + `auth_method`
  (`AuthData`) imports for `HomeAuth`; no import cycle (it does not import
  `account_status_report`, which is the module that imports it back).
