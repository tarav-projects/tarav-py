# 656 — Migrate codex onto the new account model (capture/activate, read-only homes)

## Impl.Abstract

- **Goal:** bring **codex** to parity with claude on the new account model so `agent accounts status --provider codex` reports truthfully (`aligned`/`drift`/`error:unlisted-account`, never `undeterminable`), via the full **capture → activate** flow. **Read-only on homes** — no codex materialize.
- **Status:** complete. Codex migrated on the new model — `status --provider codex` reports truthfully (br homes `aligned`; mislabeled `jp/mm/tk` homes `error:unlisted-account`; no `undeterminable`). **Zero production code changed** (Slice 1 confirmed the generic stack already handles codex); the rest was data migration. Full suite: 201 passed.
- **Scope (in):**
  - re-point codex **profiles** to the `<account-id>/<method>` addressing (the only reason status currently reads `undeterminable`).
  - **capture** every codex home's live `Auth.Data` (archival, content-dedup), filed by real `Account.Identity`.
  - **activate** one artifact per codex account that has a live credential.
  - a **codex status behavior test** locking in that the generic new-model stack handles codex.
- **Scope (out):**
  - **codex materialize / any home write** — read-only on homes throughout (capture reads homes; activate writes only the registry).
  - re-logging mislabeled homes into their named accounts (that is a login/materialize task; this Impl.Req only makes status *report* the mismatch).
  - claude, copilot, monitor, and the legacy codex reconcile/promote cluster (deferred codex teardown).
- **Source context:** this session's claude migration (the template) + `654`/`655`. Conceptual home: `agentos-pkg` `Account.Management` (`Auth.Data.Capture`, `Auth.Data.Activation`, `Account.Identity`, `Unknown.Account`, `Auth.Data.Aligned`/`Drift`).

## Impl.Index

### Codex.Current.State

- codex `accounts.json` is already migrated (settings shape): accounts `br`/`jp`/`mm`/`tk`, each `auth_methods.file = {class: "auth-json"}`, identity carrying `provider_account_id`.
- codex `registry/active.json` is **empty** — codex was never captured/activated into the new registry.
- codex **profiles** still use old account refs (`["br"]`, no `/method`) → the status candidate gate finds no method → `undeterminable`. This is the sole blocker to status reading.
- `CodexAuthMethod` reads `auth.json` and extracts identity from the access_token `chatgpt_account_id` claim; it is registered in `auth_method_registry`. `resolve_account_by_identity` matches on `provider_account_id` (codex's identity field). All generic — no codex-specific status/capture/activate code needed.

### Homes.Hold.Br (the reality this migration must report, not hide)

- **observed:** all nine codex homes currently read identity `07de2ad9…` = account **`br`**, identical content `b27d9a90…`. The `jp`/`mm`/`tk`-named homes are mislabeled — they hold br's credential, not their named account's.
- consequence: only `br` has a live credential to capture/activate. `jp`/`mm`/`tk` accounts exist in settings but have no live home credential.
- the **correct** end state is honest reporting, not forced alignment: br homes → `aligned`; the mislabeled homes (candidate `jp/mm/tk`, holding br) → `error:unlisted-account`. Do **not** paper over this by adding br to every home's candidate set — the candidate is the profile's *intent*; the mismatch is real and surfacing it is the point.
- fixing the mislabeled homes (logging each into its account) is out of scope (a home write / login task).

### Capture.Activate.Generic

- capture is provider-agnostic: read home via `CodexAuthMethod` → `extract_identity` → `resolve_account_by_identity` (real account, e.g. br) → `store_artifact` (content-dedup) → `append_capture` (dedup on `account/method/artifact_id`). It files by **real identity**, never the home name. Identifiable orphans (no settings match) go to `Unknown.Account` (none expected here — all resolve to br).
- the method name is resolved by **class**: the captured class is `auth-json` (`CodexAuthMethod.name`); the account's matching method is `file`. (A small `auth_registry` helper `method_for_class(provider, account, class)` may be added if not present.)
- activate is `set_active(provider, account, method, artifact_id)` — a pure registry pointer move, no home write.
- capture-first safety does not apply here (no materialize); capture is purely additive/archival.

### Status.Reports.Truth

- after re-point + capture(br) + activate(br), `agent accounts status --provider codex` must show: br homes `aligned`; mislabeled homes `error:unlisted-account`; any non-br-but-known home `drift`; none `undeterminable`.
- this is `Auth.Data.Aligned`/`Auth.Data.Drift` + the candidate gate, identical to claude — the migration just supplies the data.

## Execution.Plan

Claude-template, codex data + one regression test. Read-only on homes throughout.

### Slice 1 — codex status behavior test (regression lock)
- **changes:** a behavior test that `build_status_report("codex")` works on the new model: codex settings fixture + a captured+activated codex `auth.json` home (via `CodexAuthMethod`) → `aligned`; a home whose `auth.json` carries a foreign identity → `error:unlisted-account`.
- **path exercised:** `account_status_report` → `auth_method_registry` → `CodexAuthMethod` → `auth_registry`.
- **observable result:** the codex fixtures produce `aligned` / `error:unlisted-account`.
- **check (RED→GREEN):** if it passes with no production change, that confirms codex needs only the data migration (expected). If it fails, fix the minimal surfaced gap (e.g. a missing `method_for_class` helper) — that is the RED→GREEN. Do not invent production code the test does not force.

### Slice 2 — re-point codex profiles (data)
- **changes:** rewrite each codex profile's `accounts` to `<account-id>/file` (per the profile's intended account; the multi-account default home keeps all four as `*/file`). Back up profiles first (alongside the existing migration backup).
- **observable result:** `agent accounts status --provider codex` no longer prints `undeterminable` — every home now reads and reports a real status.
- **check:** live status run; assert no `undeterminable` line.

### Slice 3 — capture + activate codex (data, read-only homes)
- **changes:** capture every codex home (generic capture path; dedups to br's single artifact given current reality), then activate br's artifact for `br/file`. `jp/mm/tk` get no active (no live credential) — leave them unset.
- **observable result:** codex `captures.jsonl` holds br's artifact; `active.json` = `{"br/file": <id>}`.
- **check:** live; inspect `registry/` for codex; `active_artifact_id("codex","br","file")` is set.

### Slice 4 — verify truthful status (live)
- **changes:** none beyond verification.
- **observable result:** `agent accounts status --provider codex`: br homes `aligned`; mislabeled `jp/mm/tk` homes `error:unlisted-account`; none `undeterminable`.
- **check:** live status run recorded in `Impl.Log`, with the per-home identity reality noted (all-br).

### Risks / deviation triggers
- **all-br reality** — if some homes are NOT br at execution time (a home re-logged-in since this Impl.Req was written), capture files them by their real identity and status reports accordingly; do not force candidates to match. Re-scan at Slice 3.
- **no live credential for jp/mm/tk** — expected; activate only accounts with a captured artifact. Not an error.
- **stay codex + read-only** — touch no home contents, no claude/copilot code, no codex reconcile/promote cluster. Capture reads; activate writes only the registry.
- **profile intent** — candidates encode the profile's intended account, not the credential currently present; the gate surfacing a mismatch is correct behavior.

### Acceptance signals
- `status --provider codex` reports real states (no `undeterminable`); br aligned; mislabeled homes flagged.
- homes are never written; codex registry has br captured + active.
- codex behavior test green; full suite green; no non-codex code touched.

## Impl.Log

- **Confirmed (Slice 1).** The codex status behavior test passed with **no production change** — the generic stack (`CodexAuthMethod` + `auth_method_registry` + `auth_registry` + `account_status_report`) already handles codex. No `method_for_class` helper was needed; the capture step resolved the method by class **inline** in the migration script (status goes candidate→method→class, so it never needed the reverse lookup). Kept production code untouched per `No.Gold.Plating`.
- **Reality confirmed live (`Homes.Hold.Br`).** All nine codex homes hold br's credential (`07de2ad9`, content `b27d9a90`); capture deduped to a single artifact; only `br/file` was activated. The mislabeled `jp/mm/tk` homes report `error:unlisted-account` — the correct, truthful outcome. Re-logging those homes into their named accounts is a home-write/login task, out of scope.
- **Live verification.** `status --provider codex`: `~/.codex`, `~/.codex-br`, managed `codex/br` → `aligned`; the six `jp/mm/tk` homes → `error:unlisted-account`; none `undeterminable`.
- **Data, not repo.** Profile re-point + capture/activate mutate `~/.agentos` (profiles backed up alongside the existing migration backup); the only repo change is `tests/test_codex_account_status_report.py`.
