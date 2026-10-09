"""CLI adapter for the Operator Context store."""

from __future__ import annotations

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import entity
from tarav.l0.kernel.current import current_records
from tarav.l1.records import RecordRegistry

from . import OperatorContext, OperatorContextStore


def _store(args) -> OperatorContextStore:
    registry = RecordRegistry(Path(args.registry)) if args.registry else None
    return OperatorContextStore(registry)


def _output(value) -> int:
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


def _session() -> dict | None:
    from tarav.l1.agent.current_session import CurrentSessionError, current_session

    try:
        found = current_session()
    except CurrentSessionError:
        return None
    return {"provider": found.provider, "session_id": found.session_id}


def _project(path: str | None) -> dict | None:
    if path is None:
        return None
    from tarav.l0.project import resolve_agentos_project

    found = resolve_agentos_project(Path(path))
    if found is None:
        raise CliError(f"No Tarav Project at {path}")
    marker = found.require_marker()
    return {"id": marker.project_id, "root": str(Path(marker.root).resolve())}


def _fields(args) -> dict:
    if (args.data is None) == (args.file is None):
        raise CliError("Give the object's fields with exactly one of --data or --file")
    text = args.data if args.data is not None else Path(args.file).read_text(encoding="utf-8")
    fields = json.loads(text)
    if not isinstance(fields, dict):
        raise CliError("The object's fields must be a JSON object")
    reserved = {"type", "id", "created_at", "project", "session"} & set(fields)
    if reserved:
        raise CliError(f"These fields are set by the store: {', '.join(sorted(reserved))}")
    return fields


# tarav.breadcrumb a6efd61c89a948edb23f371d068306f354421850a857b82ff015281bcff2245b
def _cmd_put(args) -> int:
    """Place a new object, or replace the fields of an existing one."""
    store = _store(args)
    fields = _fields(args)
    if args.id is not None:
        current = store.load(args.id)
        if args.type is not None and entity(type(current)).name != args.type:
            raise CliError(f"Object {args.id} is {entity(type(current)).name}, not {args.type}")
        context = type(current)(
            current.id, created_at=current.created_at,
            project=_project(args.project) if args.project else current.project,
            session=current.session, **{**current.fields, **fields})
    else:
        if args.type is None:
            raise CliError("A new object needs --type")
        context_type = current_records().resolve_type(args.type)
        if not issubclass(context_type, OperatorContext):
            raise CliError(f"{args.type} is not an Operator Context Type")
        context = context_type.new(project=_project(args.project), session=_session(), **fields)
    key = store.put(context)
    return _output({"status": "ok", "id": key, "type": entity(type(context)).name,
                    "store": str(store.map.root)})


def _cmd_show(args) -> int:
    intake = _store(args).take(args.id)
    return _output({"status": "ok", "hash": intake.hash, "record": intake.record})


def _cmd_list(args) -> int:
    store = _store(args)
    rows = []
    for name in store.names():
        context = store.load(name)
        if args.session_id and (context.session or {}).get("session_id") != args.session_id:
            continue
        rows.append({"id": name, "type": entity(type(context)).name,
                     "created_at": context.created_at, "project": context.project,
                     "session": context.session})
    return _output({"status": "ok", "store": str(store.map.root), "objects": rows})


def _cli(handler):
    def run(args):
        try:
            return handler(args)
        except (OSError, ValueError, TypeError) as error:
            raise CliError(str(error)) from error
    return run


def register_operator_context_commands(subparsers) -> None:
    parser = subparsers.add_parser(
        "operator-context",
        help="Place and read the typed objects an operator hands to other workflows.")
    commands = parser.add_subparsers(dest="operator_context_command", required=True)

    put = commands.add_parser("put", help="Place an object, or change one with --id.")
    put.add_argument("--type", help="Operator Context Type name; required for a new object.")
    put.add_argument("--data", help="The object's fields, as a JSON object.")
    put.add_argument("--file", help="A JSON file holding the object's fields.")
    put.add_argument("--id", help="An existing object whose fields are replaced.")
    put.add_argument("--project", help="A folder of the Project the object is about.")
    put.set_defaults(handler=_cli(_cmd_put))

    show = commands.add_parser("show", help="Show one object and the hash of its record.")
    show.add_argument("--id", required=True)
    show.set_defaults(handler=_cli(_cmd_show))

    listing = commands.add_parser("list", help="List the objects in the store.")
    listing.add_argument("--session-id", help="Only objects placed by this session.")
    listing.set_defaults(handler=_cli(_cmd_list))

    for command in (put, show, listing):
        command.add_argument("--registry", help="Record Registry root; defaults to the standard one.")
