# Chat Session Model Design

## Goal
- Define the canonical session model for `agentos chat session`.
- Unify `list`, `find`, `stats`, and `extract` around one shared logical object: `session`.
- Keep the command surface small. Do not add new top-level verbs like `resolve` or `locate`.

## Accepted Command Surface
- `list` = selection: all, view: sessions
- `find <query>` = selection: query, view: sessions
- `find <query> --artifacts` = selection: query, view: sessions plus backing artifacts
- `find <query> --artifacts --grep` = selection: query, view: sessions plus backing artifacts plus search findings
- `stats [query]` = selection: all or query, view: stats
- `extract <query>` = selection: query, view: dialog

## Core Concepts
- `session`: logical cross-provider chat session
- `backing_artifact`: provider-native persisted storage that defines or proves a session
- `match`: why a queried session matched
- `search_finding`: non-canonical evidence such as grep hits
- `provider_diagnostic`: debug metadata about configured homes, searched targets, missing targets, sqlite roots, and similar runtime details

## Modeling Rules
- `session` is the default row everywhere.
- `backing_artifact` is part of the canonical session model.
- `search_finding` is not part of the canonical session model.
- Provider-specific session fields must live under `native`, not at the top level.
- The only globally unique session identity is `uri`.
- `session_id` is only unique within one provider instance.
- `display_name` is human-oriented only and must not be treated as the primary identity.

## Canonical Session Schema

```jsonc
{
  "uri": "agentos://chat-session/codex/9b5b0e2b4a2d.../019cd2fe-ff22-70f2-a131-2c00c0b21166",
  "provider": "codex",
  "provider_instance_fingerprint": "9b5b0e2b4a2d...",
  "session_id": "019cd2fe-ff22-70f2-a131-2c00c0b21166",
  "display_name": "tape-uri-discovery-refactor",
  "display_name_field": "thread_name",
  "created_at": "2026-03-08T01:09:00.000Z",
  "updated_at": "2026-03-10T12:13:33.263Z",
  "extractable": true,
  "backing_artifact_count": 2,
  "primary_backing_artifact": {
    "role": "transcript",
    "storage_kind": "file",
    "path": "/abs/path/to/rollout.jsonl",
    "locator": null,
    "extractable": true
  },
  "native": {
    "thread_name": "tape-uri-discovery-refactor"
  }
}
```

## Backing Artifact Schema

```jsonc
{
  "role": "session_index",
  "storage_kind": "file",
  "path": "/abs/path/to/session_index.jsonl",
  "locator": {
    "kind": "jsonl_record_match",
    "match": { "id": "019cd2fe-ff22-70f2-a131-2c00c0b21166" }
  },
  "extractable": false
}
```

### Allowed `storage_kind`
- `file`
- `directory`
- `sqlite_row`

### Recommended `role` Vocabulary
- `transcript`
- `metadata`
- `session_index`
- `session_root`
- `session_diff`
- `sqlite_session_row`

## Match Schema

```jsonc
{
  "query": "tape-uri-discovery-refactor",
  "kind": "exact_identity",
  "fields": [
    {
      "field": "thread_name",
      "value": "tape-uri-discovery-refactor"
    }
  ]
}
```

## Response Envelopes

### `list`

```jsonc
{
  "status": "ok",
  "command": "chat session list",
  "selection": {
    "kind": "all",
    "providers": ["codex", "claude-code"],
    "filters": {
      "sort": "newest",
      "limit": 20,
      "extractable": true,
      "updated_since": "72h",
      "user_contain": "session model"
    }
  },
  "expansions": [],
  "session_count": 12,
  "sessions": []
}
```

### `find <query>`

```jsonc
{
  "status": "ok",
  "command": "chat session find",
  "selection": {
    "kind": "query",
    "query": "tape-uri-discovery-refactor",
    "providers": null
  },
  "expansions": ["match"],
  "session_count": 1,
  "sessions": [
    {
      "uri": "agentos://chat-session/codex/9b5b0e2b4a2d.../019cd2fe-ff22-70f2-a131-2c00c0b21166",
      "provider": "codex",
      "provider_instance_fingerprint": "9b5b0e2b4a2d...",
      "session_id": "019cd2fe-ff22-70f2-a131-2c00c0b21166",
      "display_name": "tape-uri-discovery-refactor",
      "display_name_field": "thread_name",
      "created_at": "2026-03-08T01:09:00.000Z",
      "updated_at": "2026-03-10T12:13:33.263Z",
      "extractable": true,
      "backing_artifact_count": 2,
      "primary_backing_artifact": {
        "role": "transcript",
        "storage_kind": "file",
        "path": "/abs/path/to/rollout.jsonl",
        "locator": null,
        "extractable": true
      },
      "native": {
        "thread_name": "tape-uri-discovery-refactor"
      },
      "match": {
        "query": "tape-uri-discovery-refactor",
        "kind": "exact_identity",
        "fields": [
          { "field": "thread_name", "value": "tape-uri-discovery-refactor" }
        ]
      }
    }
  ]
}
```

### `find <query> --artifacts`

```jsonc
{
  "status": "ok",
  "command": "chat session find",
  "selection": {
    "kind": "query",
    "query": "tape-uri-discovery-refactor",
    "providers": null
  },
  "expansions": ["match", "backing_artifacts"],
  "session_count": 1,
  "sessions": [
    {
      "uri": "agentos://chat-session/codex/9b5b0e2b4a2d.../019cd2fe-ff22-70f2-a131-2c00c0b21166",
      "provider": "codex",
      "provider_instance_fingerprint": "9b5b0e2b4a2d...",
      "session_id": "019cd2fe-ff22-70f2-a131-2c00c0b21166",
      "display_name": "tape-uri-discovery-refactor",
      "display_name_field": "thread_name",
      "created_at": "2026-03-08T01:09:00.000Z",
      "updated_at": "2026-03-10T12:13:33.263Z",
      "extractable": true,
      "backing_artifact_count": 2,
      "primary_backing_artifact": {
        "role": "transcript",
        "storage_kind": "file",
        "path": "/abs/path/to/rollout.jsonl",
        "locator": null,
        "extractable": true
      },
      "native": {
        "thread_name": "tape-uri-discovery-refactor"
      },
      "match": {
        "query": "tape-uri-discovery-refactor",
        "kind": "exact_identity",
        "fields": [
          { "field": "thread_name", "value": "tape-uri-discovery-refactor" }
        ]
      },
      "backing_artifacts": [
        {
          "role": "transcript",
          "storage_kind": "file",
          "path": "/abs/path/to/rollout.jsonl",
          "locator": null,
          "extractable": true
        },
        {
          "role": "session_index",
          "storage_kind": "file",
          "path": "/abs/path/to/session_index.jsonl",
          "locator": {
            "kind": "jsonl_record_match",
            "match": { "id": "019cd2fe-ff22-70f2-a131-2c00c0b21166" }
          },
          "extractable": false
        }
      ]
    }
  ]
}
```

### `find <query> --artifacts --grep`

```jsonc
{
  "status": "ok",
  "command": "chat session find",
  "selection": {
    "kind": "query",
    "query": "tape-uri-discovery-refactor",
    "providers": null
  },
  "expansions": ["match", "backing_artifacts", "search_findings"],
  "session_count": 1,
  "sessions": [],
  "search_finding_count": 3,
  "search_findings": []
}
```

### `stats`

Inventory mode:

```jsonc
{
  "status": "ok",
  "command": "chat session stats",
  "selection": {
    "kind": "all",
    "providers": null
  },
  "stats": {
    "session_count": 12,
    "extractable_session_count": 10,
    "non_extractable_session_count": 2,
    "by_provider": [
      {
        "provider": "codex",
        "session_count": 4,
        "extractable_session_count": 4,
        "non_extractable_session_count": 0
      }
    ]
  }
}
```

Resolved-session mode:

```jsonc
{
  "status": "ok",
  "command": "chat session stats",
  "selection": {
    "kind": "query",
    "query": "tape-uri-discovery-refactor"
  },
  "session": {},
  "stats": {}
}
```

### `extract`
- Keep output unwrapped for now.
- It is still a view over one resolved session, but the current `jsonl` and `markdown` output is good for streaming and scripting.

## Provider Mapping

### `codex`
- `native.thread_name`
- `backing_artifacts`: rollout `transcript`, `session_index`
- `created_at`: first rollout record or dialog turn
- `updated_at`: session index `updated_at` or rollout mtime

### `claude-code`
- `native.title`
- `backing_artifacts`: CLI project `transcript`, desktop `metadata`
- `created_at`: first project turn or desktop `createdAt`
- `updated_at`: max of project and desktop timestamps

### `copilot-cli`
- `native`: empty
- `backing_artifacts`: `transcript` `events.jsonl`, optional `session_root`
- `created_at`: `session.start`
- `updated_at`: last event or session root mtime

### `gemini-cli`
- `native`: empty
- `backing_artifacts`: session `transcript` `.json`
- `created_at`: `startTime` or first message
- `updated_at`: `lastUpdated`

### `openclaw`
- `native.session_keys`
- `native.agent_id`
- `backing_artifacts`: `transcript`, `session_index`
- `created_at`: first session or message record
- `updated_at`: index `updatedAt` or latest record

### `opencode`
- `native`: empty
- `backing_artifacts`: `session_diff`, `sqlite_session_row`
- `created_at`: first message time
- `updated_at`: session row `time_updated`, latest message, or db or diff mtime

## Migration Map
- `provider_family` -> drop; keep `provider`
- `provider_instance` -> remove from default session row; add later only as an opt-in expansion if needed
- `primary_artifact_path` -> `primary_backing_artifact.path`
- `canonical_finding_count` -> `backing_artifact_count`
- `thread_name`, `title`, `session_keys`, `agent_id` -> move under `native`
- `findings` -> no longer the default `find` output
- current `providers` debug array -> move under `provider_diagnostics` and make it opt-in

## Important Constraints
- `search_findings` must stay separate from `backing_artifacts`.
- `grep` hits are search evidence, not canonical storage.
- Default session rows should not include full provider-instance summaries.
- `created_at` is best-effort and may be `null`.
- `locator` is required for backing artifacts that identify one record inside a shared container such as `session_index.jsonl`, `sessions.json`, or `opencode.db`.

## Conceptual Renames from Current Code
- Current `canonical_findings()` should become model-facing `backing_artifacts`.
- Current `primary_artifact_path()` should become model-facing `primary_backing_artifact`.

## First Implementation Plan
- Introduce internal dataclasses for `session`, `backing_artifact`, and `match`.
- Teach `list` to emit the new session rows.
- Flip `find` to session-first output.
- Add `--artifacts`.
- Keep `extract` output unwrapped.
- Move current provider debug arrays behind a diagnostics flag or keep them temporarily as compatibility output.
