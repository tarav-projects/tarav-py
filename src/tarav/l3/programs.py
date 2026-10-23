"""Program commands execute inside the selected Project's existing trusted harness."""

import json
from pathlib import Path
import sys

from tarav.l0.kernel import entity
from tarav.l1.programs import ProgramError

from .check import in_harness


# tarav.breadcrumb 4810ee307226
# tarav.breadcrumb b3b1880d24b0
def report_program(project, *, operation, program=None, token=None, run_id=None, action=None, data=None):
    try:
        if not hasattr(project, "programs"):
            raise ProgramError("This Project Type does not provide a Programs manager")
        manager = project.programs
        if operation == "list":
            value = {"programs": [{"id": str(entity(cls).id), "name": str(entity(cls).name)}
                                   for cls in manager.definitions()],
                     "runs": [{"id": str(run.id), "program": str(run.typed.program),
                               "state": str(run.typed.state), "arrival": run.typed.arrival,
                               "phase": run.typed.phase, "pending": run.typed.pending}
                              for run in manager.runs()]}
        elif operation == "start":
            value = manager.runner(program).start(data=data)
        elif operation in {"show", "resume", "recover"}:
            runner = manager.for_run(run_id)
            value = (runner.load(run_id).records.to_record() if operation == "show" else
                     runner.recover(run_id) if operation == "recover" else runner.frame(runner.load(run_id)))
        else:
            runner = manager.for_token(token)
            value = (runner.choose(token, action) if operation == "choose" else
                     runner.step(token, data=data) if operation == "step" else runner.status(token))
        print(json.dumps(value, indent=2))
        return 1 if value.get("advanced") is False or value.get("coherent") is False else 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args):
    try:
        data = json.loads(args.data.read_text()) if args.data is not None else None
        if args.data is not None and not isinstance(data, dict):
            raise ProgramError("Program input data must be a JSON object")
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return in_harness(args, command="tarav program", module="tarav.l3.programs", function="report_program",
                      options={"operation": args.program_operation, "program": args.program,
                               "token": args.token, "run_id": args.run_id, "action": args.action, "data": data})


def register_program_commands(subparsers):
    parser = subparsers.add_parser("program", help="Run trusted Project Program classes through checked States.")
    operations = parser.add_subparsers(dest="program_operation", required=True)
    for name, help_text in (
        ("list", "List this Project's registered Program classes and runs."),
        ("start", "Check the initial State and start one Program run."),
        ("show", "Read the retained run, data and arrival history."),
        ("resume", "Read the current token and next operations without advancing."),
        ("choose", "Choose one declared StateAction under the current token."),
        ("step", "Check the pending action; issue a new token only on arrival."),
        ("status", "Check coherence with the token's current State, without advancing."),
        ("recover", "Explicitly recover Action projections from the authoritative run."),
    ):
        cmd = operations.add_parser(name, help=help_text)
        cmd.add_argument("--project", type=Path, nargs="?", const=Path("."), required=True)
        cmd.add_argument("--json", action="store_true", help="Output is structured JSON.")
        cmd.set_defaults(program=None, token=None, run_id=None, action=None, data=None, handler=_run)
        if name == "start":
            cmd.add_argument("--program", required=True, help="Registered Program class name or Type UUID.")
        if name in {"show", "resume", "recover"}:
            cmd.add_argument("--run", dest="run_id", required=True)
        if name in {"choose", "step", "status"}:
            cmd.add_argument("--token", required=True)
        if name == "choose":
            cmd.add_argument("--action", required=True, help="Available StateAction class name or Type UUID.")
        if name in {"start", "step"}:
            cmd.add_argument("--data", type=Path, help="JSON object file containing program input.")
