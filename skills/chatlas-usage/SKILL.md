---
name: agentos-chatlas-usage
description: Use when Codex needs to work with chat session data in `agentos` through the maintained Chatlas dataset rather than live provider debug commands. Trigger for Chatlas tasks such as refreshing the dataset, querying sessions, resolving one session by id/URI/name/native field, inspecting provider stats, reading inline standard-model views, or exporting raw artifacts.
---

# Chatlas Usage

Use Chatlas as the default surface for chat session work.

Prefer `agentos chatlas ...` for normal session workflows. Use `agentos chat debug ...` only when the task is explicitly about live provider diagnostics, raw artifact extraction, or connector troubleshooting.

## Default Command Mapping

- Refresh dataset: `agentos chatlas update`
- Inventory/query sessions: `agentos chatlas query`
- Aggregate dataset stats: `agentos chatlas stats`
- Print inline standard-model views: `agentos chatlas views inline`
- Export raw artifacts: `agentos chatlas raw path` / `agentos chatlas raw export`

## Working Rules

- Treat Chatlas as the source of truth for session data.
- Default Chatlas dataset root is `~/Documents/chatlas`.
- Do not use removed `agentos chat session ...` commands.
- Do not default to `agentos chat debug ...` for normal session lookup or export.
- If the task depends on fresh provider state, run `agentos chatlas update` before querying.
- If the user is only asking about already-materialized dataset contents, query first and avoid unnecessary updates.
- `agentos chatlas update` uses the raw scan cache by default; set `--scan-cache false` only when you need a deeper archive scan.
- `agentos chatlas update` uses the session-index cache by default; set `--session-index-cache false` only when you need a deeper session-index rebuild.
- `agentos chatlas update` prints progress to stderr by default; disable live feedback with `--verbose-mode=quiet`.
- `agentos chatlas update` prints no final stdout payload by default; request machine-readable output with `--output-mode=json`.

## Query Workflow

1. If freshness matters, run `agentos chatlas update` first.
2. Use `agentos chatlas query` to resolve sessions.
3. Add only the expansion flags needed for the task.

Common patterns:

```bash
agentos chatlas query
agentos chatlas query "<query>" --include-match
agentos chatlas query "<query>" --include-match --include-provider-stats
agentos chatlas query "<query>" --include-artifacts
agentos chatlas query "<query>" --updated-since 2d --sort newest
agentos chatlas query "<query>" --compact
agentos chatlas query "<query>" --include-artifacts
agentos chatlas update
agentos chatlas update --scan-cache false
agentos chatlas update --session-index-cache false
agentos chatlas update --verbose-mode=quiet --output-mode=json
```

Use these flags intentionally:

- `--include-match`: show exact matched fields for identity resolution
- `--include-artifacts`: include backing artifact rows
- `--include-provider-stats`: include provider-specific stats for each resolved session
- `--updated-since`: restrict to recently updated sessions, e.g. `2d` or `72h`
- `--compact`: return identifier-oriented session rows
- `--extractable`: keep only sessions whose primary artifact can be extracted

## Inline View Workflow

Use `agentos chatlas views inline` after resolution when the task needs a standard-model session view rather than just metadata.

```bash
agentos chatlas views inline "<query>" --view full --format json
agentos chatlas views inline "<query>" --view transcript --format json
agentos chatlas views inline "<query>" --view user --format json
agentos chatlas views inline "<query>" --view replay --format json
agentos chatlas views inline "<query>" --view events --format json
agentos chatlas views inline "<query>" --view zip-transcript --format json
agentos chatlas raw path "<query>"
agentos chatlas raw export "<query>" --format json
```

View guidance:

- `full`: complete standard session model
- `transcript`: visible user/assistant transcript messages and matching message events
- `user`: visible user-authored messages only
- `replay`: visible messages plus lightweight tool-call replay data
- `events`: canonical event tape with derived projections emptied
- `zip-transcript`: minimal session header plus visible user/assistant text messages only

## When To Use `chat debug`

Use `agentos chat debug ...` only for live-side work such as:

- checking provider homes directly without relying on Chatlas
- searching raw live provider artifacts
- extracting from a specific artifact path with `--file`
- using `--raw` extraction
- connector/debug tasks where dataset mediation is undesirable

If the task is “find a session”, “inspect a session”, “export a standard-model view”, “export raw artifacts”, or “work with preserved chat history”, Chatlas is the right tool.
