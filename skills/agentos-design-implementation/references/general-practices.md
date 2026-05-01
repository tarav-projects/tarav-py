# General Implementation Practices

Always-loaded reference. Apply these on every implementation task.

## Before Touching Code

- Read the target files first. Never propose changes to code you have not read.
- Understand the existing patterns in the codebase. Match them instead of introducing new conventions.
- Check for related tests, types, and consumers before changing an interface.

## Writing Code

- Implement the minimum change that satisfies the requirement. Nothing more.
- Prefer editing existing files over creating new ones.
- Do not add abstractions for a single use case. Three similar lines are better than a premature helper.
- Do not add error handling for scenarios that cannot happen. Validate at system boundaries only.
- Do not add comments, docstrings, or type annotations to code you did not change.
- Only add comments where the logic is not self-evident.

## Moving Forward, Not Sideways

Backward-compatibility shims, legacy fallbacks, and regression scaffolding are errors unless the user explicitly requests them. This is one of the most common drifts from desired behavior.

- When implementing a new design, replace the old code. Do not wrap it, gate it, or keep it "just in case."
- Do not rename old symbols to `_deprecated_*` or re-export them for compatibility. If the design says it is replaced, delete it.
- Do not write migration code or format adapters for old data shapes. If the design defines a new format, implement the new format. Migration is a separate concern — only add it when explicitly requested.
- Do not write tests that assert old behavior alongside new behavior. Tests should validate the new design, not preserve the old one.
- If existing tests break because the design changed, update them to match the new design. Broken tests are signals to update, not reasons to add compatibility layers.
- The only exception is an explicit user instruction to maintain backward compatibility or provide migration. "Explicit" means stated directly, not inferred from context.

## Avoiding Common Pitfalls

- No feature flags for internal changes.
- No "while I'm here" refactors — stay scoped to the task.
- No speculative generalization. Build for the current requirement.
- Check for security issues: injection, XSS, SQL injection, path traversal. Fix immediately if introduced.

## After Each Change

- Verify the change does not break existing behavior in the immediate area.
- Keep the diff focused. If a chunk's diff is touching unrelated code, split it.
- Suggest a commit when a meaningful unit of work is complete.
