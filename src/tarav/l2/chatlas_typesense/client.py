"""Small Typesense HTTP boundary; embedding generation belongs to the server."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from tarav.l0._core.home import tarav_home_dir
from tarav.l1.chatlas.paths import default_chatlas_root


class TypesenseError(ValueError):
    pass


# tarav.breadcrumb 976538ee5436
@dataclass(frozen=True)
class TypesenseConfig:
    normal_model_root: Path
    api_key: str = field(repr=False)
    url: str = "http://127.0.0.1:8108"
    collection: str = "chatlas_messages_v1"
    embedding_model: str = "ts/all-MiniLM-L12-v2"
    chunk_chars: int = 800
    chunk_overlap: int = 80
    batch_size: int = 100
    timeout: int = 120

    def __post_init__(self):
        url = urlsplit(self.url)
        if (url.scheme not in {"http", "https"} or not url.hostname or url.username
                or url.password or url.query or url.fragment):
            raise TypesenseError("Typesense URL must be HTTP(S), without credentials, query or fragment")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.collection):
            raise TypesenseError("Typesense collection must contain only letters, numbers, _ or -")
        if not self.api_key or any(c in self.api_key for c in "\r\n"):
            raise TypesenseError("Typesense requires an API key from a private file or environment")
        if not isinstance(self.embedding_model, str) or not self.embedding_model:
            raise TypesenseError("embedding_model must be a nonempty string")
        for key in ("chunk_chars", "chunk_overlap", "batch_size", "timeout"):
            if type(getattr(self, key)) is not int:
                raise TypesenseError(f"{key} must be an integer")
        if not 0 <= self.chunk_overlap < self.chunk_chars or self.chunk_chars < 1:
            raise TypesenseError("require 0 <= chunk_overlap < chunk_chars")
        if not 1 <= self.batch_size <= 1000 or not 1 <= self.timeout <= 3600:
            raise TypesenseError("batch_size must be 1..1000 and timeout 1..3600 seconds")

    @classmethod
    def load(cls, path: Path | None = None, *, normal_model_root: Path | None = None):
        path = path or tarav_home_dir() / "chatlas-typesense.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            payload = {}
        except (OSError, UnicodeError, ValueError) as exc:
            raise TypesenseError(f"cannot read Typesense configuration: {path}") from exc
        allowed = {"url", "collection", "embedding_model", "normal_model_root", "api_key_file",
                   "chunk_chars", "chunk_overlap", "batch_size", "timeout"}
        if not isinstance(payload, dict) or payload.keys() - allowed:
            raise TypesenseError(f"invalid Typesense configuration fields: {path}")
        values = dict(payload)
        key_file = os.environ.get("TARAV_TYPESENSE_API_KEY_FILE") or values.pop("api_key_file", None)
        values.pop("api_key_file", None)
        api_key = os.environ.get("TARAV_TYPESENSE_API_KEY", "")
        if not api_key and key_file:
            try:
                api_key = Path(key_file).expanduser().read_text(encoding="utf-8").strip()
            except (OSError, TypeError, UnicodeError) as exc:
                raise TypesenseError("cannot read Typesense API key file") from exc
        if "TARAV_TYPESENSE_URL" in os.environ:
            values["url"] = os.environ["TARAV_TYPESENSE_URL"]
        root = normal_model_root or values.pop("normal_model_root", None)
        values.pop("normal_model_root", None)
        try:
            root = Path(root).expanduser().resolve() if root is not None else default_chatlas_root() / "normal-model"
            return cls(normal_model_root=root, api_key=api_key, **values)
        except (TypeError, AttributeError) as exc:
            raise TypesenseError(f"invalid Typesense configuration values: {path}") from exc


class TypesenseClient:
    def __init__(self, config: TypesenseConfig):
        self.config = config

    def request(self, method: str, path: str, *, params=None, payload=None, raw=False, missing=False):
        url = self.config.url.rstrip("/") + path
        if params:
            url += "?" + urlencode(params)
        data = payload.encode("utf-8") if isinstance(payload, str) else (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        )
        request = Request(url, data=data, method=method, headers={
            "X-TYPESENSE-API-KEY": self.config.api_key,
            "Content-Type": "text/plain" if isinstance(payload, str) else "application/json",
        })
        try:
            with urlopen(request, timeout=self.config.timeout) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            if missing and exc.code == 404:
                return None
            # Do not print server bodies or headers that may reflect credentials.
            raise TypesenseError(f"Typesense {method} {path} failed (HTTP {exc.code})") from exc
        except (OSError, URLError, UnicodeError) as exc:
            raise TypesenseError(f"cannot reach Typesense for {method} {path}") from exc
        if raw:
            return text
        try:
            value = json.loads(text)
            if not isinstance(value, dict):
                raise ValueError("expected an object")
            return value
        except ValueError as exc:
            raise TypesenseError(f"Typesense returned invalid JSON for {method} {path}") from exc

    @property
    def collection_path(self):
        return f"/collections/{self.config.collection}"

    def collection(self):
        return self.request("GET", self.collection_path, missing=True)

    # tarav.breadcrumb 7bd46d467c3f
    def ensure_collection(self):
        collection = self.collection()
        if collection is None:
            collection = self.request("POST", "/collections", payload={
                "name": self.config.collection,
                "metadata": {"chatlas_typesense_schema": 1, "index_id": uuid4().hex},
                "fields": [
                    {"name": "text", "type": "string"},
                    *({"name": name, "type": "string", "facet": True} for name in
                      ("side", "provider", "session_identity", "session_id", "source_version")),
                    {"name": "started_at", "type": "int64", "optional": True},
                    {"name": "embedding", "type": "float[]", "embed": {
                        "from": ["text"], "model_config": {"model_name": self.config.embedding_model},
                    }},
                ],
            })
        fields = {f.get("name"): f for f in collection.get("fields", [])}
        embedding = fields.get("embedding", {}).get("embed", {})
        if (collection.get("metadata", {}).get("chatlas_typesense_schema") != 1
                or not collection.get("metadata", {}).get("index_id")
                or not {"text", "side", "provider", "session_identity", "session_id", "source_version", "started_at"} <= fields.keys()
                or embedding.get("from") != ["text"]
                or embedding.get("model_config", {}).get("model_name") != self.config.embedding_model):
            raise TypesenseError("incompatible Typesense collection; use a new collection name")
        return collection

    def import_documents(self, documents: list[dict]):
        if not documents:
            return
        text = self.request("POST", self.collection_path + "/documents/import",
                            params={"action": "upsert"},
                            payload="\n".join(json.dumps(doc, ensure_ascii=False) for doc in documents), raw=True)
        try:
            results = [json.loads(line) for line in text.splitlines() if line.strip()]
            failed = sum(result.get("success") is not True for result in results)
        except (ValueError, AttributeError) as exc:
            raise TypesenseError("invalid Typesense bulk import response") from exc
        if len(results) != len(documents) or failed:
            raise TypesenseError(f"Typesense bulk import incomplete: {failed} rejected, "
                                 f"{len(results)} responses for {len(documents)} documents")

    def delete_older(self, identity: str, version: str):
        result = self.request("DELETE", self.collection_path + "/documents", params={
            "filter_by": f"session_identity:={identity} && source_version:!={version}",
        })
        if type(result.get("num_deleted")) is not int or result["num_deleted"] < 0:
            raise TypesenseError("Typesense did not acknowledge stale-document deletion")
        return result
