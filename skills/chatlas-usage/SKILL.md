---
name: agentos-chatlas-usage
description: Use when Codex needs to work with chat session data in `agentos` through the maintained Chatlas dataset rather than live provider debug commands. Trigger for Chatlas tasks such as refreshing the dataset, querying sessions, resolving one session by id/URI/name/native field, inspecting summaries or provider stats, or exporting transcripts and summaries.
---

# Chatlas Usage

Use Chatlas as the default surface for chat session work.

Prefer `agentos chatlas ...` for normal session workflows. Use `agentos chat debug ...` only when the task is explicitly about live provider diagnostics, raw artifact extraction, or connector troubleshooting.

## Default Command Mapping

- Refresh dataset: `agentos chatlas update`
- Inventory/query sessions: `agentos chatlas query`
- Aggregate dataset stats: `agentos chatlas stats`
- Export transcript or summary: `agentos chatlas export`

## Working Rules

- Treat Chatlas as the source of truth for session data.
- Default Chatlas dataset root is `~/Documents/chatlas`.
- Do not use removed `agentos chat session ...` commands.
- Do not default to `agentos chat debug ...` for normal session lookup or export.
- If the task depends on fresh provider state, run `agentos chatlas update` before querying.
- If the user is only asking about already-materialized dataset contents, query first and avoid unnecessary updates.
- `agentos chatlas update` uses the raw scan cache by default; disable only with `--scan-cache=false` when you need a deep archive scan.
- `agentos chatlas update` uses the normalized session cache by default; disable only with `--normalized-cache=false` when you need a deep normalized-session rebuild.
- `agentos chatlas update` uses the derived transcript cache by default; disable only with `--transcript-cache=false` when you need a deep transcript rebuild.
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
agentos chatlas query --user-contain "<text>" --include-summary
agentos chatlas query "<query>" --include-artifacts
agentos chatlas update
agentos chatlas update --scan-cache=false
agentos chatlas update --normalized-cache=false
agentos chatlas update --transcript-cache=false
agentos chatlas update --verbose-mode=quiet --output-mode=json
```

Use these flags intentionally:

- `--include-match`: show exact matched fields for identity resolution
- `--include-artifacts`: include backing artifact rows
- `--include-summary`: include brief summary
- `--summary-level brief|detailed`: include derived summary levels
- `--include-provider-stats`: include provider-specific stats for each resolved session
- `--include-transcript-filter-match`: show why transcript filters matched

## Export Workflow

Use `agentos chatlas export` after resolution when the task needs artifact contents rather than metadata.

```bash
agentos chatlas export "<query>" --kind transcript --format markdown
agentos chatlas export "<query>" --kind transcript --format jsonl
agentos chatlas export "<query>" --kind summary --summary-level detailed --format markdown
```

## When To Use `chat debug`

Use `agentos chat debug ...` only for live-side work such as:

- checking provider homes directly without relying on Chatlas
- searching raw live provider artifacts
- extracting from a specific artifact path with `--file`
- using `--raw` extraction
- connector/debug tasks where dataset mediation is undesirable

If the task is “find a session”, “inspect a session”, “export a transcript”, or “work with preserved chat history”, Chatlas is the right tool.
