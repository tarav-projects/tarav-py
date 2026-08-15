# Chat.Script: knights-knaves

A tool-free logic-puzzle conversation that isolates reasoning and assistant `message`
fragments. It carries no file, shell, or web work, so a faithful tape has zero tool events —
the defining property that makes reasoning divergence readable.

- **target:** `reasoning` events + assistant `message` fragments, with tool events absent
- **lineage:** none intended (linear tape); an interrupted+rerun capture will introduce a fork
- **status:** draft — one diagnostic session recorded (see below)

## Canonical user turns

Paste these verbatim, in order, identically into every provider. Do not paraphrase.

1. Let's reason through a logic puzzle together — think it through in words, and don't write or run any code. On an island, every inhabitant is either a knight (always tells the truth) or a knave (always lies). You meet two people, A and B. A says: "At least one of us is a knave." What are A and B?
2. Walk me through why A cannot be a knave.
3. Now a harder variant: A says "B is a knight" and B says "We are of opposite types." What are A and B?
4. I think you made a mistake — check your reasoning about B again.
5. Step back: what general strategy are you using to solve these? Describe the method, not the answers.
6. Suppose a third type existed — a spy who can either lie or tell the truth freely. Would your method still work? Reason it through.
7. Summarize the key reasoning principles we covered as a numbered list.

## Expected neutral shape

Assert structure, not payload. Reasoning wording differs across providers and is tolerated.

- message events: 7 user + N assistant (N >= 7)
- tool.call / tool.result: **0** — the defining property; any tool event means the script leaked or a provider ignored the steer, and is logged per-session
- `reasoning` events: expected wherever the provider raw carries thinking; a provider whose raw has thinking but whose normal tape has no `reasoning` is a lossy normalizer gap
- lineage refs: 0 on a clean capture

## Recorded provider sessions

Acceptance filter: a session enters the corpus only if its conversational `payload.role==user`
turns are verbatim-identical and in order to the canonical turns above, after stripping
local-command and `command-name` messages.

| provider | session_id | identity_hash | captured | note |
|---|---|---|---|---|
| claude-code | e38f8b71-6fef-41e8-96c3-c13136aa8e94 | 76aa35f2a24426ee466384e911ac136feba9fb0ddb6f55e2e913d46d32feb750 | 2026-07-02 | clean; tool-free (0); reasoning events 0 |
| claude-code | 838d2d58-5ed7-4f19-8690-1059cd6320c4 | 8fc3013bd67427da3684589daec2f00765da7db6baacd5c5631b7cc38b377a88 | 2026-07-02 | clean; tool-free (0); reasoning events 0 |
| codex | 019f225c-20f4-77b0-a4b6-0739c375cecc | 803cfea816f750ff759a484be7d7185c9ad143da9f1353abf12103358bf7a952 | 2026-07-02 | clean; tool-free (0); reasoning events 4 |
| codex | 019f2277-4eb2-7e01-9ee8-b03cd78b8248 | bdcbf7843c960c30ac0f8a491cf311aeb47764a3e94b57b81fb1bc4809b397ea | 2026-07-02 | clean; tool-free (0); reasoning events 5 |
| claude-code | 0c8644ed-5d25-490f-9c8c-7bdb705c7270 | 9e360a787d2d388d874ec746dd1b04f3ce65f126e3872dc7f21bd9f38db4de2d | 2026-07-02 | diagnostic, not clean-corpus: interrupted+rerun (lineage fork) and local-command/`/exit` noise in the user stream; tool-free held (0 tool events); source of findings F1 and F2 |
