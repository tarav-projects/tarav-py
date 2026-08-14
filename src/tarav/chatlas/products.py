# $kw: --from Chatlas.View.Model
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import sys
from typing import Any, Iterator
from uuid import uuid4

from tarav._core.errors import CliError
from filelock import FileLock, Timeout

from tarav.chatlas._payload_helpers import dict_list
from tarav.chatlas.index_query import (
    select_materialization_row,
    select_one_chatlas_index_row,
)
from tarav.chatlas.normalization.session_model import (
    project_chatlas_session_model_view,
)
from tarav.chatlas.paths import default_chatlas_root
from tarav.chatlas.poi import ChatlasCommitLintError, raise_chatlas_commit_poi
from tarav.chatlas.session_cache import load_chatlas_session_model


PRODUCTS_ROOT = "products"
STAGING_ROOT = "_staging"
LOCKS_ROOT = "locks"
MANIFEST_FILENAME = "manifest.json"



COMPRESSION_FLOOR_MIN_SOURCE_BYTES = 50_000
COMPRESSION_FLOOR_MAX_RETAINED_RATIO = 0.70




COMPRESSION_WINDOW_SOURCE_BYTES = 10_000
COMPRESSION_WINDOW_MAX_RETAINED_RATIO = 0.90



COMPRESSION_WINDOW_MIN_UNTOUCHED_SHARE = 0.15







COMPRESSION_COLLAPSE_MIN_SOURCE_BYTES = 800
COMPRESSION_COLLAPSE_MAX_SUMMARY_BYTES = 40





COMPRESSION_WINDOW_MIN_RETAINED_RATIO = 0.10
COMPRESSION_WINDOW_MIN_CRUSHED_SHARE = 0.15
INPUT_FILENAME = "input.json"
ZIP_TRANSCRIPT_SUMMARY = "zip-transcript-summary"
ZIP_TRANSCRIPT_SUMMARY_ARTIFACT = "zip-transcript-summary.json"
_SUMMARY_REFERENCE = Path(
    "tarav-chatlas-md/skills/tarav-chatlas-pkg/references/"
    "producer-zip-transcript-summary.md"
)


@dataclass(frozen=True)
class ProductDefinition:
    name: str
    description: str
    input_view: str
    artifact_filename: str
    producer: str
    producer_reference: Path


@dataclass(frozen=True)
class ProductContext:
    root: Path
    definition: ProductDefinition
    session: dict[str, Any]
    identity_hash: str
    depot_path: Path
    input_payload: dict[str, object]
    input_fingerprint: str
    definition_fingerprint: str


def registered_products() -> tuple[ProductDefinition, ...]:
    return (
        ProductDefinition(
            name=ZIP_TRANSCRIPT_SUMMARY,
            description="Agent-produced compact transcript preserving every user turn.",
            input_view="zip-transcript",
            artifact_filename=ZIP_TRANSCRIPT_SUMMARY_ARTIFACT,
            producer="agentic",
            producer_reference=_SUMMARY_REFERENCE,
        ),
    )


def product_definition(name: str) -> ProductDefinition:
    for definition in registered_products():
        if definition.name == name:
            return definition
    known = ", ".join(value.name for value in registered_products())
    raise CliError(f"unknown Chatlas product: {name}; known products: {known}")


def chatlas_products_list(*, chatlas_root: Path | None = None) -> dict[str, object]:
    root = _chatlas_root(chatlas_root)
    return {
        "status": "ok",
        "command": "chatlas products list",
        "chatlas_root": str(root),
        "products_root": str(root / PRODUCTS_ROOT),
        "products": [_definition_payload(value) for value in registered_products()],
    }


def chatlas_products_get(
    *,
    product: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    return _product_result(
        command="chatlas products get",
        context=_context_from_selector(
            product=product, chatlas_root=chatlas_root, selectors=selectors
        ),
        explain=explain,
    )


def chatlas_products_status(
    *,
    product: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    return _product_result(
        command="chatlas products status",
        context=_context_from_selector(
            product=product, chatlas_root=chatlas_root, selectors=selectors
        ),
        explain=explain,
    )


def chatlas_products_path(
    *,
    product: str,
    explain: bool = False,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    result = _product_result(
        command="chatlas products path",
        context=_context_from_selector(
            product=product, chatlas_root=chatlas_root, selectors=selectors
        ),
        explain=explain,
    )
    artifact = result["product"].get("artifact")
    result["path"] = artifact.get("path") if isinstance(artifact, dict) else None
    return result


def chatlas_products_stage(
    *,
    product: str,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(
        product=product, chatlas_root=chatlas_root, selectors=selectors
    )
    return _stage_context(context)


def chatlas_products_produce(
    *,
    product: str,
    chatlas_root: Path | None = None,
    **selectors: object,
) -> dict[str, object]:
    context = _context_from_selector(
        product=product, chatlas_root=chatlas_root, selectors=selectors
    )
    stage = _stage_context(context)
    stage_payload = stage["stage"]
    stage_path = Path(str(stage_payload["path"]))
    output_path = stage_path / context.definition.artifact_filename
    return {
        "status": "ok",
        "command": "chatlas products produce",
        "product": context.definition.name,
        "stage": stage_payload,
        "prompt": _production_prompt(
            context,
            input_path=stage_path / INPUT_FILENAME,
            output_path=output_path,
            stage_id=str(stage_payload["stage_id"]),
        ),
    }


def _resolve_stage(
    stage_id: str, root: Path
) -> tuple[ProductContext, Path, Path]:
    """Resolve a stage id to its product context, stage dir, and artifact path.

    Shared by commit, check, and scaffold so the fingerprint guards cannot drift
    between the command that validates and the command that writes.
    """
    stage_path = root / PRODUCTS_ROOT / STAGING_ROOT / stage_id
    stage_manifest = _read_json_object(
        stage_path / MANIFEST_FILENAME, description="Chatlas product stage manifest"
    )
    name = _required_string(stage_manifest, "product", "product stage manifest")
    identity_hash = _required_string(
        stage_manifest, "identity_hash", "product stage manifest"
    )
    context = _context_from_selector(
        product=name,
        chatlas_root=root,
        selectors={"identity_hash": identity_hash},
    )
    if stage_manifest.get("input_fingerprint") != context.input_fingerprint:
        raise CliError("Chatlas product input changed after staging; create a new stage")
    if stage_manifest.get("definition_fingerprint") != context.definition_fingerprint:
        raise CliError("Chatlas product definition changed after staging; create a new stage")
    return context, stage_path, stage_path / context.definition.artifact_filename


def chatlas_products_check(
    *,
    stage_id: str,
    allow_low_compression: bool = False,
    allow_aggressive_compression: bool = False,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    """Run the commit linter against a staged artifact without committing it.

    Reports a refusal as data rather than only raising: the producing agent
    reads this payload to learn what is still wrong, so the failure path has to
    stay machine-readable.
    """
    root = _chatlas_root(chatlas_root)
    context, _stage_path, artifact_path = _resolve_stage(stage_id, root)
    result: dict[str, object] = {
        "stage_id": stage_id,
        "product": context.definition.name,
        "identity_hash": context.identity_hash,
        "artifact_path": str(artifact_path),
        "ok": False,
        "finding": None,
        "error": None,
        "allow_low_compression": allow_low_compression,
        "allow_aggressive_compression": allow_aggressive_compression,
    }
    if not artifact_path.is_file():
        result["error"] = f"missing staged Chatlas product artifact: {artifact_path}"
        return _check_payload(result)
    try:
        payload = _read_json_object(
            artifact_path, description=f"Chatlas {context.definition.name} artifact"
        )
        _validate_product_artifact(
            context,
            payload=payload,
            artifact_path=artifact_path,
            allow_low_compression=allow_low_compression,
            allow_aggressive_compression=allow_aggressive_compression,
        )
    except ChatlasCommitLintError as exc:
        result["finding"] = exc.poi.as_dict()
        result["error"] = str(exc)
        return _check_payload(result)
    except CliError as exc:
        result["error"] = str(exc)
        return _check_payload(result)
    result["ok"] = True
    return _check_payload(result)


def _check_payload(result: dict[str, object]) -> dict[str, object]:
    return {
        "status": "ok" if result["ok"] else "error",
        "command": "chatlas products check",
        "check": result,
    }


def chatlas_products_scaffold(
    *, stage_id: str, force: bool = False, chatlas_root: Path | None = None
) -> dict[str, object]:
    """Write a structurally complete, semantically empty artifact into the stage.

    Everything the producer must not invent is copied from the staged input:
    the envelope fields, the session object, and every user turn verbatim.
    Assistant text is left empty so the linter names exactly the turns that
    still need writing.
    """
    root = _chatlas_root(chatlas_root)
    context, _stage_path, artifact_path = _resolve_stage(stage_id, root)
    if artifact_path.exists() and not force:
        raise CliError(
            f"staged Chatlas product artifact already exists: {artifact_path} "
            "(pass --force to overwrite)"
        )
    source = context.input_payload
    source_turns = dict_list(source.get("turns"))
    turns = [
        {**turn, "text": turn.get("text") if turn.get("role") == "user" else ""}
        for turn in source_turns
    ]
    payload = {
        "class": source.get("class"),
        "schema_version": source.get("schema_version"),
        "view": source.get("view"),
        "session": source.get("session"),
        "turns": turns,
    }
    _write_json(artifact_path, payload)
    to_fill = sum(1 for turn in source_turns if turn.get("role") == "assistant")
    return {
        "status": "ok",
        "command": "chatlas products scaffold",
        "scaffold": {
            "stage_id": stage_id,
            "product": context.definition.name,
            "identity_hash": context.identity_hash,
            "artifact_path": str(artifact_path),
            "turn_count": len(turns),
            "assistant_turns_to_fill": to_fill,
        },
    }


def chatlas_products_commit(
    *,
    stage_id: str,
    allow_low_compression: bool = False,
    allow_aggressive_compression: bool = False,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    root = _chatlas_root(chatlas_root)
    context, stage_path, artifact_path = _resolve_stage(stage_id, root)
    if not artifact_path.is_file():
        raise CliError(f"missing staged Chatlas product artifact: {artifact_path}")
    payload = _read_json_object(
        artifact_path, description=f"Chatlas {context.definition.name} artifact"
    )
    _validate_product_artifact(
        context,
        payload=payload,
        artifact_path=artifact_path,
        allow_low_compression=allow_low_compression,
        allow_aggressive_compression=allow_aggressive_compression,
    )
    content = artifact_path.read_bytes()
    manifest = {
        "class": "agentos_chatlas.product.manifest",
        "schema_version": 1,
        "product": context.definition.name,
        "identity_hash": context.identity_hash,
        "input_view": context.definition.input_view,
        "input_fingerprint": context.input_fingerprint,
        "definition_fingerprint": context.definition_fingerprint,
        "producer": context.definition.producer,
        "created_at": _utc_now(),


        "compression": _compression_record(
            context.input_payload,
            payload,
            allow_low_compression=allow_low_compression,
            allow_aggressive_compression=allow_aggressive_compression,
        ),
        "artifact": {
            "name": context.definition.artifact_filename,
            "path": str(context.depot_path / context.definition.artifact_filename),
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "content_type": "application/json",
        },
    }
    with product_materialization_lock(
        product=context.definition.name,
        identity_hash=context.identity_hash,
        chatlas_root=root,
    ):
        _replace_product_depot(
            context.depot_path,
            artifact_name=context.definition.artifact_filename,
            artifact_content=content,
            manifest=manifest,
        )
    if stage_path.exists():
        shutil.rmtree(stage_path)
    return _product_result(
        command="chatlas products commit", context=context, explain=False
    )


def chatlas_products_run_produce(
    *,
    product: str,
    provider: str,
    rows: list[dict[str, object]],
    profile: str | None = None,
    model: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    concurrency: int = 1,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    root = _chatlas_root(chatlas_root)
    if concurrency < 1:
        raise CliError("Chatlas product run concurrency must be at least 1")

    def run_one(row: dict[str, object]) -> dict[str, object]:
        try:
            return _run_product_for_row(
                row=row,
                product=product,
                provider=provider,
                profile=profile,
                model=model,
                dry_run=dry_run,
                force=force,
                root=root,
            )
        except CliError as exc:
            return {
                "identity_hash": row.get("identity_hash"),
                "exit_code": 1,
                "error": str(exc),
            }




    if concurrency == 1 or len(rows) <= 1:
        results = [run_one(row) for row in rows]
    else:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(run_one, rows))

    failures = [
        {
            "identity_hash": result.get("identity_hash"),
            "error": result.get("error") or result.get("commit_error"),
        }
        for result in results
        if _run_failed(result, dry_run=dry_run)
    ]
    return {
        "status": "ok" if not failures else "error",
        "command": "chatlas products run-produce",
        "product": product,
        "dry_run": dry_run,
        "concurrency": concurrency,
        "run_count": len(results),
        "skipped_count": sum(1 for result in results if result.get("skipped")),
        "failed_count": len(failures),
        "failures": failures,
        "runs": results,
    }


def _run_failed(result: dict[str, object], *, dry_run: bool) -> bool:
    if result.get("skipped"):
        return False
    if result.get("error") or result.get("commit_error"):
        return True
    return result.get("exit_code", 0 if dry_run else 1) != 0


def _run_product_for_row(
    *,
    row: dict[str, object],
    product: str,
    provider: str,
    profile: str | None,
    model: str | None,
    dry_run: bool,
    force: bool,
    root: Path,
) -> dict[str, object]:
    from tarav.agent.providers.registry import resolve_agent
    from tarav.agent.run_runtime import AgentCommandConfig, AgentRunConfig

    context = _context_from_row(product=product, chatlas_root=root, session=dict(row))
    identity_hash = context.identity_hash
    if not force and _product_state(context)["state"] == "fresh":
        return {"identity_hash": identity_hash, "skipped": True, "reason": "fresh"}

    if dry_run:
        stage_path = root / PRODUCTS_ROOT / STAGING_ROOT / "<stage-id>"
        prompt = _production_prompt(
            context,
            input_path=stage_path / INPUT_FILENAME,
            output_path=stage_path / context.definition.artifact_filename,
            stage_id="<stage-id>",
        )
        agent = resolve_agent(provider=provider, profile=profile, start_path=root)
        command = agent.run_dry(
            AgentCommandConfig(
                prompt=prompt, model=model, interaction_mode="non_interactive"
            )
        )
        return {
            "identity_hash": identity_hash,
            "prompt": prompt,
            "agent_command": list(command.lines),
        }

    prepared = chatlas_products_produce(
        product=product, chatlas_root=root, identity_hash=identity_hash
    )
    prompt = str(prepared["prompt"])
    stage_id = str(prepared["stage"]["stage_id"])
    agent = resolve_agent(provider=provider, profile=profile, start_path=root)
    run = agent.run(
        AgentCommandConfig(
            prompt=prompt, model=model, interaction_mode="non_interactive"
        ),
        AgentRunConfig(cwd=root, process_mode="terminal"),
    )
    result: dict[str, object] = {
        "identity_hash": identity_hash,
        "exit_code": run.exit_code,
        "stage_id": stage_id,
    }
    if run.exit_code == 0:
        try:
            result["commit"] = chatlas_products_commit(
                stage_id=stage_id, chatlas_root=root
            )
        except CliError as exc:
            result["commit_error"] = str(exc)
    else:
        result["error"] = f"agent exited {run.exit_code}"
    return result


@contextmanager
def product_materialization_lock(
    *,
    product: str,
    identity_hash: str,
    chatlas_root: Path | None = None,
) -> Iterator[None]:
    root = _chatlas_root(chatlas_root)
    lock_path = root / LOCKS_ROOT / PRODUCTS_ROOT / product / f"{identity_hash}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(lock_path)
    print(f"[chatlas] acquiring product lock: {lock_path}", file=sys.stderr)
    try:
        lock.acquire(timeout=0)
    except Timeout:
        print(f"[chatlas] waiting for product lock: {lock_path}", file=sys.stderr)
        lock.acquire()
    print(f"[chatlas] acquired product lock: {lock_path}", file=sys.stderr)
    try:
        yield
    finally:
        lock.release()
        print(f"[chatlas] released product lock: {lock_path}", file=sys.stderr)


def _context_from_selector(
    *, product: str, chatlas_root: Path | None, selectors: dict[str, object]
) -> ProductContext:
    root = _chatlas_root(chatlas_root)
    session = select_one_chatlas_index_row(
        command=f"chatlas products {product}", chatlas_root=root, **selectors
    )
    session = select_materialization_row(
        session,
        uri=_optional_string(selectors.get("uri")),
        instances=_optional_string_tuple(selectors.get("instances")),
        provider_instance_fingerprint=_optional_string(
            selectors.get("provider_instance_fingerprint")
        ),
    )
    return _context_from_row(product=product, chatlas_root=root, session=session)


def _context_from_row(
    *, product: str, chatlas_root: Path, session: dict[str, Any]
) -> ProductContext:
    definition = product_definition(product)
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise CliError("Chatlas product requires one session identity_hash")
    session_model = load_chatlas_session_model(session, chatlas_root=chatlas_root)
    input_payload = project_chatlas_session_model_view(
        session_model, view=definition.input_view
    )
    reference_path = _resolve_reference(definition.producer_reference)
    reference_content = reference_path.read_text(encoding="utf-8")
    definition_fingerprint = _json_sha256(
        {
            **_definition_payload(definition),
            "producer_reference_content": reference_content,
            "artifact_shape": "zip-transcript.v1",
        }
    )
    return ProductContext(
        root=chatlas_root,
        definition=definition,
        session=session,
        identity_hash=identity_hash,
        depot_path=chatlas_root / PRODUCTS_ROOT / definition.name / identity_hash,
        input_payload=input_payload,
        input_fingerprint=_json_sha256(input_payload),
        definition_fingerprint=definition_fingerprint,
    )


def _product_result(
    *, command: str, context: ProductContext, explain: bool
) -> dict[str, object]:
    state = _product_state(context, explain=explain)
    return {
        "status": "ok",
        "command": command,
        "chatlas_root": str(context.root),
        "product": {
            "name": context.definition.name,
            "input_view": context.definition.input_view,
            "identity_hash": context.identity_hash,
            "state": state["state"],
            "warning": state.get("warning"),
            "artifact": state.get("artifact"),
            "freshness": state["freshness"],
            "production": {
                "required": state["state"] == "production_required",
                "command": "tarav chatlas products produce",
            },
        },
    }


def _product_state(
    context: ProductContext, *, explain: bool = False
) -> dict[str, object]:
    manifest_path = context.depot_path / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return {
            "state": "production_required",
            "warning": "Chatlas product is missing; production is required",
            "artifact": None,
            "freshness": {"state": "missing"},
        }
    try:
        manifest = _read_json_object(
            manifest_path, description="Chatlas product manifest"
        )
    except CliError as exc:
        return {
            "state": "production_required",
            "warning": str(exc),
            "artifact": None,
            "freshness": {"state": "invalid"},
        }
    artifact = manifest.get("artifact")
    artifact_path = context.depot_path / context.definition.artifact_filename
    input_matches = manifest.get("input_fingerprint") == context.input_fingerprint
    definition_matches = (
        manifest.get("definition_fingerprint") == context.definition_fingerprint
    )
    artifact_exists = artifact_path.is_file()
    fresh = input_matches and definition_matches and artifact_exists
    freshness: dict[str, object] = {
        "state": "fresh" if fresh else "stale",
        "input_matches": input_matches,
        "definition_matches": definition_matches,
        "artifact_exists": artifact_exists,
    }
    if explain:
        freshness.update(
            {
                "current_input_fingerprint": context.input_fingerprint,
                "observed_input_fingerprint": manifest.get("input_fingerprint"),
                "current_definition_fingerprint": context.definition_fingerprint,
                "observed_definition_fingerprint": manifest.get(
                    "definition_fingerprint"
                ),
            }
        )
    return {
        "state": "fresh" if fresh else "production_required",
        "warning": None
        if fresh
        else "Chatlas product is stale; production is required",
        "artifact": artifact if isinstance(artifact, dict) else None,
        "freshness": freshness,
    }


def _stage_context(context: ProductContext) -> dict[str, object]:
    stage_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:12]}"
    stage_path = context.root / PRODUCTS_ROOT / STAGING_ROOT / stage_id
    stage_path.mkdir(parents=True, exist_ok=False)
    _write_json(stage_path / INPUT_FILENAME, context.input_payload)
    _write_json(
        stage_path / MANIFEST_FILENAME,
        {
            "class": "agentos_chatlas.product.stage",
            "schema_version": 1,
            "stage_id": stage_id,
            "product": context.definition.name,
            "identity_hash": context.identity_hash,
            "input_view": context.definition.input_view,
            "input_fingerprint": context.input_fingerprint,
            "definition_fingerprint": context.definition_fingerprint,
            "created_at": _utc_now(),
        },
    )
    return {
        "status": "ok",
        "command": "chatlas products stage",
        "stage": {
            "stage_id": stage_id,
            "path": str(stage_path),
            "input_path": str(stage_path / INPUT_FILENAME),
            "output_path": str(stage_path / context.definition.artifact_filename),
        },
    }


def _production_prompt(
    context: ProductContext, *, input_path: Path, output_path: Path, stage_id: str
) -> str:
    reference_path = _resolve_reference(context.definition.producer_reference)
    return (
        "Read this producer reference for compression rules:\n"
        f"{reference_path}\n\n"
        f"Read the input {context.definition.input_view} view from: {input_path}\n"
        f"Write exactly one JSON artifact to: {output_path}\n\n"
        "Do not build the artifact by hand. First run "
        f"`tarav chatlas products scaffold --stage-id {stage_id} --json`, which "
        "writes the skeleton with class, schema_version, view, session, turn "
        "count, order, roles, and every user turn already correct. Then fill only "
        "the empty assistant text fields, summarizing aggressively and leaving "
        "none blank. Then run "
        f"`tarav chatlas products check --stage-id {stage_id} --json` and fix "
        "whatever it reports until it passes. Do not write any other file. "
        "Return only the path written."
    )


def _validate_product_artifact(
    context: ProductContext,
    *,
    payload: dict[str, Any],
    artifact_path: Path,
    allow_low_compression: bool = False,
    allow_aggressive_compression: bool = False,
) -> None:
    source = context.input_payload
    for field in ("class", "schema_version", "view"):
        if payload.get(field) != source.get(field):
            raise CliError(
                f"Chatlas {context.definition.name} artifact field {field} must "
                f"match input view: {artifact_path}"
            )
    if not isinstance(payload.get("session"), dict):
        raise CliError(
            f"Chatlas {context.definition.name} artifact session must be an object"
        )
    if not isinstance(payload.get("turns"), list):
        raise CliError(
            f"Chatlas {context.definition.name} artifact turns must be an array"
        )
    _lint_zip_transcript_summary_commit(
        payload,
        source_payload=source,
        artifact_path=artifact_path,
        allow_low_compression=allow_low_compression,
        allow_aggressive_compression=allow_aggressive_compression,
    )


def _lint_zip_transcript_summary_commit(
    payload: dict[str, Any],
    *,
    source_payload: dict[str, object],
    artifact_path: Path,
    allow_low_compression: bool = False,
    allow_aggressive_compression: bool = False,
) -> None:
    blank_indices: list[int] = []
    source_session = source_payload.get("session")
    if payload.get("session") != source_session:
        raise_chatlas_commit_poi(
            "Session.Mismatch",
            artifact_path=artifact_path,
            situation="session must match source zip-transcript session",
            evidence={"source_session": source_session, "summary_session": payload.get("session")},
        )
    source_turns = dict_list(source_payload.get("turns"))
    summary_turns = dict_list(payload.get("turns"))
    if len(summary_turns) != len(source_turns):
        raise_chatlas_commit_poi(
            "Turn.CountMismatch",
            artifact_path=artifact_path,
            situation=(
                "turn count must match source zip-transcript "
                f"({len(summary_turns)} != {len(source_turns)})"
            ),
            evidence={"source_turn_count": len(source_turns), "summary_turn_count": len(summary_turns)},
        )
    turns = payload.get("turns")
    if not isinstance(turns, list) or len(summary_turns) != len(turns):
        raise_chatlas_commit_poi(
            "Turn.InvalidObject",
            artifact_path=artifact_path,
            situation="each turn must be a JSON object",
            evidence={"turn_count": len(turns or []), "object_turn_count": len(summary_turns)},
        )
    for index, (source_turn, summary_turn) in enumerate(
        zip(source_turns, summary_turns, strict=True)
    ):
        source_role = source_turn.get("role")
        summary_role = summary_turn.get("role")
        if summary_role != source_role:
            raise_chatlas_commit_poi(
                "Turn.RoleMismatch",
                artifact_path=artifact_path,
                situation=f"turn {index} role must match source zip-transcript",
                evidence={"turn_index": index, "source_role": source_role, "summary_role": summary_role},
            )
        source_text = source_turn.get("text")
        summary_text = summary_turn.get("text")
        if not isinstance(summary_text, str):
            raise_chatlas_commit_poi(
                "Turn.TextNotString",
                artifact_path=artifact_path,
                situation=f"turn {index} text must be a string",
                evidence={"turn_index": index, "actual_type": type(summary_text).__name__},
            )
        if source_role == "user" and summary_text != source_text:
            raise_chatlas_commit_poi(
                "Turn.UserTextNotVerbatim",
                artifact_path=artifact_path,
                situation=f"turn {index} user text must match source verbatim",
                evidence={"turn_index": index, "source_text": source_text, "summary_text": summary_text},
            )
        if source_role == "assistant" and not summary_text.strip():
            blank_indices.append(index)

    if blank_indices:
        raise_chatlas_commit_poi(
            "Turn.AssistantTextBlank",
            artifact_path=artifact_path,
            situation=(
                f"{len(blank_indices)} assistant turns are still blank; "
                f"first is turn {blank_indices[0]}"
            ),
            evidence={
                "turn_index": blank_indices[0],
                "blank_turn_count": len(blank_indices),
                "blank_turn_indices": blank_indices,
            },
        )

    _lint_compression_collapse(
        source_turns,
        summary_turns,
        artifact_path=artifact_path,
        allow_aggressive_compression=allow_aggressive_compression,
    )
    _lint_compression_floor(
        source_turns,
        summary_turns,
        artifact_path=artifact_path,
        allow_low_compression=allow_low_compression,
    )
    _lint_compression_windows(
        source_turns,
        summary_turns,
        artifact_path=artifact_path,
        allow_low_compression=allow_low_compression,
    )
    _lint_compression_crushed_windows(
        source_turns,
        summary_turns,
        artifact_path=artifact_path,
        allow_aggressive_compression=allow_aggressive_compression,
    )


def _compression_record(
    source_payload: dict[str, object],
    payload: dict[str, Any],
    *,
    allow_low_compression: bool,
    allow_aggressive_compression: bool = False,
) -> dict[str, object]:
    source_bytes = _assistant_text_bytes(dict_list(source_payload.get("turns")))
    summary_bytes = _assistant_text_bytes(dict_list(payload.get("turns")))
    large_enough = source_bytes >= COMPRESSION_FLOOR_MIN_SOURCE_BYTES
    return {
        "source_assistant_bytes": source_bytes,
        "summary_assistant_bytes": summary_bytes,
        "retained_ratio": (
            round(summary_bytes / source_bytes, 4) if source_bytes else None
        ),
        "floor_applied": large_enough and not allow_low_compression,
        "collapse_applied": large_enough and not allow_aggressive_compression,
        "allow_low_compression": allow_low_compression,
        "allow_aggressive_compression": allow_aggressive_compression,
    }


def _assistant_text_bytes(turns: list[dict[str, Any]]) -> int:
    return sum(
        len(str(turn.get("text") or "").encode("utf-8"))
        for turn in turns
        if turn.get("role") == "assistant"
    )


def _lint_compression_floor(
    source_turns: list[dict[str, Any]],
    summary_turns: list[dict[str, Any]],
    *,
    artifact_path: Path,
    allow_low_compression: bool,
) -> None:
    """Refuse an artifact that never actually compressed anything.

    Structure and verbatimness are checkable; compression is the one axis with
    no gate, so producers optimize away from it. Measured over assistant text
    only, because user turns are verbatim by contract and would otherwise mask
    an untouched assistant body.
    """
    if allow_low_compression:
        return
    source_bytes = _assistant_text_bytes(source_turns)
    if source_bytes < COMPRESSION_FLOOR_MIN_SOURCE_BYTES:
        return
    summary_bytes = _assistant_text_bytes(summary_turns)
    retained_ratio = summary_bytes / source_bytes
    if retained_ratio <= COMPRESSION_FLOOR_MAX_RETAINED_RATIO:
        return
    raise_chatlas_commit_poi(
        "Compression.Insufficient",
        artifact_path=artifact_path,
        situation=(
            f"assistant text retains {retained_ratio:.0%} of the source "
            f"({summary_bytes} of {source_bytes} bytes); resummarize the "
            "longest assistant turns until it retains at most "
            f"{COMPRESSION_FLOOR_MAX_RETAINED_RATIO:.0%}. Do not truncate text "
            "to reach the ratio; if this session genuinely cannot compress "
            "further, commit with --allow-low-compression and say why"
        ),
        evidence={
            "source_assistant_bytes": source_bytes,
            "summary_assistant_bytes": summary_bytes,
            "retained_ratio": round(retained_ratio, 4),
            "max_retained_ratio": COMPRESSION_FLOOR_MAX_RETAINED_RATIO,
            "longest_assistant_turns": _longest_assistant_turns(summary_turns),
        },
    )


def _lint_compression_collapse(
    source_turns: list[dict[str, Any]],
    summary_turns: list[dict[str, Any]],
    *,
    artifact_path: Path,
    allow_aggressive_compression: bool,
) -> None:
    """Refuse an artifact where a substantial assistant turn became a stub.

    This is the primary loss gate. It names exact turns rather than reporting a
    ratio because the repair path here is generative: an agent told only that it
    compressed too hard can pad, re-narrate, or invent filler, and invented text
    is unfalsifiable against the source. Pointing at specific source turns keeps
    the fix a restoration rather than a composition.
    """
    if allow_aggressive_compression:
        return
    if _assistant_text_bytes(source_turns) < COMPRESSION_FLOOR_MIN_SOURCE_BYTES:
        return
    collapsed: list[dict[str, int]] = []
    for index, (source_turn, summary_turn) in enumerate(
        zip(source_turns, summary_turns, strict=True)
    ):
        if source_turn.get("role") != "assistant":
            continue
        source_size = len(str(source_turn.get("text") or "").encode("utf-8"))
        summary_size = len(str(summary_turn.get("text") or "").encode("utf-8"))
        if (
            source_size >= COMPRESSION_COLLAPSE_MIN_SOURCE_BYTES
            and summary_size <= COMPRESSION_COLLAPSE_MAX_SUMMARY_BYTES
        ):
            collapsed.append(
                {
                    "turn_index": index,
                    "source_text_bytes": source_size,
                    "summary_text_bytes": summary_size,
                }
            )
    if not collapsed:
        return
    spans = ", ".join(
        f"turn {item['turn_index']} ({item['source_text_bytes']}B -> "
        f"{item['summary_text_bytes']}B)"
        for item in collapsed[:10]
    )
    raise_chatlas_commit_poi(
        "Compression.TurnCollapsed",
        artifact_path=artifact_path,
        situation=(
            f"{len(collapsed)} assistant turns collapsed to a stub: {spans}. "
            "Re-read those turns in the staged input and restore what a later "
            "turn depends on — decisions, commands, paths, identifiers, "
            "results, unresolved issues. Restore from the source; do not pad "
            "to a length. If those turns genuinely carried nothing, commit "
            "with --allow-aggressive-compression and say why"
        ),
        evidence={
            "collapsed_turn_count": len(collapsed),
            "collapsed_turns": collapsed[:20],
            "collapsed_turn_indices": [item["turn_index"] for item in collapsed],
            "min_source_bytes": COMPRESSION_COLLAPSE_MIN_SOURCE_BYTES,
            "max_summary_bytes": COMPRESSION_COLLAPSE_MAX_SUMMARY_BYTES,
        },
    )


def _lint_compression_crushed_windows(
    source_turns: list[dict[str, Any]],
    summary_turns: list[dict[str, Any]],
    *,
    artifact_path: Path,
    allow_aggressive_compression: bool,
) -> None:
    """Refuse an artifact that reduced a whole region to almost nothing.

    Secondary to the per-turn collapse check: it catches loss spread thinly
    across many turns, where no single turn is a stub but the region as a whole
    no longer carries its content. Kept loose and material-gated because tool
    output, build logs, and file dumps legitimately compress this far.
    """
    if allow_aggressive_compression:
        return
    source_bytes = _assistant_text_bytes(source_turns)
    if source_bytes < COMPRESSION_FLOOR_MIN_SOURCE_BYTES:
        return
    crushed = []
    for window in _compression_windows(source_turns, summary_turns):
        if not window["source_bytes"]:
            continue
        ratio = window["summary_bytes"] / window["source_bytes"]
        if ratio < COMPRESSION_WINDOW_MIN_RETAINED_RATIO:
            crushed.append({**window, "retained_ratio": round(ratio, 4)})
    crushed_share = (
        sum(window["source_bytes"] for window in crushed) / source_bytes
        if source_bytes
        else 0.0
    )
    if crushed_share < COMPRESSION_WINDOW_MIN_CRUSHED_SHARE:
        return
    spans = ", ".join(
        f"turns {window['first_turn_index']}-{window['last_turn_index']} "
        f"({window['retained_ratio']:.0%})"
        for window in crushed
    )
    raise_chatlas_commit_poi(
        "Compression.RegionCrushed",
        artifact_path=artifact_path,
        situation=(
            f"{len(crushed)} transcript regions retain almost none of their "
            f"source: {spans}. Re-read those ranges in the staged input and "
            "restore what later turns refer back to. Restore from the source; "
            "do not pad to a ratio. If those regions were genuinely disposable "
            "output, commit with --allow-aggressive-compression and say why"
        ),
        evidence={
            "crushed_window_count": len(crushed),
            "crushed_windows": crushed,
            "crushed_share": round(crushed_share, 4),
            "window_source_bytes": COMPRESSION_WINDOW_SOURCE_BYTES,
            "min_retained_ratio": COMPRESSION_WINDOW_MIN_RETAINED_RATIO,
            "min_crushed_share": COMPRESSION_WINDOW_MIN_CRUSHED_SHARE,
        },
    )


def _compression_windows(
    source_turns: list[dict[str, Any]], summary_turns: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group assistant turns into windows of roughly equal source size.

    Windows accumulate whole turns in transcript order and never split one, so a
    turn larger than the window budget simply becomes its own window.
    """
    windows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for index, (source_turn, summary_turn) in enumerate(
        zip(source_turns, summary_turns, strict=True)
    ):
        if source_turn.get("role") != "assistant":
            continue
        if current is None:
            current = {
                "first_turn_index": index,
                "last_turn_index": index,
                "source_bytes": 0,
                "summary_bytes": 0,
            }
        current["last_turn_index"] = index
        current["source_bytes"] += len(str(source_turn.get("text") or "").encode("utf-8"))
        current["summary_bytes"] += len(str(summary_turn.get("text") or "").encode("utf-8"))
        if current["source_bytes"] >= COMPRESSION_WINDOW_SOURCE_BYTES:
            windows.append(current)
            current = None
    if current is not None:
        windows.append(current)
    return windows


def _lint_compression_windows(
    source_turns: list[dict[str, Any]],
    summary_turns: list[dict[str, Any]],
    *,
    artifact_path: Path,
    allow_low_compression: bool,
) -> None:
    """Refuse an artifact that left a whole region of the transcript untouched.

    The global floor is satisfiable by crushing a few huge turns, so this checks
    that compression happened across the transcript rather than in one place.
    The threshold is loose on purpose: it answers "was this region worked on at
    all", not "was it compressed as hard as the rest".
    """
    if allow_low_compression:
        return
    source_bytes = _assistant_text_bytes(source_turns)
    if source_bytes < COMPRESSION_FLOOR_MIN_SOURCE_BYTES:
        return
    untouched = []
    for window in _compression_windows(source_turns, summary_turns):
        if not window["source_bytes"]:
            continue
        ratio = window["summary_bytes"] / window["source_bytes"]
        if ratio > COMPRESSION_WINDOW_MAX_RETAINED_RATIO:
            untouched.append({**window, "retained_ratio": round(ratio, 4)})
    untouched_share = (
        sum(window["source_bytes"] for window in untouched) / source_bytes
        if source_bytes
        else 0.0
    )
    if untouched_share < COMPRESSION_WINDOW_MIN_UNTOUCHED_SHARE:
        return
    spans = ", ".join(
        f"turns {window['first_turn_index']}-{window['last_turn_index']} "
        f"({window['retained_ratio']:.0%})"
        for window in untouched
    )
    raise_chatlas_commit_poi(
        "Compression.RegionUntouched",
        artifact_path=artifact_path,
        situation=(
            f"{len(untouched)} transcript regions were left essentially "
            f"uncompressed: {spans}. Summarize the assistant turns in those "
            "ranges; overall compression elsewhere does not cover them"
        ),
        evidence={
            "untouched_window_count": len(untouched),
            "untouched_windows": untouched,
            "untouched_share": round(untouched_share, 4),
            "window_source_bytes": COMPRESSION_WINDOW_SOURCE_BYTES,
            "max_retained_ratio": COMPRESSION_WINDOW_MAX_RETAINED_RATIO,
            "min_untouched_share": COMPRESSION_WINDOW_MIN_UNTOUCHED_SHARE,
        },
    )


def _longest_assistant_turns(
    turns: list[dict[str, Any]], *, limit: int = 10
) -> list[dict[str, int]]:
    """Name the turns worth resummarizing first, so the retry is targeted."""
    sizes = [
        {"turn_index": index, "text_bytes": len(str(turn.get("text") or "").encode("utf-8"))}
        for index, turn in enumerate(turns)
        if turn.get("role") == "assistant"
    ]
    sizes.sort(key=lambda item: item["text_bytes"], reverse=True)
    return sizes[:limit]


def _replace_product_depot(
    path: Path,
    *,
    artifact_name: str,
    artifact_content: bytes,
    manifest: dict[str, object],
) -> None:
    temp_path = path.with_name(f".{path.name}.tmp-{uuid4().hex}")
    backup_path = path.with_name(f".{path.name}.old-{uuid4().hex}")
    temp_path.mkdir(parents=True, exist_ok=False)
    try:
        (temp_path / artifact_name).write_bytes(artifact_content)
        _write_json(temp_path / MANIFEST_FILENAME, manifest)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.rename(backup_path)
        try:
            temp_path.rename(path)
        except Exception:
            if backup_path.exists() and not path.exists():
                backup_path.rename(path)
            raise
        if backup_path.exists():
            shutil.rmtree(backup_path)
    finally:
        if temp_path.exists():
            shutil.rmtree(temp_path)


def _definition_payload(definition: ProductDefinition) -> dict[str, object]:
    return {
        "name": definition.name,
        "description": definition.description,
        "input_view": definition.input_view,
        "artifact_filename": definition.artifact_filename,
        "producer": definition.producer,
        "producer_reference": str(definition.producer_reference),
    }


def _resolve_reference(relative_path: Path) -> Path:
    source = Path(__file__).resolve()
    for base in (Path.cwd().resolve(), *source.parents):
        candidate = base / relative_path
        if candidate.is_file():
            return candidate
    raise CliError(f"Chatlas product producer reference is unavailable: {relative_path}")


def _chatlas_root(chatlas_root: Path | None) -> Path:
    return (chatlas_root or default_chatlas_root()).expanduser().resolve()


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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _required_string(payload: dict[str, Any], key: str, description: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise CliError(f"{description} field {key} must be a non-empty string")
    return value


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _optional_string_tuple(value: object) -> tuple[str, ...] | None:
    if value is None:
        return None
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return None


def _json_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


__all__ = [
    "ProductDefinition",
    "chatlas_products_commit",
    "chatlas_products_get",
    "chatlas_products_list",
    "chatlas_products_path",
    "chatlas_products_produce",
    "chatlas_products_run_produce",
    "chatlas_products_stage",
    "chatlas_products_status",
    "product_materialization_lock",
    "registered_products",
    "_lint_zip_transcript_summary_commit",
]
