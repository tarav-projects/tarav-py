<!-- tarav.sessions
4571385e = codex:01a06bed-b554-7770-86e3-cce2e5729994 @4571385eb2c5457a615e836d943acad00147fda45a10dbad26848faf81e2bfe1
91c6e789 = codex:01a05752-fa8d-7c62-abb2-5ff20c8260da @91c6e789df50d874a454107ba81ff86be1e99022173b3469fbcdeffaedbf86c1
-->

# Product-Surface Context References — E2E Test

Product surfaces may point directly to relevant User-Touched conversation through document-local session aliases and compact Chatlas Turn-hash prefixes.
<!-- tarav.context 4571385e:dd358589d092f9dd -->
<!-- tarav.context 91c6e789:0aac2ee71066d117 -->

The session declaration records the provider and native session ID once. Inline references contain only an alias and a short Turn-hash prefix; they do not repeat a session hash, Turn address, or full hash.
<!-- tarav.context 91c6e789:aec74b84afe504d6 -->

A context reference means only that the annotating Agent selected the Turn as relevant context for the nearby surface. It does not by itself claim authorship, approval, factual support, or semantic validation.
<!-- tarav.context 4571385e:dd358589d092f9dd -->

The notation is provisional. Markdown, LaTeX, Python, slides, and other surfaces may later specialize how the same reference is embedded or rendered.
<!-- tarav.context 91c6e789:0aac2ee71066d117 -->

For this lightweight Agent-operated workflow, session aliases are a current-surface writing convention. The workflow reuses visible aliases and does not consult Git history or an additional Tarav registry by default.
<!-- tarav.context 91c6e789:0aac2ee71066d117 -->

This experiment intentionally uses minimal Tarav infrastructure: Chatlas resolves the declared sessions and Turn prefixes, while the annotated product surface remains ordinary Markdown.
<!-- tarav.context 91c6e789:0aac2ee71066d117 -->

## Test boundary

This note tests whether a human-readable surface can carry compact references that an Agent can resolve back to exact User Turns. It does not define the final reference grammar, a generalized fragment-addressing system, or a permanent parser.
