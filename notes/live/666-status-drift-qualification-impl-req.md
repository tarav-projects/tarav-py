# 666 — status drift qualification (`home-newer` / `home-older` / `no-active`)

## Impl.Abstract

- **Scope:** qualify `status`'s undifferentiated `drift` so each drifted home says
  *which* lifecycle op fixes it. Split `drift` into:
  - `drift:home-newer` — the home's `Auth.Data` is fresher than the active ref → **rotate**.
  - `drift:home-older` — the active ref is fresher than the home → **materialize**.
  - `drift:no-active` — the home holds a credential but nothing is active for that
    account/method yet → **rotate**.
  - `drift` (bare) — refs differ but the freshness ranks are unorderable
    (equal, or `None`) → inspect.
  `aligned` is unchanged.
- **Status:** COMPLETE.
- **Source context:** design discussion (this session), the natural readout for the
  `rotate --materialize` reconciler built in 664. Principle the user set: **status
  is only a consumer** — the freshness comparison is a primitive built on what
  rotation already owns (`AuthMethod.rotation_rank`), not new logic in status.
- **Out of scope:** changing rotation/materialize behaviour, the registry format, or
  any home write; auto-acting on drift (status stays read-only); a new CLI verb.

## Impl.Index

### Block: the freshness comparison is `rotation_rank`, reused
- Evidence: `AuthMethod.rotation_rank(auth_data, captured_at) -> float | None`
  (`auth_method.py:71`) is the head-of-line key rotation already ranks by
  (`rotation.rotate`, `rotation.py:67`). Both providers derive it from the payload
  (codex token `exp` `codex/auth_method.py:61`; claude `claudeAiOauth.expiresAt`
  `claude/auth_method.py:153`); the ABC default is `captured_at`.
- Decision: drift direction = `rotation_rank(home_auth)` vs
  `rotation_rank(active_auth)`, **feeding the same `captured_at` basis to both
  sides** (the active ref's capture-record `ts`). Direction then comes purely from
  payload-derived divergence; a default-rank method (no payload date) yields equal
  ranks → unorderable → bare `drift`. This is the honest "can't tell" path and needs
  no way to detect whether a method overrode `rotation_rank`.

### Block: a `rotation.py` primitive; status consumes it
- Evidence: `rotation.py` already has `_epoch(ts)` (`:31`) and reads the capture
  pool via `R.captures_for` / `R.record_ref_id`; `R.auth_data_for_ref` resolves a
  ref to its payload; `R.active_ref` gives the active pointer.
- Decision: add `rotation.drift_against_active(provider, account, method,
  home_method, home_auth) -> "newer" | "older" | None`. It reads `active_ref`,
  resolves `auth_data_for_ref` for it, finds that ref's capture `ts` (the basis,
  via the capture record; `_epoch`; `0.0` when no record joins it), ranks both
  sides with `home_method.rotation_rank`, and returns the direction (`None` when
  either rank is `None` or they tie). Registry-side only; no home read/write. The
  `home_method`/`home_auth` come from the caller (status already has them via
  `read_home_auth`).
- Decision: `status_for_home` (`account_status_report.py:50`) maps the result.
  Current state (`Hard.Evidence`): after `read_home_auth` + account/candidate
  resolution it computes `active = R.active_ref(...)` and branches
  aligned / drift(reason "home Auth.Data is not the active one") / drift(reason "no
  active artifact registered…"). New mapping: `active is None` → `drift:no-active`;
  `active == found.method.ref_id(found.auth)` → `aligned` (unchanged); else call
  `drift_against_active` → `drift:home-newer` / `drift:home-older` / bare `drift`.
  Status gains no ranking knowledge — it only relabels.

### Block: the four drift labels and their fixes
- `drift:home-newer` → rotate · `drift:home-older` → materialize ·
  `drift:no-active` → rotate · `drift` → inspect. The reason strings carry the
  rationale (e.g. "home credential is newer than active — rotate";
  "active is newer than home — materialize"; "no active ref registered — rotate";
  "home differs from active but freshness is unorderable").
- Decision (forks settled): `no-active` is **kept distinct** from `home-newer`
  (different cause, clearer signal); the unorderable residual is **bare `drift`**,
  not a manufactured `drift:undetermined`.

## Execution.Plan

Ordering: the comparison primitive first (unit-testable in isolation), then the
status mapping that consumes it (observable via the report). Each slice
`RED.GREEN.Test.Suite`-driven, test-first.

### Slice 1 — `rotation.drift_against_active` primitive
- Changes: add `drift_against_active(...)` to `rotation.py` (+ a small private
  `_active_captured_at(provider, account, method, ref)` helper using
  `captures_for`/`record_ref_id`/`_epoch`). Export it.
- Path: registry-side ranking — `active_ref` → `auth_data_for_ref` → `rotation_rank`
  both sides on the active's capture `ts` basis.
- Observable result: for a codex `account/method` whose active ref has token
  `exp=A`, a home payload with `exp>A` → `"newer"`, `exp<A` → `"older"`, equal →
  `None`; `None` when there is no active or its payload is unresolvable.
- Check (RED→GREEN): new `tests/test_agent_rotation_drift.py` (or extend
  `test_agent_rotation.py`) — seed an active codex ref (known `exp`) and call with
  home `AuthData`s of greater/lesser/equal `exp`; assert `"newer"/"older"/None`.
  RED before the function exists.

### Slice 2 — `status_for_home` maps to qualified labels
- Changes: rewrite the drift branch of `status_for_home` to emit
  `drift:home-newer` / `drift:home-older` / `drift:no-active` / `drift` per the
  mapping, with matching reasons, consuming `drift_against_active`.
- Path: `agent accounts status [--provider …]` → `build_status_report` →
  `status_for_home`.
- Observable result: a home fresher than active reports `drift:home-newer`; a home
  staler than active reports `drift:home-older`; a home with no active ref reports
  `drift:no-active`; an aligned home still `aligned`.
- Check (RED→GREEN): extend `tests/test_agent_account_status_report.py` — three
  seeded homes (newer / older / no-active) over a codex account with differing
  token `exp`, asserting each home's `status` label (and that aligned stays
  `aligned`). RED before the mapping change.

### Risks / deviation triggers
- **Basis symmetry:** both sides must be ranked with the *same* `captured_at` value,
  else a default-rank method would falsely order by mismatched bases. Pass one basis
  to both calls; do not pass a home-side `captured_at`.
- **No capture record for the active ref** (directly-activated via the content
  fallback): `_active_captured_at` returns `0.0`; for payload-derived providers this
  is irrelevant (basis ignored), for default-rank it yields a tie → bare `drift`.
  Acceptable — never raise.
- **Direction must not flip rotate/materialize meaning:** `home-newer`⇒rotate (pull
  the fresher home into the pool and activate it), `home-older`⇒materialize (push
  the fresher active into the stale home). Keep the labels glued to those fixes in
  the reasons.
- Keep `status` read-only and total — any unresolved case degrades to bare `drift`
  or the existing `undeterminable` (no readable home), never an error.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- Live: `agent accounts status --provider claude-code` shows the drifted homes now
  carrying `drift:home-newer` / `drift:home-older` (the 664 live run had two drifted
  browser homes), aligned homes unchanged — read-only.
- `drift_against_active` is the only place the comparison lives; `status_for_home`
  contains no `rotation_rank` call.

## Impl.Log

- Both slices RED→GREEN. Suite 189→194 (+5), lint clean.
- Decision in open space (existing test preserved): `test_status_drift_when_active_differs`
  activates an unresolvable ref (`deadbeef`) — under the new mapping its payload
  resolves to None ⇒ `drift_against_active` returns None ⇒ bare `drift`, which the
  existing assertion already expects. Left untouched (faithful to the "unorderable →
  bare drift" rule).
- No import cycle from `account_status_report → rotation`: `rotation` imports
  `auth_registry`/`auth_method`/`auth_method_registry`, none of which import
  `account_status_report`.
- Live acceptance partial: `agent accounts status --provider claude-code` ran
  read-only and the `aligned` path is intact, but every live home currently reads
  `aligned` (no drift on real data now), so the qualified labels are exercised by
  unit tests only, not live.
