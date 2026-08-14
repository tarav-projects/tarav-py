# $kw: --from Iterante.Driver
"""In-env turn runner — `python -m iterante._runner`.

Launched by the runtime inside the resolved Mission.Env. Runs one turn through the
harness and emits the resulting frame as a sentinel-prefixed JSON line on stdout,
so it survives any output the mission itself prints. Harness errors go to stderr
as JSON with a non-zero exit.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from pathlib import Path

from tarav.iterante.errors import dev_bypass, record_fatal
from tarav.iterante.harness import AgentError, execute_turn
from tarav.iterante.redact import redact

FRAME_SENTINEL = "__ITERANTE_FRAME__ "
_ERROR_KEY = "error"




def frame_line(result: dict) -> str:
    """Encode a turn result as the sentinel-framed stdout line."""
    return FRAME_SENTINEL + json.dumps(result) + "\n"


def error_line(msg: str) -> str:
    """Encode an error message as the stderr envelope line."""
    return json.dumps({_ERROR_KEY: msg}) + "\n"


def parse_error(stderr: str) -> str:
    """Decode the error envelope from runner stderr, falling back to raw text."""
    text = stderr.strip()
    try:
        return json.loads(text).get(_ERROR_KEY, text)
    except (json.JSONDecodeError, AttributeError):
        return text


def _emit_mission_output(buf: io.StringIO) -> None:
    """Forward whatever the mission printed, scrubbed by the output sensors."""
    text = buf.getvalue()
    if text:
        sys.stdout.write(redact(text))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iterante._runner")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--mission-dir", required=True)
    parser.add_argument("--token")
    parser.add_argument("--submit", help="submit result as a JSON object")
    parser.add_argument("--no-persist", action="store_true")
    args = parser.parse_args(argv)



    captured = io.StringIO()
    try:
        submit_result = json.loads(args.submit) if args.submit else None
        with contextlib.redirect_stdout(captured):
            result = execute_turn(
                rd=Path(args.run_dir),
                mission_dir=Path(args.mission_dir),
                submit_result=submit_result,
                persist=not args.no_persist,
                token=args.token,
            )
    except AgentError as e:



        _emit_mission_output(captured)
        sys.stderr.write(error_line(redact(str(e))))
        return 1
    except Exception as e:


        _emit_mission_output(captured)
        sys.stderr.write(error_line(record_fatal(e, log_dir=Path(args.run_dir), verbose=dev_bypass())))
        return 1

    _emit_mission_output(captured)
    sys.stdout.write(frame_line(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
