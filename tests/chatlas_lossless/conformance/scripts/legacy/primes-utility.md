# Chat.Script: primes-utility

> A `Chat.Script` is a fixed, verbatim sequence of user turns run identically across
> providers. Each provider run produces a native session; Chatlas normalizes each into a
> `Chatlas.Session.Model`. The cross-provider test asserts the **neutral projection**
> (messages / tool.call / tool.result) converges, tolerating native telemetry divergence.

- **target:** tool-call / tool-result event pairing + chronological ordering
- **lineage:** none (linear tape expected)
- **status:** draft — canonical turns below; claude take is pre-canonical (see drift note)

## Canonical user turns

Paste these verbatim, in order, identically into every provider. Do not paraphrase.

1. Create a new folder called primes-lab in the current directory and cd into it.
2. Write a Python file primes.py that prints all prime numbers below a number given as the first CLI argument.
3. Run it with the argument 30 and show me the output.
4. There's an off-by-one risk — does it correctly handle the case where the argument itself is prime? Test it with 31.
5. Add a short README.md explaining how to run the script.
6. List the files in the folder so I can confirm what we created.
7. Summarize everything we did in this session as a numbered list.

## Expected neutral shape

Assert structure, not payload. Prose/stdout wording differs across providers and is tolerated.

- message events: 7 user + N assistant (N >= 7)
- tool.call / tool.result: >= 3 paired (folder, run, ls minimum); >= 2 of the calls name a write tool (primes.py, README.md)
- lineage refs: 0 (linear tape)
- final assistant event: long-form summary message
- native-tolerated (do NOT compare across providers): session.update, usage, metric, and any other provider telemetry kinds

## Recorded provider sessions

Acceptance filter: a session enters the corpus only if its `payload.role==user` turns are
**verbatim-identical and in order** to the canonical turns above. Everything else (assistant
count, tool count, telemetry) varies by provider and run and is observational, not a filter.

| provider | session_id | identity_hash | captured | note |
|---|---|---|---|---|
| claude-code | 4ca705e4-39cc-4cf1-a991-c32cf4d1df6e | 32fff3f05465871f5d1e532221d0af569653dbb2d8ca2a8a4ef8ad4e57e35170 | 2026-06-29 | verbatim-identical; project cc-tmp |
| claude-code | aa268f60-ff6a-4555-a8a0-e955626ca5a9 | 87178affa7515ef066533f85dd6747f87cd879be888a59f53c42a3f5f0897883 | 2026-06-29 | verbatim-identical; 2nd run (determinism sample); project tmp2 |
| claude-code | 67ab8040-dccf-4fa7-8b70-d8b62f3ca1d1 | 31b549e954cd3fa23bd8a7386a3d3a135b79ee7f1fb953fd76a0f3343d5e7c1f | 2026-06-29 | verbatim-identical; project tmp |
| claude-code | 7be05340-ee20-4752-a573-1f99ecb2b2ff | 111825aeafde5078d64fc8a8704bb80b879953c02af81df9b162de4edd145270 | 2026-06-29 | verbatim-identical; project tmp3 |
| codex | 019f133f-036b-7500-8e97-ffc790b0d628 | 78b5460cc1a4188bbf037f089d4a8ae3c66cfee46c90390c8f92fa90fafcad49 | 2026-06-29 | verbatim-identical; project tmp2 |
| codex | 019f1413-d5a3-7452-83e4-89713516f9f1 | 393962736f1b0258166e1c980100e39007d6a84a07262ba4767d382eecd3ae85 | 2026-06-29 | verbatim-identical; project tmp2 |
| codex | 019f1381-812f-7d53-af64-aaaf76d965b9 | f1a1fc532ab65e10c18d26c7aa9c699860e7abc46ef77b9adb798099fda88e84 | 2026-06-29 | verbatim-identical; project tmp4 |
| claude-code | 615fdc15-9ba3-48ea-b6fb-e50b68277091 | 90a478aa495883971307fbb25e14b4ec0cfa91c4809bd8c1dcbe505eafd5ba3b | 2026-06-29 | verbatim-identical; project tmp |
| claude-code | f900be15-ca13-4ca8-b7ea-d82e4a88b3b5 | 730be494c773fa254c9be0424c71d3ab4fcc8855b42cc39a5cf112980a361bf7 | 2026-06-29 | verbatim-identical; project tmp2 |
| codex | 019f1423-540b-76f3-be39-420ec24d25b5 | 96f603309ed5ed8d25a0594c5b81d45d8e211d7e52ad435e8ca70b022735f3e8 | 2026-06-29 | verbatim-identical; project tmp3 |
| codex | 019f1422-f373-7760-aa3e-6a2da1f853c1 | a1e54eb3e1ee8c5b35e5dbe0a7e9f18817c98f46bc076067f74178c973b7f3b3 | 2026-06-29 | verbatim-identical; project tmp4 |

<!-- Add one row per provider run. identity_hash is the stable join key; session_id is provider-native. -->
