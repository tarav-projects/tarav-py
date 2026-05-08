from __future__ import annotations


COPILOT_CHATLAS_DEFAULT_INCLUDES = (
    "session-state/**/events.jsonl",
    "session-state/*.jsonl",
    "session-state/**/files/**",
    "session-state/**/plan.md",
    "session-state/**/checkpoints/*.md",
    "copilot-instructions.md",
)

COPILOT_CHATLAS_DEFAULT_EXCLUDES = (
    "pkg/",
    "logs/",
    "ide/",
    "session-state/**/workspace.yaml",
    "session-state/**/checkpoints/index.md",
    "session-state/**/vscode.metadata.json",
    "session-state/**/session.db",
    "session-state/**/rewind-snapshots/**",
    "session-state/**/*.lock",
    "command-history-state.json",
    "config.json",
)


__all__ = [
    "COPILOT_CHATLAS_DEFAULT_EXCLUDES",
    "COPILOT_CHATLAS_DEFAULT_INCLUDES",
]
