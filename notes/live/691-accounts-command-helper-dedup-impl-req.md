# Accounts Command Helper Dedup - impl-req

## Impl.Abstract

- **scope:** collapse three repeated-knowledge patterns inside `agentos.agent.commands.accounts` into module-local helpers: `<account-id>/<method>` parsing, provider-set resolution, and short-ref truncation.
- **status:** implemented
- **source:** `hugentics-codebase-cleaner --AUTO` pass on the `agentos accounts` system.
- **current state:** `commands/accounts.py` repeats `args.account.partition("/")` + validation 4x with divergent `CliError` strings, repeats `(args.provider,) if args.provider is not None else providers_with_auth_methods()` 4x, and repeats the 12-char `[:12]` ref-shortening idiom ~10x (some with `(x or '-')` None-guards).
- **out of scope:** changing any `agentos accounts` CLI contract, argument names, output shape (human or JSON), error semantics beyond message-string unification, or touching the lifecycle primitives / other command modules.

## Impl.Index

### Accounts.AccountMethod.Parsing

- `<account-id>/<method>` splitting is one domain operation with one failure mode.
- the four call sites differ only in the command label embedded in the error.
- a single `_split_account_method(account, command_label)` returning `(account_id, method)` and raising a consistent `CliError` removes the duplication.
- the helper stays module-local; no shared utility layer is justified.

### Accounts.Provider.Resolution

- "the given provider, else every provider with an auth-method" is one repeated decision.
- a single `_resolve_providers(provider)` expresses it once for list/orphans/rotate/capture-global.
- `status` deliberately resolves against `_AGENT_ACCOUNT_MANAGEMENT_PROVIDER_CHOICES` instead and is left unchanged.

### Accounts.ShortRef.Formatting

- the 12-char short-ref is a repeated presentation convention.
- a single `_short(ref)` accepting `str | None` and rendering `-` for `None` unifies the bare `ref[:12]` and `(x or '-')[:12]` forms.
- purely presentational; JSON payloads keep full ids.

## Execution.Plan

### Slice 1 - Account/method parse helper

- add `_split_account_method(account, command_label)` and route the 4 call sites through it.
- preserve each site's effective error contract (a `CliError` on malformed input).
- check: `cd agentos-py && uv run pytest tests/test_agent_accounts_capture_activate.py tests/test_agent_accounts_rotate.py tests/test_agent_accounts_list.py tests/test_agent_accounts_materialize.py tests/test_codex_accounts_materialize.py`
- status: complete

### Slice 2 - Provider resolution + short-ref helpers

- add `_resolve_providers(provider)` and route list/orphans/rotate/capture-global through it.
- add `_short(ref)` and route the presentational `[:12]` sites through it.
- keep JSON output byte-identical; keep human output identical in substance.
- check: same focused account tests as Slice 1.
- status: complete

### Slice 3 - Verification

- run the full agent-accounts focused suite plus Ruff on the touched file.
- inspect the diff for no CLI/JSON contract drift.
- status: complete

## Acceptance.Signals

- `commands/accounts.py` has one account/method parser, one provider resolver, and one short-ref formatter.
- no `partition("/")` or `providers_with_auth_methods()` inline duplication remains in that file.
- human and JSON outputs for list/orphans/capture/activate/rotate/materialize/status are unchanged.
- focused account tests and Ruff pass.

## Deviation.Triggers

- stop if unifying error strings would change a tested error contract in a way beyond wording.
- stop if a helper makes a call site harder to read than the inline form.
- stop if the cleanup pulls in changes outside `commands/accounts.py`.

## Impl.Log

- (filled during execution)
