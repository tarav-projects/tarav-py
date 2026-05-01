---
name: agentos-session-zip-transcript
description: Resolve a chat session from a session id, session URI, or provider-agnostic query, extract its conversation with `agentos chatlas`, and return a compressed transcript artifact. Use when the user wants prior session context loaded in a smaller form that preserves full user turns but not the exact original assistant wording.
---

# Session Zip Transcript

Return a compressed transcript for a prior chat session.

This skill must run as an agent by default, not inline in the caller context. `agentos chatlas` handles deterministic resolution and extraction from the maintained chat dataset. The agent always compresses the transcript before returning it.

## Trigger Boundary

Use this skill for prior-session transcript recovery and compression.

Do not use it for:

- recapping the current live chat inline
- quote-accurate archival output
- generic session management unrelated to returning a compressed transcript artifact

## Execution Mode

- Run this skill in a separate agent by default.
- Do not perform the transcript compression inline in the caller context unless the user explicitly asks for that fallback.
- The point of this skill is to keep transcript-processing work and compression reasoning out of the caller context.

## Use This Skill When

- The user gives a session id, session URI, or session query and wants the prior conversation back in a compact form.
- The caller needs user intent preserved exactly, but does not need the original assistant wording.
- The caller must keep transcript-processing work out of their own context.

## Compression Quality Bar

Hold the output to this quality bar:

1. **Zero user-turn loss**: preserve every user turn in full and in order.
2. **Minimal redundancy**: compress assistant content aggressively when it repeats or adds no new state.
3. **Maximum scannability**: make the artifact easy to continue from quickly without pretending it is the original transcript.

## Workflow

1. Resolve the session.
2. Extract the conversation transcript.
3. Compress the transcript in-agent.
4. Return only the compressed transcript artifact.

## Missing Input

If the user provides neither:

- a session id
- a session URI
- nor a provider-agnostic session query

stop and return this short failure shape:

```text
Could not resolve a prior session because no session identifier or query was provided.
Provide one of:
- a session id
- an agentos://chat-session/... URI
- a query that can be resolved with `agentos chatlas query --include-match`
```

## Step 1: Resolve The Session

If the input is already an `agentos://chat-session/...` URI, use it directly.

Otherwise resolve it with:

```bash
agentos chatlas query "<query>" --include-match
```

Resolution rules:

- If `session_count` is `1`, use the returned `sessions[0].uri`.
- If `session_count` is `0`, fail clearly and say the session could not be found.
- If `session_count` is greater than `1`, do not guess. Return this short ambiguity report shape:

```text
Multiple prior sessions matched the query. I did not choose one automatically.

Candidates:
- provider: <provider> | session_id: <session-id> | uri: <uri>
- provider: <provider> | session_id: <session-id> | uri: <uri>

Reply with the exact `session_id` or `uri` to continue.
```

## Step 2: Extract The Transcript

Extract the structured transcript view with:

```bash
agentos chatlas export "<resolved-uri>" --view zip-transcript --format json
```

Use JSON `zip-transcript` extraction unless the user explicitly asks for another supported export view.

Interpret the export as the Chatlas session model:

- Use `chat.messages` as the primary ordered turn source.
- Preserve message roles from the structured payload.
- Convert text content blocks to plain turn text before compression.
- `zip-transcript` already filters to visible user/assistant text content only; do not expect images, encrypted content, opaque reasoning, tool payloads, or normalization metadata to be present.
- Use `event_refs` on messages only as lightweight provenance when needed; do not reconstruct the full event tape.

## Step 3: Compress In-Agent

Always compress the transcript. Do not switch behavior based on transcript length.

Hard rules:

- Preserve every user turn in full.
- Preserve user wording exactly.
- Preserve chronological order.
- Compress every assistant turn to the shortest direct form that keeps new information.
- Short high-signal command outputs may be kept verbatim.
- High-signal but long outputs must be compressed structurally, not copied wholesale.
- Do not keep progress chatter, repeated framing, or filler.
- Do not pretend the output is the original transcript.

Keep assistant content only when it carries session state that matters later, such as:

- decisions
- accepted plans
- constraints
- concrete results
- failures
- warnings
- unresolved issues
- commands, paths, flags, identifiers, or counts that matter for continuation

Usually drop assistant content that is only:

- speculative framing
- unaccepted suggestions
- process narration
- repeated summaries
- tone-only filler
- status chatter that did not change the outcome

Compression checklist:

1. Preserve every user turn fully.
2. Preserve accepted decisions and concrete outcomes.
3. Preserve failures and unresolved issues.
4. Drop chatter and repeated framing.
5. Compress long outputs structurally instead of copying them wholesale.

Keep in assistant turns:

- answers
- decisions
- constraints
- concrete facts
- command names, flags, identifiers, and counts when they matter
- failures, warnings, and unresolved issues
- code-change outcomes or test results when they matter

Drop or compress aggressively:

- progress updates
- statements about what the agent is about to do
- statements that a run is in progress
- repeated summaries
- apology/filler language
- redundant caveats
- verbose prose that adds no new information

Preferred assistant rewrite shape:

- result
- evidence
- decision
- unresolved issue, only if one remains

If a long structured output matters, compress it into a short factual summary instead of pasting the full block.

Examples:

- Good: `Found 46 likely heartbeat sessions; current reused session: 6a5c95ab-...; 2 extra debugging sessions.`
- Bad: a 46-line session id dump when the exact full list is not required to preserve the conversation outcome.

## Step 4: Return The Artifact

The returned artifact must be self-describing. Start it with this notice or equivalent wording:

```text
[compressed transcript]
User turns are preserved in full.
Assistant turns are compressed for brevity and may not match the original wording.
Do not treat this artifact as the original transcript.
```

Add a short provenance header before the first transcript turn when the information is available:

```text
source-session-id: <session-id>
source-session-uri: <resolved-uri>
resolved-via: agentos chatlas query --include-match
extracted-via: agentos chatlas export --view zip-transcript --format json
```

When both a session id and URI are available, include both. Treat these as first-class provenance data, not optional decoration.

Then emit the transcript in a stable turn-based format:

```text
[user]
<full user content>

[assistant]
<compressed assistant content>
```

## Output Requirements

- Return the compressed transcript artifact itself, not a prose summary about it.
- Keep the artifact plain and readable.
- If extraction fails, report the failure briefly instead of fabricating output.
- If resolution is ambiguous, stop before extraction.

## Session Content Sensitivity

- Treat the returned artifact as sensitive prior-session content.
- Do not broaden or remix it with unrelated repository discovery or external context.
- Do not present the artifact as a casual recap when it is actually a derived transcript.

## Notes

- This skill is for continuation and context recovery, not quote-accurate archival use.
- The caller must be aware that the returned transcript is compressed and not original.
- Prefer Chatlas dataset resolution over `agentos chat debug ...`; the debug surface is for live connector diagnostics, not normal prior-session recovery.
