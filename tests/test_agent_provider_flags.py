from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.providers import resolve_agent_config
from agentos.agent.run_runtime import (
    AgentCommandConfig,
    build_agent_command_argv,
    provider_model_flag,
    provider_prompt_flag,
)
from agentos.testing import AgentosTestEnvironment


def _argv(provider: str) -> tuple[str, ...]:
    return build_agent_command_argv(
        AgentCommandConfig(prompt="hi", model="X"),
        provider=provider,
        cli_command=("/bin/echo",),
        run_args=(),
        default_model=None,
    )


def test_provider_flags_are_derived_from_provider_not_config() -> None:
    # copilot/claude: model flagged, prompt flagged
    assert _argv("copilot-cli") == ("/bin/echo", "--model", "X", "-p", "hi")
    assert _argv("claude-code") == ("/bin/echo", "--model", "X", "-p", "hi")
    # codex: model flagged, prompt positional (no prompt flag)
    assert _argv("codex") == ("/bin/echo", "--model", "X", "hi")
    assert provider_prompt_flag("codex") is None
    assert provider_model_flag("codex") == "--model"


def test_provider_without_model_flag_rejects_a_model() -> None:
    with pytest.raises(Exception):
        _argv("gemini-cli")  # no model flag defined for this provider


def test_profile_cannot_override_provider_flags(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # A profile that still carries the old flag fields must be harmlessly
    # ignored — never parsed onto the config, never overriding the provider.
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    environment.write_profile(
        "copilot-jp",
        provider="copilot-cli",
        cli_command=["/bin/echo"],
        homes=[str(tmp_path / "h")],
        accounts=["jp"],
        model_flag="--WRONG",
        prompt_flag="--WRONG",
    )

    config = resolve_agent_config(
        provider="copilot-cli",
        profile="copilot-jp",
        start_path=tmp_path,
    )

    # The field no longer exists on the resolved config at all.
    assert not hasattr(config, "model_flag")
    assert not hasattr(config, "prompt_flag")
