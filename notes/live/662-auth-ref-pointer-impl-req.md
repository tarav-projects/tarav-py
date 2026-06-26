# 662 — Auth.Ref: the activation pointer is a method-defined ref_id

## Impl.Abstract

- **Scope:** Re-semanticize the registry's activation pointer from "artifact id"
  to **`ref_id`** — a method-defined unique reference to a captured credential.
  Add an abstract `AuthMethod.ref_id(auth_data) -> str` seam (codex/claude return
  `content_id`, so `ref_id == artifact_id` as stored today). The **artifact blob
  stays the secret store** (content-addressed, unchanged); the capture record
  **joins `ref_id → artifact_id`**. `active.json` keys by `ref_id`;
  `activate`/`rotate`/`materialize`/`status` follow the rename.
- **Status:** COMPLETE.
- **Source context:** Design discussion (this session). Motive: `activate
  --artifact <sha>` hardwired the artifact-store model into the public surface and
  does not generalize to a method that defines its credential reference
  differently. Builds on 659/660/661. Index grounding: `Auth.Ref` (the reference
  the registry activates), `Active.Auth.Data`, `Auth.Data.Artifact`,
  `Auth.Data.Activation`.
- **Out of scope:** truly artifact-less methods (user confirmed: even an
  externally-stored secret is pulled into the artifact store — artifacts remain
  the secret store); the `status` drift qualification (`home-newer`/`home-older`),
  a separate follow-up; the session-package "artifact" usages (a different,
  unrelated concept).

## Impl.Index

### Block: Auth.Ref is the activation pointer; ref_id is method-defined
- Evidence (user, this session): "we should have some id we can use as pointer.
  Each auth-method can define one, it is free, but it needs to be unique." And:
  "there is no default — it is a per-auth-method stuff; it just needs to be a
  unique identifier." And: "artifacts are not how we define Auth.Ref and Identity."
- Decision: add **abstract** `AuthMethod.ref_id(auth_data) -> str` — every method
  must define it; uniqueness per credential-version is the method's contract;
  there is **no inherited default**. `CodexAuthMethod` and `ClaudeAuthMethod`
  return `auth_data.content_id()`, so `ref_id == content_id == today's
  artifact_id` ⇒ **no live `active.json`/`captures.jsonl` migration**.
- Decision: the **artifact store is unchanged** — `store_artifact` stays
  content-addressed (the secret store). The pointer the registry activates is the
  `ref_id`; the artifact is one resolution of it.

### Block: the capture record joins ref_id → artifact_id
- Current state (`Hard.Evidence`): `auth_registry.append_capture` already records
  `artifact_id: str | None` (`auth_registry.py:199`); `active.json` maps
  `account/method → artifact_id` (`:266`, `:273`); `is_captured` dedups on
  `(account, method, artifact_id)` (`:216`).
- Decision: the capture record gains `ref_id` (always present) beside
  `artifact_id` (the content-addressed storage key, nullable). `active.json` keys
  by `ref_id`. Dedup (`is_captured`) keys by `ref_id` (the credential-version
  identity). Add a resolver `auth_data_for_ref(provider, account, method, ref_id)
  -> AuthData | None` (find the capture record with that `ref_id`, read its
  `artifact_id` blob) — the single place that turns a pointer back into a payload.
- Decision: rename `active_artifact_id → active_ref` (`No.Legacy.Allowed`),
  returning the `ref_id`.

### Block: every consumer follows the pointer rename
- Current state: `rotation.py` keys candidates and `set_active` by `artifact_id`
  (`:46,55,69`); `account_status_report` compares `active == auth.content_id()`
  (`account_status_report.py:76`); `_materialize_account` reads
  `read_artifact(active_id)` (`commands.py:454-459`); `activate` takes `--artifact`
  and validates a blob exists (`commands.py:429-431,773`); capture/rotate output
  print `artifact_id` (`commands.py:319,326,348,360,...`).
- Decision: rotation ranks by `ref_id` (reads each candidate's payload via the
  capture record's `artifact_id`), `set_active`s a `ref_id`. `status` compares
  `active_ref == method.ref_id(home_auth)` (no artifact read — a pure ref compare;
  the correct generalization of today's content compare). `materialize` resolves
  the active `ref_id` via `auth_data_for_ref`. `activate` becomes `--ref`. Output
  vocabulary shifts `artifact_id → ref_id` where the value is the pointer.

## Execution.Plan

Ordering: the seam first (nothing consumes it yet), then the registry/capture +
rotation re-point end-to-end, then the CLI/status/materialize surface. Each slice
is `RED.GREEN.Test.Suite`-driven, test-first. Because `ref_id == content_id` for
both providers, existing behavior is preserved; field/flag **names** change, so
expect to update tests asserting the old `artifact_id`/`--artifact` vocabulary
(`No.Legacy.Allowed`, not regression slop).

### Slice 1 — `AuthMethod.ref_id` seam (abstract) + provider impls
- Changes: add abstract `ref_id(auth_data) -> str` to `AuthMethod`
  (`auth_method.py`); implement on `CodexAuthMethod` and `ClaudeAuthMethod`
  returning `auth_data.content_id()`.
- Path: the provider seam.
- Observable result: `CodexAuthMethod().ref_id(auth) == auth.content_id()` and
  same for claude; `AuthMethod` cannot be instantiated without it (abstract).
- Check (RED→GREEN): unit test asserting `ref_id == content_id` for both
  providers (RED before the methods exist).

### Slice 2 — registry + capture + rotation re-point to ref_id (end-to-end)
- Changes: `append_capture` records `ref_id`; `is_captured` keys by `ref_id`;
  rename `active_artifact_id → active_ref`; `set_active` stores a `ref_id`; add
  `auth_data_for_ref(...)`. `capture.capture_home` computes `ref_id =
  auth_method.ref_id(auth)` and records it; `CaptureResult` carries `ref_id`
  (plus the storage `artifact_id`). `rotation.rotate` keys candidates by `ref_id`
  and `set_active`s a `ref_id` (reading payloads through the record's
  `artifact_id`). Update the `auth_registry` module docstring (`:6`).
- Path: capture → rotate → `active.json` holds a `ref_id`.
- Observable result: a capture writes a record carrying `ref_id`; `rotate`
  activates a `ref_id`; `active_ref` returns it; `auth_data_for_ref` round-trips a
  `ref_id` back to its `AuthData`.
- Check (RED→GREEN): the rotation + capture suites pass under the new vocabulary
  (update assertions from `artifact_id`); a new registry test for
  `auth_data_for_ref` round-trip and `active_ref` keying.

### Slice 3 — CLI `--ref`, status compare, materialize resolve (end-to-end)
- Changes: `activate` parser `--artifact → --ref`; `_cmd_agent_accounts_activate`
  validates the `ref_id` is known (a capture exists / resolves) and `set_active`s
  it. `_materialize_account` reads the active payload via `active_ref` +
  `auth_data_for_ref`. `account_status_report.status_for_home` compares
  `active_ref == method.ref_id(auth)`. Capture/rotate/materialize output and JSON
  keys: `artifact_id → ref_id` where it is the pointer.
- Path: `agent accounts activate --ref <id>`; `status`; `materialize`.
- Observable result: `activate --ref <ref>` sets active; `status` still reports
  `aligned`/`drift` correctly; `materialize` writes the active credential.
- Check (RED→GREEN): handler test for `activate --ref` (and that a malformed/
  unknown ref errors); status aligned/drift tests pass under ref comparison;
  materialize test resolves the active ref. Update existing tests using
  `--artifact`/`active_artifact_id`/`active_artifact_id` JSON keys.

### Risks / deviation triggers
- Naming collision: the capture record already has an `auth_ref` field (the
  `AccountIdentity` summary — identity, not the pointer). Keep them distinct:
  `auth_ref` = identity block, **`ref_id`** = the pointer. Do not merge.
- `is_captured` re-keying to `ref_id`: confirm the materialize capture-first path
  (`commands.py:469`) and global capture still dedup correctly (ref==content now,
  so behavior is unchanged; the change is conceptual).
- A future method with `ref_id != content_id` would make `read_artifact(ref)`
  wrong — that is exactly why `auth_data_for_ref` (the join) exists; ensure no
  consumer shortcuts by passing a `ref_id` straight to `read_artifact`.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- Live: `agent accounts status` unchanged (still aligned/drift as before);
  `agent accounts activate --ref <id>` works; `agent accounts rotate --dry-run`
  unchanged; `active.json` not rewritten (values already valid `ref_id`s).
- `agent accounts activate --help` shows `--ref`, not `--artifact`.

## Impl.Log

- All 3 slices RED→GREEN. Suite 178 passing, lint clean.
- Deviation (plan was wrong): the plan claimed "no `captures.jsonl` migration"
  because `ref_id == content_id`. True for *values*, but **old capture records
  have no `ref_id` field at all** — written before this change. Rotation (which
  now keys candidates on `ref_id`) found nothing → live codex `jp/mm/tk` showed
  `skipped`. Fix: read-time backfill `auth_registry.record_ref_id(record) =
  record.ref_id or record.artifact_id` (correct, since old ref==content==
  artifact), applied in `is_captured`, `auth_data_for_ref`, and rotation candidate
  enumeration. Genuinely no on-disk migration. Caught by the live
  `rotate --dry-run` acceptance check, not the unit suite.
- Decision in open space: `auth_data_for_ref` falls back to
  `read_artifact(ref_id)` when no capture record joins the ref (a directly-
  activated artifact with no capture row). Safe because for artifact-backed
  methods the `ref_id` is the content-addressed storage key; a method whose
  `ref_id != content_id` would require the capture-record join and resolve to None.
- Minor ordering: the `status` ref-compare and `materialize` ref-resolve (nominal
  Slice 3 logic) landed in Slice 2 because the `active_artifact_id → active_ref`
  rename forced those call sites at once; kept the suite green per slice.
- Live verified: `activate --help` shows `--ref`; `status` unchanged; `rotate
  --dry-run` reports 0 changes with no `skipped` after the backfill. `active.json`
  not rewritten.
