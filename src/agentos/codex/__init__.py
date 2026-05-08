from __future__ import annotations


def register_codex_commands(subparsers) -> None:
    from .commands import register_codex_commands as register

    register(subparsers)

__all__ = [
    "register_codex_commands",
]
