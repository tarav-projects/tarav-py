"""Thin command surface for the typed DOI registry."""
# tarav.breadcrumb 09b57325812a

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from . import Archive, DOI
from .model import LocalLocator, RemoteLocator, RepositoryDOI, RepositoryHints


def _command(args):
    try:
        archive = Archive(args.registry)
        if args.operation == "init":
            archive.store.create()
            result = {"registry": str(archive.root)}
        elif args.operation == "list":
            result = {"ids": list(archive.ids())}
        elif args.operation == "show":
            result = archive.read(args.doi).records.to_record()
        elif args.operation in {"register", "update"}:
            payload = json.loads(Path(args.record).read_text())
            obj = archive.store.records.from_record(payload)
            if not isinstance(obj, DOI):
                raise ValueError("Record must declare a DOI Type")
            method = archive.register if args.operation == "register" else archive.update
            result = method(obj).records.to_record()
        else:
            locators = [LocalLocator(args.path)]
            locators.extend(RemoteLocator(uri) for uri in args.remote)
            hints = RepositoryHints.collect(args.path) if args.collect_hints else None
            result = archive.register(RepositoryDOI(label=args.label, locators=locators,
                                                    hints=hints)).records.to_record()
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, TypeError, LookupError) as exc:
        raise CliError(str(exc)) from exc


def register_archive_commands(subparsers):
    parser = subparsers.add_parser("archive", help="Maintain typed DOI resource declarations.")
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("init", "list", "show", "register", "update", "repository"):
        command = commands.add_parser(operation)
        command.add_argument("--registry", help="Record Registry partition; defaults to Archive's partition.")
        command.add_argument("--json", action="store_true", help="Output is JSON.")
        if operation == "show":
            command.add_argument("--doi", required=True)
        elif operation in {"register", "update"}:
            command.add_argument("--record", required=True, help="Typed DOI JSON Record.")
        elif operation == "repository":
            command.add_argument("--path", required=True)
            command.add_argument("--label")
            command.add_argument("--remote", action="append", default=[])
            command.add_argument("--collect-hints", action="store_true", help="Read a bounded local Git commit sample.")
        command.set_defaults(handler=_command)
