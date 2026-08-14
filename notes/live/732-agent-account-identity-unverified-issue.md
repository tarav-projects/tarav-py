# Agent monitor reports usage without verifying whose account it is - issue

## Issue.Abstract

- **symptom:** `tarav agent accounts monitor` reports per-account usage with
  `fetched_identity: null` and `identity_match: "unknown"` for every claude-code target. A home that
  reads the *wrong* account's credential produces plausible usage numbers instead of an error.
- **status:** open
- **found:** 2026-08-13, during the tarav home migration (note 532). Three claude-code homes moved
  from `~/.agentos/agent/homes/...` to `~/.tarav/agent/homes/...`; `br` silently reported `jp`'s
  usage and the monitor reported `ok`.
- **severity:** the monitor is the surface used to decide which account to spend. Attributing one
  account's consumption to another is a wrong answer presented as a right one.

## Repro (as observed)

The credential-borrowing bug that triggered it is fixed (note 532 — the cross-home generic Keychain
service was removed from `claude_keychain_service_names`). The *detection* gap is not. To reproduce
the gap without reintroducing the bug: point a profile's home at a directory whose Keychain entry
belongs to a different account, then

```
tarav agent accounts monitor --once --json
```

Observed during the incident, for all three claude-code targets:

```
account_status.fetched_identity  = null
account_status.identity_match    = "unknown"
account_status.usage_status      = "ok"
status                           = "ok"
```

Two targets returned byte-identical rows (`Burst 56% / Weekly 16%`) while naming different accounts.
Nothing in the frame flagged it. It was caught by a human noticing the duplicate numbers.

## Root.Cause

- `agent/account_status_report.py:status_for_home` resolves identity via
  `read_home_auth(provider, home)` -> `extract_identity`. When the auth read returns `None` the entry
  is emitted as `status="undeterminable"`, and the **usage lane proceeds independently**.
- the usage fetch does not consult the identity result. `usage_status: "ok"` and the monitor target
  `status: "ok"` are computed from whether the fetch succeeded, not from whether the fetched usage
  belongs to the configured account.
- so the two lanes disagree silently: identity says "I cannot tell whose home this is", usage says
  "here are the numbers", and the frame renders the numbers under the configured account's label.
- `claude-code` is the exposed provider because its Auth.Data lives in the macOS Keychain keyed by
  home path, so it is the one whose identity read can fail while the provider CLI still runs and
  reports usage.

## Expected

- when identity cannot be established, usage must not be attributed. The target should render as
  unattributed/degraded rather than as that account's numbers.
- when identity *is* established and does not match the configured account, that is an error
  (`error:unlisted-account` already exists for this case in the status lane) and must propagate to
  the monitor frame instead of being confined to `accounts status`.
- `identity_match: "unknown"` should be visible in the monitor surface, not only in the JSON.

## Notes

- `codex` targets carry `identity_match: "verified"`, so the verification path works where auth is
  file-based in the home. The gap is the *coupling* between the identity lane and the usage lane,
  not identity resolution itself.
- after the note-532 fix the three homes read `[aligned]` with correct accounts, so this issue is
  currently latent rather than active.
- related: `agent/account_status_report.py`, `agent/auth_method_registry.py:read_home_auth`,
  `agent/providers/claude_code/keychain.py`.
