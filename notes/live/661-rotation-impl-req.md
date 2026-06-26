# 661 — Rotation: activate the head-of-line captured artifact

## Impl.Abstract

- **Scope:** Add **rotation** — move the `Active.Auth.Data` pointer for an
  `account/method` to the captured artifact a per-provider rule names as the
  *head of the line* (the credential that *should* be active). Two layers:
  - a **pure-pool primitive** `rotate(provider, account, method)` —
    `Auth.Registry`-only `Auth.Data.Activation`; it reads only registry data
    (capture log + stored artifact payloads + current active) and writes only the
    active pointer. It never reads a home or the provider.
  - a **CLI verb** `agent accounts rotate` that **captures first** (homes
    read-only, via the existing global capture) and then rotates, with flags to
    skip capture and to preview.
- **Status:** COMPLETE.
- **Source context:** Design discussion (this session). Motivated by the live
  `agent accounts status`: capture keeps up (660) but the active pointer is frozen,
  so refreshed homes read as `drift` (e.g. claude `om/browser`, `jp/browser`).
  Builds on req 659 (`auth_registry`, `_unknown` guard) and 660
  (`capture.py`, `capture_all_homes`, `providers_with_auth_methods`). Index
  grounding: `Auth.Data.Rotation`, `Auth.Data.Activation`, `Active.Auth.Data`,
  `Better.Data.Available`.
- **Out of scope:** qualifying the `status` `drift` state into
  `home-newer`/`home-older` (a separate follow-up — rotation is the action, drift
  qualification is the diagnosis); materialize-after-rotate; copilot (no
  `AuthMethod`, so never in the pool — naturally skipped); changing capture.

## Impl.Index

### Block: rotation is registry-only — the head-of-line rule reads stored data
- Evidence (user, this session): "this is an Auth.registry only method, so it must
  use what is in the registry. If the registry is not capturing the necessary
  data, we must add that data as `Auth.Data`." And: "rotation is all about
  activation, a home read-only operation."
- Registry-resident inputs: the capture log `captures.jsonl` (carries `ts` per
  capture) and the stored artifact payloads `artifacts/<id>` (the full
  `Auth.Data`, so `expiresAt` / token `exp` / `last_refresh` are already in the
  registry). Confirmed present in live artifacts: claude `claudeAiOauth.expiresAt`,
  codex `tokens.access_token` JWT `exp` + top-level `last_refresh`.
- Decision: the ranking rule consumes only `(AuthData, captured_at)` — both
  registry-resident. If a future ranking signal is not in the stored `Auth.Data`,
  the fix is to capture it (extend `Auth.Data`), never to read outside the pool.

### Block: head-of-line is a per-provider rank on the AuthMethod
- Current state (`Hard.Evidence`): `auth_method.py:44` reserves "freshness
  derivation … for a later rebuild" — this is that hook. `AuthMethod` is an ABC
  with `read_auth_data`/`extract_identity`/`materialize`.
- Decision: add a **non-abstract** `AuthMethod.rotation_rank(auth_data,
  captured_at) -> float | None`. Default (base class) = `captured_at` epoch
  (every method is rotatable by agentos capture time). `None` means "no criterion
  — skip this account/method (manual)". It is "ONE date / one criterion we
  decide, per provider" (user) — providers override with their stored payload date.
- Decision: per the user, the criterion is not load-bearing and is swappable;
  ranking is "higher = should be head", ties broken by `captured_at` then
  `artifact_id` for determinism.

### Block: the pure-pool primitive and the capture-first CLI are different layers
- Evidence (user): "we must differentiate the primitive in the code from the
  command in the CLI. The primitive should be pure-pool, but the command will
  capture — we can add a flag to control that."
- Decision: `rotate(provider, account, method, *, dry_run=False)` in a new
  `src/agentos/agent/rotation.py` is pure-pool. The CLI handler composes
  `capture_all_homes` (660) then the rotation sweep; `--no-capture` skips the
  capture step, `--dry-run` previews (no `set_active`, and capture runs in its own
  dry-run).
- Decision: rotatable `account/method` pairs come from **settings**
  (`auth_registry.load_settings` accounts → `auth_methods`); `_unknown` is never a
  settings account, so the 659 `set_active` guard is never hit.

## Execution.Plan

Ordering: pure-pool primitive with the default rank first (reaches a testable
endpoint fast), then provider rank overrides, then the sweep + CLI. Each slice is
`RED.GREEN.Test.Suite`-driven, test-first.

### Slice 1 — registry enumerator + pure-pool `rotate` with default rank
- Changes: add `auth_registry.captures_for(provider, account, method) ->
  list[dict]` (capture records for that key, `_unknown` excluded naturally by the
  caller passing a real account). Add `AuthMethod.rotation_rank` default (returns
  `captured_at`). New `agent/rotation.py` with `RotateResult` (provider, account,
  method, previous_active, new_active, changed, skipped) and
  `rotate(provider, account, method, *, dry_run=False)`: gather candidate
  `artifact_id`s (dedup; a repeated artifact's `captured_at` is its **earliest**
  `ts` = its registration date), read each payload, rank via the method, pick the
  max (tie-break), `set_active` if it differs from current — unless `dry_run`.
- Path: `auth_registry` + `rotation` over a seeded pool, no homes.
- Observable result: given two captured artifacts for `acct/method` (active = the
  older), `rotate` sets active to the newer and returns `changed=True`; a second
  call returns `changed=False`; `dry_run=True` reports the intended new active but
  leaves `active.json` untouched.
- Check (RED→GREEN): unit test in a new `tests/test_agent_rotation.py` seeding two
  artifacts + capture records + an active pointer; assert the active flip, the
  idempotent re-run, and the dry-run no-write.

### Slice 2 — codex + claude `rotation_rank` overrides (payload date)
- Changes: override `rotation_rank` on `CodexAuthMethod` (token `exp` from the
  stored payload, reusing its JWT parsing) and `ClaudeAuthMethod`
  (`claudeAiOauth.expiresAt`). Update the `auth_method.py:44` reserved-for-later
  comment (`No.Legacy.Allowed`).
- Path: `rotate` over a pool where capture order and payload-date order disagree.
- Observable result: capture a **lower-`exp`** artifact *last* (so it is newest by
  capture time) — rotation still selects the **higher-`exp`** artifact, proving the
  provider date wins over capture time.
- Check (RED→GREEN): per-provider unit tests building two artifacts with crafted
  `exp`/`expiresAt`, asserting `rotation_rank` ordering and that `rotate` picks the
  payload-fresher one.

### Slice 3 — `rotate_all` sweep + `agent accounts rotate` CLI verb
- Changes: add `rotation.rotate_all(provider, *, dry_run=False)` (iterate
  settings accounts × methods, call `rotate`, collect results). Add the `rotate`
  subparser + `_cmd_agent_accounts_rotate`: provider set = `providers_with_auth_methods`
  (or `--provider`); optional `--account <id/method>` to scope to one; capture-first
  via `capture_all_homes` unless `--no-capture`; `--dry-run` threads through both
  capture and rotate; `--json` list output; text output prints `acct/method:
  old → new (changed|unchanged|skipped)` + a tally.
- Path: `agent accounts rotate [--provider] [--account] [--no-capture] [--dry-run] [--json]`.
- Observable result: against a seeded drifted account, `rotate` (capture-first)
  flips active to the head and reports it; `--dry-run` writes nothing; `--no-capture`
  rotates over the existing pool only.
- Check (RED→GREEN): handler-level tests — capture-first rotate flips a drifted
  account; `--dry-run` leaves `active.json` and `captures.jsonl` unchanged;
  `--no-capture` does not read homes (no capture-log growth).

### Risks / deviation triggers
- A candidate artifact may fail to parse its rank field (malformed/rotated-out
  token). `rotation_rank` should return `None` for that artifact (it drops out of
  ranking) rather than raise; if **all** candidates rank `None`, the pair is
  `skipped` (reported, active untouched). Confirm both providers degrade this way.
- `captured_at` dedup choice (earliest `ts` per artifact) is a decision, not a
  gap — stated above; revisit only if a test shows it picks wrong.
- If settings has an account whose method has **no** captures yet, `rotate` returns
  `skipped` (empty pool), never an error.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `agent accounts rotate --provider claude-code --dry-run` over live data reports
  the intended active flips for the drifted `om`/`jp` browser accounts and writes
  nothing; a real run then makes `agent accounts status` show them `aligned` for
  the head home (other homes correctly become stale `drift`, to be materialized).
- `status` and `capture` behavior unchanged.

## Impl.Log

- All 3 slices RED→GREEN. Suite 164→176 (+12), lint clean.
- Deviation (Slice 1 ranking tie-break): the plan said default rank = earliest
  `ts` (registration date), tie-break `captured_at` then `artifact_id`.
  `utc_now_iso()` is **second-granularity**, so same-second captures tie and
  `artifact_id` ordering is arbitrary. Changed to: per-artifact `captured_at` =
  its **most recent** capture `ts`, and the deterministic tie-break is the
  **capture-sequence index** (file order in `captures.jsonl`) — "most recently
  captured wins". Providers' fine-grained `exp`/`expiresAt` rarely tie, so this
  only governs the default path.
- Deviation (Slice 1 tests): both real providers override `rotation_rank`, so the
  ABC default is unreachable through a real provider. Retargeted the primitive
  mechanics tests to real codex payloads (with `exp`); covered the ABC default via
  a minimal stub `AuthMethod` and added an explicit capture-sequence tie-break test.
- Live finding (not a deviation): `agent accounts rotate --dry-run` reports **0
  changes** — for every claude account the active artifact already holds the
  highest `expiresAt` in the pool (verified). So rotation is correctly a no-op and
  the remaining `status` drift is **stale homes** (older than active) → the
  materialize axis. This is exactly the deferred `drift:home-older` follow-up; the
  qualified-drift status work would surface it.
- `--dry-run` limitation (by design): capture-first also runs dry, so a
  just-refreshed-but-uncaptured home is not in the pool during a preview; the
  preview reflects the existing pool. A real run captures first, then rotates.
