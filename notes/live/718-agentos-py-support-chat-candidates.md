# agentos-py Support Chat Candidates

## Result

- status: clean candidate extraction
- heuristic: resolved Chatlas anchors present in production Python annotations under `src/agentos/**/*.py`
- scanned files: 190
- resolved anchors: 13 / 13
- candidate chats: 8
- findings: 0
- standing: candidates only; `agentos-py` currently has no local or package Index surface establishing mandatory `Project.Support.Chats` closure

## Reproduction

```bash
agentos chatlas anchory sessions \
  --source src/agentos \
  --glob '*.py' \
  --regex '\^(?P<anchor>c\d{8}-\d+[a-z]?)' \
  --json
```

Tests were intentionally excluded because fixture anchors can collide with live-looking anchor keys. `AGENTS.md` and prose notes were excluded because examples and historical discussion are weaker project-relevance signals than production-code annotations.

## Candidates

### Stronger by distinct anchor count

- `70f37740ee2f60bf0a03905329a478a64da5cee1f0c84ab838e2c5d77fcccb5a`
  - `codex` / `019f98cf-a0bf-7b63-8fe1-5936d8f6d570`
  - anchors: 5 — `c20260725-12u`, `c20260725-14u`, `c20260725-15u`, `c20260725-25u`, `c20260725-32u`
  - concentration: Skillware commands and edition history
  - Chat.Index: `missing`
  - URI: `agentos://chat-session/codex/46626a3c3c87c26a0f98210757f09592b8c516e3877777e33e37653cb9706ded/019f98cf-a0bf-7b63-8fe1-5936d8f6d570`
- `29bf3344a529cae123bafe3a42966c1464029644967fbd31af37f232e1b3dff8`
  - `codex` / `019f94cb-153d-79f1-9cfb-828545d7b4dc`
  - anchors: 2 — `c20260729-46u`, `c20260729-49u`
  - concentration: Wayfinder plus the shared POI/linter annotation applied across 24 production files
  - Chat.Index: `missing`
  - URI: `agentos://chat-session/codex/46626a3c3c87c26a0f98210757f09592b8c516e3877777e33e37653cb9706ded/019f94cb-153d-79f1-9cfb-828545d7b4dc`

### Single-anchor candidates

- `129193c615fb3ab1f23ea81c974294d360660bece753a6bdc5fca2bcfeb62604` — `codex` / `019fb4de-328e-7622-bb70-faa01998199b` — `c20260730-33u` — Anchory amendment validation — Chat.Index: `missing`
- `2933093622370cfdd5ef597dc4285277eadff4d320c1b9a40f698ce53dfcafdb` — `codex` / `019fbfbd-6fa3-74c0-a6dc-206aa3b3cb25` — `c20260802-103u` — Index line identity and collision semantics — Chat.Index: `missing`
- `6f7f95adf906608bf1b0b2409681f8e5ee7ded5d4247803120a4e816af37e9fb` — `claude-code` / `f3ea0509-5568-4a10-884b-bf1991962d29` — `c20260722-24u` — Skillware model — Chat.Index: `missing`
- `7a5f398c43a3109ceddadc95e6d0b22c8d1b06abe334cf27b8447f37dac89ccf` — `codex` / `019f95b4-2a99-7053-a8da-8eb30cee4fcf` — `c20260724-31u` — Bloberia — Chat.Index: `missing`
- `942769cb32608188fa1acb30bb4fb07f09c3fbbf55431fa6ec51243f9609455f` — `codex` / `019f9910-2823-7ad2-a89e-be08084e11cf` — `c20260725-27u` — Skillware build/model — Chat.Index: `missing`
- `fb3b663159176ce44af1456ea6ea309a1caec77407d136754a571c29cdc8ab38` — `codex` / `019fb5c1-7d23-7332-8654-2e863e4e7ef0` — `c20260802-1u` — Skillware context — Chat.Index: `materialized`

## Anchor Coverage

- `c20260722-24u` — 1 file: `src/agentos/skillware/model.py`
- `c20260724-31u` — 3 Bloberia files
- `c20260725-12u`, `c20260725-14u`, `c20260725-15u`, `c20260725-25u`, `c20260725-32u` — Skillware commands and edition-history surfaces
- `c20260725-27u` — 3 Skillware build/model files
- `c20260729-46u` — 3 Wayfinder files
- `c20260729-49u` — 24 shared POI/linter-related files
- `c20260730-33u` — 2 Anchory files
- `c20260802-103u` — 2 Index identity/linter files
- `c20260802-1u` — 1 Skillware context file

## Follow-up Candidates

- Add project-local Index support to `agentos-support-chats` if project indexes should materialize the same registry contract as package indexes.
- Decide whether production-code annotation anchors are an accepted candidate heuristic or only a diagnostic hint.
- Agent-review the eight chats before accepting any into a future `Project.Support.Chats` registry.
- Capturing the seven missing Chat.Index surfaces would make later review cheaper; this is not automatic authorization to capture them.
