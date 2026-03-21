---
name: agentos-index-notes-create-skill
description: "Agentos Index Notes System: Design and create a new index maintenance skill through interactive Q&A"
user-invocable: true
disable-model-invocation: true
---

# Agentos Index Notes Skill Creator

Read and follow `skills/agentos-index-note-base/FOUNDATION.md` before proceeding.

You guide the user through designing and creating a new skill for the Agentos Index Notes Maintenance System.

**This is a CONVERSATION, not a form.** All questions MUST be printed as plain text in the chat. NEVER use `AskUserQuestion` or any interactive/UI tool to ask questions. Just type them out.

## Workflow

### Phase 1: Load Context

1. Read `skills/agentos-index-note-base/FOUNDATION.md`
2. Discover all existing index notes skills: glob `skills/agentos-index-notes-*/SKILL.md`
3. Read each discovered skill file
4. Summarize to the user:
   - What the Agentos Index Notes Maintenance System is (1-2 sentences from the foundation)
   - What skills already exist (name + one-line purpose for each)
   - Tell the user you'll now ask questions to design their new skill

### Phase 2: Interview

Ask numbered questions, **2-4 per round**. Offer concrete options (a/b/c) when possible.

Cover these topics across rounds:

1. **Purpose** — What does this skill do? What problem does it solve?
2. **Scan target** — What does it scan or check? (codebase, index, both, external)
3. **Mode** — Autonomous (`agentos-index-notes-*-auto`, scan + report) or interactive (`agentos-index-notes-*-interview`, conversational Q&A)?
4. **Workflow phases** — What are the major steps? (e.g., orient, scan, rank, report)
5. **Ranking/selection** — How should findings be prioritized? What makes one finding more important than another?
6. **Output format** — Standard foundation report, or does this skill need a different output? (Most skills should use the standard format.)
7. **Exceptions** — Does this skill need to deviate from any foundation constraints? (e.g., writing files, different report format)

After each user reply:
- Acknowledge decisions made
- Ask follow-up questions if ambiguities remain
- Continue the loop

**Keep rounds short**: 2-4 questions maximum per round.

The loop ends when the user says to proceed (e.g., "create it", "go ahead", "looks good").

### Phase 3: Create Skill

1. **Print a summary** of all decisions to chat — do NOT write this summary to a file:
   ```
   ## New Skill Summary
   - Name: agentos-index-notes-<name>
   - Purpose: ...
   - Mode: autonomous / interactive
   - Phases: ...
   - Key behaviors: ...
   - Foundation exceptions: none / ...
   ```

2. **Write the SKILL.md file** at `skills/agentos-index-notes-<name>/SKILL.md`

   The generated skill MUST follow these conventions:

   **Frontmatter:**
   ```yaml
   ---
   name: agentos-index-notes-<name>
   description: "Agentos Index Notes System: <clear description with searchable keywords>"
   user-invocable: true
   disable-model-invocation: true
   ---
   ```

   **Structure:**
   - First line after frontmatter heading: `Read and follow skills/agentos-index-note-base/FOUNDATION.md before proceeding.`
   - One-sentence description of what the skill does
   - **Key constraints block** duplicated inline from foundation:
     ```
     **Key constraints (duplicated from foundation):**
     - **Never modify any file** — analysis and reporting only
     - Report is **printed to chat** (ephemeral), never saved to a file
     - 3-5 findings, <10 lines each, bullet-point structured text
     - Be direct — brevity over completeness
     ```
     Omit or adjust individual constraints only if the interview explicitly determined an exception.
   - Phased workflow (## Workflow with ### Phase N: Name subsections)
   - Report template showing the expected output format
   - Optionally a report example if it helps clarify

   **Quality checks:**
   - Total file should be <500 lines
   - Focused on one concern — not a Swiss-army-knife skill
   - Step-by-step workflow that an agent can follow without ambiguity
   - Use existing `agentos-index-notes-*` skills as structural reference

3. Tell the user the file was created and suggest they invoke it to test.
