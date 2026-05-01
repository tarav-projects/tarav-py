# General Preferences

Always-loaded reference. These are standing preferences that apply across all implementation work.

## Simplicity

- Prefer simple over clever. If two approaches work, pick the one that is easier to read.
- Prefer flat over nested. Reduce indentation levels where possible.
- Prefer explicit over implicit. Make data flow and dependencies visible.

## Naming

- Names should describe what something does or holds, not how it is implemented.
- Match existing naming conventions in the codebase. Do not introduce new styles.

## Structure

- Keep functions short and focused on a single responsibility.
- Prefer composition over inheritance.
- Group related changes together in commits and in code.

## Dependencies

- Do not add new dependencies without clear justification.
- Prefer standard library solutions when they are adequate.
- If a dependency is added, pin it to a specific version.

## Testing

- If the codebase has tests, ensure changes are covered or at least do not break existing tests.
- Write tests when the design calls for them, not speculatively.
- Prefer testing behavior over testing implementation details.
