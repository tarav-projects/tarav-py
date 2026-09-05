"""Git-backed authoritative Record repository for Assertion Scoring."""

from __future__ import annotations

from collections import deque
import json
import os
import subprocess
from pathlib import Path
from typing import Mapping

from filelock import FileLock

from tarav._core.persistence import atomic_write_json, atomic_write_text

from .model import (
    GROUNDING_TASK_TYPE,
    POOL_TYPE,
    RECORD_KINDS,
    RESULT_TYPE,
    RUN_TYPE,
    SCORE_COMPUTATION_TYPE,
    JsonObject,
    ScoringError,
    content_hash,
    reference_target_type,
    validate_record,
)


REPOSITORY_TYPE = "Tarav.Assertion.Scoring.Repository"


def default_scoring_root() -> Path:
    configured = os.getenv("TARAV_SCORING_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / "Documents" / "tarav" / "scoring").resolve()


class ScoringRepository:
    """One-file-per-Record storage whose retained history is ordinary Git."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()

    @property
    def marker_path(self) -> Path:
        return self.root / "repository.json"

    @classmethod
    def initialize(cls, root: Path | None = None) -> ScoringRepository:
        repository = cls(root or default_scoring_root())
        if repository.marker_path.exists():
            return repository.open()
        if repository.root.exists() and any(repository.root.iterdir()):
            raise ScoringError(
                f"refusing to initialize a non-empty scoring directory: {repository.root}"
            )
        repository.root.mkdir(parents=True, exist_ok=True)
        for dirname in sorted(set(RECORD_KINDS.values())):
            (repository.root / dirname).mkdir()
        atomic_write_json(
            repository.marker_path,
            {"type": REPOSITORY_TYPE, "schema_version": 1},
            ensure_ascii=False,
        )
        atomic_write_text(repository.root / ".gitignore", ".write.lock\n")
        repository._git("init", "-q")
        repository._git("config", "user.name", "Tarav")
        repository._git("config", "user.email", "tarav@local.invalid")
        repository._commit_all("Initialize Tarav Assertion Scoring repository")
        return repository

    def open(self) -> ScoringRepository:
        if not self.marker_path.is_file():
            raise ScoringError(
                f"scoring repository not initialized: {self.root}; run `tarav scoring init`"
            )
        marker = self._read_json(self.marker_path)
        if marker != {"schema_version": 1, "type": REPOSITORY_TYPE}:
            raise ScoringError(f"invalid scoring repository marker: {self.marker_path}")
        if not (self.root / ".git").is_dir():
            raise ScoringError(f"scoring repository has no Git history: {self.root}")
        missing = [
            dirname
            for dirname in sorted(set(RECORD_KINDS.values()))
            if not (self.root / dirname).is_dir()
        ]
        if missing:
            raise ScoringError(
                "scoring repository is missing Record directories: "
                + ", ".join(missing)
            )
        return self

    def save(
        self, record: Mapping[str, object], *, message: str | None = None
    ) -> JsonObject:
        payload = dict(record)
        validate_record(payload)
        path = self.path_for(payload)
        with FileLock(str(self.root / ".write.lock")):
            if path.exists():
                previous = self._read_json(path)
                if previous.get("type") != payload["type"]:
                    raise ScoringError(
                        "a Record UUID cannot be rebound to another Type"
                    )
            atomic_write_json(path, payload, ensure_ascii=False)
            self._commit_path(
                path, message or f"Store {payload['type']} {payload['id']}"
            )
        return payload

    def create(self, record: Mapping[str, object]) -> JsonObject:
        path = self.path_for(record)
        if path.exists():
            raise ScoringError(f"scoring Record already exists: {record.get('id')}")
        return self.save(record)

    def records(self, record_type: str | None = None) -> tuple[JsonObject, ...]:
        if record_type is not None and record_type not in RECORD_KINDS:
            raise ScoringError(f"unknown scoring Record type: {record_type}")
        types = (record_type,) if record_type else tuple(RECORD_KINDS)
        records = [
            self._load_path(path)
            for kind in types
            for path in sorted((self.root / RECORD_KINDS[kind]).glob("*.json"))
        ]
        return tuple(sorted(records, key=lambda item: str(item.get("created_at", ""))))

    def resolve(self, selector: str, *, record_type: str | None = None) -> JsonObject:
        candidates = self.records(record_type)
        exact = [item for item in candidates if item["id"] == selector]
        matches = exact or [
            item for item in candidates if str(item["id"]).startswith(selector)
        ]
        if len(matches) != 1:
            detail = (
                "not found" if not matches else f"ambiguous ({len(matches)} matches)"
            )
            raise ScoringError(f"scoring Record {selector!r} is {detail}")
        return matches[0]

    def result_for_run(self, run_id: str) -> JsonObject | None:
        matches = [
            result
            for result in self.records(RESULT_TYPE)
            if _reference_id(result.get("run_ref")) == run_id
        ]
        if len(matches) > 1:
            raise ScoringError(f"Ranking Run has multiple Results: {run_id}")
        return matches[0] if matches else None

    def results_for_pool(self, pool: Mapping[str, object]) -> tuple[JsonObject, ...]:
        """Select Results by following Result → Run → Task → Pool."""

        validate_record(pool)
        if pool.get("type") != POOL_TYPE:
            raise ScoringError("Result selection requires an Assertion.Pool")
        pool_id = str(pool["id"])
        selected: list[JsonObject] = []
        for result in self.records(RESULT_TYPE):
            run = self.resolve_reference(_reference(result, "run_ref"))
            task = self.resolve_reference(_reference(run, "task_ref"))
            if _reference_id(task.get("pool_ref")) == pool_id:
                selected.append(result)
        return tuple(selected)

    def resolve_reference(self, reference: Mapping[str, object]) -> JsonObject:
        """Resolve one exact scoring Record edition, including from Git history."""

        target_type = reference_target_type(reference)
        if target_type is None:
            raise ScoringError(
                f"Reference is external to the scoring repository: {reference.get('type')}"
            )
        identity = str(reference.get("id", ""))
        expected_hash = str(reference.get("record_sha256", ""))
        relative = Path(RECORD_KINDS[target_type]) / f"{identity}.json"
        path = self.root / relative
        if path.is_file():
            current = self._load_path(path)
            if content_hash(current) == expected_hash:
                return current
        commits = self._git(
            "log", "--format=%H", "--all", "--", str(relative)
        ).stdout.splitlines()
        for commit in commits:
            shown = self._git("show", f"{commit}:{relative}", check=False)
            if shown.returncode != 0:
                continue
            try:
                candidate = json.loads(shown.stdout)
            except json.JSONDecodeError:
                continue
            if not isinstance(candidate, dict):
                continue
            try:
                validate_record(candidate)
            except ScoringError:
                continue
            if content_hash(candidate) == expected_hash:
                return candidate
        raise ScoringError(
            "exact scoring Record edition is not recoverable: "
            f"{reference.get('type')} {reference.get('id')}@{expected_hash}"
        )

    def trace(self, record: Mapping[str, object]) -> JsonObject:
        """Expand direct Record dependencies without inventing semantic ancestry."""

        root = dict(record)
        validate_record(root)
        pending = deque([root])
        seen: set[tuple[str, str]] = set()
        records: list[JsonObject] = []
        edges: list[JsonObject] = []
        external: list[JsonObject] = []
        while pending:
            current = pending.popleft()
            current_id = str(current["id"])
            current_ref = {
                "type": f"{current['type']}.Reference",
                "id": current_id,
                "record_sha256": content_hash(current),
            }
            current_key = (current_id, str(current_ref["record_sha256"]))
            if current_key in seen:
                continue
            seen.add(current_key)
            records.append(current)
            for field, reference in _direct_references(current):
                target_type = reference_target_type(reference)
                if target_type is None:
                    external.append(
                        {
                            "from_ref": current_ref,
                            "field": field,
                            "reference": reference,
                        }
                    )
                    continue
                dependency = self.resolve_reference(reference)
                edges.append(
                    {
                        "from_ref": current_ref,
                        "field": field,
                        "to_ref": dict(reference),
                    }
                )
                pending.append(dependency)
        return {
            "root_ref": {
                "type": f"{root['type']}.Reference",
                "id": root["id"],
                "record_sha256": content_hash(root),
            },
            "records": records,
            "edges": edges,
            "external_references": external,
        }

    def path_for(self, record: Mapping[str, object]) -> Path:
        record_type = str(record.get("type", ""))
        dirname = RECORD_KINDS.get(record_type)
        if dirname is None:
            raise ScoringError(f"unsupported scoring Record type: {record_type}")
        record_id = str(record.get("id", ""))
        return self.root / dirname / f"{record_id}.json"

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _load_path(self, path: Path) -> JsonObject:
        payload = self._read_json(path)
        validate_record(payload)
        if self.path_for(payload) != path:
            raise ScoringError(f"scoring Record is stored at the wrong path: {path}")
        return payload

    @staticmethod
    def _read_json(path: Path) -> JsonObject:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ScoringError(f"cannot read scoring JSON {path}: {exc}") from exc
        if not isinstance(value, dict):
            raise ScoringError(f"scoring JSON must contain an object: {path}")
        return value

    def _commit_path(self, path: Path, message: str) -> None:
        relative = path.relative_to(self.root)
        self._git("add", "--", str(relative))
        if self._git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        self._git("commit", "-q", "-m", message)

    def _commit_all(self, message: str) -> None:
        self._git("add", "--all")
        self._git("commit", "-q", "-m", message)

    def _git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ("git", "-C", str(self.root), *args),
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:
            raise ScoringError(f"cannot run Git for scoring repository: {exc}") from exc
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise ScoringError(f"Git failed in scoring repository: {detail}")
        return result


def _reference(record: Mapping[str, object], field: str) -> Mapping[str, object]:
    value = record.get(field)
    if not isinstance(value, dict):
        raise ScoringError(f"{field} must be a typed Reference")
    return value


def _reference_id(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    identity = value.get("id")
    return identity if isinstance(identity, str) else None


def _direct_references(
    record: Mapping[str, object],
) -> tuple[tuple[str, Mapping[str, object]], ...]:
    record_type = record.get("type")
    references: list[tuple[str, Mapping[str, object]]] = []
    if record_type == GROUNDING_TASK_TYPE:
        references.append(("pool_ref", _reference(record, "pool_ref")))
        candidates = record.get("candidates")
        if not isinstance(candidates, list):
            raise ScoringError("candidates must be a list")
        for index, candidate in enumerate(candidates):
            if not isinstance(candidate, dict):
                raise ScoringError("candidate must be an object")
            references.append(
                (
                    f"candidates[{index}].assertion_ref",
                    _reference(candidate, "assertion_ref"),
                )
            )
    elif record_type == RUN_TYPE:
        references.append(("task_ref", _reference(record, "task_ref")))
    elif record_type == RESULT_TYPE:
        references.append(("run_ref", _reference(record, "run_ref")))
    elif record_type == SCORE_COMPUTATION_TYPE:
        references.append(("definition_ref", _reference(record, "definition_ref")))
        result_refs = record.get("result_refs")
        if not isinstance(result_refs, list):
            raise ScoringError("result_refs must be a list")
        for index, reference in enumerate(result_refs):
            if not isinstance(reference, dict):
                raise ScoringError("result_refs must contain typed References")
            references.append((f"result_refs[{index}]", reference))
    return tuple(references)


__all__ = ["REPOSITORY_TYPE", "ScoringRepository", "default_scoring_root"]
