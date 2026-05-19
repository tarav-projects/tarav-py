from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Protocol
from uuid import uuid4

from agentos._core.errors import CliError
from agentos.chatlas.delta_scan import default_chatlas_root
from agentos.chatlas.index_query import select_one_chatlas_index_row
from agentos.chatlas.session_model import (
    build_chatlas_session_model_from_index_row,
    project_chatlas_session_model_view,
)

_VIEWS_ROOT = "views"
_STAGING_ROOT = "_staging"
_MANIFEST_FILENAME = "manifest.json"
_ZIP_TRANSCRIPT_ARTIFACT = "zip-transcript.json"
_SUMMARY_ARTIFACT = "summary.json"
_SUMMARY_ARTIFACT_CLASS = "agentos.chatlas.zip_transcript_agent_summary"
_ZIP_TRANSCRIPT_AGENT_SUMMARY_REFERENCE = (
    "/Users/pereiro/projects/agentos-project/agentos-md/skills/chatlas-usage/"
    "references/producer-zip-transcript-agent-summary.md"
)


@dataclass(frozen=True)
class ChatlasViewArtifactContract:
    primary_artifact: str
    required_artifacts: tuple[str, ...]
    content_type: str


@dataclass(frozen=True)
class ChatlasViewStatus:
    state: str
    manifest: dict[str, Any] | None
    artifact: dict[str, object] | None
    freshness: dict[str, object]
    production: dict[str, object] | None = None
    fields: dict[str, object] | None = None


@dataclass(frozen=True)
class ChatlasPreparedAgentProduction:
    prompt: str
    stage_id: str | None
    stage_path: Path | None
    output_artifact_path: Path
    final_artifact_path: Path
    diagnostics: dict[str, object]


class ChatlasViewWorkflow(Protocol):
    name: str
    kind: str
    description: str
    artifact_contract: ChatlasViewArtifactContract

    def current_status(
        self,
        context: "ChatlasViewContext",
        *,
        explain: bool = False,
    ) -> ChatlasViewStatus: ...

    def produce(
        self,
        context: "ChatlasViewContext",
    ) -> dict[str, object]: ...

    def production_instructions(
        self,
        context: "ChatlasViewContext",
    ) -> dict[str, object]: ...

    def build_produce_prompt(
        self,
        context: "ChatlasViewContext",
    ) -> str: ...

    def prepare_agent_production(
        self,
        context: "ChatlasViewContext",
        *,
        dry_run: bool = False,
    ) -> ChatlasPreparedAgentProduction: ...


@dataclass(frozen=True)
class ChatlasViewContext:
    chatlas_root: Path
    workflow: ChatlasViewWorkflow
    parameters: list[dict[str, object]]
    source_rows: list[dict[str, Any]]
    cache_key: str
    slot_path: Path


def compute_chatlas_view_cache_key(
    *,
    view: str,
    parameters: list[dict[str, object]],
) -> str:
    return hashlib.sha256(
        _canonical_json({"view": view, "parameters": parameters}).encode("utf-8")
    ).hexdigest()


def resolve_chatlas_view_slot_path(
    *,
    view: str,
    cache_key: str,
    chatlas_root: Path | None = None,
) -> Path:
    root = _chatlas_root(chatlas_root)
    return root / _VIEWS_ROOT / view / cache_key


def chatlas_views_list(*, chatlas_root: Path | None = None) -> dict[str, object]:
    root = _chatlas_root(chatlas_root)
    return {
        "status": "ok",
        "command": "chatlas views list",
        "chatlas_root": str(root),
        "views_root": str(root / _VIEWS_ROOT),
        "views": [
            {
                "name": workflow.name,
                "kind": workflow.kind,
                "description": workflow.description,
                "artifact_contract": _artifact_contract_payload(workflow.artifact_contract),
            }
            for workflow in _registered_workflows()
        ],
    }


def chatlas_views_get(
    *,
    view: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(view=view, chatlas_root=chatlas_root, selectors=selectors)
    status = _ensure_available(context, explain=explain)
    return _view_result(
        command="chatlas views get",
        context=context,
        status=status,
        explain=explain,
    )


def chatlas_views_status(
    *,
    view: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(view=view, chatlas_root=chatlas_root, selectors=selectors)
    status = _ensure_available(context, explain=explain)
    return _view_result(
        command="chatlas views status",
        context=context,
        status=status,
        explain=explain,
    )


def chatlas_views_path(
    *,
    view: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(view=view, chatlas_root=chatlas_root, selectors=selectors)
    status = _ensure_available(context, explain=explain)
    result = _view_result(
        command="chatlas views path",
        context=context,
        status=status,
        explain=explain,
    )
    artifact = result["view"].get("artifact")
    result["path"] = artifact.get("primary_path") if isinstance(artifact, dict) else None
    return result


def chatlas_views_stage(
    *,
    view: str,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(view=view, chatlas_root=chatlas_root, selectors=selectors)
    return _stage_external_view_context(context)


def _stage_external_view_context(context: ChatlasViewContext) -> dict[str, object]:
    view = context.workflow.name
    if context.workflow.kind != "external":
        raise CliError(f"chatlas views stage only supports external views: {view}")

    stage_id = _new_stage_id()
    stage_path = context.chatlas_root / _VIEWS_ROOT / _STAGING_ROOT / stage_id
    stage_path.mkdir(parents=True, exist_ok=False)
    metadata = {
        "class": "agentos.chatlas.view.stage",
        "schema_version": 1,
        "stage_id": stage_id,
        "view": context.workflow.name,
        "parameters": context.parameters,
        "source_rows": context.source_rows,
        "cache_key": context.cache_key,
        "target_slot_path": str(context.slot_path),
        "artifact_contract": _artifact_contract_payload(context.workflow.artifact_contract),
        "created_at": _utc_now(),
        "production": context.workflow.production_instructions(context),
    }
    _write_json(stage_path / _MANIFEST_FILENAME, metadata)
    return {
        "status": "ok",
        "command": "chatlas views stage",
        "stage": {
            "stage_id": stage_id,
            "path": str(stage_path),
            "manifest_path": str(stage_path / _MANIFEST_FILENAME),
        },
        "view": {
            "name": context.workflow.name,
            "parameters": context.parameters,
            "cache_key": context.cache_key,
            "production": metadata["production"],
        },
    }


def chatlas_views_commit(
    *,
    stage_id: str,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    root = _chatlas_root(chatlas_root)
    stage_path = root / _VIEWS_ROOT / _STAGING_ROOT / stage_id
    stage_manifest_path = stage_path / _MANIFEST_FILENAME
    stage_manifest = _read_json_object(stage_manifest_path, description="Chatlas view stage manifest")
    view_name = _string_field(stage_manifest, "view", description="stage manifest")
    workflow = _workflow_by_name(view_name)
    parameters = _parameters_from_manifest(stage_manifest)
    source_rows = _source_rows_from_manifest(stage_manifest)
    cache_key = _string_field(stage_manifest, "cache_key", description="stage manifest")
    expected_cache_key = compute_chatlas_view_cache_key(view=view_name, parameters=parameters)
    if cache_key != expected_cache_key:
        raise CliError("Chatlas view stage manifest cache_key does not match view parameters")

    context = _context_from_parameters(
        workflow=workflow,
        chatlas_root=root,
        parameters=parameters,
        source_rows=source_rows,
    )
    if context.cache_key != cache_key:
        raise CliError("Chatlas view stage target does not match cache key")

    artifact_files = _validate_required_stage_artifacts(
        stage_path,
        workflow.artifact_contract,
        context=context,
    )
    observed_dependencies = _observed_dependencies_for_commit(workflow, context)
    artifacts = _artifact_payloads(
        context.slot_path,
        artifact_files,
        contract=workflow.artifact_contract,
    )
    manifest = _committed_manifest(
        context=context,
        state="fresh",
        producer="external",
        observed_dependencies=observed_dependencies,
        artifacts=artifacts,
        fields={},
    )
    _replace_slot_from_stage(
        stage_path=stage_path,
        slot_path=context.slot_path,
        manifest=manifest,
        artifact_files=artifact_files,
    )
    return _view_result(
        command="chatlas views commit",
        context=context,
        status=context.workflow.current_status(context, explain=False),
        explain=False,
    )


def chatlas_produce(
    *,
    view: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(view=view, chatlas_root=chatlas_root, selectors=selectors)
    if context.workflow.kind == "internal":
        status = _ensure_available(context, explain=explain)
        return _view_result(
            command="chatlas produce",
            context=context,
            status=status,
            explain=explain,
        )
    prompt = context.workflow.build_produce_prompt(context)
    return {
        "status": "ok",
        "command": "chatlas produce",
        "view": context.workflow.name,
        "kind": context.workflow.kind,
        "prompt": prompt,
    }


def chatlas_run_produce(
    *,
    view: str,
    provider: str,
    profile: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    chatlas_root: Path | None = None,
    rows: list[dict[str, object]],
) -> dict[str, object]:
    from agentos.agent.providers import resolve_agent
    from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig

    workflow = _workflow_by_name(view)
    root = _chatlas_root(chatlas_root)
    agent_cwd = root

    results: list[dict[str, object]] = []
    for row in rows:
        context = _context_from_parameters(
            workflow=workflow,
            chatlas_root=root,
            parameters=[_canonical_session_parameter(row)],
            source_rows=[row],
        )

        if not force and not dry_run:
            status = workflow.current_status(context)
            if status.state == "fresh":
                results.append({"skipped": True, "reason": "fresh"})
                continue

        try:
            prepared = workflow.prepare_agent_production(context, dry_run=dry_run)
        except CliError as exc:
            results.append({
                "exit_code": 1,
                "prepare_error": str(exc),
            })
            continue
        prompt = prepared.prompt

        if dry_run:
            agent = resolve_agent(provider=provider, profile=profile, start_path=agent_cwd)
            command_config = AgentCommandConfig(prompt=prompt, model=model, interaction_mode="non_interactive")
            dry_result = agent.run_dry(command_config)
            results.append({
                "prompt": prompt,
                "prepared": _prepared_agent_production_payload(prepared),
                "agent_command": list(dry_result.lines),
            })
            continue

        agent = resolve_agent(provider=provider, profile=profile, start_path=agent_cwd)
        command_config = AgentCommandConfig(prompt=prompt, model=model, interaction_mode="non_interactive")
        run_config = AgentRunConfig(cwd=agent_cwd, process_mode="terminal")
        result = agent.run(command_config, run_config)
        run_result: dict[str, object] = {
            "exit_code": result.exit_code,
            "prepared": _prepared_agent_production_payload(prepared),
        }
        if result.exit_code == 0:
            if prepared.stage_id is None:
                run_result["commit_error"] = "prepared production did not create a stage"
            else:
                try:
                    commit_result = chatlas_views_commit(stage_id=prepared.stage_id, chatlas_root=root)
                except CliError as exc:
                    run_result["commit_error"] = str(exc)
                else:
                    run_result["commit"] = commit_result
                    run_result["artifact_path"] = str(prepared.final_artifact_path)
        results.append(run_result)

    if dry_run:
        return {
            "status": "ok",
            "command": "chatlas run-produce",
            "dry_run": True,
            "view": view,
            "run_count": len(results),
            "runs": results,
        }

    skipped = sum(1 for r in results if r.get("skipped"))
    failed = sum(
        1
        for r in results
        if not r.get("skipped") and (r.get("exit_code", 1) != 0 or r.get("commit_error"))
    )
    return {
        "status": "ok" if failed == 0 else "error",
        "command": "chatlas run-produce",
        "view": view,
        "run_count": len(results),
        "skipped_count": skipped,
        "failed_count": failed,
        "runs": results,
    }


def _ensure_available(
    context: ChatlasViewContext,
    *,
    explain: bool,
) -> ChatlasViewStatus:
    status = context.workflow.current_status(context, explain=explain)
    if status.state in {"fresh", "production_required"}:
        return status
    if context.workflow.kind == "internal" and status.state in {"missing", "stale"}:
        context.workflow.produce(context)
        produced_status = context.workflow.current_status(context, explain=explain)
        if produced_status.state == "fresh":
            return ChatlasViewStatus(
                state="produced",
                manifest=produced_status.manifest,
                artifact=produced_status.artifact,
                freshness=produced_status.freshness,
                production=produced_status.production,
                fields=produced_status.fields,
            )
        return produced_status
    return status


class ZipTranscriptWorkflow:
    name = "zip-transcript"
    kind = "internal"
    description = "Materialized text-only session transcript for compact agent consumption."
    artifact_contract = ChatlasViewArtifactContract(
        primary_artifact=_ZIP_TRANSCRIPT_ARTIFACT,
        required_artifacts=(_ZIP_TRANSCRIPT_ARTIFACT,),
        content_type="application/json",
    )

    def current_status(
        self,
        context: ChatlasViewContext,
        *,
        explain: bool = False,
    ) -> ChatlasViewStatus:
        manifest = _read_manifest_if_present(context.slot_path)
        current_fingerprint = _zip_transcript_fingerprint(context.source_rows[0])
        if manifest is None:
            return ChatlasViewStatus(
                state="missing",
                manifest=None,
                artifact=None,
                freshness={
                    "state": "missing",
                    "current_fingerprint": current_fingerprint,
                },
                fields={},
            )
        artifact = _primary_artifact_from_manifest(context.slot_path, manifest)
        observed_fingerprint = _observed_dependency_fingerprint(manifest, "source-session")
        state = "fresh" if observed_fingerprint == current_fingerprint else "stale"
        freshness: dict[str, object] = {
            "state": state,
            "current_fingerprint": current_fingerprint,
            "observed_fingerprint": observed_fingerprint,
        }
        if explain:
            freshness["dependencies"] = _manifest_dependency_list(manifest)
        return ChatlasViewStatus(
            state=state,
            manifest=manifest,
            artifact=artifact,
            freshness=freshness,
            fields={},
        )

    def produce(self, context: ChatlasViewContext) -> dict[str, object]:
        zip_payload = _zip_transcript_payload(context.source_rows[0])
        artifact_bytes = (_canonical_json(zip_payload) + "\n").encode("utf-8")
        artifact_hash = _bytes_sha256(artifact_bytes)
        artifact_path = context.slot_path / self.artifact_contract.primary_artifact
        artifacts = [
            {
                "name": self.artifact_contract.primary_artifact,
                "path": str(artifact_path),
                "content_type": self.artifact_contract.content_type,
                "sha256": artifact_hash,
                "size_bytes": len(artifact_bytes),
                "primary": True,
            }
        ]
        manifest = _committed_manifest(
            context=context,
            state="fresh",
            producer="internal",
            observed_dependencies=[
                _source_session_dependency(
                    context.parameters[0],
                    fingerprint=_zip_transcript_fingerprint(context.source_rows[0]),
                )
            ],
            artifacts=artifacts,
            fields={"turn_count": len(zip_payload.get("turns", []))},
        )
        _replace_slot_with_files(
            slot_path=context.slot_path,
            files={self.artifact_contract.primary_artifact: artifact_bytes},
            manifest=manifest,
        )
        return manifest

    def production_instructions(self, context: ChatlasViewContext) -> dict[str, object]:
        _ = context
        return {"mode": "internal", "action": "auto-produce"}

    def build_produce_prompt(self, context: ChatlasViewContext) -> str:
        raise CliError(
            f"chatlas produce is not supported for internal view: {self.name}"
        )

    def prepare_agent_production(
        self,
        context: ChatlasViewContext,
        *,
        dry_run: bool = False,
    ) -> ChatlasPreparedAgentProduction:
        _ = (context, dry_run)
        raise CliError(
            f"chatlas run-produce is not supported for internal view: {self.name}"
        )


class ZipTranscriptAgentSummaryWorkflow:
    name = "zip-transcript-agent-summary"
    kind = "external"
    description = "Agent-produced lower-token transcript derived from a materialized zip-transcript view."
    artifact_contract = ChatlasViewArtifactContract(
        primary_artifact=_SUMMARY_ARTIFACT,
        required_artifacts=(_SUMMARY_ARTIFACT,),
        content_type="application/json",
    )

    def current_status(
        self,
        context: ChatlasViewContext,
        *,
        explain: bool = False,
    ) -> ChatlasViewStatus:
        manifest = _read_manifest_if_present(context.slot_path)
        dependency_status = _zip_transcript_dependency_status(context, explain=explain)
        if manifest is None:
            return ChatlasViewStatus(
                state="production_required",
                manifest=None,
                artifact=None,
                freshness={
                    "state": "missing",
                    **_dependency_summary(dependency_status, explain=explain),
                },
                production=self.production_instructions(context),
                fields={},
            )
        artifact = _primary_artifact_from_manifest(context.slot_path, manifest)
        observed_fingerprint = _observed_dependency_fingerprint(manifest, "view:zip-transcript")
        current_fingerprint = dependency_status.freshness.get("current_fingerprint")
        dependency_state = dependency_status.state
        state = "fresh"
        freshness_state = "fresh"
        if dependency_state not in {"fresh", "produced"}:
            state = "production_required"
            freshness_state = "stale"
        elif observed_fingerprint != current_fingerprint:
            state = "production_required"
            freshness_state = "stale"
        freshness: dict[str, object] = {
            "state": freshness_state,
            "current_fingerprint": current_fingerprint,
            "observed_fingerprint": observed_fingerprint,
            **_dependency_summary(dependency_status, explain=explain),
        }
        if explain:
            freshness["dependencies"] = _manifest_dependency_list(manifest)
        return ChatlasViewStatus(
            state=state,
            manifest=manifest,
            artifact=artifact,
            freshness=freshness,
            production=self.production_instructions(context) if state == "production_required" else None,
            fields={},
        )

    def produce(self, context: ChatlasViewContext) -> dict[str, object]:
        _ = context
        raise CliError("external Chatlas views cannot be auto-produced")

    def production_instructions(self, context: ChatlasViewContext) -> dict[str, object]:
        stage_hint = {
            "command": "agentos chatlas views stage",
            "view": self.name,
            "parameters": context.parameters,
        }
        return {
            "mode": "external",
            "state": "production_required",
            "required_artifacts": list(self.artifact_contract.required_artifacts),
            "primary_artifact": self.artifact_contract.primary_artifact,
            "stage": stage_hint,
        }

    def build_produce_prompt(self, context: ChatlasViewContext) -> str:
        return self.prepare_agent_production(context, dry_run=True).prompt

    def prepare_agent_production(
        self,
        context: ChatlasViewContext,
        *,
        dry_run: bool = False,
    ) -> ChatlasPreparedAgentProduction:
        dependency_context = _zip_transcript_dependency_context(context)
        if dry_run:
            dependency_status = dependency_context.workflow.current_status(dependency_context)
            stage_id = None
            stage_path = context.chatlas_root / _VIEWS_ROOT / _STAGING_ROOT / "<stage-id>"
        else:
            dependency_status = _ensure_available(dependency_context, explain=False)
            if dependency_status.state not in {"fresh", "produced"}:
                raise CliError(
                    "cannot prepare zip-transcript-agent-summary: "
                    f"zip-transcript dependency is {dependency_status.state}"
                )
            stage_payload = _stage_external_view_context(context)
            stage = stage_payload.get("stage", {})
            stage_id = stage.get("stage_id") if isinstance(stage, dict) else None
            stage_path_value = stage.get("path") if isinstance(stage, dict) else None
            if not isinstance(stage_id, str) or not isinstance(stage_path_value, str):
                raise CliError("chatlas views stage returned an invalid stage payload")
            stage_path = Path(stage_path_value)

        source_artifact_path = _expected_primary_artifact_path(dependency_context)
        output_artifact_path = stage_path / self.artifact_contract.primary_artifact
        final_artifact_path = context.slot_path / self.artifact_contract.primary_artifact
        prompt = _zip_transcript_agent_summary_prepared_prompt(
            source_artifact_path=source_artifact_path,
            output_artifact_path=output_artifact_path,
            final_artifact_path=final_artifact_path,
        )
        return ChatlasPreparedAgentProduction(
            prompt=prompt,
            stage_id=stage_id,
            stage_path=stage_path,
            output_artifact_path=output_artifact_path,
            final_artifact_path=final_artifact_path,
            diagnostics={
                "dependency_view": dependency_context.workflow.name,
                "dependency_state": dependency_status.state,
                "dependency_artifact_path": str(source_artifact_path),
                "target_view": self.name,
                "target_cache_key": context.cache_key,
            },
        )


def _zip_transcript_agent_summary_prepared_prompt(
    *,
    source_artifact_path: Path,
    output_artifact_path: Path,
    final_artifact_path: Path,
) -> str:
    return (
        "Read this producer reference for artifact shape and compression rules:\n"
        f"{_ZIP_TRANSCRIPT_AGENT_SUMMARY_REFERENCE}\n"
        "The parent Chatlas runner has already prepared the dependency and stage.\n"
        "\n"
        f"Read source transcript JSON from: {source_artifact_path}\n"
        f"Write exactly one artifact file to: {output_artifact_path}\n"
        f"The committed target path after parent commit will be: {final_artifact_path}\n"
        "\n"
        "Do not run Chatlas staging or commit commands. Do not write to the committed "
        "target path. Do not create or modify any other Chatlas view artifact.\n"
        "\n"
        "Write compact JSON with this shape: "
        '{"class":"agentos.chatlas.zip_transcript_agent_summary",'
        '"schema_version":1,"view":"zip-transcript-agent-summary",'
        '"source_view":"zip-transcript","session":<source session>,'
        '"turns":[{"role":<role>,"text":<text>}]}.\n'
        "Copy `session` from the source. Preserve every source turn in order. "
        "Preserve every user turn text verbatim. Preserve every role exactly. "
        "Summarize assistant turns aggressively but keep nonblank text with decisions, "
        "commands, paths, identifiers, test results, failures, warnings, unresolved "
        "issues, and enough context for later references to remain intelligible.\n"
        "Return only the path you wrote."
    )


def _expected_primary_artifact_path(context: ChatlasViewContext) -> Path:
    return context.slot_path / context.workflow.artifact_contract.primary_artifact


def _prepared_agent_production_payload(prepared: ChatlasPreparedAgentProduction) -> dict[str, object]:
    return {
        "stage_id": prepared.stage_id,
        "stage_path": str(prepared.stage_path) if prepared.stage_path is not None else None,
        "output_artifact_path": str(prepared.output_artifact_path),
        "final_artifact_path": str(prepared.final_artifact_path),
        "diagnostics": prepared.diagnostics,
    }


def _zip_transcript_dependency_context(context: ChatlasViewContext) -> ChatlasViewContext:
    workflow = _workflow_by_name("zip-transcript")
    return _context_from_parameters(
        workflow=workflow,
        chatlas_root=context.chatlas_root,
        parameters=context.parameters,
        source_rows=context.source_rows,
    )


def _session_selector_flags(parameter: dict[str, object]) -> str:
    identity_hash = parameter.get("identity_hash")
    if isinstance(identity_hash, str) and identity_hash:
        return f"--identity-hash {identity_hash}"
    uri = parameter.get("uri")
    if isinstance(uri, str) and uri:
        return f"--uri {uri}"
    session_id = parameter.get("session_id")
    if isinstance(session_id, str) and session_id:
        return f"--session-id {session_id}"
    raise CliError("cannot build session selector for chatlas produce: no identity_hash, uri, or session_id")


def _zip_transcript_dependency_status(
    context: ChatlasViewContext,
    *,
    explain: bool,
) -> ChatlasViewStatus:
    dependency_context = _zip_transcript_dependency_context(context)
    return _ensure_available(dependency_context, explain=explain)


def _registered_workflows() -> tuple[ChatlasViewWorkflow, ...]:
    workflows: tuple[ChatlasViewWorkflow, ...] = (
        ZipTranscriptWorkflow(),
        ZipTranscriptAgentSummaryWorkflow(),
    )
    names = [workflow.name for workflow in workflows]
    if len(names) != len(set(names)):
        raise CliError("duplicate Chatlas view workflow names registered")
    return workflows


def _workflow_by_name(name: str) -> ChatlasViewWorkflow:
    for workflow in _registered_workflows():
        if workflow.name == name:
            return workflow
    known = ", ".join(workflow.name for workflow in _registered_workflows())
    raise CliError(f"unknown Chatlas view: {name}; known views: {known}")


def _context_from_selector(
    *,
    view: str,
    chatlas_root: Path | None,
    selectors: dict[str, object],
) -> ChatlasViewContext:
    workflow = _workflow_by_name(view)
    root = _chatlas_root(chatlas_root)
    session = select_one_chatlas_index_row(
        command=f"chatlas views {view}",
        chatlas_root=root,
        **selectors,
    )
    return _context_from_parameters(
        workflow=workflow,
        chatlas_root=root,
        parameters=[_canonical_session_parameter(session)],
        source_rows=[session],
    )


def _context_from_parameters(
    *,
    workflow: ChatlasViewWorkflow,
    chatlas_root: Path,
    parameters: list[dict[str, object]],
    source_rows: list[dict[str, Any]],
) -> ChatlasViewContext:
    cache_key = compute_chatlas_view_cache_key(view=workflow.name, parameters=parameters)
    return ChatlasViewContext(
        chatlas_root=chatlas_root,
        workflow=workflow,
        parameters=parameters,
        source_rows=source_rows,
        cache_key=cache_key,
        slot_path=resolve_chatlas_view_slot_path(
            view=workflow.name,
            cache_key=cache_key,
            chatlas_root=chatlas_root,
        ),
    )


def _canonical_session_parameter(session: dict[str, Any]) -> dict[str, object]:
    parameter: dict[str, object] = {
        "type": "chatlas.indexed-session",
    }
    for key in (
        "uri",
        "provider",
        "instance",
        "provider_instance_fingerprint",
        "session_id",
        "identity_hash",
    ):
        value = session.get(key)
        if value is not None:
            parameter[key] = value
    return parameter


def _zip_transcript_payload(session: dict[str, Any]) -> dict[str, object]:
    session_model = build_chatlas_session_model_from_index_row(session)
    return project_chatlas_session_model_view(session_model, view="zip-transcript")


def _zip_transcript_fingerprint(session: dict[str, Any]) -> str:
    return _json_sha256(_zip_transcript_payload(session))


def _source_session_dependency(
        parameter: dict[str, object],
    *,
    fingerprint: str,
) -> dict[str, object]:
    return {
        "name": "source-session",
        "type": "chatlas.indexed-session",
        "fingerprint": fingerprint,
        "parameter": _without_index_row(parameter),
    }


def _observed_dependencies_for_commit(
    workflow: ChatlasViewWorkflow,
    context: ChatlasViewContext,
) -> list[dict[str, object]]:
    if workflow.name == "zip-transcript-agent-summary":
        dependency_status = _zip_transcript_dependency_status(context, explain=False)
        return [
            {
                "name": "view:zip-transcript",
                "type": "chatlas.view",
                "view": "zip-transcript",
                "cache_key": compute_chatlas_view_cache_key(
                    view="zip-transcript",
                    parameters=context.parameters,
                ),
                "fingerprint": dependency_status.freshness.get("current_fingerprint"),
                "state": dependency_status.state,
            }
        ]
    return []


def _view_result(
    *,
    command: str,
    context: ChatlasViewContext,
    status: ChatlasViewStatus,
    explain: bool,
) -> dict[str, object]:
    view_payload: dict[str, object] = {
        "view": context.workflow.name,
        "name": context.workflow.name,
        "state": status.state,
        "kind": context.workflow.kind,
        "parameters": context.parameters,
        "cache_key": context.cache_key,
        "slot_path": str(context.slot_path),
        "artifact": status.artifact,
        "freshness": status.freshness,
        "production": status.production,
        "fields": status.fields or {},
    }
    if explain and status.manifest is not None:
        view_payload["manifest"] = status.manifest
    return {
        "status": "ok",
        "command": command,
        "chatlas_root": str(context.chatlas_root),
        "view": view_payload,
    }


def _committed_manifest(
    *,
    context: ChatlasViewContext,
    state: str,
    producer: str,
    observed_dependencies: list[dict[str, object]],
    artifacts: list[dict[str, object]],
    fields: dict[str, object],
) -> dict[str, object]:
    return {
        "class": "agentos.chatlas.view.manifest",
        "schema_version": 1,
        "view": context.workflow.name,
        "parameters": context.parameters,
        "cache_key": context.cache_key,
        "state": state,
        "producer": producer,
        "created_at": _utc_now(),
        "artifact_contract": _artifact_contract_payload(context.workflow.artifact_contract),
        "observed_dependencies": observed_dependencies,
        "artifacts": artifacts,
        "primary_artifact": context.workflow.artifact_contract.primary_artifact,
        "fields": fields,
    }


def _replace_slot_with_files(
    *,
    slot_path: Path,
    files: dict[str, bytes],
    manifest: dict[str, object],
) -> None:
    temp_path = slot_path.with_name(f".{slot_path.name}.tmp-{uuid4().hex}")
    temp_path.mkdir(parents=True, exist_ok=False)
    try:
        for name, content in files.items():
            target = temp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        _write_json(temp_path / _MANIFEST_FILENAME, manifest)
        _replace_directory(temp_path=temp_path, target_path=slot_path)
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)


def _replace_slot_from_stage(
    *,
    stage_path: Path,
    slot_path: Path,
    manifest: dict[str, object],
    artifact_files: list[Path],
) -> None:
    temp_path = slot_path.with_name(f".{slot_path.name}.tmp-{uuid4().hex}")
    temp_path.mkdir(parents=True, exist_ok=False)
    try:
        for artifact_path in artifact_files:
            shutil.copy2(artifact_path, temp_path / artifact_path.name)
        _write_json(temp_path / _MANIFEST_FILENAME, manifest)
        _replace_directory(temp_path=temp_path, target_path=slot_path)
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)


def _replace_directory(*, temp_path: Path, target_path: Path) -> None:
    backup_path = target_path.with_name(f".{target_path.name}.old-{uuid4().hex}")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        target_path.rename(backup_path)
    try:
        temp_path.rename(target_path)
    except Exception:
        if backup_path.exists() and not target_path.exists():
            backup_path.rename(target_path)
        raise
    if backup_path.exists():
        shutil.rmtree(backup_path)


def _validate_required_stage_artifacts(
    stage_path: Path,
    contract: ChatlasViewArtifactContract,
    *,
    context: ChatlasViewContext,
) -> list[Path]:
    artifact_paths: list[Path] = []
    for artifact_name in contract.required_artifacts:
        artifact_path = stage_path / artifact_name
        if not artifact_path.is_file():
            raise CliError(f"missing staged Chatlas view artifact: {artifact_path}")
        _validate_stage_artifact_payload(
            artifact_path,
            contract=contract,
            context=context,
        )
        artifact_paths.append(artifact_path)
    return artifact_paths


def _artifact_payloads(
    slot_path: Path,
    artifact_files: list[Path],
    *,
    contract: ChatlasViewArtifactContract,
) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    for artifact_path in artifact_files:
        content = artifact_path.read_bytes()
        target_path = slot_path / artifact_path.name
        artifacts.append(
            {
                "name": artifact_path.name,
                "path": str(target_path),
                "content_type": contract.content_type
                if artifact_path.name in contract.required_artifacts
                else "application/octet-stream",
                "sha256": _bytes_sha256(content),
                "size_bytes": len(content),
                "primary": artifact_path.name == contract.primary_artifact,
            }
        )
    return artifacts


def _validate_stage_artifact_payload(
    artifact_path: Path,
    *,
    contract: ChatlasViewArtifactContract,
    context: ChatlasViewContext,
) -> None:
    if contract.primary_artifact != _SUMMARY_ARTIFACT or artifact_path.name != _SUMMARY_ARTIFACT:
        return
    payload = _read_json_object(
        artifact_path,
        description="Chatlas zip-transcript-agent-summary artifact",
    )
    if payload.get("class") != _SUMMARY_ARTIFACT_CLASS:
        raise CliError(
            "Chatlas zip-transcript-agent-summary artifact field class must be "
            f"{_SUMMARY_ARTIFACT_CLASS!r}: {artifact_path}"
        )
    if payload.get("view") != "zip-transcript-agent-summary":
        raise CliError(
            "Chatlas zip-transcript-agent-summary artifact field view must be "
            f"'zip-transcript-agent-summary': {artifact_path}"
        )
    if payload.get("source_view") != "zip-transcript":
        raise CliError(
            "Chatlas zip-transcript-agent-summary artifact field source_view must be "
            f"'zip-transcript': {artifact_path}"
        )
    if not isinstance(payload.get("session"), dict):
        raise CliError(
            "Chatlas zip-transcript-agent-summary artifact field session must be "
            f"a JSON object: {artifact_path}"
        )
    if not isinstance(payload.get("turns"), list):
        raise CliError(
            "Chatlas zip-transcript-agent-summary artifact field turns must be "
            f"a JSON array: {artifact_path}"
        )
    _lint_zip_transcript_agent_summary_commit(
        payload,
        source_payload=_zip_transcript_payload(context.source_rows[0]),
        artifact_path=artifact_path,
    )


def _lint_zip_transcript_agent_summary_commit(
    payload: dict[str, Any],
    *,
    source_payload: dict[str, object],
    artifact_path: Path,
) -> None:
    source_session = source_payload.get("session")
    if payload.get("session") != source_session:
        raise CliError(
            "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
            f"session must match source zip-transcript session: {artifact_path}"
        )
    source_turns = _dict_list(source_payload.get("turns"))
    summary_turns = _dict_list(payload.get("turns"))
    if len(summary_turns) != len(source_turns):
        raise CliError(
            "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
            f"turn count must match source zip-transcript "
            f"({len(summary_turns)} != {len(source_turns)}): {artifact_path}"
        )
    if len(summary_turns) != len(payload.get("turns", [])):
        raise CliError(
            "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
            f"each turn must be a JSON object: {artifact_path}"
        )

    for index, (source_turn, summary_turn) in enumerate(zip(source_turns, summary_turns, strict=True)):
        source_role = source_turn.get("role")
        summary_role = summary_turn.get("role")
        if summary_role != source_role:
            raise CliError(
                "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
                f"turn {index} role must match source zip-transcript "
                f"({summary_role!r} != {source_role!r}): {artifact_path}"
            )
        source_text = source_turn.get("text")
        summary_text = summary_turn.get("text")
        if not isinstance(summary_text, str):
            raise CliError(
                "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
                f"turn {index} text must be a string: {artifact_path}"
            )
        if source_role == "user" and summary_text != source_text:
            raise CliError(
                "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
                f"turn {index} user text must match source zip-transcript verbatim: "
                f"{artifact_path}"
            )
        if source_role == "assistant" and not summary_text.strip():
            raise CliError(
                "Chatlas zip-transcript-agent-summary Commit.Linter failed: "
                f"turn {index} assistant text must not be blank: {artifact_path}"
            )


def _primary_artifact_from_manifest(
    slot_path: Path,
    manifest: dict[str, Any],
) -> dict[str, object] | None:
    primary_name = manifest.get("primary_artifact")
    artifacts = manifest.get("artifacts")
    if not isinstance(primary_name, str) or not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("name") != primary_name:
            continue
        payload = dict(artifact)
        path = slot_path / primary_name
        payload["primary_path"] = str(path)
        payload["exists"] = path.is_file()
        return payload
    return None


def _read_manifest_if_present(slot_path: Path) -> dict[str, Any] | None:
    manifest_path = slot_path / _MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    return _read_json_object(manifest_path, description="Chatlas view manifest")


def _read_json_object(path: Path, *, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CliError(f"cannot read {description}: {path} ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid {description} JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{description} must be a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_canonical_json(payload) + "\n", encoding="utf-8")


def _parameters_from_manifest(manifest: dict[str, Any]) -> list[dict[str, object]]:
    parameters = manifest.get("parameters")
    if not isinstance(parameters, list) or not all(isinstance(item, dict) for item in parameters):
        raise CliError("Chatlas view manifest parameters must be a JSON object array")
    return [_canonical_jsonable(item) for item in parameters]


def _source_rows_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    source_rows = manifest.get("source_rows")
    if not isinstance(source_rows, list) or not all(isinstance(item, dict) for item in source_rows):
        raise CliError("Chatlas view stage manifest source_rows must be a JSON object array")
    return [_canonical_jsonable(item) for item in source_rows]


def _string_field(payload: dict[str, Any], key: str, *, description: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CliError(f"{description} field {key} must be a non-empty string")
    return value


def _artifact_contract_payload(contract: ChatlasViewArtifactContract) -> dict[str, object]:
    return {
        "primary_artifact": contract.primary_artifact,
        "required_artifacts": list(contract.required_artifacts),
        "content_type": contract.content_type,
    }


def _observed_dependency_fingerprint(manifest: dict[str, Any], name: str) -> object:
    for dependency in _manifest_dependency_list(manifest):
        if dependency.get("name") == name:
            return dependency.get("fingerprint")
    return None


def _manifest_dependency_list(manifest: dict[str, Any]) -> list[dict[str, object]]:
    dependencies = manifest.get("observed_dependencies")
    if not isinstance(dependencies, list):
        return []
    return [dependency for dependency in dependencies if isinstance(dependency, dict)]


def _dependency_summary(status: ChatlasViewStatus, *, explain: bool) -> dict[str, object]:
    dependency: dict[str, object] = {
        "dependency_state": status.state,
    }
    if explain:
        dependency["dependency_freshness"] = status.freshness
    return dependency


def _without_index_row(parameter: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in parameter.items() if key != "index_row"}


def _dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _chatlas_root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


def _json_sha256(value: object) -> str:
    return _bytes_sha256(_canonical_json(value).encode("utf-8"))


def _bytes_sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(_canonical_jsonable(value), ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _canonical_jsonable(value: object) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonical_jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, list):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_canonical_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_stage_id() -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:12]}"
