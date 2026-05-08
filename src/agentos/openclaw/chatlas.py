from __future__ import annotations


OPENCLAW_CHATLAS_DEFAULT_INCLUDES = (
    "agents/*/sessions/**",
    "agents/*/agent/*.md",
    "agents/*/agent/*.json",
    "agents/*/agent/*.toml",
    "agents/*/agent/*.yaml",
    "agents/*/agent/*.yml",
    "agents/*/agent/*.ini",
    "workspace/AGENTS.md",
    "workspace/BOOTSTRAP.md",
    "workspace/HEARTBEAT.md",
    "workspace/IDENTITY.md",
    "workspace/SOUL.md",
    "workspace/TOOLS.md",
    "workspace/USER.md",
    "cron/jobs.json",
)

OPENCLAW_CHATLAS_DEFAULT_EXCLUDES = ("agents/*/agent/auth*.json",)


__all__ = [
    "OPENCLAW_CHATLAS_DEFAULT_EXCLUDES",
    "OPENCLAW_CHATLAS_DEFAULT_INCLUDES",
]
