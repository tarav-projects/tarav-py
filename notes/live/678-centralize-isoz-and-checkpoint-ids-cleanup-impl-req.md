# 678 — cleanup: centralize ISO-Z formatting + profile-check checkpoint ids

## Impl.Abstract

- **Scope (cleanup — repeated knowledge):** two same-dimension centralizations, both
  behavior-preserving, verifiable together.
  - **A. Finish the ISO-Z helper centralization** (started in 673). The
    `astimezone(UTC) → isoformat → "+00:00"→"Z"` formatting is hand-rolled in **five**
    places beyond `clock.iso_z`. They differ only in **sub-second precision**:
    microsecond-**stripping** (`forum/core.py:431`, matching `clock.iso_z`) vs
    microsecond-**keeping** (`agent/usage_registry.py:_iso_z`, `copilot/account_status.py:653`,
    `claude/account_status.py:1210`). Make precision a **parameter** on the one canonical
    helper and migrate every copy to it.
  - **B. Centralize the profile-check checkpoint ids.** `agent/profile_check.py` repeats
    the bare literals `"account_registered"` / `"home_exists"` / `"home_aligned"` across
    its checkpoint helpers, and the tests repeat them again. Name them once as module
    constants and reference the constants.
- **Decision:**
  - A: extend `clock.iso_z` to `iso_z(value, *, drop_micros: bool = True)` — default
    keeps today's strip behavior, so every existing `iso_z(x)` call is unchanged. The
    three microsecond-keeping copies call `iso_z(value, drop_micros=False)`; `forum`
    (strips) calls `iso_z(value)`. Delete `usage_registry._iso_z`. **Net behavior change:
    none** — each call site maps to the helper form matching its current output.
  - B: add `CHECKPOINT_ACCOUNT_REGISTERED` / `CHECKPOINT_HOME_EXISTS` /
    `CHECKPOINT_HOME_ALIGNED` constants in `profile_check.py`, use them in the checkpoint
    helpers, export them in `__all__`, and reference them from the tests.
- **Status:** COMPLETE.
- **Source context:** `hugentics-codebase-cleaner` scan after 675/676/677. 673 already
  made `clock` the ISO-Z home and **explicitly flagged** `usage_registry._iso_z` as a
  deferred follow-up (its microsecond difference blocked a silent fold then — the
  `drop_micros` parameter resolves it without changing behavior).
- **Out of scope (do NOT touch):**
  - **Unifying the precision policy** — do not "fix" the microsecond-keeping call sites to
    strip (or vice-versa). Preserve each site's current output exactly; this cleanup
    centralizes the *formatting mechanics*, not the precision decision.
  - Any other `clock` behavior, `utc_now_iso`, or timestamp semantics.
  - The checkpoint *logic*, reasons, or `profile_check` behavior — only the id literals.

## Impl.Index

### Block A: one ISO-Z formatter, precision as a parameter (`Hard.Evidence`)
- Canonical: `clock.iso_z(value)` = UTC, `microsecond=0`, isoformat, `Z` (`clock.py:6`).
- Hand-rolled copies: `forum/core.py:431` (strips — same as canonical);
  `usage_registry.py:136` `_iso_z` (keeps), `copilot/account_status.py:653` (keeps),
  `claude/account_status.py:1210` (keeps).
- Decision: `iso_z(value, *, drop_micros: bool = True)`; `drop_micros=True` reproduces the
  current strip, `False` reproduces the keep. Migrate all four copies to the matching
  form; drop the local `_iso_z`. `utc_now_iso` is unaffected (default `drop_micros=True`).

### Block B: named checkpoint ids (`Hard.Evidence`)
- `profile_check.py` uses the three id strings as bare literals at `:41/43/45` (account),
  `:51/53/54` (home_exists), `:61/69/72` (home_aligned). Tests key on the same literals.
- Decision: module constants for the three ids; the helpers and tests use them. The id
  *values* are unchanged (so any serialized/rendered output is identical). `ping-failed`
  in `workflows.py` is a different module's error_type — **out of scope**, leave it.

## Execution.Plan

Two behavior-preserving slices. Verification = the full suite (these helpers are covered
by `test_core_clock`, the usage/account tests, and `test_agent_profile_check`) + lint.
`No.Regression`: add only a focused `iso_z(drop_micros=False)` unit check; assert nothing
else new.

### Slice 1 — `iso_z(drop_micros=…)` + migrate the copies (Block A)
- Changes: add the `drop_micros` keyword to `clock.iso_z`; migrate `forum` →
  `iso_z(value)`, and `usage_registry` / `copilot` / `claude` → `iso_z(value,
  drop_micros=False)`; delete `usage_registry._iso_z`.
- Path: every timestamp these modules format.
- Observable result: identical output at every call site (strippers still strip, keepers
  still keep); no hand-rolled ISO-Z formatter remains outside `clock`.
- Check (RED→GREEN): add a `test_core_clock` case for `iso_z(aware_dt_with_micros,
  drop_micros=False)` → keeps microseconds, and the default → strips (RED before the
  keyword exists). Existing usage/account/forum tests stay green (behavior identical).

### Slice 2 — checkpoint-id constants (Block B)
- Changes: define the three constants in `profile_check.py`, use them in the checkpoint
  helpers, add to `__all__`; update `tests/test_agent_profile_check.py` to reference them.
- Path: `agent.profile_check()` result ids.
- Observable result: the emitted `CheckpointResult.id` values are byte-identical; the ids
  now have a single definition.
- Check (RED→GREEN): the existing `test_agent_profile_check` assertions (keyed on the id
  values) stay green; switch them to the constants so a future id rename can't drift the
  test. No new behavior test needed.

### Risks / deviation triggers
- **Micros misclassification:** if any migrated call site's output changes (a stripper
  made to keep or vice-versa), that is a regression — revert that site. The classification
  is fixed in Block A; honor it.
- **`iso_z` call fan-out:** `iso_z(x)` is used in ~8 places; the new keyword defaults to
  today's behavior, so those are untouched — do not add the keyword to them.
- **Scope guard (hard boundary):** do not unify precision policy, do not touch
  `workflows.py`'s `ping-failed`, do not change checkpoint logic. A change that reshapes
  behavior aborts the run (cleanup never broadens its own scope).

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- No `astimezone(...).isoformat().replace("+00:00", "Z")` formatter exists outside
  `clock.py`; `usage_registry._iso_z` is gone.
- The three checkpoint ids have one definition each in `profile_check.py`; emitted id
  values unchanged.
- Every migrated timestamp call site produces byte-identical output to before.

## Impl.Log

- Both slices done test-first (RED→GREEN). Suite 246→247 (+1 `iso_z(drop_micros=False)`
  clock case). Lint clean. **No deviations.**
- Slice 1: `clock.iso_z` grew `*, drop_micros: bool = True`. Migrated `forum/core.py` →
  `iso_z(parsed)` (dropped the now-unused `timezone` import); `usage_registry._iso_z`
  deleted, its one caller now `iso_z(recorded_at, drop_micros=False)`. `copilot` /
  `claude` `_datetime_to_iso` kept as thin wrappers whose bodies became
  `return iso_z(value, drop_micros=False)` — removes the hand-rolled formatter with zero
  caller churn (both have several call sites). No `astimezone(...).isoformat().replace`
  formatter remains outside `clock.py`.
- **Scope note (broader grep, held to plan):** `claude`/`codex` `_iso_from_epoch_seconds`
  and `sessions`/`extractors` millisecond formatters also contain
  `.isoformat().replace("+00:00","Z")`, but they are structurally different (epoch-built,
  or `timespec="milliseconds"`) — `iso_z(drop_micros=…)` cannot reproduce them. Left
  untouched per the Impl.Req's four-copy scope; no scope broadening.
- Slice 2: three `CHECKPOINT_*` constants added to `profile_check.py`, used in every
  checkpoint helper and exported in `__all__`. Test literals switched to the constants
  (values unchanged, so emitted ids are byte-identical).
