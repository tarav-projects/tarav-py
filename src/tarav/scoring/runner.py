"""Generic Agent runner for rendered Ranking Tasks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from tarav.agent.providers.registry import resolve_agent
from tarav.agent.run_runtime import AgentCommandConfig, AgentRunConfig

from .model import JsonObject, ScoringError, create_run, now_iso
from .repository import ScoringRepository


def prepare_run(
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
    preview: bool,
) -> JsonObject:
    runner = {
        "type": "Agent.Ranking.Task.Runner" if not preview else "Preview.Ranking.Task.Runner",
        "provider": provider,
        "profile": profile,
        "home": str(home) if home is not None else None,
        "model": model,
        "account": account,
        "cwd": str(cwd),
    }
    run = create_run(
        task=task,
        runner=runner,
        repository_root=str(repository.root),
        seed=seed,
        status="Preview" if preview else "Prepared",
    )
    return repository.create(run)


def execute_run(
    *,
    repository: ScoringRepository,
    run: JsonObject,
    timeout_sec: int | None,
) -> tuple[JsonObject, JsonObject | None]:
    runner = run.get("runner")
    if not isinstance(runner, dict):
        raise ScoringError("Ranking Run has no typed runner")
    cwd = Path(str(runner.get("cwd", "."))).expanduser().resolve()
    home_value = runner.get("home")
    home = Path(home_value) if isinstance(home_value, str) else None
    running = {**run, "status": "Running", "started_at": now_iso()}
    repository.save(running, message=f"Start Ranking Run {run['id']}")
    try:
        agent = resolve_agent(
            provider=_optional_string(runner.get("provider")),
            profile=_optional_string(runner.get("profile")),
            start_path=cwd,
            home=home,
        )
        effective_model = _optional_string(runner.get("model")) or agent.default_model
        effective_account = _optional_string(runner.get("account")) or (
            agent.account.account if agent.account is not None else None
        )
        running = {
            **running,
            "runner": {
                **runner,
                "resolved_provider": agent.provider,
                "resolved_profile": agent.profile_id,
                "resolved_home": str(agent.home) if agent.home is not None else None,
                "resolved_model": effective_model,
                "resolved_account": effective_account,
            },
        }
        repository.save(running, message=f"Resolve Ranking Runner {run['id']}")
        result = agent.run(
            AgentCommandConfig(
                prompt=str(run["rendered_prompt"]),
                model=effective_model,
                account=effective_account,
                interaction_mode="non_interactive",
            ),
            AgentRunConfig(cwd=cwd, process_mode="capture", timeout_sec=timeout_sec),
        )
    except Exception as exc:
        failed: JsonObject = {
            **running,
            "status": "Failed",
            "completed_at": now_iso(),
            "execution": {
                "error_type": type(exc).__name__,
                "message": str(exc),
            },
        }
        repository.save(failed, message=f"Fail Ranking Run {run['id']}")
        raise
    submitted = repository.result_for_run(str(run["id"]))
    stdout = result.stdout or ""
    stderr = result.stderr or ""
    final_status = (
        "Completed"
        if result.exit_code == 0 and submitted is not None
        else "Exited.Without.Result"
        if result.exit_code == 0
        else "Failed"
    )
    completed: JsonObject = {
        **running,
        "status": final_status,
        "completed_at": now_iso(),
        "execution": {
            "exit_code": result.exit_code,
            "stdout_bytes": len(stdout.encode("utf-8")),
            "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
            "stderr_bytes": len(stderr.encode("utf-8")),
            "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
            "result_id": submitted["id"] if submitted else None,
        },
    }
    repository.save(completed, message=f"Complete Ranking Run {run['id']}")
    return completed, submitted


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


__all__ = ["execute_run", "prepare_run"]
