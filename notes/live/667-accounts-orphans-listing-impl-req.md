# 667 — `agent accounts orphans` (read-only listing for manual adoption)

## Impl.Abstract

- **Scope:** surface the `_unknown` bucket so an agent/human can perform adoption
  **manually** (edit `accounts.json` + point `active.json`). No adoption mechanics
  — just visibility.
  - **`agent accounts orphans [--provider] [--json]`** — read-only. Lists the
    captured orphans (identifiable credentials filed under `UNKNOWN_ACCOUNT`),
    **grouped by identity** (each distinct identity = one candidate account to
    declare). Per group: the identity (provider_account_id / email / label), the
    `auth_class`, and the captured `ref_id`(s) newest-first with their `ts`.
  - **Text mode** = factual summary, **no secret material**.
  - **`--json`** = the adopter's full worksheet: the same structure **plus the
    complete `Auth.Data` payload** for each ref (read from the artifact). This is
    the deliberate "dump everything" surface — the agent consumes it and writes the
    two files itself.
- **Status:** COMPLETE.
- **Source context:** design discussion (this session). Decided: adoption stays a
  manual edit (rare, judgment-heavy); the system's only job is to make orphans
  visible with everything an adopter needs. The data already exists
  (`auth_registry.orphan_captures`, `auth_registry.py:270`) with no surface on it.
  Relates to the `Unknown.Account` design (req 659) and `set_active`'s
  "adopt the orphan first" error (`auth_registry.py:343`).
- **Out of scope:** any `adopt` primitive/command or settings/registry write; the
  `status` report (explicitly left clean — it reports registered accounts only); a
  re-file of orphan captures. Read-only end to end.

## Impl.Index

### Block: orphans grouped by identity is the registry reader
- Current state (`Hard.Evidence`): `orphan_captures(provider)`
  (`auth_registry.py:270`) returns the raw `captures.jsonl` records whose
  `account == UNKNOWN_ACCOUNT`. Each record carries `auth_ref` (an
  `AccountIdentity.summary()` → `provider_account_id`/`email`/`label`/`raw`,
  `account_status.py:36`), `class` (the `auth_class` = method axis), `ref_id`,
  `artifact_id`, `ts`. `record_ref_id` backfills the ref. `read_artifact(provider,
  artifact_id)` resolves a payload.
- Decision: add `auth_registry.orphan_groups(provider) -> list[dict]`. Group the
  orphan records **by identity anchor** (`auth_ref.provider_account_id`); records
  with no anchor fall into a single `null`-identity group (still listed, refs
  deduped). Each group:
  `{"identity": {...auth_ref summary...}, "auth_class": <class>, "refs":
  [{"ref_id", "artifact_id", "ts"} …newest-first, distinct ref_id…],
  "last_seen": <ts>}`. Grouping/dedup/recency live here (the reader), so the
  command is a pure formatter — consistent with "CLI is just a consumer".
- Why group by identity (not by ref): orphans all share `method = auth_class` in
  the bucket, so a ref-pool view would merge distinct people. The identity anchor
  is exactly the decision the adopter makes ("this identity becomes account X").

### Block: the command formats; `--json` dumps full Auth.Data
- Current state (`Hard.Evidence`): `_cmd_agent_accounts_list`
  (`commands.py:368`) is the shape to mirror — `--provider?` (else
  `providers_with_auth_methods()`), `--json` via `format_json_output`, a text
  branch. No `--account` here (orphans are not account-scoped).
- Decision: `_cmd_agent_accounts_orphans` iterates providers, calls
  `orphan_groups`, and renders:
  - **text:** per provider, per orphan group — identity line
    (`provider_account_id` + email/label if present), `auth_class`, and each
    `ref_id[:12]` + `ts`. An empty provider prints "(no orphans)". **No payload.**
  - **`--json`:** `{"command", "providers", "orphans": [ {provider, identity,
    auth_class, refs:[{ref_id, artifact_id, ts, auth_data: <full payload>}]} ]}`
    where `auth_data` is `R.read_artifact(provider, artifact_id).payload`. The
    secret-dump decision lives in the command (presentation), gated to `--json`.
- Security note (conscious surface): `--json` intentionally emits raw `Auth.Data`
  (tokens/secrets). These are the user's own local registry artifacts (mode 600);
  the dump is the adoption interface. The **text default stays secret-free** so
  casual/observable use never prints credentials.

## Execution.Plan

Ordering: the registry reader first (unit-testable, the data source), then the
command that formats it (observable endpoint). Each slice `RED.GREEN.Test.Suite`,
test-first.

### Slice 1 — `auth_registry.orphan_groups`
- Changes: add `orphan_groups(provider)` (group by identity anchor, distinct refs
  newest-first, `last_seen`). Export it.
- Path: registry read over `orphan_captures` / `record_ref_id`.
- Observable result: two orphan captures of the same identity (two refs) collapse
  to one group with both refs newest-first; two distinct identities yield two
  groups; an anchorless orphan lands in the `null`-identity group.
- Check (RED→GREEN): new `tests/test_agent_orphans.py` — seed `_unknown` capture
  records (via `append_capture` with `account=UNKNOWN_ACCOUNT`) for two identities
  with differing `ts`; assert group count, identity keys, per-group ref order
  (recency), and `last_seen`. RED before the function exists.

### Slice 2 — `agent accounts orphans` command (+ `--json` payload dump)
- Changes: add `_cmd_agent_accounts_orphans` + an `orphans` subparser
  (`--provider?`, `--json`). Text = secret-free summary; `--json` attaches each
  ref's full `Auth.Data` payload.
- Path: `agent accounts orphans [--provider P] [--json]`.
- Observable result: with one orphan stored, text prints its identity + class +
  ref (no token); `--json` returns the group with `refs[].auth_data` equal to the
  stored payload. With no orphans, text prints "(no orphans)" per provider and
  `--json` returns an empty `orphans` list.
- Check (RED→GREEN): `tests/test_agent_orphans.py` (extend) — a handler test
  capturing stdout: assert the text body names the identity and ref but **not** the
  secret value; assert the `--json` body carries the full `auth_data` payload. RED
  before the handler exists.

### Risks / deviation triggers
- **Secret leakage in text:** the text branch must never print `auth_data` / raw
  token fields — only identity, class, ref, ts. If a faithful summary seems to need
  more, stop — that is a scope/security deviation.
- **Anchorless orphans:** identity may be `None` (unreadable identity still filed
  under `_unknown`). Do not drop these — group under `null` and still list refs.
  Never raise on a degenerate orphan record.
- **No write path:** this req must not call `set_active`, `store_artifact`,
  `append_capture`, or touch settings. Any temptation to "help" by re-filing is a
  hard scope boundary — adoption stays manual.
- **`--json` payload resolution:** a ref whose artifact is missing
  (`read_artifact` → None) should still list, with `auth_data: null` — never error.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- `orphan_groups` is the only place grouping/dedup happens;
  `_cmd_agent_accounts_orphans` is a pure formatter.
- Live: `agent accounts orphans` (text) lists any real `_unknown` identities
  secret-free; `agent accounts orphans --json` includes the full `Auth.Data`. (If
  no live orphans exist, both run cleanly and report empty.)
- `agent accounts orphans --help` reflects the surface.

## Impl.Log

- Both slices RED→GREEN. Suite 194→199 (+5), lint clean.
- Decision in open space (no secret read in text mode): the handler builds the
  secret-free base groups once; it only calls `read_artifact` (resolving the secret
  payload) inside the `--json` branch. So text mode never even touches the artifact
  blobs — secrets are read solely for the worksheet dump.
- Live acceptance: `agent accounts orphans` (text) and `--help` run clean; no live
  orphans exist right now, so both providers print "(no orphans)" — the populated
  path (identity + ref secret-free; `--json` full `Auth.Data`) is covered by unit
  tests only.
