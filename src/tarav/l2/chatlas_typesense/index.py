"""Read stored Normal Models only; manage a replaceable Typesense projection."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
from collections.abc import Callable

from filelock import FileLock

from tarav.l0._core.home import tarav_home_dir
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.chatlas.normal_model import ChatlasNormalModel

from .client import TypesenseClient, TypesenseConfig, TypesenseError


_IDENTITY = re.compile(r"[0-9a-f]{64}")
_FILES = ("main.json", "events.jsonl", "messages.jsonl", "turns.jsonl")


def _digest(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def source_version(directory: Path, config: TypesenseConfig) -> str:
    digest = sha256()
    digest.update(json.dumps([config.embedding_model, config.chunk_chars, config.chunk_overlap]).encode())
    for filename in _FILES:
        digest.update(filename.encode())
        with (directory / filename).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    return digest.hexdigest()


# tarav.breadcrumb 80df11ee6864
def project_model(directory: Path, config: TypesenseConfig, version: str) -> list[dict]:
    model = ChatlasNormalModel.open(directory)
    header = model.model_header()
    session = header["session"]
    if session["identity_hash"] != directory.name:
        raise TypesenseError("Normal Model directory and session identity disagree")
    events = list(model.iter_events())
    messages = list(model.iter_messages())
    turns = list(model.iter_turns())
    for name, rows in (("events", events), ("messages", messages), ("turns", turns)):
        if header["counts"][name] != len(rows):
            raise TypesenseError(f"Normal Model {name} count mismatch")
    event_times = {}
    for event in events:
        try:
            stamp = _timestamp(event["started_at"])
        except (ValueError, OverflowError, OSError):
            stamp = None
        event_times[event["event_address"], event["event_hash"]] = stamp
    message_keys = {(m["message_address"], m["message_hash"]) for m in messages}
    turn_refs: dict[tuple, list] = {}
    for turn in turns:
        reference = {"turn_address": turn["turn_address"], "turn_hash": turn["turn_hash"]}
        for ref in turn["message_refs"]:
            if (ref["message_address"], ref["message_hash"]) not in message_keys:
                raise TypesenseError("Chat.Turn references an unavailable exact Chat.Message")
            turn_refs.setdefault((ref["message_address"], ref["message_hash"]), []).append(reference)
    documents = []
    seen = set()
    for message in messages:
        key = (message["message_address"], message["message_hash"])
        if key in seen:
            raise TypesenseError("duplicate exact Chat.Message in Normal Model")
        seen.add(key)
        dates = []
        for ref in message["event_refs"]:
            event = (ref["event_address"], ref["event_hash"])
            if event not in event_times:
                raise TypesenseError("Chat.Message references an unavailable exact Event")
            if event_times[event] is not None:
                dates.append(event_times[event])
        text = message["text"]
        for number, start in enumerate(range(0, len(text), config.chunk_chars - config.chunk_overlap)):
            end = min(start + config.chunk_chars, len(text))
            if text[start:end].strip():
                documents.append({
                    "id": _digest([session["identity_hash"], *key, number]),
                    "text": text[start:end], "side": message["side"],
                    "provider": session["provider"], "session_id": session["session_id"],
                    "session_identity": session["identity_hash"], "source_version": version,
                    **({"started_at": min(dates)} if dates else {}),
                    "source": {
                        "normal_model": str(directory), "session": session,
                        "message_ref": {"message_address": key[0], "message_hash": key[1]},
                        "turn_refs": turn_refs.get(key, []), "event_refs": message["event_refs"],
                        "text_start": start, "text_end": end,
                    },
                })
            if end == len(text):
                break
    return documents


# tarav.breadcrumb c2da406f2df5
class TypesenseIndex:
    def __init__(self, config: TypesenseConfig, *, state_path: Path | None = None):
        self.config = config
        self.client = TypesenseClient(config)
        key = _digest([config.url, config.collection, str(config.normal_model_root)])
        self.state_path = state_path or tarav_home_dir() / "cache/chatlas-typesense" / f"{key}.json"

    def models(self) -> list[Path]:
        if not self.config.normal_model_root.is_dir():
            return []
        return sorted(path for path in self.config.normal_model_root.iterdir()
                      if path.is_dir() and _IDENTITY.fullmatch(path.name))

    def status(self) -> dict:
        health = self.client.request("GET", "/health")
        collection = self.client.collection()
        try:
            state = json.loads(self.state_path.read_text())
            indexed_sessions = len(state["sessions"]) if (
                collection and state["index_id"] == collection.get("metadata", {}).get("index_id")) else 0
        except (OSError, ValueError, KeyError, TypeError):
            indexed_sessions = 0
        return {"healthy": health.get("ok") is True, "url": self.config.url,
                "collection": self.config.collection, "collection_exists": collection is not None,
                "indexed_documents": collection.get("num_documents", 0) if collection else 0,
                "normal_model_root": str(self.config.normal_model_root),
                "normal_model_root_exists": self.config.normal_model_root.is_dir(),
                "normal_models": len(self.models()), "checkpointed_sessions": indexed_sessions}

    def sync(self, *, limit_sessions: int | None = None, force: bool = False,
             progress: Callable[[dict], None] | None = None) -> dict:
        if limit_sessions is not None and limit_sessions < 1:
            raise TypesenseError("limit_sessions must be positive")
        models = self.models()
        if not models:
            raise TypesenseError(f"no stored Normal Models in {self.config.normal_model_root}; "
                                 "transfer Normal Model files first (sync never normalizes raw data)")
        if limit_sessions is not None:
            models = models[:limit_sessions]
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.state_path) + ".lock"):
            collection = self.client.ensure_collection()
            index_id = collection["metadata"]["index_id"]
            try:
                state = json.loads(self.state_path.read_text())
                if (not isinstance(state, dict) or state.get("index_id") != index_id
                        or not isinstance(state.get("sessions"), dict)):
                    state = {}
            except (OSError, ValueError):
                state = {}
            sessions = state.setdefault("sessions", {})
            state["index_id"] = index_id
            report = {"indexed_sessions": 0, "unchanged_sessions": 0,
                      "indexed_documents": 0, "errors": []}
            for directory in models:
                try:
                    version = source_version(directory, self.config)
                    if not force and sessions.get(directory.name) == version:
                        report["unchanged_sessions"] += 1
                        continue
                    documents = project_model(directory, self.config, version)
                    if source_version(directory, self.config) != version:
                        raise TypesenseError("Normal Model files changed while being read")
                    for offset in range(0, len(documents), self.config.batch_size):
                        self.client.import_documents(documents[offset:offset + self.config.batch_size])
                    self.client.delete_older(directory.name, version)
                    sessions[directory.name] = version
                    atomic_write_json(self.state_path, state)
                    report["indexed_sessions"] += 1
                    report["indexed_documents"] += len(documents)
                except Exception as exc:
                    # Sessions are independent. Preserve the previous index and
                    # checkpoint only after a complete, acknowledged import.
                    message = str(exc).replace(self.config.api_key, "[redacted]")
                    report["errors"].append({"normal_model": str(directory), "error": message})
                finally:
                    if progress is not None:
                        progress({"indexed_sessions": report["indexed_sessions"],
                                  "unchanged_sessions": report["unchanged_sessions"],
                                  "indexed_documents": report["indexed_documents"],
                                  "errors": len(report["errors"])})
            return report

    def search(self, query: str, *, side: str | None = None, provider: str | None = None,
               since: str | None = None, limit: int = 10, order: str = "relevance") -> dict:
        if not query.strip() or not 1 <= limit <= 100:
            raise TypesenseError("search requires nonempty text and limit 1..100")
        if order not in {"relevance", "oldest", "newest"}:
            raise TypesenseError("order must be relevance, oldest or newest")
        filters = []
        for name, value, allowed in (("side", side, {"user", "agent"}),
                                     ("provider", provider, {"codex", "claude-code"})):
            if value is not None:
                if value not in allowed:
                    raise TypesenseError(f"invalid {name} filter")
                filters.append(f"{name}:={value}")
        if since:
            try:
                filters.append(f"started_at:>={_timestamp(since)}")
            except ValueError as exc:
                raise TypesenseError("since must be an ISO date or timestamp") from exc
        params = {
            "q": query, "query_by": "text,embedding", "per_page": limit,
            "filter_by": " && ".join(filters), "exclude_fields": "embedding",
        }
        # tarav.breadcrumb aaabc630ff06
        if order != "relevance":
            direction = "asc" if order == "oldest" else "desc"
            params["sort_by"] = f"started_at:{direction},_text_match:desc"
        result = self.client.request("GET", self.client.collection_path + "/documents/search", params=params)
        return {"found": result["found"], "search_time_ms": result.get("search_time_ms"),
                "hits": [hit["document"] for hit in result["hits"]]}
