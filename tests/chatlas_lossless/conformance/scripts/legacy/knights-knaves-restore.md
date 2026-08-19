# Chat.Script: knights-knaves-restore

A restore/rollback variant of `knights-knaves`. It runs the base turns, then uses an executer
direction to roll the conversation back to a previous turn and take a different continuation —
producing a true fork (one parent, two child turns). It probes `Session.Lineage`.

- **base:** `knights-knaves` turns 1–3, then a fork at turn 3
- **target:** `Session.Lineage` — abandoned branch vs active path after a rollback
- **status:** four valid captures recorded (2 claude fork, 2 codex rollback); source of finding F3

## Operator run

Turns 1–4 are the base `knights-knaves` turns; turn 4 is the branch that gets abandoned.

1. (base turn 1) Let's reason through a logic puzzle together — think it through in words, and don't write or run any code. On an island, every inhabitant is either a knight (always tells the truth) or a knave (always lies). You meet two people, A and B. A says: "At least one of us is a knave." What are A and B?
2. (base turn 2) Walk me through why A cannot be a knave.
3. (base turn 3) Now a harder variant: A says "B is a knight" and B says "We are of opposite types." What are A and B?
4. (abandoned) I think you made a mistake — check your reasoning about B again.
   - » EXECUTER DIRECTION — RESTORE: after the assistant answers turn 4, roll the conversation back to the state just after turn 3 (turn 4 and its response become an abandoned branch). «
5. (active, sent from the turn-3 fork point) Good. Now a different challenge: can a single inhabitant ever truthfully say "I am a knave"? Reason it out.
6. Summarize the key reasoning principles we covered as a numbered list.

## Resulting lineage

- fork point: turn 3's response
- children: turn 4 (abandoned) and turn 5-alt (active)
- active visible path: turns 1, 2, 3, 5-alt, 6

## Same-experiment check (raw)

Both providers execute the same script and the same rollback; only the native encoding differs.

- claude: DAG via `parentUuid` — turn 4 and turn 5-alt share the parent (turn 3's response);
  the abandoned branch stays reachable off the active path.
- codex: linear rollout plus a `thread_rolled_back` sentinel — turn 4 and its response sit inline
  before the sentinel; turn 5-alt continues after it.

A capture is valid only if the rollback actually happened: claude raw shows two children on one
parent; codex raw contains a `thread_rolled_back` record. A run without that signal is a failed
restore attempt, not a fork, and is discarded.

## Expected neutral shape

- active path user turns: 1, 2, 3, 5-alt, 6 (verbatim)
- lineage refs > 0 — turn 4 present but marked off the active path, referencing turn 3 as origin
- the tree projection shows turn 3 with two children
- tool events: 0 intended (codex may ignore the steer; logged per-session, not a failure)

## Recorded provider sessions

| provider | session_id | identity_hash | captured | note |
|---|---|---|---|---|
| claude-code | 4d113706-668b-44cf-a68a-91acc44e57a0 | 26ebb93f21812f3436432d23ab0b1bdb3f106f7c55e3fc7ea99a3fa7bdad8f94 | 2026-07-02 | valid fork; raw `parentUuid` two children on turn-3 response; normal flattened (F3) |
| claude-code | 36d3dd6b-4444-4102-b8b8-fd7303007110 | aca0026b14b6df92f3d11f62016514bcd729ef16dbc31a6b8f03b327fd5c63fb | 2026-07-02 | valid fork; normal flattened (F3) |
| codex | 019f23d3-95f8-71d1-b832-8bb63adcf269 | f0be13e80a85700d1e6e3fa9e6a9c066c6b933d779ed896953c0ac6e385b8dcb | 2026-07-02 | valid rollback; raw `thread_rolled_back` ×1; normal flattened (F3); codex used tools despite steer |
| codex | 019f23d3-a221-71c0-9cd2-f02e72b5a533 | 777b52c811fcd2bbb8cd5c02cee2c3de4a641d7e15cf90ce850c0c37885778c5 | 2026-07-02 | valid rollback; raw `thread_rolled_back` ×1; normal flattened (F3); codex used tools despite steer |
