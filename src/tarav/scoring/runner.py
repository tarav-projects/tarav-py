"""Preparation and optional execution of frozen Ranking Runs."""

from __future__ import annotations

from pathlib import Path
import subprocess
from typing import Any, Mapping

from tarav import __version__
from tarav.agent.providers.registry import resolve_agent
from tarav.agent.run_runtime import AgentCommandConfig, AgentRunConfig

from .model import JsonObject, ScoringError, create_run, render_run
from .repository import ScoringRepository


UNKNOWN_RUNNER_TYPE = "Unknown.Ranking.Runner"
AGENT_RUNNER_TYPE = "Agent.Ranking.Task.Runner"


def prepare_run(
    *,
    repository: ScoringRepository,
    task: JsonObject,
    runner: Mapping[str, object],
    seed: str | None = None,
) -> tuple[JsonObject, str]:
    """Register one frozen Run and return its exact prompt separately."""

    run = create_run(
        task=task,
        runner=runner,
        repository_root=str(repository.root),
        code_provenance=code_provenance(),
        seed=seed,
    )
    repository.create(run)
    return run, render_run(
        task=task,
        run=run,
    )


def prepare_unknown_run(
    *,
    repository: ScoringRepository,
    task: JsonObject,
    seed: str | None = None,
) -> tuple[JsonObject, str]:
    return prepare_run(
        repository=repository,
        task=task,
        runner={"type": UNKNOWN_RUNNER_TYPE},
        seed=seed,
    )


def prepare_agent_run(
    *,
    repository: ScoringRepository,
    task: JsonObject,
    provider: str | None,
    profile: str | None,
    home: Path | None,
    model: str | None,
    account: str | None,
    cwd: Path,
    seed: str | None,
) -> tuple[JsonObject, str]:
    """Resolve Agent provenance before freezing the Run."""

    agent = resolve_agent(
        provider=provider,
        profile=profile,
        start_path=cwd,
        home=home,
    )
    effective_model = model or agent.default_model
    effective_account = account or (
        agent.account.account if agent.account is not None else None
    )
    runner = {
        "type": AGENT_RUNNER_TYPE,
        "provider": agent.provider,
        "profile": agent.profile_id,
        "home": str(agent.home) if agent.home is not None else None,
        "model": effective_model,
        "account": effective_account,
        "cwd": str(cwd),
    }
    return prepare_run(
        repository=repository,
        task=task,
        runner=runner,
        seed=seed,
    )


def execute_run(
    *,
    repository: ScoringRepository,
    run: JsonObject,
    timeout_sec: int | None,
) -> tuple[JsonObject, JsonObject]:
    """Execute a prepared Agent Run without mutating its frozen Record."""

    runner = run.get("runner")
    if not isinstance(runner, dict) or runner.get("type") != AGENT_RUNNER_TYPE:
        raise ScoringError("only a resolved Agent Ranking Runner can be executed")
    if repository.result_for_run(str(run["id"])) is not None:
        raise ScoringError(f"Ranking Run already has a Result: {run['id']}")
    task = repository.resolve_reference(_reference(run, "task_ref"))
    prompt = render_run(
        task=task,
        run=run,
    )
    cwd = Path(str(runner.get("cwd", "."))).expanduser().resolve()
    home_value = runner.get("home")
    home = Path(home_value) if isinstance(home_value, str) else None
    agent = resolve_agent(
        provider=_optional_string(runner.get("provider")),
        profile=_optional_string(runner.get("profile")),
        start_path=cwd,
        home=home,
    )
    result = agent.run(
        AgentCommandConfig(
            prompt=prompt,
            model=_optional_string(runner.get("model")),
            account=_optional_string(runner.get("account")),
            interaction_mode="non_interactive",
        ),
        AgentRunConfig(cwd=cwd, process_mode="capture", timeout_sec=timeout_sec),
    )
    if result.exit_code != 0:
        raise ScoringError(f"Ranking Agent exited with status {result.exit_code}")
    submitted = repository.result_for_run(str(run["id"]))
    if submitted is None:
        raise ScoringError("Ranking Agent exited without submitting a Result")
    return run, submitted


def code_provenance() -> JsonObject:
    root = Path(__file__).resolve().parents[3]
    commit = subprocess.run(
        ("git", "-C", str(root), "rev-parse", "HEAD"),
        capture_output=True,
        text=True,
        check=False,
    )
    dirty = subprocess.run(
        ("git", "-C", str(root), "status", "--porcelain"),
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "version": __version__,
        "git_commit": commit.stdout.strip() if commit.returncode == 0 else None,
        "dirty": dirty.returncode != 0 or bool(dirty.stdout.strip()),
    }


def _reference(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, dict):
        raise ScoringError(f"{field} must be a typed Reference")
    return value


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = [
    "AGENT_RUNNER_TYPE",
    "UNKNOWN_RUNNER_TYPE",
    "code_provenance",
    "execute_run",
    "prepare_agent_run",
    "prepare_run",
    "prepare_unknown_run",
]
