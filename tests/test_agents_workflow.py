import pytest

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import entity
from tarav.l1.agent.current_session import (
    CurrentSession,
    CurrentSessionAbsent,
    CurrentSessionAmbiguous,
    CurrentSessionUnsupported,
    ReportsCurrentSession,
    current_session,
    session_reporters,
)
from tarav.l1.agent.identity import AGENTS_WORKFLOW_SHIP
from tarav.l1.agent.providers.claude_code.agent import ClaudeAgent
from tarav.l1.agent.providers.codex.agent import CodexAgent
from tarav.l1.agent.providers.copilot_cli.agent import CopilotAgent
from tarav.l1.agent.providers.registry import PROVIDER_ADAPTERS
from tarav.l1.agent.workflow import AgentsWorkflow
from tarav.l1.chatlas import commands as chatlas_commands
from tarav.l3.runtime import create_runtime


# tarav.breadcrumb 6a2eafa70b86
def test_runtime_registers_the_agents_workflow():
    runtime = create_runtime()

    assert runtime.workflows.get("Tarav.Workflow.Agents") is AgentsWorkflow
    assert runtime.workflows.get(AGENTS_WORKFLOW_SHIP) is AgentsWorkflow
    assert entity(AgentsWorkflow).name == "Tarav.Workflow.Agents"


def test_the_supported_providers_are_claude_codex_and_copilot():
    assert set(PROVIDER_ADAPTERS) == {"claude-code", "codex", "copilot-cli"}


def test_a_provider_reports_its_session_by_inheriting_the_capability():
    assert issubclass(ClaudeAgent, ReportsCurrentSession)
    assert issubclass(CodexAgent, ReportsCurrentSession)
    assert not issubclass(CopilotAgent, ReportsCurrentSession)
    assert set(session_reporters()) == {"claude-code", "codex"}
    assert ClaudeAgent.current_session_id({"CLAUDE_CODE_SESSION_ID": " abc "}) == "abc"
    assert CodexAgent.current_session_id({"CODEX_THREAD_ID": ""}) is None


def test_current_session_names_the_one_reporting_provider():
    assert current_session(environ={"CODEX_THREAD_ID": "t1"}) == CurrentSession("codex", "t1")
    assert current_session("claude-code", environ={
        "CLAUDE_CODE_SESSION_ID": "s1", "CODEX_THREAD_ID": "t1",
    }) == CurrentSession("claude-code", "s1")


def test_current_session_never_guesses():
    with pytest.raises(CurrentSessionAbsent) as nothing:
        current_session(environ={})
    assert nothing.value.provider is None

    with pytest.raises(CurrentSessionAbsent) as missing:
        current_session("codex", environ={"CLAUDE_CODE_SESSION_ID": "s1"})
    assert (missing.value.provider, missing.value.variable) == ("codex", "CODEX_THREAD_ID")

    with pytest.raises(CurrentSessionAmbiguous) as several:
        current_session(environ={"CLAUDE_CODE_SESSION_ID": "s1", "CODEX_THREAD_ID": "t1"})
    assert set(several.value.providers) == {"claude-code", "codex"}

    with pytest.raises(CurrentSessionUnsupported):
        current_session("copilot-cli", environ={})


def test_chatlas_keeps_its_current_session_behavior(monkeypatch):
    monkeypatch.delenv("CODEX_THREAD_ID", raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "s1")
    assert chatlas_commands._resolve_current_session(None) == ("claude-code", "s1")
    assert chatlas_commands._resolve_current_session("claude-code") == ("claude-code", "s1")

    with pytest.raises(CliError, match="found no CODEX_THREAD_ID for provider codex"):
        chatlas_commands._resolve_current_session("codex")
    with pytest.raises(CliError, match="is not supported for provider: copilot-cli"):
        chatlas_commands._resolve_current_session("copilot-cli")

    monkeypatch.setenv("CODEX_THREAD_ID", "t1")
    with pytest.raises(CliError, match="is ambiguous; supply --provider explicitly"):
        chatlas_commands._resolve_current_session(None)

    monkeypatch.delenv("CODEX_THREAD_ID")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")
    with pytest.raises(CliError, match="found no verified harness context"):
        chatlas_commands._resolve_current_session(None)
