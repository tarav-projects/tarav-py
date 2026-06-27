# 663 — `agent accounts list` + activate-by-prefix

## Impl.Abstract

- **Scope:** Make the capture pool discoverable and `activate` usable by hand.
  - **`agent accounts list`** — show the captured `Auth.Ref`s (the `ref_id`s) for
    an `account/method`, ordered by capture recency, marking which is `active` and
    which is the rotation `head`. Read-only.
  - **`activate --ref <prefix>`** — accept a unique **prefix** of a `ref_id`
    (resolved against that account/method's pool); error if the prefix is
    ambiguous, error if it matches nothing. A full `ref_id` still works.
- **Status:** COMPLETE.
- **Source context:** Design discussion (this session). `activate` (req 662) takes
  a 64-char `ref_id`, but there is no way to *see* the available refs, so it is
  unusable on its own — you must hand-inspect `captures.jsonl`. `list` is the
  discovery half; prefix resolution removes the need to paste a full sha. Builds
  on 659/660/661/662.
- **Out of scope:** activate-by-index (rejected — positional/fragile; prefix is
  the chosen handle); the `status` drift qualification; any write beyond the
  existing `activate` pointer set.

## Impl.Index

### Block: list reads the existing pool — nothing new is stored
- Evidence: the readers already exist — `auth_registry.captures_for(provider,
  account, method)`, `record_ref_id(record)` (the ref backfill), `active_ref(...)`
  (`auth_registry.py:288,227,167`). Settings accounts/methods come from
  `load_settings`/`_accounts`. Rotation's head-of-line is
  `rotation.rotate(..., dry_run=True).new_active`.
- Decision: a pool row per **distinct `ref_id`** for an `account/method`, keeping
  its most recent capture `ts`, ordered **ts-desc (recency)** — so "second most
  recent" is row index 1. Each row carries: short ref (12), captured-at, and
  markers `active` (== `active_ref`) and `head` (what `rotate --dry-run` would
  pick). The `head` marker reuses `rotation` (registry-only); a pool with no
  rankable candidate simply has no `head`.
- Decision: scope mirrors `status`/`capture` — `--provider` optional (else all
  providers with an auth-method), `--account <id/method>` optional (else every
  declared `account/method` from settings, grouped). `--json` emits the rows.

### Block: a registry pool reader is the shared seam
- Decision: add `auth_registry.pool_for(provider, account, method) ->
  list[PoolEntry]` (or a list of dicts): distinct `ref_id`s with their latest
  `ts`, recency-ordered. Both `list` (display) and prefix resolution (matching)
  read it — one source of truth for "the refs that exist for this
  account/method". `list`'s `head` marker is layered on top via `rotation`.

### Block: activate resolves a ref prefix, erroring on ambiguity
- Current state (`Hard.Evidence`): `_cmd_agent_accounts_activate`
  (`commands.py:422`) validates `auth_data_for_ref(provider, account, method,
  args.ref)` and `set_active`s the literal `args.ref`.
- Decision: before validating, resolve `args.ref` as a **prefix** against
  `pool_for(provider, account, method)`'s `ref_id`s: exactly one match → use it;
  >1 match → `CliError` listing the colliding short refs; 0 matches → `CliError`
  ("no captured ref matches prefix"). A full `ref_id` is the trivial unique-prefix
  case. Resolution lives in `auth_registry` (`resolve_ref_prefix(...)`) so it is
  testable without the CLI.

## Execution.Plan

Ordering: the shared `pool_for` reader + `list` verb first (reaches an observable
endpoint fast and gives prefix resolution its data source), then prefix
resolution in `activate`. Each slice `RED.GREEN.Test.Suite`-driven, test-first.

### Slice 1 — `pool_for` reader + `agent accounts list` verb
- Changes: add `auth_registry.pool_for(provider, account, method)` (distinct
  `ref_id`s, latest `ts`, recency-ordered). Add `_cmd_agent_accounts_list` + a
  `list` subparser (`--provider?`, `--account?`, `--json`); text output prints
  per `account/method` the indexed rows with `active`/`head` markers; `--json`
  emits the structured rows. `head` via `rotation.rotate(dry_run=True)`.
- Path: `agent accounts list [--provider P] [--account id/method] [--json]`.
- Observable result: with two captured refs for an account/method (one active),
  `list` prints both newest-first, index 0/1, the active one marked `active`; an
  empty pool prints an empty/"no captures" line; `--json` returns the rows.
- Check (RED→GREEN): a new `tests/test_agent_accounts_list.py` — seed two captures
  (distinct refs, known order) + an active pointer; assert the recency order, the
  `active` marker on the right row, and the JSON shape (RED before the verb).
  Plus a registry unit test for `pool_for` (distinct refs, latest ts, order).

### Slice 2 — `activate --ref <prefix>` with ambiguity error
- Changes: add `auth_registry.resolve_ref_prefix(provider, account, method,
  prefix) -> str` (unique match → ref; ambiguous → `CliError` listing matches;
  none → `CliError`). `_cmd_agent_accounts_activate` resolves `args.ref` through it
  before `auth_data_for_ref`/`set_active`.
- Path: `agent accounts activate --ref <prefix>`.
- Observable result: a unique prefix activates the full ref; a full ref still
  works; a prefix matching two refs errors and names them; a prefix matching none
  errors.
- Check (RED→GREEN): registry unit tests for `resolve_ref_prefix` (unique /
  ambiguous-raises / none-raises / full-ref) + a handler test that
  `activate --ref <short-unique-prefix>` sets the expected active pointer and an
  ambiguous prefix raises `CliError`.

### Risks / deviation triggers
- `head` marker couples `list` to `rotation`. Keep it best-effort: if ranking
  yields no head (empty/unrankable pool), omit the marker rather than error — list
  is read-only and must never fail on a degenerate pool.
- Prefix ambiguity must consider only the **distinct** `ref_id`s of that
  account/method (not the whole provider), so the same short prefix under a
  different account never collides here.
- A very short prefix could match many; the ambiguity error is the intended,
  safe outcome — do not auto-pick the most recent.

### Acceptance signals
- Full suite green (`uv run pytest`), lint clean (`uv run ruff check src/ tests/`).
- Live: `agent accounts list --provider claude-code --account br/browser` prints
  the real pool newest-first with the active row marked; `agent accounts activate
  --provider claude-code --account br/browser --ref <short-prefix>` activates the
  intended ref; an ambiguous short prefix errors.
- `agent accounts list --help` and `activate --help` reflect the surfaces.

## Impl.Log

- Both slices RED→GREEN. Suite 178→182 (+4), lint clean.
- Decision in open space (semantics tightening): `activate` now resolves its
  `--ref` through `resolve_ref_prefix`, which reads `pool_for` (capture records).
  So activate requires the ref to be in the **discoverable pool** — you can only
  activate what `list` shows. This is stricter than 662, where
  `auth_data_for_ref` had a content-addressed fallback that let you activate a
  stored-but-uncaptured artifact. Updated `test_activate_sets_pointer` to capture
  first (faithful to real flow). The `auth_data_for_ref` fallback still serves
  read/materialize resolution; only activate's entry point tightened.
- Live verified: `list --provider claude-code --account br/browser` prints the
  pool newest-first with `(active head)` on the right row; prefix-`activate`
  resolves a unique prefix. (No genuinely ambiguous short prefix exists in that
  live pool — all first hex chars differ — so ambiguity is covered by unit test
  only.)
- Note: a stray live `activate --ref 0` during verification matched uniquely
  (only one ref began with `0`) and moved the active pointer; restored it to the
  head ref `22e51ee2aa9d` immediately after.
