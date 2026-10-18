"""Query adapter for retained usage traces."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from collections.abc import Callable

from tarav.l0.kernel import Ship, WorkflowShip
from tarav.l0._core.errors import CliError
from tarav.l0.kernel.workflows import TaravWorkflow

from . import UsageRegistry


# tarav.breadcrumb eed9e202f400
def register_usage_commands(
    subparsers: argparse._SubParsersAction,
    *,
    registry: UsageRegistry,
    workflow_resolver: Callable[[str], type[TaravWorkflow]],
) -> None:
    parent = subparsers.add_parser("usage", help="Inspect recent Tarav usage traces")
    children = parent.add_subparsers(dest="usage_command")
    query = children.add_parser("query", help="Query recent workflow-attributed traces")
    query.add_argument("--workflow", help="Workflow name or Ship")
    query.add_argument("--project", help="Project Ship")
    query.add_argument("--subject")
    query.add_argument("--type", dest="trace_type", help="Exact usage trace Type label")
    query.add_argument("--since", help="ISO datetime")
    query.add_argument("--jmespath", help="JMESPath predicate over each JSON row")
    query.add_argument("--limit", type=int)

    def run(args: argparse.Namespace) -> int:
        try:
            workflow: type[TaravWorkflow] | WorkflowShip | None = None
            if args.workflow:
                try:
                    workflow = WorkflowShip(args.workflow)
                except ValueError:
                    workflow = workflow_resolver(args.workflow)
            project = Ship(args.project) if args.project else None
            since = datetime.fromisoformat(args.since) if args.since else None
            rows = registry.query(
                workflow=workflow,
                project=project,
                subject=args.subject,
                trace_type=args.trace_type,
                since=since,
                expression=args.jmespath,
                limit=args.limit,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CliError(f"invalid usage query: {exc}") from exc
        print(json.dumps(rows, indent=2))
        return 0

    # tarav.breadcrumb f9d50eaccb67
    query.set_defaults(
        handler=run,
        usage_descriptor=lambda args: {
            key: value
            for key, value in (
                ("workflow", args.workflow), ("project", args.project),
                ("subject", args.subject), ("since", args.since),
                ("type", args.trace_type),
                ("jmespath", args.jmespath), ("limit", args.limit),
            )
            if value is not None
        },
    )
