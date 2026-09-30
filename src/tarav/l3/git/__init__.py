"""Installed Git process adapters."""

from .commands import register_breadcrumb_git_commands, register_commands

__all__ = ["register_breadcrumb_git_commands", "register_commands"]
