# Add `USE WHEN` To SKILL Frontmatter Description

## Recommendation

When drafting or upgrading a `SKILL.md`, make the frontmatter `description` explicitly include a `USE WHEN` segment that explains the triggering mechanism.

## Why It Matters

- It makes trigger behavior easier to mine and compare across skills.
- It reduces vague descriptions that describe capability but not activation.
- It helps separate adjacent skills by saying when the skill should actually fire.

## Apply This When

- writing a new `SKILL.md`
- upgrading an existing skill description
- reviewing trigger precision or skill overlap

## Preferred Shape

Use a short capability statement followed by an explicit `USE WHEN ...` clause.

Example shape:

```yaml
description: Improve a git-tracked codebase in place by making targeted cleanup refactors. USE WHEN the user wants the agent to simplify code, reduce duplication, address SSOT or DRY violations, remove poor abstractions, centralize repeated knowledge, tighten boundaries, or generally clean up a repository after implementation.
```

## Notes

- Keep the `USE WHEN` clause concrete and trigger-oriented.
- Prefer specific user intents over abstract capability labels.
- Avoid bloating the description with implementation detail that belongs in the body.
