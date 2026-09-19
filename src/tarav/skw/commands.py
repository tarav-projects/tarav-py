"""Public SKW command composition."""

from __future__ import annotations

import argparse

from .document import register_commands as register_document_commands
from .skills import register_commands as register_skill_commands, skill_document


def register_skw_commands(subparsers: argparse._SubParsersAction, *, registry) -> None:
    parser = subparsers.add_parser(
        "skw",
        help="Compile typed SKW documents and operate skill packages.",
    )
    commands = parser.add_subparsers(dest="skw_command", required=True)
    def document_factory(source, *, project=None):
        return skill_document(source, project=project, registry=registry)

    register_document_commands(commands, document_factory=document_factory)
    register_skill_commands(commands, registry=registry)


__all__ = ["register_skw_commands"]
