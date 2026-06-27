# 664 — auth-lifecycle primitives (activate, materialize) + `rotate --materialize`

## Impl.Abstract

- **Scope:** Make all four `Auth.Data` lifecycle operations standalone primitives,
  then add a `--materialize` reconcile flag to `rotate`.
  - **Principle (FUNDAMENTAL):** capture / activate / materialize / rotate each get
    a clean primitive module under `src/agentos/agent/`; the CLI handlers in
    `commands.py` are thin consumers (parse args → call primitive → format output).
    No lifecycle logic lives in `commands.py`.
  - **Extract `activation.py`** from inline `_cmd_agent_accounts_activate`.
  - **Extract `materialization.py`** from inline `_materialize_account`, and add a
    fleet `materialize_all(provider)` (the reconciler).
  - **`rotate --materialize`** — after the rotate pass, push each home's
    account/method active ref into stale homes (capture-first), so one command runs
    the maintenance loop capture → rotate → materialize.
- **Status:** READY.
- **Source context:** Design discussion (this session). `capture.py` (660) and
  `rotation.py` (661) already follow the primitive shape; activate (662/663) and
  materialize still have their logic trapped in CLI handlers. Builds on
  659–663. Memory: `project_auth_lifecycle_primitives`.
- **Out of scope:** changing `activate`/`materialize` *behavior* (the extractions
  are behavior-preserving — see the one allowed addition in the materialize block);
  the `status` drift qualification (`home-newer`/`home-older`); any new CLI verbs
  (`--materialize` is a flag on the existing `rotate`, mirroring `--global` on
  `capture`).

## Impl.Index

### Block: activate is a primitive; the handler consumes it
- Current state (`Hard.Evidence`): `_cmd_agent_accounts_activate`
  (`commands.py:478`) inlines the whole flow: parse `account/method`, then
  `R.resolve_ref_prefix` → `R.auth_data_for_ref` (validate, `CliError` if missing)
  → `R.set_active`, then print/JSON.
- Decision: add `activation.py` with
  `activate(provider, account, method, ref_prefix) -> ActivateResult`. It resolves
  the prefix, validates the payload exists (raising `CliError` exactly as today),
  sets the active pointer, and returns `ActivateResult(provider, account, method,
  ref_id)`. The handler shrinks to: split `account/method`, call `activate`, print.
  Behavior-preserving — same errors, same active-pointer effect.

### Block: materialize is a primitive; single-home and fleet both live there
- Current state (`Hard.Evidence`): `_materialize_account` (`commands.py:498`)
  inlines: resolve `auth_method`, read `active_ref` + `auth_data_for_ref` (the
  payload to write), then **capture-first** the live home
  (`Capture.Over.Materialization`: `store_artifact` + `append_capture` if a new
  identifiable ref), then `auth_method.materialize(payload, home)` unless
  `args.check`. The CLI verb (`commands.py:873`) passes `--provider/--home/--account
  /--check/--force/--json`.
- Decision: add `materialization.py` with
  `materialize_account(provider, account, method, home, *, check=False) ->
  MaterializeResult`. It carries the existing body (capture-first, then write unless
  `check`). **One allowed behavior addition (the stale gate):** capture-first
  already reads the home's live `Auth.Data`; compare its `ref_id` to the active ref
  — if equal, the home is already aligned, so **skip the write** and report
  `status="aligned"`. This is what makes the fleet reconciler stale-only and is a
  strict improvement for the single-home path too (no needless rewrite of an
  identical credential). `MaterializeResult(provider, account, method, home,
  active_ref, captured_ref, status)` where `status ∈ {"materialized", "aligned",
  "check", "skipped"}`.
- Decision: add `materialize_all(provider, *, check=False) ->
  list[MaterializeResult]`. It mirrors `capture_all_homes`
  (`capture.py:63`): loop `collect_home_targets(provider)`, and for **each home**
  resolve which listed `account/method` it belongs to by reading the home (the same
  read `status`/`capture` use), then call `materialize_account`. Homes that read as
  empty / orphan / unlisted have no safe target → `status="skipped"` (no write).
  Stale-only falls out of the per-home `aligned` gate.

### Block: home → account/method resolution for the fleet reconciler
- Evidence: `collect_home_targets` (`account_status_report.py:30`) yields
  `HomeTarget(home, provider, candidates)` where candidates are
  `"<account-id>/<method>"` addresses from profiles. `capture_home`
  (`capture.py:31`) already resolves the *content's* account/method via
  `R.capture_target(provider, identity, auth_method.name)`.
- Decision: for `materialize_all`, a home's target account/method is the one its
  **current content** resolves to among the home's listed candidates — read the
  home, extract identity, resolve account; if the resolved `account/method` is a
  listed candidate, materialize that account's active ref into the home; otherwise
  skip. This keeps materialize symmetric with capture (both key off what the home
  actually holds) and never writes a home whose owner is ambiguous/unknown.

### Block: `--materialize` is a reconcile flag on rotate (all swept homes)
- Current state (`Hard.Evidence`): `_cmd_agent_accounts_rotate`
  (`commands.py:423`) is fleet-wide and home-less: capture-first
  (`capture_all_homes`) per swept provider, then `rotate`/`rotate_all`; honors
  `--provider/--account/--no-capture/--dry-run/--json`.
- Decision: add `--materialize` (default off). After the rotate pass, for each
  swept provider call `materialize_all(provider, check=dry_run)` and fold the
  results into output. `--dry-run` maps to `check=True` (no home writes), so
  `rotate --materialize --dry-run` is a full "what would the maintenance loop do?"
  preview.
- Decision (reconcile scope — **all swept**, not only-rotated): `--materialize`
  syncs *every* eligible home of the swept providers to its account/method's
  current active, **regardless of whether rotate moved that pointer**. Rationale: a
  home can drift without any rotation; `rotate --materialize` is a reconciler, not a
  "propagate this one change" hook. The narrower only-rotated reading is rejected as
  surprising (it would leave known-stale homes untouched whenever the head didn't
  move).

## Execution.Plan

Ordering: behavior-preserving extractions first (reach green fast, no new surface),
then the new fleet primitive, then the flag that consumes it. Each slice
`RED.GREEN.Test.Suite`-driven, test-first. `No.Legacy.Allowed`: after each
extraction the inline body is gone, the handler only consumes the primitive.

### Slice 1 — extract `activation.py`
- Changes: new `activation.py` (`activate(provider, account, method, ref_prefix) ->
  ActivateResult`). Rewrite `_cmd_agent_accounts_activate` to call it.
- Path: `agent accounts activate --provider P --account a/m --ref <prefix>`.
- Observable result: identical to today — unique prefix activates, ambiguous/none
  raises `CliError`, the active pointer is set.
- Check (RED→GREEN): a registry/primitive test `test_agent_activation.py` —
  `activate` sets the expected active ref for a unique prefix (RED before the module
  exists), and raises `CliError` on ambiguous/none. The existing
  `tests/test_agent_accounts_capture_activate.py` activate tests must stay green
  unchanged (proves the handler extraction is behavior-preserving).

### Slice 2 — extract `materialization.py` (`materialize_account`, stale gate)
- Changes: new `materialization.py` (`MaterializeResult`, `materialize_account`).
  Rewrite `_materialize_account` to call it and format `status`.
- Path: `agent accounts materialize --provider P --home H --account a/m [--check]`.
- Observable result: a stale home is rewritten (`status="materialized"`); a home
  already holding the active ref is left untouched with `status="aligned"`; capture-
  first still archives the live home; `--check` still writes nothing.
- Check (RED→GREEN): `test_agent_materialization.py` — `materialize_account` writes
  the active payload into a stale home and returns `materialized`; against a home
  that already holds the active ref it returns `aligned` and does **not** rewrite
  (RED first — today's inline path always writes). Existing
  `test_agent_accounts_materialize.py` / `test_codex_accounts_materialize.py` stay
  green (adjust only if they asserted an unconditional rewrite of an already-active
  home — that is the intended `aligned` change, update faithfully).

### Slice 3 — `materialize_all` fleet reconciler
- Changes: add `materialize_all(provider, *, check=False)` to `materialization.py`:
  loop `collect_home_targets`, resolve each home's listed `account/method` from its
  content, `materialize_account` it (stale-only via the gate), skip
  empty/orphan/unlisted homes.
- Path: primitive only (no CLI yet) — exercised directly in test.
- Observable result: across two profile homes (one stale, one already aligned) for
  the same account, `materialize_all` rewrites the stale one (`materialized`) and
  reports the other `aligned`; an orphan/unlisted home is `skipped`.
- Check (RED→GREEN): extend `test_agent_materialization.py` — seed profiles with
  two homes + a captured/active ref; assert the per-home statuses and that only the
  stale home's file changed.

### Slice 4 — `rotate --materialize` (+ `--dry-run` → check)
- Changes: add `--materialize` to the rotate subparser; in
  `_cmd_agent_accounts_rotate`, after the rotate pass, when set, call
  `materialize_all(provider, check=dry_run)` per swept provider and add a
  materialized section to text + JSON output.
- Path: `agent accounts rotate [--provider P] --materialize [--dry-run]`.
- Observable result: with a stale home and a fresher captured ref, `rotate
  --materialize` rotates the active to the head **and** writes that ref into the
  stale home; `--dry-run` reports both intentions and writes nothing.
- Check (RED→GREEN): `test_agent_accounts_rotate.py` (extend) — a handler test that
  `rotate --materialize` leaves the stale home holding the new active ref (RED:
  flag/wiring absent), and that `--dry-run` writes neither pointer nor home.

### Risks / deviation triggers
- **Home→account/method resolution ambiguity:** if a home's candidate set has
  multiple accounts and the home is empty, there is no content to resolve from —
  treat as `skipped`, never guess. Only materialize what the home's current content
  identifies as a listed account.
- **`--force` semantics:** the materialize CLI has `--force` (`commands.py:899`).
  Carry whatever it does today through the extraction unchanged; do not extend it to
  the fleet path in this req (fleet skips ambiguous homes rather than forcing).
- **Capture-first ordering must survive extraction:** `materialize_account` must
  still archive the live home *before* writing, so a soon-to-be-overwritten
  credential is never lost. The stale gate reads that same live data — do not write
  before capturing.
- **Behavior-preserving claim:** slices 1–2 must not change observable
  activate/materialize behavior except the explicit `aligned` gate. If an existing
  test encodes the old always-rewrite behavior, that is the one intended update;
  anything else is a deviation to surface.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `activation.py` and `materialization.py` exist; `_cmd_agent_accounts_activate`
  and `_materialize_account` contain no lifecycle logic — only arg-parsing, a
  primitive call, and output formatting.
- Live: `agent accounts rotate --provider claude-code --materialize --dry-run`
  previews rotate + per-home materialize intentions and writes nothing; a real
  `--materialize` run leaves the relevant home holding the active ref. (Use
  `--dry-run` for any live check first — prior session moved a live pointer by
  accident.)
- `agent accounts rotate --help` shows `--materialize`.

## Impl.Log

- (executer fills in)
