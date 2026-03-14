---
name: session-zip-transcript
description: Resolve a chat session from a session id, session URI, or provider-agnostic query, extract its conversation with `agentos chat session`, and return a compressed transcript artifact. Use when the user wants prior session context loaded in a smaller form that preserves full user turns but not the exact original assistant wording.
---

# Session Zip Transcript

Return a compressed transcript for a prior chat session.

This skill must run as an agent by default, not inline in the caller context. `agentos chat session` handles deterministic resolution and extraction. The agent always compresses the transcript before returning it.

## Execution Mode

- Run this skill in a separate agent by default.
- Do not perform the transcript compression inline in the caller context unless the user explicitly asks for that fallback.
- The point of this skill is to keep transcript-processing work and compression reasoning out of the caller context.

## Use This Skill When

- The user gives a session id, session URI, or session query and wants the prior conversation back in a compact form.
- The caller needs user intent preserved exactly, but does not need the original assistant wording.
- The caller must keep transcript-processing work out of their own context.

## Workflow

1. Resolve the session.
2. Extract the conversation transcript.
3. Compress the transcript in-agent.
4. Return only the compressed transcript artifact.

## Step 1: Resolve The Session

If the input is already an `agentos://chat-session/...` URI, use it directly.

Otherwise resolve it with:

```bash
agentos chat session find "<query>"
```

Resolution rules:

- If `finding_count` is `1`, use the returned `findings[0].uri`.
- If `finding_count` is `0`, fail clearly and say the session could not be found.
- If `finding_count` is greater than `1`, do not guess. Return a short ambiguity report with the candidate `provider`, `session_id`, and `uri`.

## Step 2: Extract The Transcript

Extract markdown with:

```bash
agentos chat session extract "<resolved-uri>" --format markdown
```

Use markdown extraction unless the user explicitly asks for another format.

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
resolved-via: agentos chat session find
extracted-via: agentos chat session extract --format markdown
```

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

## Notes

- This skill is for continuation and context recovery, not quote-accurate archival use.
- The caller must be aware that the returned transcript is compressed and not original.
