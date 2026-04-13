---
name: chatlas-query-session
description: Resolve Chatlas sessions through compact metadata-only queries without transcript export. Use when Codex is explicitly invoked as `$chatlas-query-session` to find one or more prior sessions by session id, URI, display name, native field, provider or instance, recency, or transcript text filters and should return compact identifiers rather than transcripts, summaries, or continuation artifacts.
---

# Chatlas Query Session

Use this skill to find prior sessions through the Chatlas query surface only.

Keep the job token-cheap and metadata-only. Refresh with Chatlas update when freshness matters, then resolve with Chatlas query and return compact session rows.

This skill must run as an agent by default, not inline in the caller context. The separate agent should do the refresh, query, and compact result formatting, then return only the final metadata-oriented result.

## Execution Mode

- Run this skill in a separate agent by default.
- Do not perform the refresh and query inline in the caller context unless the user explicitly asks for that fallback.
- The point of this skill is to keep query work, result filtering, and compact formatting out of the caller context.

## Operating Surface

The allowed `agentos` commands in this skill are exactly:

- `agentos chatlas update --verbose-mode=quiet`
- `agentos chatlas query`

Treat `agentos chatlas query` as the full query surface. Add only the smallest set of query flags needed for the request.

Never use:

- `agentos chatlas export`
- transcript inspection outside Chatlas query filters
- any other `agentos` command

The reason is deliberate: this skill exists to stay token-cheap and metadata-only. If the task needs transcript contents, transcript summaries, or a continuation handoff, stop and use a different skill.

## Working Rules

- Use this skill only when it was explicitly invoked.
- Default to `--compact`.
- Default to `--sort newest --limit 10`.
- Override the default sort order or result count only when the user explicitly asks for a different ordering or a different number of results.
- Run `agentos chatlas update --verbose-mode=quiet` first when the request is freshness-sensitive.
- Treat `chatlas update` as a preflight freshness step only.
- On successful update, ignore the success payload and continue to the query.
- On failed update, report the failure briefly and stop.
- Use the positional `query` argument for exact identity resolution against URI, instance, session id, display name, fingerprint, and native fields.
- Use `--user-contain` when the user says the text appeared in a user turn.
- Use `--text-contain` when the text may appear in any transcript turn.
- Use `--updated-since` for recency windows such as `72h`, `14d`, or `2w`.
- Use `--provider` and `--instance` when the request already constrains those fields.
- Use `--sort newest` by default because this skill should prefer the latest activity first.
- Use `--limit 10` by default to keep the result set compact.
- Use `--include-match` for exact identity lookup when the matching field matters to the answer.
- Avoid `--include-summary`, `--include-artifacts`, `--include-provider-stats`, and `--include-transcript-filter-match` unless the user explicitly needs that extra metadata.

## Output Contract

Return metadata only.

Default compact row fields:

- `provider`
- `instance`
- `session_id`
- `updated_at`

Optional fields:

- `uri` only when the user explicitly asks for it or when URI is the locator they provided
- exact match details only when `--include-match` was needed

## Self Detection

Often the currently running chat session will also match the query.

- If the active chat session can be identified from the running context, the current thread, or an exact session locator already present in the task, compare the matched rows against that active session.
- If one matched row is the active chat session, keep it in the result set and annotate it with `(current)` beside the session identifier.
- If multiple rows are returned, annotate only the row that matches the active session.
- If the active session cannot be identified reliably, do not guess and do not add the label.

Result rules:

- One match: return the single compact row.
- Multiple matches: return up to the top 10 compact rows by latest activity unless the user explicitly requested a different limit or sort order, and do not choose one automatically.
- Zero matches: say that no session matched and briefly state the key filters you used.

Do not widen the task into transcript export, manual transcript browsing, or continuation reconstruction.

## Freshness Rule

- If compact query output unexpectedly lacks `instance`, run `agentos chatlas update --verbose-mode=quiet` once and retry the same query once.
- Describe that retry as a normalized-session refresh. Do not claim that update avoids all raw archive rediscovery.
- Do not introduce extra `chatlas update` flags in this skill.

## Short Tutorial

Refresh first when fresh provider state matters:

```bash
agentos chatlas update --verbose-mode=quiet
```

Resolve one known session id or URI:

```bash
agentos chatlas query "019d77ba-3a0e-75b0-9211-7e90e882a67c" --compact --include-match
agentos chatlas query "agentos://chat-session/codex/.../019d77ba-3a0e-75b0-9211-7e90e882a67c" --compact --include-match
```

Find sessions where the user said specific text within a recent window:

```bash
agentos chatlas query --user-contain "check `taralib_dart/notes/live/500-stdlib-dart-update-plan-2026-04-05.md.`" --updated-since 14d --sort newest --compact
```

Find sessions where text appeared anywhere in the transcript:

```bash
agentos chatlas query --text-contain "normalized cache" --updated-since 7d --sort newest --limit 5 --compact
```

Filter to a provider or resolved instance when the request already gives that constraint:

```bash
agentos chatlas query --provider codex --instance codex-tk --user-contain "chatlas query" --sort newest --compact
```
