"""`agent accounts monitor` command and its interactive input thread."""

from __future__ import annotations

import argparse
import sys
import termios
import tty
from threading import Thread

from tarav.l1.agent.commands._shared import (
    _add_project_argument,
    _config_start_path,
)


def _cmd_agent_accounts_monitor(args: argparse.Namespace) -> int:
    from tarav.l1.agent.monitor import (
        RichMonitorRenderer,
        build_monitor_loop,
        dumps_monitor_json,
    )

    max_ticks = 1 if args.once else args.max_ticks
    loop = build_monitor_loop(
        start_path=_config_start_path(args),
        interval_sec=args.interval_sec,
        max_ticks=max_ticks,
    )
    try:
        if args.json:
            if max_ticks is None:

                def print_json_tick(frame, state) -> None:
                    print(dumps_monitor_json(frame, state), flush=True)

                loop.run(on_tick=print_json_tick)
                return 0

            frame, state = loop.run(wait_for_first_frame=True)
            print(dumps_monitor_json(frame, state))
            return 0

        with RichMonitorRenderer() as renderer:
            if _should_listen_for_monitor_enter(args):
                _start_monitor_input_thread(loop)
            loop.run(on_tick=renderer.render, wait_for_first_frame=args.once)
        return 0
    except KeyboardInterrupt:
        return 130


def _cmd_agent_accounts_monitor_dev_test(args: argparse.Namespace) -> int:
    from rich.console import Console

    from tarav.l1.agent.monitor.dev_test import build_dev_test_frame
    from tarav.l1.agent.monitor.render import rich_monitor_frame

    console = Console()
    console.print(
        rich_monitor_frame(
            build_dev_test_frame(),
            width=console.width,
            pad_bars=console.is_terminal,
        )
    )
    return 0


def _should_listen_for_monitor_enter(args: argparse.Namespace) -> bool:
    return not args.json and not args.once and sys.stdin.isatty()


def _start_monitor_input_thread(loop) -> Thread:
    import select

    from tarav.l1.agent.monitor import (
        MONITOR_AUTO_MATERIALIZE_TOGGLE_ALARM,
        MONITOR_ENTER_ALARM,
        MONITOR_MATERIALIZE_ALARM,
        MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
    )

    def listen_for_input() -> None:
        stdin = sys.stdin
        fd = stdin.fileno()
        previous_attrs = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while not loop.stop_requested.is_set():
                readable, _, _ = select.select([stdin], [], [], 0.1)
                if not readable:
                    continue
                char = stdin.read(1)
                if char == "":
                    return
                if char in {"\n", "\r"}:
                    loop.set_alarm(MONITOR_ENTER_ALARM, remaining_ticks=0)
                elif char.lower() == "r":
                    loop.set_alarm(
                        MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
                        remaining_ticks=0,
                    )
                elif char.lower() == "m":
                    loop.set_alarm(MONITOR_MATERIALIZE_ALARM, remaining_ticks=0)
                elif char.lower() == "a":
                    loop.set_alarm(
                        MONITOR_AUTO_MATERIALIZE_TOGGLE_ALARM,
                        remaining_ticks=0,
                    )
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, previous_attrs)

    thread = Thread(
        target=listen_for_input,
        name="tarav-monitor-input",
        daemon=True,
    )
    thread.start()
    return thread


def _register_monitor_command(accounts_subparsers) -> None:
    accounts_monitor_parser = accounts_subparsers.add_parser(
        "monitor",
        help="Run configured account monitor workflows.",
    )
    _add_project_argument(accounts_monitor_parser)
    accounts_monitor_parser.add_argument(
        "--once",
        action="store_true",
        help="Run exactly one monitor tick.",
    )
    accounts_monitor_parser.add_argument(
        "--max-ticks",
        type=int,
        default=None,
        help="Maximum monitor ticks to run. Omit for a continuous monitor loop.",
    )
    accounts_monitor_parser.add_argument(
        "--interval-sec",
        type=float,
        default=1.0,
        help="Target seconds between monitor ticks.",
    )
    accounts_monitor_parser.add_argument(
        "--json",
        action="store_true",
        help="Print monitor state and frame as JSON.",
    )
    accounts_monitor_parser.set_defaults(handler=_cmd_agent_accounts_monitor)


    monitor_subparsers = accounts_monitor_parser.add_subparsers(
        dest="monitor_command",
        required=False,
    )
    monitor_dev_test_parser = monitor_subparsers.add_parser(
        "dev-test",
        help="Render monitor UI candidate rows (dev sandbox for comms snippets).",
    )
    monitor_dev_test_parser.set_defaults(
        handler=_cmd_agent_accounts_monitor_dev_test
    )
