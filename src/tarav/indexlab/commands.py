# $kw: --from User.Touched
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav.poi.runtime import (
    LinterReportSelectionError,
    build_linter_document,
    render_linter_text,
)

from .linter import CHECK_REGISTRY, lint_records, lint_store
from .model import (
    EvidenceNeighborhood,
    IndexRecord,
    Operation,
    RecordModelError,
    SupportSet,
)
from .projection import ProjectionError, fold_records, project_records
from .render import RenderError, render_kernel_writing
from .touch import UserTouchMock, UserTouchSource
from .workspace import IndexLibrary, IndexWorkspace, RecordStore, WorkspaceError


CAPTURE_MANIFEST_SCHEMA = "tarav.indexlab-capture-manifest.v1"
TOUCH_MOCK_FILENAME = "user-touch-mock.json"


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _open_library(args: argparse.Namespace) -> IndexLibrary:
    return IndexLibrary.open(Path(args.library))


def _open_workspace(args: argparse.Namespace) -> IndexWorkspace:
    return _open_library(args).resolve(args.workspace)


def _open_store(args: argparse.Namespace) -> RecordStore:
    return RecordStore(_open_workspace(args))


def _cmd_library_init(args: argparse.Namespace) -> int:
    try:
        library = IndexLibrary.initialize(Path(args.library))
    except WorkspaceError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-library-result.v1",
            "library": str(library.root),
        }
    )
    return 0


def _cmd_workspace_create(args: argparse.Namespace) -> int:
    try:
        library = _open_library(args)
        workspace = library.create_workspace(
            args.name,
            touch_adapter=args.touch_adapter,
        )
    except WorkspaceError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-workspace-result.v1",
            "library": str(library.root),
            "name": args.name,
            "id": workspace.id,
            "workspace": str(workspace.root),
            "depot": str(workspace.root),
            "touch_adapter": workspace.touch_adapter,
        }
    )
    return 0


def _cmd_workspace_list(args: argparse.Namespace) -> int:
    try:
        library = _open_library(args)
        entries = library.list_workspaces()
    except WorkspaceError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-workspace-list.v1",
            "library": str(library.root),
            "count": len(entries),
            "workspaces": [
                {
                    "name": entry.name,
                    "id": entry.id,
                    "workspace": str(entry.root),
                    "depot": str(entry.root),
                    "touch_adapter": entry.workspace.touch_adapter,
                }
                for entry in entries
            ],
        }
    )
    return 0


def _cmd_capture(args: argparse.Namespace) -> int:
    try:
        store = _open_store(args)
        manifest = json.loads(Path(args.manifest).read_text("utf-8"))
        records = _parse_manifest(manifest)
        stored = store.append_many(records)
    except (OSError, ValueError, RecordModelError, WorkspaceError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-capture-result.v1",
            "workspace": str(store.workspace.root),
            "captured": len(stored),
            "record_ids": [record.id for record in stored],
            "ordinals": [record.ordinal for record in stored],
        }
    )
    return 0


def _cmd_records(args: argparse.Namespace) -> int:
    try:
        store = _open_store(args)
        records = store.list()
    except WorkspaceError as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-record-list.v1",
            "workspace": str(store.workspace.root),
            "count": len(records),
            "records": [record.to_dict() for record in records],
        }
    )
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    try:
        store = _open_store(args)
        projection, errors = fold_records(store.list())
    except (WorkspaceError, ProjectionError) as exc:
        raise CliError(str(exc)) from exc
    if errors:
        raise CliError(
            "records do not fold into a coherent projection:\n"
            + "\n".join(f"- {error}" for error in errors)
        )
    _print_json(projection.to_dict())
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    try:
        projection = project_records(_open_store(args).list())
        rendered = render_kernel_writing(projection, block=args.block)
    except (ProjectionError, RenderError, WorkspaceError) as exc:
        raise CliError(str(exc)) from exc
    if rendered:
        print(rendered)
    return 0


# $kw: --note [DC] the lint command fails closed on the verified standing, not the clean one: a blocked check could not be evaluated, so it never earns a zero exit
def _cmd_lint(args: argparse.Namespace) -> int:
    if args.list_checks:
        for entry in CHECK_REGISTRY:
            state = "dev" if entry.dev else ("on " if entry.default_on else "off")
            print(f"{entry.name:26} [{state}] {entry.tier:11} {entry.source()}")
        return 0
    try:
        store = _open_store(args)
        mock_path = store.workspace.root / TOUCH_MOCK_FILENAME
        if store.workspace.touch_adapter == "mock":
            if not mock_path.is_file():
                raise WorkspaceError(
                    f"mock touch adapter requires {TOUCH_MOCK_FILENAME}: "
                    f"{store.workspace.root}"
                )
            source = UserTouchMock.from_dict(json.loads(mock_path.read_text("utf-8")))
        else:
            factory = getattr(args, "touch_source", None)
            if factory is None:
                raise WorkspaceError(
                    "no touch adapter is wired for this workspace's touch_adapter"
                )
            source = factory(Path(args.chatlas_root) if args.chatlas_root else None)
        report = lint_store(
            store,
            source=source,
            check=args.check,
            skip=args.skip,
            dev=args.lane == "dev",
            subjects=args.record_id,
            tripwires=args.tripwire,
        )
        document = build_linter_document(
            report,
            run_class="IndexLab.Linter.Run",
            limit=args.limit,
            poi_classes=args.poi_class,
            poi_ids=args.poi_id,
            statuses=args.status,
        )
    except (OSError, ValueError, WorkspaceError, LinterReportSelectionError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        _print_json(document)
    else:
        print(render_linter_text(document))
    return 0 if report.verified else 1


def _cmd_seed_mock(args: argparse.Namespace) -> int:
    try:
        store = _open_store(args)
        if store.workspace.touch_adapter != "mock":
            raise WorkspaceError(
                "mock scenario requires a workspace configured with touch_adapter 'mock'"
            )
        if store.list():
            raise WorkspaceError("mock scenario requires an empty Index.Workspace")
        source, records = _mock_scenario()
        stored = store.append_many(records)
        atomic_write_json(
            store.workspace.root / TOUCH_MOCK_FILENAME,
            source.to_dict(),
        )
        projection = project_records(stored)
        report = lint_records(stored, source=source)
        lint_document = build_linter_document(
            report,
            run_class="IndexLab.Linter.Run",
            limit=20,
        )
    except (OSError, ValueError, WorkspaceError, ProjectionError) as exc:
        raise CliError(str(exc)) from exc
    _print_json(
        {
            "schema": "tarav.indexlab-mock-scenario.v1",
            "workspace": str(store.workspace.root),
            "records": [record.to_dict() for record in stored],
            "projection": projection.to_dict(),
            "lint": lint_document,
        }
    )
    return 0 if report.verified else 1


def _parse_manifest(value: object) -> tuple[IndexRecord, ...]:
    if not isinstance(value, dict) or value.get("schema") != CAPTURE_MANIFEST_SCHEMA:
        raise ValueError(f"manifest schema must be {CAPTURE_MANIFEST_SCHEMA!r}")
    raw_records = value.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise ValueError("capture manifest records must be a non-empty list")
    return tuple(IndexRecord.from_dict(raw) for raw in raw_records)


def _mock_scenario() -> tuple[UserTouchMock, tuple[IndexRecord, ...]]:
    source = UserTouchMock()
    kernel_touch = source.add_turn(
        "mock-chat",
        "user",
        "Touched.Index is a maintained sequence of context-attached records.",
    )
    kernel_writer = source.add_turn(
        "mock-chat",
        "agent",
        "The record operation creates the Recording.Kernel block.",
    )
    units_touch = source.add_turn(
        "mock-chat",
        "user",
        "Index.Line is the capturable unit and Index.Block is the semantic unit.",
    )
    units_writer = source.add_turn(
        "mock-chat",
        "agent",
        "The line is captured inside the block.",
    )

    def support(user, agent) -> SupportSet:
        return SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="mock-chat",
                    grounding=(user.ref,),
                    context=(agent.ref,),
                ),
            )
        )

    records = (
        IndexRecord(
            id="mock-record-block",
            ordinal=0,
            context=source.record_context("mock-chat", kernel_writer.turn_ref),
            operation=Operation(
                type="block.create",
                parameters={
                    "block_id": "mock-block",
                    "isoblock_id": "mock-isoblock",
                    "name": "Recording.Kernel",
                },
            ),
            support=support(kernel_touch, kernel_writer),
        ),
        IndexRecord(
            id="mock-record-line",
            ordinal=0,
            context=source.record_context("mock-chat", units_writer.turn_ref),
            operation=Operation(
                type="line.capture",
                parameters={
                    "line_id": "mock-line",
                    "isoline_id": "mock-isoline",
                    "block_id": "mock-block",
                    "label": "^mock-semantic-units",
                    "text": "Index.Line is capturable; Index.Block is semantic.",
                },
            ),
            support=support(units_touch, units_writer),
            assertions=({"line_type": "DF"},),
        ),
    )
    return source, records


def _add_library_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--library",
        required=True,
        help="Explicit initialized Index.Library root; no default is inferred.",
    )


def _add_workspace_selector(parser: argparse.ArgumentParser) -> None:
    _add_library_argument(parser)
    parser.add_argument(
        "--workspace",
        required=True,
        help="Workspace name or stable UUID resolved through the selected library.",
    )


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


# $kw: --note [DC] the kernel declares the touch port and the composition root injects the adapter, so indexlab never imports the chat store it resolves through
def register_indexlab_commands(
    subparsers: argparse._SubParsersAction,
    *,
    touch_source: Callable[[Path | None], UserTouchSource] | None = None,
) -> None:
    parser = subparsers.add_parser(
        "indexlab",
        help="Experimental Touched.Index recording kernel in an explicit workspace.",
        description=(
            "Develop and inspect the experimental recording kernel. Every writer is "
            "confined to a workspace resolved through an explicit Index.Library."
        ),
    )
    commands = parser.add_subparsers(dest="indexlab_command", required=True)

    library_parser = commands.add_parser(
        "library", help="Initialize the explicit user-level workspace registry."
    )
    library_commands = library_parser.add_subparsers(
        dest="indexlab_library_command", required=True
    )
    library_init_parser = library_commands.add_parser(
        "init", help="Initialize an empty Index.Library."
    )
    _add_library_argument(library_init_parser)
    library_init_parser.set_defaults(handler=_cmd_library_init)

    workspace_parser = commands.add_parser(
        "workspace", help="Create or list independently rooted Index.Workspaces."
    )
    workspace_commands = workspace_parser.add_subparsers(
        dest="indexlab_workspace_command", required=True
    )
    create_parser = workspace_commands.add_parser(
        "create", help="Create a named workspace and its Bloberia/Git root."
    )
    _add_library_argument(create_parser)
    create_parser.add_argument("--name", required=True, help="Workspace name.")
    create_parser.add_argument(
        "--touch-adapter",
        choices=("chatlas", "mock"),
        default="chatlas",
        help="Explicit User.Touch adapter for this workspace.",
    )
    create_parser.set_defaults(handler=_cmd_workspace_create)
    list_parser = workspace_commands.add_parser(
        "list", help="List the library's workspace names, identities, and roots."
    )
    _add_library_argument(list_parser)
    list_parser.set_defaults(handler=_cmd_workspace_list)

    capture_parser = commands.add_parser(
        "capture", help="Append context-attached records from one JSON manifest."
    )
    _add_workspace_selector(capture_parser)
    capture_parser.add_argument("--manifest", required=True, help="Capture manifest JSON file.")
    capture_parser.set_defaults(handler=_cmd_capture)

    records_parser = commands.add_parser(
        "records", help="List the authoritative ordered Index.Record surface."
    )
    _add_workspace_selector(records_parser)
    records_parser.set_defaults(handler=_cmd_records)

    project_parser = commands.add_parser(
        "project", help="Fold records into the current semantic block projection."
    )
    _add_workspace_selector(project_parser)
    project_parser.set_defaults(handler=_cmd_project)

    render_parser = commands.add_parser(
        "render", help="Render the current semantic projection as Kernel.Writing."
    )
    _add_workspace_selector(render_parser)
    render_parser.add_argument(
        "--block",
        help="Render one exact active block by dotted name or Block.Id.",
    )
    render_parser.set_defaults(handler=_cmd_render)

    lint_parser = commands.add_parser(
        "lint", help="Surface mechanical IndexLab findings and POIs."
    )
    _add_workspace_selector(lint_parser)
    lint_parser.add_argument(
        "--chatlas-root",
        help="Optional Chatlas root used by the read-only touch adapter.",
    )
    lint_parser.add_argument(
        "--lane",
        choices=("dev",),
        default=None,
        help="Run registered development checks in place of their strict counterparts.",
    )
    lint_parser.add_argument(
        "--record-id",
        action="append",
        help="Lint only this exact Index.Record; repeatable.",
    )
    lint_parser.add_argument(
        "--tripwire",
        action="append",
        help=(
            "Emit one Tripwire.Hit for every literal occurrence in selected "
            "Index.Record string values; repeatable."
        ),
    )
    lint_parser.add_argument(
        "--check", action="append", help="Run only this check; repeatable."
    )
    lint_parser.add_argument(
        "--skip", action="append", help="Skip this check; repeatable."
    )
    lint_parser.add_argument(
        "--limit",
        type=_nonnegative_int,
        default=20,
        help="Maximum POI instances to render; 0 shows summaries only.",
    )
    lint_parser.add_argument(
        "--poi-class",
        action="append",
        default=[],
        help="Show instances of this POI class; repeatable.",
    )
    lint_parser.add_argument(
        "--poi-id",
        action="append",
        default=[],
        help="Show this POI instance; repeatable.",
    )
    lint_parser.add_argument(
        "--status",
        action="append",
        choices=("failed", "blocked", "blessed"),
        default=[],
        help="Show instances with this status; repeatable.",
    )
    lint_parser.add_argument(
        "--list-checks", action="store_true", help="Print the check catalog."
    )
    lint_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    lint_parser.set_defaults(handler=_cmd_lint, touch_source=touch_source)

    scenario_parser = commands.add_parser(
        "scenario", help="Run deterministic recording-kernel scenarios."
    )
    scenario_commands = scenario_parser.add_subparsers(
        dest="indexlab_scenario_command", required=True
    )
    mock_parser = scenario_commands.add_parser(
        "seed-mock", help="Seed and lint the deterministic User.Touch.Mock scenario."
    )
    _add_workspace_selector(mock_parser)
    mock_parser.set_defaults(handler=_cmd_seed_mock)


__all__ = ["CAPTURE_MANIFEST_SCHEMA", "register_indexlab_commands"]
