# 659 — Unknown.Account lands in auth_registry

## Impl.Abstract

- **Scope:** Make `Unknown.Account` a first-class concept in `auth_registry` so the
  singular `Auth.Data.Capture` primitive *never rejects* an identifiable orphan.
  Lift the crude inline orphan fallback in the capture command into a total
  resolver on `auth_registry`, add the reserved-bucket reader, and guard the
  bucket against activation / runnability.
- **Status:** READY (not started).
- **Source context:** Design discussion (this session) grounding on the index
  concept `Unknown.Account` (`agentos-md/.../appendix/Account.Management-appendix.md:183`)
  and `Auth.Data.Capture` ("classifies, never rejects", line 143). Follows the
  new-model credential work in reqs 654–658.
- **Out of scope:** the global-capture *scanner* (a separate primitive, built
  later, that loops all homes and **uses** the singular capture); any CLI global
  verb; the adoption *move* (re-filing/activating an orphan when its real account
  registers). `_unknown` here is purely a registry bucket — a place to check for
  an auth-method — never activated.

## Impl.Index

### Block: Unknown.Account is a reserved per-provider registry bucket
- Evidence: index `Unknown.Account` — "structurally a reserved `Provider.Account`
  per provider, reusing the `Provider.Account → Auth.Method → Auth.Data.Artifact`
  nesting"; "keeps the extracted identity, so an orphan can be adopted ... once
  that account is registered"; "hard errors over unknown credentials belong
  downstream — activation, materialization, use — never at capture".
- Decision: the bucket lives in the **state** layer (captures.jsonl + artifacts),
  **not** settings. `accounts.json` stays "user-declared accounts". The reserved
  id is the constant `UNKNOWN_ACCOUNT = "_unknown"` (leading `_` cannot collide
  with a user account-id).
- Decision: for an orphan the method axis is the **auth_class** (no user-given
  name exists; the class is the stable mechanism id) → `_unknown/auth-json`,
  `_unknown/ambient-browser-login`.

### Block: capture is total — never rejects an identifiable orphan
- Current state (`Hard.Evidence`): `src/agentos/agent/commands.py:301`
  `_cmd_agent_accounts_capture` already has an **inline** fallback at lines
  317–318: `account, method = "unknown", auth_method.name`. It uses a bare
  literal `"unknown"` (not the reserved `_unknown`), and the orphan-routing
  decision lives in the command handler rather than in `auth_registry`.
- Decision: introduce `auth_registry.capture_target(provider, identity,
  auth_class) -> tuple[str, str]` returning `(account_id, method)`, **never
  None**: known identity → `(resolve_account_by_identity, method_for_class or
  class)`; orphan (identity is None, or extracts but maps to no account) →
  `(UNKNOWN_ACCOUNT, auth_class)`. The capture command calls this instead of its
  inline branch. Capture stays **singular**: one home, first readable auth-data,
  no scan machinery.
- Note: `resolve_account_by_identity` stays as-is (it may return None — that is
  the orphan signal `capture_target` consumes).

### Block: the bucket is read-only state, never activated, never runnable
- Decision: add `auth_registry.orphan_captures(provider) -> list[dict]` — the
  capture records filed under `UNKNOWN_ACCOUNT`. This is the "place to check for
  an auth-method" seam; later adoption will read it.
- Decision: `account_exists(UNKNOWN_ACCOUNT)` must stay False (the bucket is not
  a declared, runnable account). It is already False because `_unknown` is never
  in settings; lock it with a test.
- Decision: `set_active` must **reject** the reserved id — there is no
  `_unknown/<method>` active pointer. Guard with a raised `CliError`.

## Execution.Plan

Ordering: registry primitive first (the seam), then the command consumes it,
then the guards. `RED.GREEN.Test.Suite` drives each slice test-first.

### Slice 1 — `capture_target` total resolver (registry)
- Changes: add `UNKNOWN_ACCOUNT = "_unknown"` and `capture_target(provider,
  identity, auth_class)` to `src/agentos/agent/auth_registry.py`; export both.
- Path: `auth_registry` resolution used by capture.
- Observable result: known identity routes to its `(account, method)`; an orphan
  (None identity, or unmatched identity) routes to `(_unknown, auth_class)`;
  return is never None.
- Check (RED→GREEN): new unit test in `tests/test_*auth_registry*` (create if
  absent) seeding one known account via `_helpers.seed_codex_account`, asserting
  `capture_target` for a matching identity returns `(account, method)` and for an
  unmatched/None identity returns `("_unknown", auth_class)`.

### Slice 2 — singular capture consumes `capture_target`
- Changes: replace the inline `if account is not None / else "unknown"` branch in
  `_cmd_agent_accounts_capture` (`commands.py:315–318`) with a single
  `account, method = R.capture_target(provider, identity, auth_method.name)`.
- Path: `agent accounts capture --provider <p> --home <home>` for an
  unregistered home.
- Observable result: capturing a home whose identity matches no account files the
  artifact + capture record under `_unknown/<auth_class>` (was the bare
  `"unknown"`); a known home is unchanged.
- Check (RED→GREEN): behavior test invoking the capture handler against a home
  with an identity not in settings; assert the capture record's `account` is
  `_unknown` and `method` is the auth_class, and the artifact is stored. Update
  any existing capture test that asserted the old literal `"unknown"`
  (`No.Legacy.Allowed`).

### Slice 3 — `orphan_captures` reader
- Changes: add `auth_registry.orphan_captures(provider) -> list[dict]` returning
  capture records whose `account == UNKNOWN_ACCOUNT`; export it.
- Path: registry read after an orphan capture.
- Observable result: after capturing an orphan, `orphan_captures(provider)`
  returns that record (with its `auth_ref` identity preserved); returns `[]` when
  none.
- Check (RED→GREEN): unit test capturing an orphan then asserting
  `orphan_captures` returns one record carrying the extracted identity, and that
  a known-account capture does **not** appear in it.

### Slice 4 — guards: not runnable, not activatable
- Changes: `set_active` raises `CliError` when `account_id == UNKNOWN_ACCOUNT`.
  Add a test asserting `account_exists(UNKNOWN_ACCOUNT)` is False.
- Path: activation + run/monitor account validation.
- Observable result: `set_active(provider, "_unknown", method, artifact)` raises;
  `account_exists(provider, "_unknown")` is False.
- Check (RED→GREEN): unit tests for both. The activation guard test is RED before
  the guard, GREEN after.

### Risks / deviation triggers
- If a provider's `extract_identity` can return an identity object that is
  "present but empty" (no usable id), confirm `resolve_account_by_identity`
  treats it as orphan (returns None) — `capture_target` relies on that. If not, a
  deviation: decide whether empty-identity is orphan or unreadable.
- `auth_method.name` is the auth_class today (capture passes it as `auth_class`).
  Confirm that holds for both providers before relying on it for the method axis.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- Live: `agent accounts capture` on an unregistered home files under
  `_unknown/<class>`; `agent accounts status` still reports
  `error:unlisted-account` for that home (capture and status stay independent).

## Impl.Log

- (empty — not started)
