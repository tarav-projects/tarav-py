---
name: agentos-skills-miner-ingenier
description: Mine local and external sources to discover reusable patterns, examples, workflows, and supporting artifacts for creating or upgrading agent skills. USE WHEN the user has a prompt idea, a skill idea, or an existing skill and wants to research similar work, discuss the best design moves, and later create or update the full skill stack; start from `references/source-registry.md`, add dynamic sources, and edit the target only after explicit user approval.
---

# Skills Miner Ingenier

Mine sources to improve skill design. This skill owns the whole loop: research, discussion, and eventual application.

This is a `Batchy.Skill` — called like a terminal command. Load `agentos-skills-base` for the full convention.

- `-h` / `--help` prints the help into the chat instead of running (`Batchy.Skill.Help`).
- supplied flags resolve to the `Skill.Arg` names below; a bare idea or skill path is `--target`.

## Skill.Arg.Section

### Skill.Arg:Skill.Target
- what to work on: a prompt or capability description for a new skill, or an existing skill path/folder to upgrade
- the skill self-detects whether this is a new skill, an upgrade, or a source comparison
- required: true
- help: "the new-skill idea or the existing skill to upgrade"
- examples: --target "skills/agentos-foo"

### Skill.Arg:Sources
- extra sources to mine and any source constraints, beyond the curated registry
- required: false
- help: "extra sources or source constraints"
- examples: --sources "github.com/danielmiessler/fabric, ./local-skills"

### Skill.Arg:Platform
- target agent or platform constraints for the resulting skill
- required: false
- help: "target agent/platform constraints"
- examples: --platform "claude-code"

## Default Sources

- Read [references/source-registry.md](references/source-registry.md) first.
- Read [references/custom-recommendations/README.md](references/custom-recommendations/README.md) and any relevant files under [references/custom-recommendations](references/custom-recommendations/) when they apply to the target.
- Treat registry entries as curated defaults, not a mandatory exhaustive search.
- Treat custom recommendations as high-priority local evidence when they directly apply.
- Add prompt-provided repos, folders, docs, gists, or skill paths as dynamic sources for the current task.

## Inputs

- A prompt or capability description for a new skill
- An existing skill path or folder to upgrade
- Optional source constraints or extra sources
- Optional target agent or platform constraints

## Trigger Boundary

Use this skill when research, comparison, or source mining is part of the job.

Do not trigger it for trivial direct edits where the needed change is already obvious and no mining or design discussion is necessary.

## Workflow

### 1. Inspect the target

- Determine whether the task is a new skill, a skill upgrade, or a source comparison.
- Extract search themes such as workflow shape, prompt structure, references, scripts, assets, validation, and triggering language.
- If the target is vague, start discussion immediately with a concrete first proposal instead of asking a long questionnaire.

### 2. Select sources

- Start with the registry.
- Add any prompt-provided sources for the current task.
- Choose only the sources that fit the target themes.
- Prefer a small focused set over broad crawling.

### 3. Mine sources

- Read only the relevant files or sections from each source.
- For each useful finding, classify it as `adopt`, `adapt`, or `avoid`.
- Distinguish between prompt wording, workflow structure, resource layout, validation ideas, and source-specific quirks.
- Do not blindly copy platform-specific harness details unless the target explicitly needs them.

### 4. Discuss findings

- Present high-signal findings in conversational form.
- Emphasize candidate design moves, tradeoffs, and what to copy versus avoid.
- Do not dump raw research unless the user asks for it.
- Treat the discussion as the working context for the eventual edit.

### 5. Wait for apply signal

- Do not edit the target skill before the user explicitly directs application.
- Signals such as `draft now`, `write it`, `upgrade the skill`, or `apply the conclusions` authorize editing.

### 6. Apply conclusions

- Create or update the full target skill stack as justified:
  - `SKILL.md`
  - `agents/openai.yaml`
  - `references/`
  - `scripts/`
  - `assets/`
- Add bundled resources only when the mined material clearly justifies them.
- Keep the result agent-agnostic unless the target explicitly needs product-specific behavior.
- If another local skill naturally helps during authoring, it may be used, but do not force that helper's identity into the final skill.

### 7. Optional post-apply evaluation

- For substantial skill changes, generate 2-3 realistic test prompts.
- Use them to pressure-test whether the new or upgraded skill actually triggers and behaves as intended.
- Keep this lightweight by default unless the user asks for deeper evaluation.

### 8. Validate and summarize

- Run the relevant validator when the target skill format supports one.
- Summarize what changed, which sources mattered most, and what was deferred.

## Mining Heuristics

- Prefer sources that match the task type: pattern libraries for prompt structure, real skills for workflow design, and notes or docs for domain context.
- Prefer concrete examples over generic advice.
- Prefer complete workflows over isolated slogans.
- Treat flashy prompt theater and arbitrary constraints as weak evidence.
- Treat strong trigger descriptions, progressive disclosure, validation instructions, and reusable resource choices as strong evidence.

## Repeated Best Practices

Treat the following as high-value patterns when mining sources and designing the target skill:

- Keep instructions focused and tightly scoped.
- Split large artifacts into composable pieces instead of one monolith.
- Include concrete examples or referenced files when they materially clarify usage.
- Use progressive disclosure so detailed material loads only when needed.
- Separate always-on guidance from on-demand expertise.
- Keep deterministic or repetitive steps in scripts, hooks, or workflows instead of burying them in prose.

## Artifact Selection

Before editing the target, decide where each adopted idea belongs.

- Put trigger language and core workflow into `SKILL.md`.
- Put detailed supporting material into `references/`.
- Put deterministic or repetitive steps into `scripts/`.
- Put reusable templates or output artifacts into `assets/`.
- If a mined idea is better expressed as a command, workflow, hook, or agent than as a skill instruction, say so explicitly.
- For a more detailed mapping and source ranking heuristic, read [references/mining-rubric.md](references/mining-rubric.md).

## Source Handling

- Curated defaults live in [references/source-registry.md](references/source-registry.md).
- User-maintained recommendations live in [references/custom-recommendations](references/custom-recommendations/) and should be checked early when relevant.
- Dynamic prompt-driven sources supplement the registry for the current task only.
- Clearly label whether a finding came from a local source, an external source, or a user-provided source.
- Clearly label when a finding came from a custom recommendation.
- If a source is mixed quality, say so directly.

## Example Triggers

- `Mine sources for a skill that cleans up codebases after implementation.`
- `Here is a skill path. Research similar skills and help me upgrade it.`
- `Use Fabric and local skills to design a new skill for this prompt.`

## Constraints

- Do not start editing the target skill before user approval.
- Do not research exhaustively by default; research selectively.
- Do not copy large prompt bodies verbatim when a design principle or small excerpt is enough.
- Do not overfit the result to Fabric or any single source.
- Do not create scripts, assets, or references unless they materially improve reuse.
- Keep the final target skill lean.

## Response Shape

During discussion, respond with:

- current draft direction
- best source-derived ideas to adopt
- what to avoid
- tradeoffs and next actions

When applying, respond with:

- what was created or updated
- why
- sources used
- validation run
