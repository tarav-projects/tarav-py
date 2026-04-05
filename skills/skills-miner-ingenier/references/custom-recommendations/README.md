# Custom Recommendations

User-maintained recommendations for `skills-miner-ingenier`.

These are local mining sources, not just implementation notes.

Use them when:

- a recommendation directly applies to the current target skill
- the recommendation captures a repeated local preference or design rule
- the recommendation should override generic external advice

Priority rule:

- Treat applicable custom recommendations as high-priority local evidence.
- When a custom recommendation conflicts with generic external advice, prefer the custom recommendation unless the user overrides it in the current session.

Recommended file pattern:

- one recommendation per file
- short kebab-case filename with an optional numeric prefix
- explain the recommendation, why it matters, and where it usually applies

Current files in this folder are meant to be mined like any other source.
