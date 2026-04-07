---
name: agentos-session-continue
description: Resolve a prior chat session from a session id, session URI, or provider-agnostic query, extract its conversation with `agentos chatlas`, and return a continuation handoff artifact for resuming the discussion here. Use when the goal is to continue work from another chat while keeping all user turns verbatim.
---

# Session Continue

Return a continuation handoff for a prior chat session so the discussion can resume in the current chat.

This skill must run as an agent by default, not inline in the caller context. `agentos chatlas` handles deterministic resolution and extraction from the maintained chat dataset. The agent always returns a handoff artifact oriented toward continuation, not just transcript recovery.

## Trigger Boundary

Use this skill when the user wants to continue a discussion from another session in the current chat.

Do not use it for:

- recapping the current live chat inline
- quote-accurate archival output
- generic session management unrelated to continuing the discussion here
- transcript compression when no continuation handoff is needed

## Execution Mode

- Run this skill in a separate agent by default.
- Do not perform the extraction and handoff compression inline in the caller context unless the user explicitly asks for that fallback.
- The point of this skill is to keep transcript-processing work and handoff synthesis out of the caller context.

## Use This Skill When

- The user gives a session id, session URI, or session query and wants to continue that discussion here.
- The caller needs the prior session turned into a handoff artifact optimized for resumption.
- The caller wants all user turns preserved exactly while assistant turns are compressed.

## Continuation Quality Bar

Hold the output to this quality bar:

1. **Zero user-turn loss**: preserve every user turn in full and verbatim.
2. **Continuation-first output**: make it obvious what the current goal, accepted decisions, constraints, unresolved issues, and best next move are.
3. **Minimal assistant redundancy**: compress assistant content aggressively when it repeats or adds no new state.
4. **Maximum scannability**: make the artifact easy to continue from quickly without pretending it is the original transcript.

## Workflow

1. Resolve the session.
2. Extract the conversation transcript.
3. Derive continuation state from the session.
4. Compress the assistant turns.
5. Return only the continuation handoff artifact.

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

Extract markdown with:

```bash
agentos chatlas export "<resolved-uri>" --kind transcript --format markdown
```

Use markdown extraction unless the user explicitly asks for another format.

## Step 3: Derive Continuation State

Before writing the transcript section, derive the session state that matters for continuing here.

Include only items supported by the session. Omit unknown items instead of inventing them.

Preferred continuation-state fields:

- `current-goal`
- `accepted-decisions`
- `active-constraints`
- `important-artifacts`
- `open-threads`
- `recommended-next-step`

Interpretation rules:

- `current-goal`: the main objective the session was converging on or actively pursuing near the end.
- `accepted-decisions`: decisions the user accepted or that the session clearly committed to.
- `active-constraints`: requirements, prohibitions, environment constraints, or style constraints that still govern the work.
- `important-artifacts`: commands, paths, identifiers, files, branches, URLs, counts, or names that matter for continuation.
- `open-threads`: unresolved questions, blockers, pending edits, missing validation, or follow-up work.
- `recommended-next-step`: the single best next move for resuming in the current chat.

## Step 4: Compress Assistant Turns

Always compress the assistant turns. Do not switch behavior based on transcript length.

Hard rules:

- Preserve every user turn in full.
- Preserve every user turn verbatim.
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

1. Preserve every user turn fully and verbatim.
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
- apology or filler language
- redundant caveats
- verbose prose that adds no new information

Preferred assistant rewrite shape:

- result
- evidence
- decision
- unresolved issue, only if one remains

If a long structured output matters, compress it into a short factual summary instead of pasting the full block.

## Step 5: Return The Handoff Artifact

The returned artifact must be self-describing. Start it with this notice or equivalent wording:

```text
[session continuation handoff]
User turns are preserved verbatim.
Assistant turns are compressed for brevity and may not match the original wording.
Continuation state is derived to help resume the discussion in this chat.
Do not treat this artifact as the original transcript.
```

Add a short provenance header before the continuation state when the information is available:

```text
source-session-id: <session-id>
source-session-uri: <resolved-uri>
resolved-via: agentos chatlas query --include-match
extracted-via: agentos chatlas export --kind transcript --format markdown
```

When both a session id and URI are available, include both. Treat these as first-class provenance data, not optional decoration.

Then emit the continuation state in a stable shape:

```text
[continuation-state]
current-goal: <text>

accepted-decisions:
- <decision>

active-constraints:
- <constraint>

important-artifacts:
- <artifact>

open-threads:
- <open thread>

recommended-next-step:
- <next step>
```

After that, emit the transcript in a stable turn-based format:

```text
[transcript]

[user]
<full user content>

[assistant]
<compressed assistant content>
```

## Output Requirements

- Return the continuation handoff artifact itself, not a prose summary about it.
- Keep the artifact plain and readable.
- If extraction fails, report the failure briefly instead of fabricating output.
- If resolution is ambiguous, stop before extraction.
- The artifact must make continuation easier than reading the raw transcript.

## Session Content Sensitivity

- Treat the returned artifact as sensitive prior-session content.
- Do not broaden or remix it with unrelated repository discovery or external context.
- Do not present the artifact as a casual recap when it is actually a derived continuation handoff.

## Notes

- This skill is for continuation and context recovery, not quote-accurate archival use.
- The caller must be aware that the transcript portion is compressed and not original.
- The user turns are still required to remain verbatim.
- Prefer Chatlas dataset resolution over `agentos chat debug ...`; the debug surface is for live connector diagnostics, not normal prior-session recovery.
