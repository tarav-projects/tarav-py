# Best-effort mechanics

<!-- tarav.sessions
3dbc7074 = codex:01a0baed-f147-77e2-b298-ed15249a9410 @3dbc7074117a70b90f57c98b25690d3ea15a519f0da6e05043e59b8add00d3c4
-->

Tarav should use small, best-effort mechanical primitives to reduce common operational problems. Shared primitives may provide locking, atomic file operations, state inspection, and POI production for workflows such as Breadcrumb submission.
<!-- tarav.breadcrumb 79af7eb685adc60b77ad0b1783042198d846846c46dffea9775667270b002d79 -->
<!-- tarav.breadcrumb 967eb46cb7f31ebdb69763293e54fbd4e465920b72d9f139941958522d1ff814 -->

The system does not need perfect consistency or automatic recovery. It should preserve sufficient evidence about partial and contradictory states, detect those states where practical, and surface them as POIs with enough context for agents to decide how to repair them. Keeping recovery agent-operated allows the mechanical implementation to remain small and simple.
<!-- tarav.breadcrumb 9d9a5562b8b9887ed821f67fd2ab0c2187668575345662ecc9413dfcf31726af -->
<!-- tarav.breadcrumb 2c2dab8e791533722269d32395aba83c91857fec96f461b9d76a5e5def846e30 -->
