# $kw: ^chatlas2-conformance-corpus --from Raw.Archive --from Chatlas.Session.Index --from Session.Event.Tape --from Event.Ref --note [CT] explicit corpus ingress preserves recognized anonymized specimens and validates chronological events, messages, turns, contexts, and their self-verifying refs --supp ^c20260815-29u ^c20260815-30u ^c20260815-31u ^c20260815-39u ^c20260815-42u ^d20260816-0u ^d20260816-22u ^d20260816-23u ^d20260816-26u ^d20260816-27u
from __future__ import annotations

from dataclasses import dataclass
import gzip
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Iterable

from tarav._core.errors import CliError

from .anonymizer import ANONYMIZER_VERSION, anonymize_text
from .claude import (
    ClaudeLegacyRawNormalizer,
    ClaudePromptSourceRawNormalizer,
    ClaudeRawModelVersioner,
)
from .codex import CodexRawModelVersioner, CodexRawNormalizer
from .event_ref import event_ref, resolve_event_ref
from .message_ref import (
    chat_message_ref,
    compute_chat_message_hash,
    resolve_chat_message_ref,
)
from .turn_ref import (
    chat_turn_ref,
    compute_chat_turn_hash,
    resolve_chat_turn_ref,
)
from .model import JsonObject
from .pipeline import build_normal_model_from_row, transcript_paths


SCRIPT_SCHEMA = "tarav.chatlas2.conformance.script.v1"
CAPTURE_SCHEMA = "tarav.chatlas2.conformance.capture.v1"
CANDIDATE_SCHEMA = "tarav.chatlas2.conformance.candidate.v1"

_SCRIPT_KEYS = {
    "capture_requirements",
    "features",
    "operator_actions",
    "revision",
    "schema",
    "script_id",
    "title",
    "user_messages",
}
_CAPTURE_KEYS = {
    "artifacts",
    "capture_id",
    "captured_at",
    "features",
    "identity_ref",
    "provider",
    "schema",
    "script_id",
    "script_revision",
    "session_ref",
    "status",
}


@dataclass(frozen=True, slots=True)
class ScriptSpec:
    script_id: str
    revision: int
    title: str
    user_messages: tuple[str, ...]
    operator_actions: tuple[str, ...]
    features: tuple[str, ...]
    capture_requirements: tuple[str, ...]


def load_script_spec(path: Path) -> ScriptSpec:
    payload = _load_json_object(path)
    unexpected = sorted(set(payload) - _SCRIPT_KEYS)
    missing = sorted(_SCRIPT_KEYS - set(payload))
    if unexpected:
        raise CliError(
            f"Chatlas2 script specification has unexpected keys: {unexpected}"
        )
    if missing:
        raise CliError(f"Chatlas2 script specification is missing keys: {missing}")
    if payload.get("schema") != SCRIPT_SCHEMA:
        raise CliError(f"unsupported Chatlas2 script schema: {payload.get('schema')!r}")
    script_id = _nonempty_string(payload.get("script_id"), name="script_id")
    revision = payload.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CliError("Chatlas2 script revision must be a positive integer")
    return ScriptSpec(
        script_id=script_id,
        revision=revision,
        title=_nonempty_string(payload.get("title"), name="title"),
        user_messages=_string_tuple(payload.get("user_messages"), name="user_messages"),
        operator_actions=_string_tuple(
            payload.get("operator_actions"),
            name="operator_actions",
            allow_empty=True,
        ),
        features=_string_tuple(payload.get("features"), name="features"),
        capture_requirements=_string_tuple(
            payload.get("capture_requirements"),
            name="capture_requirements",
        ),
    )


def prepare_capture(
    *,
    row: dict[str, Any],
    script: ScriptSpec,
    captured_at: str,
    features: Iterable[str],
    stage_dir: Path,
) -> Path:
    provider = _nonempty_string(row.get("provider"), name="provider")
    session_id = _nonempty_string(row.get("session_id"), name="session_id")
    identity_hash = _nonempty_string(row.get("identity_hash"), name="identity_hash")
    paths = transcript_paths(row)
    if not paths:
        raise CliError("Chatlas2 corpus ingress found no retained transcript artifacts")
    stage_artifacts = stage_dir / "artifacts"
    stage_artifacts.mkdir(parents=True, exist_ok=True)
    artifacts: list[JsonObject] = []
    prepared_artifacts: list[JsonObject] = []
    anonymous_paths: list[Path] = []
    for ordinal, source_path in enumerate(paths, start=1):
        try:
            source_bytes = source_path.read_bytes()
            source_text = source_bytes.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise CliError(
                f"cannot read text transcript artifact {source_path}: {exc}"
            ) from exc
        anonymized = anonymize_text(source_text)
        corpus_bytes = anonymized.text.encode("utf-8")
        source_digest = sha256(source_bytes).hexdigest()
        corpus_digest = sha256(corpus_bytes).hexdigest()
        staged_path = stage_artifacts / f"artifact-{ordinal}-{corpus_digest}.raw"
        staged_path.write_bytes(corpus_bytes)
        anonymous_paths.append(staged_path)
        source_version = _raw_model_version(provider, source_path)
        corpus_version = _raw_model_version(provider, staged_path)
        if source_version != corpus_version:
            raise CliError(
                "Chatlas2 anonymization changed Raw.Model.Version recognition: "
                f"{source_version!r} -> {corpus_version!r}"
            )
        artifact_id = f"artifact-{ordinal}"
        relative_path = _artifact_relative_path(corpus_digest)
        artifacts.append(
            {
                "artifact_id": artifact_id,
                "role": "transcript",
                "source_sha256": f"sha256:{source_digest}",
                "corpus_sha256": f"sha256:{corpus_digest}",
                "size": len(corpus_bytes),
                "compression": "gzip",
                "path": relative_path.as_posix(),
                "raw_model_version": source_version,
                "anonymizer_version": ANONYMIZER_VERSION,
                "replacements": anonymized.replacements,
                "warnings": list(anonymized.warnings),
            }
        )
        prepared_artifacts.append(
            {
                "artifact_id": artifact_id,
                "path": str(staged_path.resolve()),
            }
        )
    anonymous_row = _row_for_paths(row, anonymous_paths)
    if any(artifact["raw_model_version"] is not None for artifact in artifacts):
        source_model = build_normal_model_from_row(row)
        corpus_model = build_normal_model_from_row(anonymous_row)
        if _model_signature(source_model) != _model_signature(corpus_model):
            raise CliError(
                "Chatlas2 anonymization changed normalized specimen topology"
            )
        if _user_messages(corpus_model) != list(script.user_messages):
            raise CliError(
                "Chatlas2 anonymized capture does not reproduce the script's exact user messages"
            )
    feature_values = tuple(sorted(set(features)))
    if not feature_values:
        raise CliError("Chatlas2 capture features must not be empty")
    record: JsonObject = {
        "schema": CAPTURE_SCHEMA,
        "script_id": script.script_id,
        "script_revision": script.revision,
        "provider": provider,
        "session_ref": _hash_ref("session", session_id),
        "identity_ref": _hash_ref("identity", identity_hash),
        "captured_at": _nonempty_string(captured_at, name="captured_at"),
        "status": "accepted",
        "features": list(feature_values),
        "artifacts": artifacts,
    }
    record["capture_id"] = _capture_id(record)
    candidate = {
        "schema": CANDIDATE_SCHEMA,
        "record": record,
        "prepared_artifacts": prepared_artifacts,
    }
    candidate_path = stage_dir / f"candidate-{record['capture_id']}.json"
    candidate_path.write_text(_pretty_json(candidate), encoding="utf-8")
    return candidate_path


def register_candidate(candidate_path: Path, *, corpus_root: Path) -> bool:
    candidate = _load_json_object(candidate_path)
    if candidate.get("schema") != CANDIDATE_SCHEMA:
        raise CliError("unsupported Chatlas2 corpus candidate schema")
    record = candidate.get("record")
    prepared = candidate.get("prepared_artifacts")
    if not isinstance(record, dict) or not isinstance(prepared, list):
        raise CliError("invalid Chatlas2 corpus candidate")
    _validate_capture(record)
    existing = load_capture_records(corpus_root / "captures.jsonl")
    for current in existing:
        if current["capture_id"] != record["capture_id"]:
            continue
        if current == record:
            return False
        raise CliError(f"conflicting capture_id {record['capture_id']}")
    if record["capture_id"] != _capture_id(record):
        raise CliError("Chatlas2 candidate capture_id does not match its content")
    prepared_by_id: dict[str, Path] = {}
    for item in prepared:
        if not isinstance(item, dict):
            raise CliError("invalid prepared artifact entry")
        artifact_id = _nonempty_string(item.get("artifact_id"), name="artifact_id")
        path_text = _nonempty_string(item.get("path"), name="prepared artifact path")
        prepared_by_id[artifact_id] = Path(path_text)
    for artifact in record["artifacts"]:
        artifact_id = str(artifact["artifact_id"])
        source = prepared_by_id.get(artifact_id)
        if source is None:
            raise CliError(f"candidate is missing prepared artifact {artifact_id}")
        try:
            data = source.read_bytes()
        except OSError as exc:
            raise CliError(f"cannot read prepared artifact {source}: {exc}") from exc
        _verify_artifact_bytes(artifact, data)
        destination = corpus_root / str(artifact["path"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        compressed = gzip.compress(data, mtime=0)
        if destination.exists():
            try:
                existing_data = gzip.decompress(destination.read_bytes())
            except (OSError, gzip.BadGzipFile) as exc:
                raise CliError(
                    f"invalid existing corpus artifact {destination}: {exc}"
                ) from exc
            if existing_data != data:
                raise CliError(f"corpus artifact path collision at {destination}")
        else:
            destination.write_bytes(compressed)
    corpus_root.mkdir(parents=True, exist_ok=True)
    registry = corpus_root / "captures.jsonl"
    with registry.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(record) + "\n")
    return True


def load_capture_records(path: Path) -> list[JsonObject]:
    if not path.exists():
        return []
    records: list[JsonObject] = []
    seen: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise CliError(f"cannot read Chatlas2 capture registry {path}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError(
                f"invalid Chatlas2 capture registry JSON at line {line_number}: {exc.msg}"
            ) from exc
        if not isinstance(record, dict):
            raise CliError(
                f"Chatlas2 capture registry line {line_number} is not an object"
            )
        _validate_capture(record)
        capture_id = str(record["capture_id"])
        if capture_id != _capture_id(record):
            raise CliError(
                f"Chatlas2 capture_id does not match registry content at line {line_number}"
            )
        if capture_id in seen:
            raise CliError(f"duplicate Chatlas2 capture_id {capture_id}")
        seen.add(capture_id)
        records.append(record)
    return records


def verify_corpus(corpus_root: Path) -> JsonObject:
    records = load_capture_records(corpus_root / "captures.jsonl")
    artifact_count = 0
    for record in records:
        for artifact in record["artifacts"]:
            artifact_count += 1
            path = corpus_root / str(artifact["path"])
            try:
                data = gzip.decompress(path.read_bytes())
            except (OSError, gzip.BadGzipFile) as exc:
                raise CliError(
                    f"cannot reconstruct corpus artifact {path}: {exc}"
                ) from exc
            _verify_artifact_bytes(artifact, data)
    return {
        "artifact_count": artifact_count,
        "capture_count": len(records),
        "status": "ok",
    }


def check_corpus(corpus_root: Path) -> JsonObject:
    verify_corpus(corpus_root)
    specifications: dict[tuple[str, int], ScriptSpec] = {}
    for path in sorted((corpus_root / "specifications").glob("*.json")):
        specification = load_script_spec(path)
        key = (specification.script_id, specification.revision)
        if key in specifications:
            raise CliError(f"duplicate Chatlas2 script specification {key}")
        specifications[key] = specification

    results: list[JsonObject] = []
    counts = {"passed": 0, "unsupported": 0, "failed": 0}
    for record in load_capture_records(corpus_root / "captures.jsonl"):
        capture_id = str(record["capture_id"])
        key = (str(record["script_id"]), int(record["script_revision"]))
        specification = specifications.get(key)
        if specification is None:
            status = "failed"
            detail = f"missing script specification {key[0]}@{key[1]}"
        elif not _capture_is_supported(record):
            status = "unsupported"
            detail = "no compatible Raw.Normalizer"
        else:
            try:
                _check_supported_capture(
                    corpus_root=corpus_root,
                    record=record,
                    specification=specification,
                )
            except CliError as exc:
                status = "failed"
                detail = str(exc)
            else:
                status = "passed"
                detail = "normalized"
        counts[status] += 1
        results.append({"capture_id": capture_id, "detail": detail, "status": status})

    return {
        "capture_count": len(results),
        "failed_count": counts["failed"],
        "passed_count": counts["passed"],
        "results": results,
        "status": "ok" if counts["failed"] == 0 else "failed",
        "unsupported_count": counts["unsupported"],
    }


def _capture_is_supported(record: JsonObject) -> bool:
    provider = record.get("provider")
    if provider == "codex":
        supported = CodexRawNormalizer.supported_raw_model_versions
    elif provider == "claude-code":
        supported = (
            ClaudePromptSourceRawNormalizer.supported_raw_model_versions
            | ClaudeLegacyRawNormalizer.supported_raw_model_versions
        )
    else:
        return False
    return all(
        artifact.get("raw_model_version") in supported
        for artifact in record["artifacts"]
    )


def _check_supported_capture(
    *,
    corpus_root: Path,
    record: JsonObject,
    specification: ScriptSpec,
) -> None:
    with TemporaryDirectory(prefix="chatlas2-corpus-") as directory:
        paths: list[Path] = []
        for ordinal, artifact in enumerate(record["artifacts"], start=1):
            data = _read_corpus_artifact(corpus_root, artifact)
            path = Path(directory) / f"artifact-{ordinal}.raw"
            try:
                path.write_bytes(data)
            except OSError as exc:
                raise CliError(f"cannot materialize corpus artifact: {exc}") from exc
            recognized = _raw_model_version(str(record["provider"]), path)
            if recognized != artifact.get("raw_model_version"):
                raise CliError(
                    "corpus artifact Raw.Model.Version no longer matches its registration"
                )
            paths.append(path)
        row = {
            "provider": record["provider"],
            "session_id": record["session_ref"],
            "identity_hash": record["identity_ref"],
            "backing_artifacts": [
                {"path": str(path), "role": "transcript", "extractable": True}
                for path in paths
            ],
        }
        model = build_normal_model_from_row(row)
    if _user_messages(model) != list(specification.user_messages):
        raise CliError("normalized user messages differ from the script specification")
    _validate_checked_model(model)


def _read_corpus_artifact(corpus_root: Path, artifact: JsonObject) -> bytes:
    path = corpus_root / str(artifact["path"])
    try:
        data = gzip.decompress(path.read_bytes())
    except (OSError, gzip.BadGzipFile) as exc:
        raise CliError(f"cannot reconstruct corpus artifact {path}: {exc}") from exc
    _verify_artifact_bytes(artifact, data)
    return data


def _validate_checked_model(model: JsonObject) -> None:
    events = model.get("events")
    sources = model.get("sources")
    annotations = model.get("annotations")
    if not isinstance(events, list) or not events:
        raise CliError("normalized corpus capture has no event tape")
    if not isinstance(sources, list) or not isinstance(annotations, dict):
        raise CliError("normalized corpus capture has an invalid model envelope")
    if model.get("schema_version") != 6:
        raise CliError("normalized corpus capture is not Chatlas2 Normal Model v6")
    timestamps = [event.get("started_at") for event in events]
    if not all(isinstance(timestamp, str) for timestamp in timestamps):
        raise CliError("normalized corpus event has no start timestamp")
    if timestamps != sorted(timestamps):
        raise CliError("normalized corpus event tape is not chronological")
    try:
        event_refs = [event_ref(event) for event in events]
    except ValueError as exc:
        raise CliError(
            f"normalized corpus event has an invalid Event.Ref: {exc}"
        ) from exc
    event_addresses = {ref["event_address"] for ref in event_refs}
    if len(event_addresses) != len(events):
        raise CliError("normalized corpus event addresses are not unique")
    allowed_event_types = {
        ("user", "User.Event"),
        ("agent", "Agent.Event"),
        ("unresolved", "Unresolved.Event"),
    }
    if not all(
        (event.get("origin"), event.get("class")) in allowed_event_types
        for event in events
    ):
        raise CliError("normalized corpus event has an unsupported origin or class")
    source_ids = {source.get("source_id") for source in sources}
    for event in events:
        observations = event.get("observations")
        if not isinstance(observations, list) or not observations:
            raise CliError("normalized corpus event has no retained observation")
        for observation in observations:
            source_ref = observation.get("source_ref")
            if not isinstance(source_ref, dict):
                raise CliError("normalized corpus observation has no source reference")
            if source_ref.get("source_id") not in source_ids:
                raise CliError("normalized corpus source reference does not resolve")
    messages = annotations.get("chat_messages")
    if not isinstance(messages, list):
        raise CliError("normalized corpus capture has no Chat.Message projection")
    try:
        message_refs = [chat_message_ref(message) for message in messages]
    except (AttributeError, ValueError) as exc:
        raise CliError(f"normalized corpus Chat.Message.Ref is invalid: {exc}") from exc
    message_addresses = {ref["message_address"] for ref in message_refs}
    if len(message_addresses) != len(messages):
        raise CliError("normalized corpus message addresses are not unique")
    event_by_address = {event["event_address"]: event for event in events}
    event_order = {event["event_address"]: index for index, event in enumerate(events)}
    message_order: list[int] = []
    for message in messages:
        if message.get("class") != "Chat.Message":
            raise CliError("normalized corpus message has an unsupported class")
        side = message.get("side")
        if side not in {"user", "agent"}:
            raise CliError("normalized corpus Chat.Message has an unsupported side")
        _require_matched_refs(
            events,
            message.get("event_refs"),
            subject="Chat.Message",
        )
        try:
            expected_hash = compute_chat_message_hash(message)
            resolution = resolve_chat_message_ref(messages, chat_message_ref(message))
        except ValueError as exc:
            raise CliError(
                f"normalized corpus Chat.Message.Ref is invalid: {exc}"
            ) from exc
        if message.get("message_hash") != expected_hash:
            raise CliError(
                "normalized corpus Chat.Message.Hash does not match its state"
            )
        if resolution["standing"] != "MATCHED":
            raise CliError(
                f"normalized corpus Chat.Message.Ref is {resolution['standing']}"
            )
        refs = message["event_refs"]
        member_events = [event_by_address[ref["event_address"]] for ref in refs]
        if any(event.get("origin") != side for event in member_events):
            raise CliError(
                "normalized corpus Chat.Message side does not agree with member origins"
            )
        message_order.append(event_order[refs[0]["event_address"]])
    if message_order != sorted(message_order):
        raise CliError("normalized corpus Chat.Message projection is not chronological")
    turns = annotations.get("chat_turns")
    if not isinstance(turns, list):
        raise CliError("normalized corpus capture has no Chat.Turn projection")
    message_turn_membership: dict[str, int] = {}
    turn_order: list[int] = []
    for turn in turns:
        if turn.get("class") != "Chat.Turn" or turn.get("side") not in {
            "user",
            "agent",
        }:
            raise CliError("normalized corpus Chat.Turn has an invalid class or side")
        _require_matched_refs(events, turn.get("event_refs"), subject="Chat.Turn")
        refs = turn["event_refs"]
        member_events = [event_by_address[ref["event_address"]] for ref in refs]
        if any(event.get("origin") != turn.get("side") for event in member_events):
            raise CliError("normalized corpus Chat.Turn side disagrees with members")
        message_members = turn.get("message_refs")
        if not isinstance(message_members, list):
            raise CliError("normalized corpus Chat.Turn has invalid message membership")
        for ref in message_members:
            if not isinstance(ref, dict):
                raise CliError(
                    "normalized corpus Chat.Turn has invalid Chat.Message.Ref"
                )
            try:
                resolution = resolve_chat_message_ref(messages, ref)
            except ValueError as exc:
                raise CliError(
                    "normalized corpus Chat.Turn message ref is invalid"
                ) from exc
            if resolution["standing"] != "MATCHED":
                raise CliError("normalized corpus Chat.Turn message ref does not match")
            address = str(ref.get("message_address"))
            message_turn_membership[address] = (
                message_turn_membership.get(address, 0) + 1
            )
        try:
            expected_hash = compute_chat_turn_hash(
                turn,
                opaque_payload_hashes=[
                    event.get("opaque_payload_hash") for event in member_events
                ],
            )
            resolution = resolve_chat_turn_ref(turns, chat_turn_ref(turn))
        except ValueError as exc:
            raise CliError(
                f"normalized corpus Chat.Turn.Ref is invalid: {exc}"
            ) from exc
        if (
            turn.get("turn_hash") != expected_hash
            or resolution["standing"] != "MATCHED"
        ):
            raise CliError("normalized corpus Chat.Turn.Hash does not match its state")
        turn_order.append(event_order[refs[0]["event_address"]])
    if turn_order != sorted(turn_order):
        raise CliError("normalized corpus Chat.Turn projection is not chronological")
    if any(
        message_turn_membership.get(str(message["message_address"])) != 1
        for message in messages
    ):
        raise CliError("normalized corpus Chat.Message lacks one containing Chat.Turn")
    for context in annotations.get("agent_loaded_contexts", []):
        _require_matched_refs(
            events,
            [context.get("agent_event_ref")],
            subject="Agent.Loaded.Context agent",
        )
        _require_matched_refs(
            events,
            context.get("event_refs"),
            subject="Agent.Loaded.Context member",
        )


def _validate_capture(record: JsonObject) -> None:
    unexpected = sorted(set(record) - _CAPTURE_KEYS)
    missing = sorted(_CAPTURE_KEYS - set(record))
    if unexpected or missing:
        raise CliError(
            f"invalid Chatlas2 capture keys; unexpected={unexpected}, missing={missing}"
        )
    if record.get("schema") != CAPTURE_SCHEMA:
        raise CliError("unsupported Chatlas2 capture schema")
    for name in (
        "capture_id",
        "captured_at",
        "identity_ref",
        "provider",
        "script_id",
        "session_ref",
        "status",
    ):
        _nonempty_string(record.get(name), name=name)
    if record.get("status") != "accepted":
        raise CliError("Chatlas2 capture status must be 'accepted'")
    revision = record.get("script_revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise CliError("invalid Chatlas2 capture script_revision")
    _string_tuple(record.get("features"), name="features")
    artifacts = record.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise CliError("Chatlas2 capture artifacts must be a non-empty list")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise CliError("invalid Chatlas2 capture artifact")
        corpus_digest = _digest_value(
            artifact.get("corpus_sha256"), name="corpus_sha256"
        )
        expected_path = _artifact_relative_path(corpus_digest).as_posix()
        if artifact.get("path") != expected_path:
            raise CliError("Chatlas2 corpus artifact path does not match its digest")
        _digest_value(artifact.get("source_sha256"), name="source_sha256")
        size = artifact.get("size")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise CliError("invalid Chatlas2 corpus artifact size")
        if artifact.get("compression") != "gzip":
            raise CliError("unsupported Chatlas2 corpus artifact compression")


def _verify_artifact_bytes(artifact: JsonObject, data: bytes) -> None:
    digest = sha256(data).hexdigest()
    expected = _digest_value(artifact.get("corpus_sha256"), name="corpus_sha256")
    if digest != expected or len(data) != artifact.get("size"):
        raise CliError(
            f"Chatlas2 corpus artifact digest or size mismatch for {artifact.get('path')}"
        )


def _raw_model_version(provider: str, path: Path) -> str | None:
    if provider == "codex":
        return CodexRawModelVersioner().version(path)
    if provider == "claude-code":
        return ClaudeRawModelVersioner().version(path)
    return None


def _row_for_paths(row: dict[str, Any], paths: list[Path]) -> dict[str, Any]:
    return {
        "provider": row.get("provider"),
        "session_id": row.get("session_id"),
        "identity_hash": row.get("identity_hash"),
        "backing_artifacts": [
            {"path": str(path), "role": "transcript", "extractable": True}
            for path in paths
        ],
    }


def _model_signature(model: JsonObject) -> JsonObject:
    events = model["events"]
    event_shapes = {
        event["event_address"]: [event["started_at"], event["class"], event["origin"]]
        for event in events
    }
    annotations = model["annotations"]
    message_shapes = {
        message["message_address"]: [
            message["side"],
            [event_shapes[ref["event_address"]] for ref in message["event_refs"]],
        ]
        for message in annotations["chat_messages"]
        if "message_address" in message
    }
    return {
        "events": list(event_shapes.values()),
        "messages": [
            [
                message["side"],
                [event_shapes[ref["event_address"]] for ref in message["event_refs"]],
            ]
            for message in annotations["chat_messages"]
        ],
        "contexts": sorted(
            (
                [
                    event_shapes[context["agent_event_ref"]["event_address"]],
                    sorted(
                        event_shapes[ref["event_address"]]
                        for ref in context["event_refs"]
                    ),
                ]
                for context in annotations["agent_loaded_contexts"]
            ),
            key=_canonical_json,
        ),
        "turns": [
            [
                turn["side"],
                [event_shapes[ref["event_address"]] for ref in turn["event_refs"]],
                [
                    message_shapes.get(ref["message_address"], ["message"])
                    for ref in turn["message_refs"]
                ],
            ]
            for turn in annotations.get("chat_turns", [])
        ],
    }


def _user_messages(model: JsonObject) -> list[str]:
    return [
        annotation["text"]
        for annotation in model["annotations"]["chat_messages"]
        if annotation["side"] == "user"
    ]


def _require_matched_refs(
    events: list[JsonObject],
    value: object,
    *,
    subject: str,
) -> None:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(ref, dict) for ref in value)
    ):
        raise CliError(f"normalized corpus {subject} has no Event.Ref membership")
    for ref in value:
        try:
            resolution = resolve_event_ref(events, ref)
        except ValueError as exc:
            raise CliError(
                f"normalized corpus {subject} has an invalid Event.Ref"
            ) from exc
        if resolution["standing"] != "MATCHED":
            raise CliError(
                f"normalized corpus {subject} Event.Ref is {resolution['standing']}"
            )


def _capture_id(record: JsonObject) -> str:
    content = {key: value for key, value in record.items() if key != "capture_id"}
    return f"capture-{sha256(_canonical_json(content).encode('utf-8')).hexdigest()}"


def _hash_ref(kind: str, value: str) -> str:
    digest = sha256(f"{kind}\0{value}".encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _artifact_relative_path(digest: str) -> Path:
    return Path("artifacts") / "sha256" / digest[:2] / f"{digest}.raw.gz"


def _digest_value(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.startswith("sha256:"):
        raise CliError(f"invalid Chatlas2 {name}")
    digest = value.removeprefix("sha256:")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise CliError(f"invalid Chatlas2 {name}")
    return digest


def _load_json_object(path: Path) -> JsonObject:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CliError(f"cannot read Chatlas2 JSON object {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"Chatlas2 JSON value at {path} is not an object")
    return payload


def _nonempty_string(value: object, *, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"Chatlas2 {name} must be a non-empty string")
    return value


def _string_tuple(
    value: object,
    *,
    name: str,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise CliError(f"Chatlas2 {name} must be a string list")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise CliError(f"Chatlas2 {name} must contain non-empty strings")
    return tuple(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _pretty_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


__all__ = [
    "CAPTURE_SCHEMA",
    "CANDIDATE_SCHEMA",
    "SCRIPT_SCHEMA",
    "ScriptSpec",
    "check_corpus",
    "load_capture_records",
    "load_script_spec",
    "prepare_capture",
    "register_candidate",
    "verify_corpus",
]
