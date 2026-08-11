# $kw: ^wayfinder-poi-command --from POI.System --from POI.Linter --note [CT] Wayfinder registry checks use the common POI report boundary ^c20260729-49u
"""CLI adapter for the Agentos Wayfinder library."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from agentos._core.errors import CliError

from .model import (
    WayfinderError,
    WayfinderReference,
    WayfinderReferenceRoot,
    WayfinderResolutionPOI,
    parse_reference,
)
from .registry import WayfinderRegistry, WayfinderRegistryCheck
from .resolver import Wayfinder


class WayfinderCheckReport(Protocol):
    def as_dict(self) -> dict[str, object]: ...


WayfinderCheckReportBuilder = Callable[
    [WayfinderRegistryCheck, str], WayfinderCheckReport
]


def _cmd_register(args: argparse.Namespace) -> int:
    try:
        root = (
            WayfinderReferenceRoot(type="package.skill", id=args.package)
            if args.package
            else WayfinderReferenceRoot.from_dict(_load_json(args.root_json, "root"))
        )
        hints = tuple(args.hint) + tuple(
            _load_json(value, "relocation hint") for value in args.hint_json
        )
        evidence = (
            _load_json(args.identity_evidence_json, "identity evidence")
            if args.identity_evidence_json
            else None
        )
        registry = WayfinderRegistry()
        registration = registry.register(
            root,
            Path(args.path),
            relocation_hints=hints,
            identity_evidence=evidence,
        )
    except (OSError, WayfinderError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "status": "registered",
            "registry": str(registry.path),
            "registration": registration.as_dict(),
        }
    )
    return 0


def _cmd_resolve(args: argparse.Namespace, *, wayfinder: Wayfinder) -> int:
    if bool(args.reference) == bool(args.reference_json):
        raise CliError("provide exactly one reference or --reference-json")
    try:
        reference = (
            WayfinderReference.from_json(args.reference_json)
            if args.reference_json
            else parse_reference(args.reference)
        )
        result = wayfinder.resolve(reference)
    except WayfinderError as exc:
        raise CliError(str(exc)) from exc
    _print_json(result.as_dict())
    return 1 if isinstance(result, WayfinderResolutionPOI) else 0


def _cmd_check(
    args: argparse.Namespace,
    *,
    report_builder: WayfinderCheckReportBuilder,
) -> int:
    registry = WayfinderRegistry()
    result = registry.check()
    _print_json(
        report_builder(
            result,
            str(registry.path),
        ).as_dict()
    )
    return 0 if result.ok else 1


def register_wayfinder_commands(
    subparsers: argparse._SubParsersAction,
    *,
    wayfinder: Wayfinder,
    check_report_builder: WayfinderCheckReportBuilder,
) -> None:
    parser = subparsers.add_parser(
        "wayfinder",
        help="Resolve portable Agentos references through registered roots.",
    )
    commands = parser.add_subparsers(dest="wayfinder_command", required=True)

    register = commands.add_parser(
        "register",
        help="Remember the verified location of a reference root.",
    )
    root = register.add_mutually_exclusive_group(required=True)
    root.add_argument(
        "--package",
        help="Package.Skill identity to register.",
    )
    root.add_argument(
        "--root-json",
        help="Canonical Wayfinder.Reference.Root JSON object.",
    )
    register.add_argument("--path", required=True, help="Reachable root directory.")
    register.add_argument(
        "--hint",
        action="append",
        default=[],
        help="Natural-language relocation hint. Repeatable.",
    )
    register.add_argument(
        "--hint-json",
        action="append",
        default=[],
        help="Structured JSON relocation hint. Repeatable.",
    )
    register.add_argument(
        "--identity-evidence-json",
        help="Optional JSON evidence used when verifying root identity.",
    )
    register.set_defaults(handler=_cmd_register)

    resolve = commands.add_parser(
        "resolve",
        help="Resolve an index:// sugar reference or canonical reference JSON.",
    )
    resolve.add_argument(
        "reference",
        nargs="?",
        help="Portable reference sugar, currently index://package/block.",
    )
    resolve.add_argument(
        "--reference-json",
        help="Canonical Wayfinder.Reference JSON object.",
    )
    resolve.set_defaults(
        handler=lambda args: _cmd_resolve(args, wayfinder=wayfinder)
    )

    check = commands.add_parser(
        "check",
        help="Check remembered root locations without repairing them.",
    )
    check.set_defaults(
        handler=lambda args: _cmd_check(
            args,
            report_builder=check_report_builder,
        )
    )


def _load_json(value: str, label: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid {label} JSON: {exc}") from exc


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


__all__ = ["register_wayfinder_commands"]
