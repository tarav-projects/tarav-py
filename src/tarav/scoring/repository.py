"""Git-backed authoritative Record repository for Assertion Scoring."""

from __future__ import annotations

from collections import deque
import json
import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from filelock import FileLock

from tarav.l0._core.persistence import atomic_write_json, atomic_write_text

from .model import (
    GROUNDING_TASK_TYPE,
    POOL_ENROLLMENT_TYPE,
    RECORD_KINDS,
    RESULT_TYPE,
    RUN_TYPE,
    SCORING_EVENT_TYPE,
    SCORING_TRACE_TYPE,
    JsonObject,
    ScoringError,
    canonical_json,
    content_hash,
    is_pool_record_type,
    reference_target_type,
    record_relations,
    validate_record,
)


REPOSITORY_TYPE = "Tarav.Assertion.Scoring.Repository"
REPOSITORY_SCHEMA_VERSION = 2


def default_scoring_root() -> Path:
    configured = os.getenv("TARAV_SCORING_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / "Documents" / "tarav" / "scoring").resolve()


class ScoringRepository:
    """Pool-oriented Records and append-only per-Assertion scoring traces."""

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
        (repository.root / "pools").mkdir()
        (repository.root / "assertion-traces").mkdir()
        atomic_write_json(
            repository.marker_path,
            {
                "type": REPOSITORY_TYPE,
                "schema_version": REPOSITORY_SCHEMA_VERSION,
            },
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
                f"scoring repository not initialized: {self.root}; "
                "run `tarav scoring init`"
            )
        marker = self._read_json(self.marker_path)
        expected = {
            "schema_version": REPOSITORY_SCHEMA_VERSION,
            "type": REPOSITORY_TYPE,
        }
        if marker != expected:
            raise ScoringError(f"invalid scoring repository marker: {self.marker_path}")
        if not (self.root / ".git").is_dir():
            raise ScoringError(f"scoring repository has no Git history: {self.root}")
        missing = [
            dirname
            for dirname in ("pools", "assertion-traces")
            if not (self.root / dirname).is_dir()
        ]
        if missing:
            raise ScoringError(
                "scoring repository is missing directories: " + ", ".join(missing)
            )
        return self

    def save(
        self, record: Mapping[str, object], *, message: str | None = None
    ) -> JsonObject:
        payload = dict(record)
        validate_record(payload)
        if payload["type"] == SCORING_EVENT_TYPE:
            raise ScoringError("Scoring Events are append-only; use append_event")
        path = self.path_for(payload)
        with FileLock(str(self.root / ".write.lock")):
            if payload["type"] == RESULT_TYPE:
                run_id = _reference_id(payload.get("run_ref"))
                existing_result = self.result_for_run(str(run_id))
                if (
                    existing_result is not None
                    and existing_result["id"] != payload["id"]
                ):
                    raise ScoringError(f"Ranking Run already has a Result: {run_id}")
            if path.exists():
                previous = self._read_json(path)
                if previous.get("type") != payload["type"]:
                    raise ScoringError(
                        "a Record UUID cannot be rebound to another Type"
                    )
            path.parent.mkdir(parents=True, exist_ok=True)
            if is_pool_record_type(str(payload["type"])):
                for child in ("enrollments", "tasks", "runs", "results"):
                    (path.parent / child).mkdir(exist_ok=True)
            atomic_write_json(path, payload, ensure_ascii=False)
            self._commit_path(
                path, message or f"Store {payload['type']} {payload['id']}"
            )
        return payload

    def create(self, record: Mapping[str, object]) -> JsonObject:
        payload = dict(record)
        validate_record(payload)
        if payload["type"] == SCORING_EVENT_TYPE:
            return self.append_event(payload)
        path = self.path_for(payload)
        if path.exists():
            raise ScoringError(f"scoring Record already exists: {payload.get('id')}")
        return self.save(payload)

    def append_event(self, event: Mapping[str, object]) -> JsonObject:
        """Append one typed event to its Assertion Trace JSONL."""

        payload = dict(event)
        validate_record(payload)
        if payload["type"] != SCORING_EVENT_TYPE:
            raise ScoringError("append_event requires an Assertion.Scoring.Event")
        path = self.path_for(payload)
        with FileLock(str(self.root / ".write.lock")):
            if any(item["id"] == payload["id"] for item in self._read_events(path)):
                raise ScoringError(f"scoring Event already exists: {payload['id']}")
            path.parent.mkdir(parents=True, exist_ok=True)
            previous = path.read_text(encoding="utf-8") if path.exists() else ""
            serialized = json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            atomic_write_text(path, previous + serialized + "\n")
            self._commit_path(path, f"Append {payload['type']} {payload['id']}")
        return payload

    def records(self, record_type: str | None = None) -> tuple[JsonObject, ...]:
        if record_type is not None and record_type not in RECORD_KINDS:
            raise ScoringError(f"unknown scoring Record type: {record_type}")
        types = (record_type,) if record_type else tuple(RECORD_KINDS)
        records: list[JsonObject] = []
        for kind in types:
            if kind == SCORING_EVENT_TYPE:
                for path in sorted(
                    (self.root / "assertion-traces").glob("*/events.jsonl")
                ):
                    records.extend(self._read_events(path))
                continue
            records.extend(
                record
                for path in self._paths_for_type(kind)
                if (record := self._load_path(path)).get("type") == kind
            )
        return tuple(sorted(records, key=lambda item: str(item.get("created_at", ""))))

    def resolve(self, selector: str, *, record_type: str | None = None) -> JsonObject:
        candidates = self.records(record_type)
        exact = [item for item in candidates if item["id"] == selector]
        named = [item for item in candidates if item.get("name") == selector]
        matches = (
            exact
            or named
            or [item for item in candidates if str(item["id"]).startswith(selector)]
        )
        if len(matches) != 1:
            detail = (
                "not found" if not matches else f"ambiguous ({len(matches)} matches)"
            )
            raise ScoringError(f"scoring Record {selector!r} is {detail}")
        return matches[0]

    def pools(self) -> tuple[JsonObject, ...]:
        return tuple(
            record
            for record in self.records()
            if is_pool_record_type(str(record.get("type", "")))
        )

    def resolve_pool(self, selector: str) -> JsonObject:
        candidates = self.pools()
        exact = [item for item in candidates if item["id"] == selector]
        named = [item for item in candidates if item.get("name") == selector]
        matches = (
            exact
            or named
            or [item for item in candidates if str(item["id"]).startswith(selector)]
        )
        if len(matches) != 1:
            detail = (
                "not found" if not matches else f"ambiguous ({len(matches)} matches)"
            )
            raise ScoringError(f"Assertion Pool {selector!r} is {detail}")
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

    def enrollments_for_pool(
        self, pool: Mapping[str, object]
    ) -> tuple[JsonObject, ...]:
        validate_record(pool)
        if not is_pool_record_type(str(pool.get("type", ""))):
            raise ScoringError("Enrollment selection requires an Assertion.Pool")
        return tuple(
            item
            for item in self.records(POOL_ENROLLMENT_TYPE)
            if _reference_id(item.get("pool_ref")) == pool["id"]
            and item.get("status") == "Enrolled"
        )

    def enrollment_for_assertion(
        self,
        *,
        pool: Mapping[str, object],
        assertion_ref: Mapping[str, object],
    ) -> JsonObject | None:
        matches = [
            item
            for item in self.enrollments_for_pool(pool)
            if canonical_json(item.get("assertion_ref"))
            == canonical_json(assertion_ref)
        ]
        if len(matches) > 1:
            raise ScoringError("Assertion has duplicate active Pool enrollments")
        return matches[0] if matches else None

    def results_for_pools(
        self, pools: Sequence[Mapping[str, object]]
    ) -> tuple[JsonObject, ...]:
        """Select Results by following Result → Run → Task → Pool."""

        pool_ids: set[str] = set()
        for pool in pools:
            validate_record(pool)
            if not is_pool_record_type(str(pool.get("type", ""))):
                raise ScoringError("Result selection requires Assertion.Pools")
            pool_ids.add(str(pool["id"]))
        selected: list[JsonObject] = []
        for result in self.records(RESULT_TYPE):
            run = self.resolve_reference(_reference(result, "run_ref"))
            task = self.resolve_reference(_reference(run, "task_ref"))
            if _reference_id(task.get("pool_ref")) in pool_ids:
                selected.append(result)
        return tuple(selected)

    def ranking_observations(
        self, results: Sequence[Mapping[str, object]]
    ) -> tuple[tuple[JsonObject, JsonObject, dict[str, Mapping[str, object]]], ...]:
        observations = []
        for result in results:
            run = self.resolve_reference(_reference(result, "run_ref"))
            task = self.resolve_reference(_reference(run, "task_ref"))
            assertions: dict[str, Mapping[str, object]] = {}
            candidates = task.get("candidates")
            if not isinstance(candidates, list):
                raise ScoringError("Ranking Task candidates must be a list")
            for candidate in candidates:
                if not isinstance(candidate, dict):
                    raise ScoringError("Ranking Task candidate must be an object")
                candidate_id = candidate.get("id")
                if not isinstance(candidate_id, str):
                    raise ScoringError("Ranking Task candidate has no id")
                enrollment = self.resolve_reference(
                    _reference(candidate, "enrollment_ref")
                )
                assertions[candidate_id] = _reference(enrollment, "assertion_ref")
            observations.append((dict(result), run, assertions))
        return tuple(observations)

    def scoring_trace_for_assertion(
        self, assertion_ref: Mapping[str, object]
    ) -> JsonObject | None:
        matches = [
            trace
            for trace in self.records(SCORING_TRACE_TYPE)
            if canonical_json(trace.get("assertion_ref"))
            == canonical_json(assertion_ref)
        ]
        if len(matches) > 1:
            raise ScoringError("Assertion has multiple scoring Traces")
        return matches[0] if matches else None

    def events_for_trace(self, trace: Mapping[str, object]) -> tuple[JsonObject, ...]:
        validate_record(trace)
        if trace.get("type") != SCORING_TRACE_TYPE:
            raise ScoringError("scoring Event selection requires a scoring Trace")
        path = self.root / "assertion-traces" / str(trace["id"]) / "events.jsonl"
        return tuple(self._read_events(path))

    def resolve_reference(self, reference: Mapping[str, object]) -> JsonObject:
        """Resolve one exact scoring Record edition, including from Git history."""

        target_type = reference_target_type(reference)
        if target_type is None:
            raise ScoringError(
                f"Reference is external to the scoring repository: {reference.get('type')}"
            )
        identity = str(reference.get("id", ""))
        expected_hash = str(reference.get("record_sha256", ""))
        current = [
            item for item in self.records(target_type) if str(item["id"]) == identity
        ]
        if len(current) > 1:
            raise ScoringError(f"duplicate scoring Record UUID: {identity}")
        if current and content_hash(current[0]) == expected_hash:
            return current[0]
        if target_type == SCORING_EVENT_TYPE:
            raise ScoringError(
                f"exact scoring Event is not retained at HEAD: {identity}@{expected_hash}"
            )
        if not current:
            raise ScoringError(
                f"exact scoring Record is not retained at HEAD: {identity}@{expected_hash}"
            )
        relative = self.path_for(current[0]).relative_to(self.root)
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
            f"{reference.get('type')} {identity}@{expected_hash}"
        )

    def trace(self, record: Mapping[str, object]) -> JsonObject:
        root = dict(record)
        validate_record(root)
        return self.trace_reference(_record_reference(root))

    def trace_reference(self, root_reference: Mapping[str, object]) -> JsonObject:
        """Build a disposable neighborhood around a scoring or external Reference."""

        root_ref = dict(root_reference)
        pending = deque([root_ref])
        seen_refs: set[str] = set()
        seen_records: set[tuple[str, str]] = set()
        records: list[JsonObject] = []
        edges: list[JsonObject] = []
        external: list[JsonObject] = []
        current_records = self.records()
        inbound: dict[str, list[JsonObject]] = {}
        for candidate in current_records:
            for _, reference in record_relations(candidate):
                inbound.setdefault(_reference_key(reference), []).append(candidate)
        while pending:
            current_ref = pending.popleft()
            ref_key = _reference_key(current_ref)
            if ref_key in seen_refs:
                continue
            seen_refs.add(ref_key)
            target_type = reference_target_type(current_ref)
            if target_type is not None:
                current = self.resolve_reference(current_ref)
                current_key = (str(current["id"]), content_hash(current))
                if current_key not in seen_records:
                    seen_records.add(current_key)
                    records.append(current)
                for field, reference in record_relations(current):
                    edge = {
                        "from_ref": current_ref,
                        "field": field,
                        "to_ref": dict(reference),
                    }
                    if edge not in edges:
                        edges.append(edge)
                    if reference_target_type(reference) is None:
                        if dict(reference) not in external:
                            external.append(dict(reference))
                    pending.append(dict(reference))
            elif current_ref not in external:
                external.append(current_ref)
            for dependent in inbound.get(ref_key, []):
                dependent_ref = _record_reference(dependent)
                for field, reference in record_relations(dependent):
                    if _reference_key(reference) != ref_key:
                        continue
                    edge = {
                        "from_ref": dependent_ref,
                        "field": field,
                        "to_ref": current_ref,
                    }
                    if edge not in edges:
                        edges.append(edge)
                pending.append(dependent_ref)
        return {
            "root_ref": root_ref,
            "records": records,
            "edges": edges,
            "external_references": external,
        }

    def path_for(self, record: Mapping[str, object]) -> Path:
        record_type = str(record.get("type", ""))
        if record_type not in RECORD_KINDS:
            raise ScoringError(f"unsupported scoring Record type: {record_type}")
        record_id = str(record.get("id", ""))
        if is_pool_record_type(record_type):
            return self.root / "pools" / record_id / "pool.json"
        if record_type == SCORING_TRACE_TYPE:
            return self.root / "assertion-traces" / record_id / "trace.json"
        if record_type == SCORING_EVENT_TYPE:
            trace = self.resolve_reference(_reference(record, "trace_ref"))
            return self.root / "assertion-traces" / str(trace["id"]) / "events.jsonl"
        pool_id = self._pool_id_for(record)
        child_dir = {
            POOL_ENROLLMENT_TYPE: "enrollments",
            GROUNDING_TASK_TYPE: "tasks",
            RUN_TYPE: "runs",
            RESULT_TYPE: "results",
        }[record_type]
        return self.root / "pools" / pool_id / child_dir / f"{record_id}.json"

    def head(self) -> str:
        return self._git("rev-parse", "HEAD").stdout.strip()

    def _pool_id_for(self, record: Mapping[str, object]) -> str:
        record_type = record.get("type")
        if record_type in {POOL_ENROLLMENT_TYPE, GROUNDING_TASK_TYPE}:
            pool = self.resolve_reference(_reference(record, "pool_ref"))
            return str(pool["id"])
        if record_type == RUN_TYPE:
            task = self.resolve_reference(_reference(record, "task_ref"))
            return self._pool_id_for(task)
        if record_type == RESULT_TYPE:
            run = self.resolve_reference(_reference(record, "run_ref"))
            return self._pool_id_for(run)
        raise ScoringError(f"Record is not Pool-owned: {record_type}")

    def _paths_for_type(self, record_type: str) -> tuple[Path, ...]:
        pattern = {
            **{
                pool_type: "*/pool.json"
                for pool_type in RECORD_KINDS
                if is_pool_record_type(pool_type)
            },
            POOL_ENROLLMENT_TYPE: "*/enrollments/*.json",
            GROUNDING_TASK_TYPE: "*/tasks/*.json",
            RUN_TYPE: "*/runs/*.json",
            RESULT_TYPE: "*/results/*.json",
        }.get(record_type)
        if record_type == SCORING_TRACE_TYPE:
            return tuple(sorted((self.root / "assertion-traces").glob("*/trace.json")))
        if pattern is None:
            return ()
        return tuple(sorted((self.root / "pools").glob(pattern)))

    def _load_path(self, path: Path) -> JsonObject:
        payload = self._read_json(path)
        validate_record(payload)
        if self.path_for(payload) != path:
            raise ScoringError(f"scoring Record is stored at the wrong path: {path}")
        return payload

    def _read_events(self, path: Path) -> list[JsonObject]:
        if not path.exists():
            return []
        events: list[JsonObject] = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1
        ):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ScoringError(
                    f"cannot read scoring JSONL {path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(value, dict):
                raise ScoringError(
                    f"scoring JSONL line must be an object: {path}:{line_number}"
                )
            validate_record(value)
            events.append(value)
        return events

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


def _record_reference(record: Mapping[str, object]) -> JsonObject:
    return {
        "type": f"{record['type']}.Reference",
        "id": record["id"],
        "record_sha256": content_hash(record),
    }


def _reference_key(reference: Mapping[str, object]) -> str:
    return canonical_json(reference)


__all__ = ["REPOSITORY_TYPE", "ScoringRepository", "default_scoring_root"]
