# Tapes System Design Discussion

1. **AgentOS identity** — An OS for agentic workflows, aiming for simplicity, interactivity, and modularity.

2. **Core vs stdlib separation** — Core provides primitives; stdlib provides useful compositions of those primitives (e.g., common scan patterns, miners); proven project-level workflows can graduate to stdlib.

3. **AgentOS is a hybrid system** — It combines traditional code with skill/agent definitions; projects can use and compose from both layers.

4. **Tapes as primitive** — Append-only JSONL files serving as a general-purpose data structure for agents, analogous to files in a Unix filesystem.

5. **Tape versatility** — A single tape can serve as log, index, projection, or SSOT depending on how it's used, not how it's defined.

6. **Tape ownership is a pattern, not a rule** — Subsystems/agents *can* have their own tapes, but this is a common convention, not a constraint.

7. **Composability via cross-references** — Tapes can link to records in other tapes, keeping each tape focused on what's uniquely relevant.

8. **SSOT tapes** — Certain tapes can be designated as the single source of truth for a specific kind of data/result.

9. **Temporary vs foundational tapes** — Some tapes are ephemeral, others are meant to persist long-term (lifecycle details deferred).

10. **Tapes as cleaned projections** — Tapes serve as curated, queryable views of messy source material, making them easier to work with than raw sources.

11. **Accumulative cognitive spending** — Tapes let you invest inference in small chunks over time, appending analysis progressively and adapting to different cost budgets.

12. **Minimal contract for cross-referencing** — AgentOS must define a stable way to address records across tapes (an OS-level responsibility).

13. **Link resolution is an OS job** — The deterministic CLI layer handles hydrating/resolving tape cross-references, not the agent.

14. **Hybrid architecture (agents + OS)** — Cognitive tasks stay in the agent; deterministic operations (query, resolve, dedup checks) belong to the OS/CLI layer.

15. **Dedup: prior strategy** — Load top-N previously known items into the agent's prompt to prevent redundant findings.

16. **Dedup: posterior strategy** — Query the tape after a scan to catch duplicates that slipped past the prior filter.

17. **Self-tuning dedup** — Track collision frequency on the tape; the most-collided items get promoted to the prior context, pushing discovery toward novel findings.

18. **MVP workflow: TODO miner** — A skill that scans a codebase for TODO-like items (both explicit tags and semantic matches) and writes findings to a tape.

19. **Miner as an agent skill** — Stored under `agentos/skills`, it's the first concrete consumer of the tape system.

20. **Semantic reasoning in mining** — The miner should go beyond pattern matching; it uses LLM judgment to find implicit TODOs, not just tagged ones.

21. **Tape capabilities driven by MVP** — The TODO miner defines what tape operations are needed; if the current implementation falls short, redesign it.

22. **Don't overspecify** — Design decisions should stay at the primitive level; avoid baking in assumptions that belong to higher-level workflows.
