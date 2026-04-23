---
title: Account Limit Model Design
date: 2026-04-10
status: draft
---

# Account Limit Model Design

## Goal

Promote account limits into a first-class domain concept for `agentos chat accounts stats`, instead of treating limits as anonymous usage payload rows identified only by display labels such as `Burst` and `Weekly`.

This is motivated by the new `accounts_usage_total` aggregate, which needs to target one specific kind of account limit across selected instances.

## Accepted Design Direction

- `Account` has many `Limit`s.
- `Limit` is a first-class modeled object in code and in normalized payloads.
- A `Limit` has:
  - `limit_class`
  - `limit_name`
  - `limit_label`
  - class-specific normalized data
  - optional provider-specific raw details
- Not every limit has usage and time axes.
- One concrete limit class exists now:
  - `usage_over_time`
- `usage_over_time` limits provide the normalized fields needed for:
  - usage progression
  - elapsed time progression
  - aggregate pressure computation

## Core Domain Framing

The important abstraction is:

- every `Limit` belongs to a `LimitClass`
- each `LimitClass` defines its own normalized payload contract

This avoids forcing all provider limits into one flat universal schema.

Examples:

- `usage_over_time`
  - a limit with used percentage over a bounded time window
- possible future classes if real providers require them:
  - `token_balance`
  - `credit_balance`
  - `request_budget`

Those future classes are explicitly deferred until they appear in real provider data.

## First Normalized Limit Class

### `usage_over_time`

Required normalized fields:

- `used_percent`
- `period_started_at`
- `period_ends_at`

Derived values:

- elapsed percent
- usage/time pressure
- reset display and remaining time

This matches the current account usage output and the selected-accounts aggregate.

## Recommended Payload Shape

Conceptual normalized shape:

```json
{
  "limit_class": "usage_over_time",
  "limit_name": "weekly",
  "limit_label": "Weekly",
  "usage_over_time": {
    "used_percent": 28,
    "period_started_at": "2026-04-09T11:00:00Z",
    "period_ends_at": "2026-04-16T11:00:00Z"
  },
  "provider_limit": {
    "...": "provider-specific raw fields"
  }
}
```

Notes:

- `limit_label` is for presentation.
- `limit_class` + `limit_name` is the semantic identity.
- class-specific normalized fields should be nested, not flattened.

## Aggregate Config Direction

The aggregate should stop targeting limits by free-form display label and instead target the normalized limit identity:

```json
{
  "chat": {
    "accounts_usage_total": {
      "label": "Selected accounts aggregate",
      "instance_ids": ["codex-tk", "codex-jp", "claude-main"],
      "limit_class": "usage_over_time",
      "limit_name": "weekly"
    }
  }
}
```

This makes the aggregate logic explicit:

- select configured instances
- find the matching normalized limit
- compute pressure from the normalized `usage_over_time` fields

## Aggregate Semantics

For the currently accepted metric:

- aggregate used percent = average selected `used_percent`
- aggregate elapsed percent = average selected elapsed percent
- aggregate pressure = aggregate used percent / aggregate elapsed percent

This answers:

- across my selected accounts, am I consuming faster than time is passing?

This is not the same as averaging per-account ratios.

## Code Modeling Direction

Use a small typed model in code.

Recommended starting point:

- `Limit`
  - generic limit identity and metadata
- `UsageOverTimeLimitData`
  - normalized payload for the `usage_over_time` class

Preferred implementation posture:

- data-oriented typed models
- likely Python `dataclass`es
- no large inheritance framework yet

The intent is to model the domain clearly without overengineering for speculative future classes.

## Provider Mapping Direction

Each provider adapter should map raw provider quota concepts into canonical `Limit` objects.

Examples likely needed now:

- Codex `primary` -> `usage_over_time` / `burst`
- Codex `secondary` -> `usage_over_time` / `weekly`
- Claude short window -> `usage_over_time` / `burst`
- Claude long window -> `usage_over_time` / `weekly`

This mapping should be explicit and centralized in provider-specific account collectors.

## Rollout Plan

1. Add a first-class typed `Limit` model.
2. Add `UsageOverTimeLimitData`.
3. Update provider account collectors to emit normalized limits with:
   - `limit_class`
   - `limit_name`
   - `limit_label`
   - nested `usage_over_time`
4. Update formatting code to consume normalized limits instead of loose limit dicts.
5. Update `accounts_usage_total` config to target:
   - `limit_class`
   - `limit_name`
6. Keep additional limit classes deferred until real provider data requires them.

## Explicitly Deferred

- Support for additional limit classes without a real provider use case.
- A broad abstract subclass hierarchy for all future limit types.
- Any attempt to force token-only, credit-based, or timeless limits into the current `usage_over_time` contract.

