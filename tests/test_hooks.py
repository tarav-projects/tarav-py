# $kw: ^test-agentos-hooks --from Agentos.Hook --from Agentos.Hook.Invocation --note [DF] boundary tests for exact-name dispatch, isolated opaque context, failure continuation, and CLI ingress --supp ^c20260811-3u ^c20260811-12u
from __future__ import annotations

import argparse
import io
import logging

import pytest

from agentos._core.errors import CliError
from agentos.hooks import (
    AGENTOS_HOOKS_DISABLED_ENV,
    HookError,
    HookInvocation,
    HookRegistry,
    register_hook_commands,
)


def _hook_parser(registry: HookRegistry) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_hook_commands(subparsers, registry=registry)
    return parser


def _run(parser: argparse.ArgumentParser, argv: list[str]) -> int:
    args = parser.parse_args(argv)
    return int(args.handler(args))


def test_exact_name_callbacks_run_sequentially_with_isolated_context() -> None:
    registry = HookRegistry()
    seen: list[tuple[str, int]] = []

    def first(invocation: HookInvocation) -> str:
        seen.append(("first", invocation.ctx["nested"]["value"]))  # type: ignore[index]
        invocation.ctx["nested"]["value"] = 99  # type: ignore[index]
        return "ignored"

    def second(invocation: HookInvocation) -> None:
        seen.append(("second", invocation.ctx["nested"]["value"]))  # type: ignore[index]

    registry.register("agent.tool.before", first)
    registry.register("agent.tool.before", second)
    registry.register("agent.tool.after", lambda invocation: seen.append(("wrong", 0)))

    invocation = HookInvocation(
        name="agent.tool.before",
        ctx={"nested": {"value": 1}},
        ctx_type="codex",
    )

    assert registry.dispatch(invocation) is None
    assert seen == [("first", 1), ("second", 1)]
    assert invocation.ctx == {"nested": {"value": 1}}


def test_hook_registry_dispatches_only_the_selected_execution_lane() -> None:
    registry = HookRegistry()
    seen: list[str] = []
    registry.register(
        "agent.turn.stop",
        lambda invocation: seen.append("inline"),
        callback_id="tests.inline",
    )
    registry.register(
        "agent.turn.stop",
        lambda invocation: seen.append("daemon"),
        callback_id="tests.daemon",
        execution="daemon",
    )
    invocation = HookInvocation(name="agent.turn.stop", ctx={})

    registry.dispatch(invocation)
    assert seen == ["inline"]
    assert registry.has_callbacks("agent.turn.stop", execution="daemon") is True

    registry.dispatch(invocation, execution="daemon")
    assert seen == ["inline", "daemon"]


def test_callback_failure_is_logged_without_context_and_dispatch_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registry = HookRegistry()
    seen: list[str] = []

    def broken(invocation: HookInvocation) -> None:
        raise RuntimeError(f"must-not-log {invocation.ctx['secret']}")

    registry.register("agent.turn.stop", broken, callback_id="tests.broken")
    registry.register(
        "agent.turn.stop",
        lambda invocation: seen.append(invocation.ctx_type or "missing"),
        callback_id="tests.after",
    )

    with caplog.at_level(logging.ERROR, logger="agentos.hooks"):
        assert (
            registry.dispatch(
                HookInvocation(
                    name="agent.turn.stop",
                    ctx={"secret": "provider-prompt"},
                    ctx_type="claude-code",
                )
            )
            is None
        )

    assert seen == ["claude-code"]
    assert "agent.turn.stop" in caplog.text
    assert "tests.broken" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "provider-prompt" not in caplog.text
    assert "must-not-log" not in caplog.text


def test_failure_reporter_failure_does_not_stop_later_callbacks() -> None:
    registry = HookRegistry()
    seen: list[str] = []

    def broken(invocation: HookInvocation) -> None:
        raise RuntimeError("consumer failed")

    def reporter(*_args: object) -> None:
        raise OSError("log unavailable")

    registry.register("agent.turn.stop", broken, callback_id="tests.broken")
    registry.register(
        "agent.turn.stop",
        lambda invocation: seen.append(invocation.name),
        callback_id="tests.after",
    )

    registry.dispatch(
        HookInvocation(name="agent.turn.stop", ctx={}),
        failure_reporter=reporter,
    )

    assert seen == ["agent.turn.stop"]


@pytest.mark.parametrize(
    "name", ["", "session", ".start", "agent..start", "agent. start"]
)
def test_hook_name_must_be_a_nonempty_namespace(name: str) -> None:
    with pytest.raises(HookError):
        HookInvocation(name=name, ctx={})


@pytest.mark.parametrize("ctx_type", ["", "   "])
def test_present_context_type_must_be_nonempty(ctx_type: str) -> None:
    with pytest.raises(HookError):
        HookInvocation(name="agent.session.start", ctx={}, ctx_type=ctx_type)


def test_inline_cli_context_and_type_reach_callbacks(
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = HookRegistry()
    seen: list[HookInvocation] = []
    registry.register("agent.session.start", seen.append)
    parser = _hook_parser(registry)

    assert (
        _run(
            parser,
            [
                "hook",
                "--name",
                "agent.session.start",
                "--ctx-type",
                "codex",
                "--ctx",
                '{"session_id":"test-123"}',
            ],
        )
        == 0
    )
    assert seen == [
        HookInvocation(
            name="agent.session.start",
            ctx={"session_id": "test-123"},
            ctx_type="codex",
        )
    ]
    assert capsys.readouterr().out == ""


def test_stdin_cli_context_reaches_callbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = HookRegistry()
    seen: list[HookInvocation] = []
    registry.register("agent.prompt.submit", seen.append)
    parser = _hook_parser(registry)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"prompt":"hello"}'))

    assert (
        _run(
            parser,
            ["hook", "--name", "agent.prompt.submit", "--ctx-from-stdin"],
        )
        == 0
    )
    assert seen[0].ctx == {"prompt": "hello"}
    assert seen[0].ctx_type is None


def test_hook_cli_can_be_suppressed_for_internal_agent_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = HookRegistry()
    seen: list[HookInvocation] = []
    submitted: list[HookInvocation] = []
    registry.register("agent.turn.stop", seen.append)
    registry.register("agent.turn.stop", lambda _invocation: None, execution="daemon")
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_hook_commands(
        subparsers,
        registry=registry,
        daemon_submitter=submitted.append,
    )
    monkeypatch.setenv(AGENTOS_HOOKS_DISABLED_ENV, "1")

    assert _run(parser, ["hook", "--name", "agent.turn.stop", "--ctx", "{}"]) == 0
    assert seen == []
    assert submitted == []


def test_hook_cli_submits_once_only_when_daemon_callbacks_exist() -> None:
    registry = HookRegistry()
    inline: list[HookInvocation] = []
    submitted: list[HookInvocation] = []
    registry.register("agent.turn.stop", inline.append)
    registry.register(
        "agent.turn.stop",
        lambda invocation: None,
        execution="daemon",
    )
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    register_hook_commands(
        subparsers,
        registry=registry,
        daemon_submitter=submitted.append,
    )

    assert (
        _run(
            parser,
            [
                "hook",
                "--name",
                "agent.turn.stop",
                "--ctx-type",
                "codex",
                "--ctx",
                '{"session_id":"s1"}',
            ],
        )
        == 0
    )
    assert inline == [
        HookInvocation(
            name="agent.turn.stop",
            ctx={"session_id": "s1"},
            ctx_type="codex",
        )
    ]
    assert submitted == inline

    assert _run(parser, ["hook", "--name", "agent.session.start", "--ctx", "{}"]) == 0
    assert submitted == inline


@pytest.mark.parametrize("value", ["not-json", "[]", "null"])
def test_cli_rejects_malformed_or_non_object_context(value: str) -> None:
    parser = _hook_parser(HookRegistry())
    with pytest.raises(CliError):
        _run(parser, ["hook", "--name", "agent.session.start", "--ctx", value])


def test_cli_requires_exactly_one_context_source() -> None:
    parser = _hook_parser(HookRegistry())
    with pytest.raises(SystemExit):
        parser.parse_args(["hook", "--name", "agent.session.start"])
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "hook",
                "--name",
                "agent.session.start",
                "--ctx",
                "{}",
                "--ctx-from-stdin",
            ]
        )
