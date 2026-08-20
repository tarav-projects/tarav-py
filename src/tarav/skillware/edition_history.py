# $kw: ^edition-history-service --from Skw.Edition.History.Service --note [DF] validated Skillware edition/session associations with required embedded Chat.Support.Set records ^c20260725-12u --supp schema migration authorized ^c20260725-14u --supp live Chatlas resolution authorized ^c20260725-15u --supp project-default depot authorized ^c20260725-25u --supp Git-complete projection and amendment authorized ^c20260725-32u
from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.project import find_agentos_project
from tarav.bloberia.depot_v1 import (
    BloberiaDepot,
    BloberiaError,
    BloberiaRecord,
)


EDITION_SESSION_KIND = "skw.edition-session"
EDITION_SESSION_SCHEMA_VERSION = 1
CHATLAS_SUPPORT_SET_SCHEMA = "chatlas.support-set.v3"
DEFAULT_EDITION_HISTORY_DEPOT = (
    Path(".tarav") / "state" / "bloberia" / "edition-history"
)
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{4,64}$")


class EditionHistoryError(RuntimeError):
    pass


class EditionSupportResolutionError(EditionHistoryError):
    pass


EditionSupportResolver = Callable[[dict[str, object]], object]


@dataclass(frozen=True)
class EditionFile:
    project_id: str
    path: str

    @classmethod
    def resolve(cls, path: Path | str) -> "EditionFile":
        return _resolve_file(path).identity

    def as_dict(self) -> dict[str, str]:
        return {"project_id": self.project_id, "path": self.path}


def default_edition_history_depot(path: Path | str) -> Path:
    """Return the canonical depot below the Tarav project owning `path`."""
    return _resolve_file(path).project_root / DEFAULT_EDITION_HISTORY_DEPOT


@dataclass(frozen=True)
class EditionSession:
    session_id: str
    started_at: str | None
    support: dict[str, object]
    record_id: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.session_id,
            "started_at": self.started_at,
            "support": self.support,
            "record_id": self.record_id,
        }


@dataclass(frozen=True)
class EditionHistoryEntry:
    commit: str
    committed_at: str
    sessions: tuple[EditionSession, ...]

    @property
    def supported(self) -> bool:
        return bool(self.sessions)

    def as_dict(self) -> dict[str, object]:
        return {
            "commit": self.commit,
            "committed_at": self.committed_at,
            "supported": self.supported,
            "sessions": [session.as_dict() for session in self.sessions],
        }


@dataclass(frozen=True)
class EditionHistory:
    file: EditionFile
    editions: tuple[EditionHistoryEntry, ...]

    @property
    def supported_editions(self) -> int:
        return sum(edition.supported for edition in self.editions)

    @property
    def unsupported_editions(self) -> int:
        return len(self.editions) - self.supported_editions

    def as_dict(self) -> dict[str, object]:
        return {
            "file": self.file.as_dict(),
            "editions": [edition.as_dict() for edition in self.editions],
        }


@dataclass(frozen=True)
class RecordEditionSessionResult:
    created: bool
    record_id: str

    def as_dict(self) -> dict[str, object]:
        return {"created": self.created, "record_id": self.record_id}


@dataclass(frozen=True)
class AmendEditionSessionResult:
    amended: bool
    record_id: str
    revision: int

    def as_dict(self) -> dict[str, object]:
        return {
            "amended": self.amended,
            "record_id": self.record_id,
            "revision": self.revision,
        }


@dataclass(frozen=True)
class EditionHistoryFinding:
    code: str
    target: str
    message: str
    record_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "code": self.code,
            "target": self.target,
            "message": self.message,
        }
        if self.record_ids:
            payload["record_ids"] = list(self.record_ids)
        return payload


@dataclass(frozen=True)
class EditionHistoryCheckResult:
    findings: tuple[EditionHistoryFinding, ...]

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict[str, object]:
        return {
            "status": "ok" if self.ok else "error",
            "findings": [finding.as_dict() for finding in self.findings],
        }


@dataclass(frozen=True)
class _ResolvedEditionFile:
    identity: EditionFile
    project_root: Path
    absolute_path: Path


@dataclass(frozen=True)
class _Association:
    file: EditionFile
    commit: str
    committed_at: str
    session: EditionSession


class EditionHistoryService:
    """Skillware's validated edition-history boundary over one Bloberia depot."""

    def __init__(
        self,
        depot: BloberiaDepot,
        *,
        support_resolver: EditionSupportResolver | None = None,
    ) -> None:
        self.depot = depot
        self.support_resolver = support_resolver

    def record(
        self,
        file: Path | str,
        commit: str,
        session_id: str,
        *,
        support: dict[str, object],
        session_started_at: str | None = None,
    ) -> RecordEditionSessionResult:
        resolved_file = _resolve_file(file)
        full_commit, committed_at = _resolve_git_edition(
            resolved_file.project_root,
            commit,
        )
        normalized_session_id = _nonempty_string(session_id, field="session id")
        normalized_started_at = _optional_iso_timestamp(
            session_started_at,
            field="session_started_at",
        )
        normalized_support = _support_set(
            support,
            session_id=normalized_session_id,
        )
        self._resolve_support(normalized_support)

        identity_query = {
            "value": {
                "kind": EDITION_SESSION_KIND,
                "schema_version": EDITION_SESSION_SCHEMA_VERSION,
                "file": resolved_file.identity.as_dict(),
                "edition": {"commit": full_commit},
                "session": {"id": normalized_session_id},
            }
        }
        try:
            existing = self.depot.query(identity_query)
        except BloberiaError as exc:
            raise EditionHistoryError(str(exc)) from exc
        if existing:
            association = _association_from_record(existing[0])
            self._resolve_support(association.session.support)
            return RecordEditionSessionResult(
                created=False,
                record_id=association.session.record_id,
            )

        value = {
            "kind": EDITION_SESSION_KIND,
            "schema_version": EDITION_SESSION_SCHEMA_VERSION,
            "file": resolved_file.identity.as_dict(),
            "edition": {
                "commit": full_commit,
                "committed_at": committed_at,
            },
            "session": {
                "id": normalized_session_id,
                "started_at": normalized_started_at,
            },
            "support": normalized_support,
        }
        try:
            record = self.depot.create(value)
        except BloberiaError as exc:
            raise EditionHistoryError(str(exc)) from exc
        return RecordEditionSessionResult(created=True, record_id=record.id)

    def list(self, file: Path | str) -> EditionHistory:
        resolved_file = _resolve_file(file)
        identity = resolved_file.identity
        query = {
            "value": {
                "kind": EDITION_SESSION_KIND,
                "file": identity.as_dict(),
            }
        }
        try:
            records = self.depot.query(query)
        except BloberiaError as exc:
            raise EditionHistoryError(str(exc)) from exc
        associations = tuple(_association_from_record(record) for record in records)
        for association in associations:
            self._resolve_support(association.session.support)
        return _build_history(
            identity,
            associations,
            git_editions=_git_file_editions(resolved_file),
        )

    def amend(
        self,
        file: Path | str,
        record_id: str,
        *,
        support: dict[str, object],
        session_started_at: str | None = None,
    ) -> AmendEditionSessionResult:
        resolved_file = _resolve_file(file)
        try:
            record = self.depot.get(record_id)
        except BloberiaError as exc:
            raise EditionHistoryError(str(exc)) from exc
        association = _association_from_record(record)
        if association.file != resolved_file.identity:
            raise EditionHistoryError(
                f"edition-history record {record_id} does not belong to "
                f"{resolved_file.identity.path}"
            )
        normalized_support = _support_set(
            support,
            session_id=association.session.session_id,
        )
        self._resolve_support(normalized_support)
        started_at = (
            association.session.started_at
            if session_started_at is None
            else _optional_iso_timestamp(
                session_started_at,
                field="session_started_at",
            )
        )
        value = {
            "kind": EDITION_SESSION_KIND,
            "schema_version": EDITION_SESSION_SCHEMA_VERSION,
            "file": association.file.as_dict(),
            "edition": {
                "commit": association.commit,
                "committed_at": association.committed_at,
            },
            "session": {
                "id": association.session.session_id,
                "started_at": started_at,
            },
            "support": normalized_support,
        }
        if value == record.value:
            return AmendEditionSessionResult(
                amended=False,
                record_id=record.id,
                revision=record.revision,
            )
        try:
            amended = self.depot.edit(record_id, value)
        except BloberiaError as exc:
            raise EditionHistoryError(str(exc)) from exc
        return AmendEditionSessionResult(
            amended=True,
            record_id=amended.id,
            revision=amended.revision,
        )

    def check(
        self,
        targets: list[Path | str] | tuple[Path | str, ...],
        *,
        require_complete: bool = False,
    ) -> EditionHistoryCheckResult:
        resolved_files = tuple(
            sorted(
                (_resolve_file(target) for target in targets),
                key=lambda item: (item.identity.project_id, item.identity.path),
            )
        )
        if not resolved_files:
            raise EditionHistoryError("at least one edition-history target is required")
        resolved_targets = tuple(item.identity for item in resolved_files)

        depot_check = self.depot.check()
        if not depot_check.ok:
            return EditionHistoryCheckResult(
                findings=tuple(
                    EditionHistoryFinding(
                        code=f"bloberia-{finding.code}",
                        target=finding.path,
                        message=finding.message,
                        record_ids=(
                            (finding.record_id,) if finding.record_id else ()
                        ),
                    )
                    for finding in depot_check.findings
                )
            )

        try:
            records = self.depot.query(
                {"value": {"kind": EDITION_SESSION_KIND}}
            )
        except BloberiaError as exc:
            return EditionHistoryCheckResult(
                findings=(
                    EditionHistoryFinding(
                        code="bloberia-query-failed",
                        target=str(self.depot.root),
                        message=str(exc),
                    ),
                )
            )

        findings: list[EditionHistoryFinding] = []
        associations: list[_Association] = []
        supported_associations: list[_Association] = []
        for record in records:
            try:
                association = _association_from_record(record)
            except EditionHistoryError as exc:
                findings.append(
                    EditionHistoryFinding(
                        code="invalid-edition-history-record",
                        target=f"records/{record.id}.json",
                        message=str(exc),
                        record_ids=(record.id,),
                    )
                )
                continue
            associations.append(association)
            try:
                self._resolve_support(association.session.support)
            except EditionSupportResolutionError as exc:
                findings.append(
                    EditionHistoryFinding(
                        code="unresolvable-edition-support",
                        target=association.file.path,
                        message=str(exc),
                        record_ids=(record.id,),
                    )
                )
            else:
                supported_associations.append(association)

        target_keys = {
            (target.project_id, target.path) for target in resolved_targets
        }
        matching = [
            association
            for association in associations
            if (association.file.project_id, association.file.path) in target_keys
        ]
        supported_matching = [
            association
            for association in supported_associations
            if (association.file.project_id, association.file.path) in target_keys
        ]
        grouped: dict[tuple[str, str, str, str], list[str]] = {}
        for association in matching:
            key = (
                association.file.project_id,
                association.file.path,
                association.commit,
                association.session.session_id,
            )
            grouped.setdefault(key, []).append(association.session.record_id)
        for (_project_id, path, commit, session_id), record_ids in grouped.items():
            if len(record_ids) > 1:
                findings.append(
                    EditionHistoryFinding(
                        code="duplicate-edition-session",
                        target=path,
                        message=(
                            f"edition {commit} and session {session_id} "
                            "have multiple association records"
                        ),
                        record_ids=tuple(sorted(record_ids)),
                    )
                )

        files_with_history = {
            (association.file.project_id, association.file.path)
            for association in matching
        }
        for target in resolved_targets:
            if (target.project_id, target.path) not in files_with_history:
                findings.append(
                    EditionHistoryFinding(
                        code="missing-edition-history",
                        target=target.path,
                        message="target has no valid edition/session association",
                    )
                )
        if require_complete:
            supported_commits = {
                (
                    association.file.project_id,
                    association.file.path,
                    association.commit,
                )
                for association in supported_matching
            }
            for resolved_file in resolved_files:
                for commit, committed_at in _git_file_editions(resolved_file):
                    key = (
                        resolved_file.identity.project_id,
                        resolved_file.identity.path,
                        commit,
                    )
                    if key not in supported_commits:
                        findings.append(
                            EditionHistoryFinding(
                                code="unsupported-git-edition",
                                target=resolved_file.identity.path,
                                message=(
                                    f"Git edition {commit} at {committed_at} "
                                    "has no resolvable session association"
                                ),
                            )
                        )

        return EditionHistoryCheckResult(
            findings=tuple(
                sorted(
                    findings,
                    key=lambda finding: (
                        finding.target,
                        finding.code,
                        finding.record_ids,
                    ),
                )
            )
        )

    def _resolve_support(self, support: dict[str, object]) -> None:
        if self.support_resolver is None:
            raise EditionSupportResolutionError(
                "edition support resolver is required"
            )
        try:
            self.support_resolver(support)
        except EditionSupportResolutionError:
            raise
        except Exception as exc:
            detail = str(exc).strip() or type(exc).__name__
            raise EditionSupportResolutionError(
                f"edition support is not resolvable: {detail}"
            ) from exc


def _resolve_file(path: Path | str) -> _ResolvedEditionFile:
    absolute_path = Path(path).expanduser().resolve()
    if not absolute_path.is_file():
        raise EditionHistoryError(f"edition-history file does not exist: {absolute_path}")
    project = find_agentos_project(absolute_path)
    if project is None:
        raise EditionHistoryError(
            f"edition-history file is not inside a Tarav project: {absolute_path}"
        )
    try:
        project.validate()
    except (CliError, OSError, ValueError) as exc:
        raise EditionHistoryError(str(exc)) from exc
    try:
        relative_path = absolute_path.relative_to(project.root).as_posix()
    except ValueError as exc:
        raise EditionHistoryError(
            f"edition-history file is outside project root: {absolute_path}"
        ) from exc
    return _ResolvedEditionFile(
        identity=EditionFile(project_id=project.project_id, path=relative_path),
        project_root=project.root,
        absolute_path=absolute_path,
    )


def _resolve_git_edition(project_root: Path, commit: str) -> tuple[str, str]:
    commit = _nonempty_string(commit, field="commit")
    if not _COMMIT_RE.fullmatch(commit):
        raise EditionHistoryError("commit must be a hexadecimal Git commit identity")
    full_commit = _run_git(
        project_root,
        "rev-parse",
        "--verify",
        "--end-of-options",
        f"{commit}^{{commit}}",
    )
    committed_at = _run_git(
        project_root,
        "show",
        "-s",
        "--format=%cI",
        "--no-patch",
        full_commit,
    )
    return full_commit, _iso_timestamp(committed_at, field="Git committed_at")


def _git_file_editions(
    file: _ResolvedEditionFile,
) -> tuple[tuple[str, str], ...]:
    output = _run_git(
        file.project_root,
        "log",
        "--follow",
        "--format=%H%x09%cI",
        "--",
        file.identity.path,
    )
    editions: list[tuple[str, str]] = []
    for line in output.splitlines():
        commit, separator, committed_at = line.partition("\t")
        if not separator:
            raise EditionHistoryError(
                f"cannot parse Git edition history for {file.identity.path}"
            )
        editions.append(
            (
                commit.lower(),
                _iso_timestamp(committed_at, field="Git committed_at"),
            )
        )
    return tuple(reversed(editions))


def _run_git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (
            exc.stderr.strip()
            if isinstance(exc, subprocess.CalledProcessError) and exc.stderr
            else str(exc)
        )
        raise EditionHistoryError(f"cannot resolve Git edition: {detail}") from exc
    return result.stdout.strip()


def _association_from_record(record: BloberiaRecord) -> _Association:
    try:
        value = _exact_object(
            record.value,
            keys={
                "kind",
                "schema_version",
                "file",
                "edition",
                "session",
                "support",
            },
            field="record value",
        )
        if value["kind"] != EDITION_SESSION_KIND:
            raise EditionHistoryError("record kind is not skw.edition-session")
        if value["schema_version"] != EDITION_SESSION_SCHEMA_VERSION:
            raise EditionHistoryError("record schema_version is not 1")
        file_value = _exact_object(
            value["file"],
            keys={"project_id", "path"},
            field="file",
        )
        edition_value = _exact_object(
            value["edition"],
            keys={"commit", "committed_at"},
            field="edition",
        )
        session_value = _exact_object(
            value["session"],
            keys={"id", "started_at"},
            field="session",
        )
        file = EditionFile(
            project_id=_nonempty_string(
                file_value["project_id"],
                field="file.project_id",
            ),
            path=_nonempty_string(file_value["path"], field="file.path"),
        )
        commit = _nonempty_string(edition_value["commit"], field="edition.commit")
        if not _COMMIT_RE.fullmatch(commit):
            raise EditionHistoryError(
                "edition.commit must be a hexadecimal Git commit identity"
            )
        committed_at = _iso_timestamp(
            edition_value["committed_at"],
            field="edition.committed_at",
        )
        session_id = _nonempty_string(session_value["id"], field="session.id")
        support = _support_set(value["support"], session_id=session_id)
        session = EditionSession(
            session_id=session_id,
            started_at=_optional_iso_timestamp(
                session_value["started_at"],
                field="session.started_at",
            ),
            support=support,
            record_id=record.id,
        )
    except EditionHistoryError as exc:
        raise EditionHistoryError(
            f"invalid edition-history record {record.id}: {exc}"
        ) from exc
    return _Association(
        file=file,
        commit=commit.lower(),
        committed_at=committed_at,
        session=session,
    )


def _build_history(
    file: EditionFile,
    associations: tuple[_Association, ...],
    *,
    git_editions: tuple[tuple[str, str], ...],
) -> EditionHistory:
    git_keys = [(committed_at, commit) for commit, committed_at in git_editions]
    grouped: dict[tuple[str, str], list[EditionSession]] = {
        key: [] for key in git_keys
    }
    for association in associations:
        grouped.setdefault(
            (association.committed_at, association.commit),
            [],
        ).append(association.session)
    extra_keys = sorted(set(grouped) - set(git_keys))
    editions = tuple(
        EditionHistoryEntry(
            commit=commit,
            committed_at=committed_at,
            sessions=tuple(
                sorted(
                    sessions,
                    key=lambda session: (
                        session.started_at is None,
                        session.started_at or "",
                        session.session_id,
                        session.record_id,
                    ),
                )
            ),
        )
        for committed_at, commit in (*git_keys, *extra_keys)
        for sessions in (grouped[(committed_at, commit)],)
    )
    return EditionHistory(file=file, editions=editions)


def _exact_object(
    value: object,
    *,
    keys: set[str],
    field: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise EditionHistoryError(
            f"{field} must contain exactly {sorted(keys)}"
        )
    return value


def _support_set(
    value: object,
    *,
    session_id: str,
) -> dict[str, object]:
    support = _exact_object(
        value,
        keys={"app", "schema", "hint", "members"},
        field="support",
    )
    if support["app"] != "chatlas":
        raise EditionHistoryError("support.app must be 'chatlas'")
    if support["schema"] != CHATLAS_SUPPORT_SET_SCHEMA:
        raise EditionHistoryError(
            f"support.schema must be {CHATLAS_SUPPORT_SET_SCHEMA!r}"
        )
    hint = _nonempty_string(support["hint"], field="support.hint")
    raw_members = support["members"]
    if not isinstance(raw_members, list) or not raw_members:
        raise EditionHistoryError("support.members must be a non-empty list")

    members: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    includes_session = False
    for index, raw_member in enumerate(raw_members):
        member = _exact_object(
            raw_member,
            keys={"session", "turn_id", "turn_hash", "at"},
            field=f"support.members[{index}]",
        )
        member_session = _nonempty_string(
            member["session"],
            field=f"support.members[{index}].session",
        )
        turn_id = _nonempty_string(
            member["turn_id"],
            field=f"support.members[{index}].turn_id",
        )
        turn_hash = _nonempty_string(
            member["turn_hash"],
            field=f"support.members[{index}].turn_hash",
        )
        if len(turn_hash) != 64:
            raise EditionHistoryError(
                f"support.members[{index}].turn_hash must be a full SHA-256 digest"
            )
        at = _validated_iso_timestamp(
            member["at"],
            field=f"support.members[{index}].at",
        )
        identity = (member_session, turn_id)
        if identity in seen:
            raise EditionHistoryError(
                f"support.members[{index}] duplicates "
                f"{member_session}:{turn_id}"
            )
        seen.add(identity)
        includes_session = includes_session or member_session == session_id
        members.append(
            {
                "session": member_session,
                "turn_id": turn_id,
                "turn_hash": turn_hash,
                "at": at,
            }
        )

    if not includes_session:
        raise EditionHistoryError(
            "support.members must include associated session.id"
        )
    return {
        "app": "chatlas",
        "schema": CHATLAS_SUPPORT_SET_SCHEMA,
        "hint": hint,
        "members": members,
    }


def _nonempty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EditionHistoryError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_iso_timestamp(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    return _iso_timestamp(value, field=field)


def _iso_timestamp(value: object, *, field: str) -> str:
    text = _nonempty_string(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EditionHistoryError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EditionHistoryError(f"{field} must include a timezone")
    utc = parsed.astimezone(timezone.utc)
    return utc.isoformat(timespec="seconds").replace("+00:00", "Z")


def _validated_iso_timestamp(value: object, *, field: str) -> str:
    text = _nonempty_string(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EditionHistoryError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EditionHistoryError(f"{field} must include a timezone")
    return text


__all__ = [
    "CHATLAS_SUPPORT_SET_SCHEMA",
    "EDITION_SESSION_KIND",
    "EDITION_SESSION_SCHEMA_VERSION",
    "EditionFile",
    "EditionHistory",
    "EditionHistoryCheckResult",
    "EditionHistoryEntry",
    "EditionHistoryError",
    "EditionHistoryFinding",
    "EditionHistoryService",
    "EditionSession",
    "EditionSupportResolutionError",
    "EditionSupportResolver",
    "RecordEditionSessionResult",
]
