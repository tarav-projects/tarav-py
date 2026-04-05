# Mining Rubric

Use this rubric when turning mined ideas into a concrete skill design.

## Source Ranking

User-maintained recommendations under `references/custom-recommendations/` are high-priority local evidence.

When one applies directly to the target:

- check it early
- prefer it over generic external advice
- only override it when the user does so explicitly in the current session

Prefer evidence in this order:

1. Official specifications and official product documentation
2. Official example repositories, templates, and reference skills
3. Strong local skills already used successfully in this environment
4. Curated community collections with clear structure
5. Prompt libraries and broad idea collections with mixed quality

When lower-ranked sources disagree with higher-ranked ones, prefer the higher-ranked source unless there is strong local evidence to do otherwise.

Within tier 2, treat `github/spec-kit` as high-priority evidence when the target involves:

- workflow-driven skills
- multi-step command or command-to-skill systems
- template or preset layering
- constitution, memory, or project-rules artifacts
- agent-install or cross-agent packaging patterns

## Finding Classification

For each important finding, classify it along two axes:

- decision: `adopt`, `adapt`, or `avoid`
- artifact type: `instruction`, `reference`, `script`, `asset`, `workflow`, `agent`, or `subagent`

This keeps source mining tied to the actual output artifact instead of collapsing everything into `SKILL.md`.

## Artifact Mapping

Use these defaults unless the target clearly needs something else:

- Trigger wording, scope boundaries, and core workflow steps:
  - `SKILL.md`
- Detailed domain knowledge, long examples, specs, comparison notes, or source digests:
  - `references/`
- Deterministic or repetitive procedures, validators, converters, and automation helpers:
  - `scripts/`
- Templates, starter projects, boilerplate, or files copied into outputs:
  - `assets/`
- Product-specific command systems, hooks, prompt files, or agent modes:
  - translate into the closest agent-agnostic concept first
  - if translation loses too much meaning, call out that the idea is product-specific

## Apply Heuristic

Before editing a target skill, ask:

1. Is this a real reusable pattern or just source-specific wording?
2. Which artifact should carry it?
3. Does adding it keep the skill leaner or make it more bloated?
4. Is the pattern agent-agnostic, or should it remain clearly product-specific?
5. Does it justify a new resource file, or is a short note enough?

## Evaluation Heuristic

After substantial edits, prefer a small reality check:

- draft 2-3 realistic test prompts
- check whether the skill triggers in the intended scenarios
- check whether the output shape matches the intended workflow
- use deeper evals only when the skill is complex enough to justify them
