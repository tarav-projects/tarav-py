# $kw: --from Line.Home --from Chat.Index.HEAD
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from tarav._core.errors import CliError
from tarav._core.persistence import atomic_write_json
from tarav._core.project import find_agentos_project_root
from tarav.chatlas.index_check_model import LinterCheck, LinterFinding, allowed
from tarav.index_model import canonical_index_line_statement, parse_depot

from tarav.chatlas.anchory import (
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
    chatlas_anchory_depot,
    parse_line_issue_context,
)
from tarav.chatlas.chat_index import (
    HEAD_FILENAME,
    chat_index_discovery,
    chat_index_surface_path,
    load_chat_index_capture,
)
from tarav.chatlas.chat_index_audit import audit_chat_index_surface
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.paths import default_chatlas_root


PROJECT_INDEX_AUDIT_SCHEMA = "agentos.project-index.audit.v1"
RECONCILIATION_CURSOR_SCHEMA = "agentos.project-index.reconciliation-cursor.v1"
SUPPORT_CHAT_REGISTRY = "009-SUPPORT-CHATS.md"

_SUPPORT_CHAT_RE = re.compile(r"^- `(?P<identity>[0-9a-f]{64})`\s+[—-]")
_ISSUE_ID_RE = re.compile(r"^(?P<identity>Issue\.I[0-9]{4})(?:\.|$)")


def project_support_chat_identities(depot: str | Path) -> tuple[str, ...]:
    """Read the exact identities from one maintained support-chat registry."""
    path = Path(depot).expanduser().resolve() / SUPPORT_CHAT_REGISTRY
    if not path.is_file():
        return ()
    identities: list[str] = []
    for source in path.read_text(encoding="utf-8").splitlines():
        match = _SUPPORT_CHAT_RE.match(source)
        if match is not None and match.group("identity") not in identities:
            identities.append(match.group("identity"))
    return tuple(identities)


def project_index_audit(
    depot: str | Path,
    *,
    chatlas_root: Path | None = None,
    cursor_root: Path | None = None,
) -> dict[str, object]:
    """Compare one current Project.Index with each registered support Chat.Index.

    This operation is deliberately read-only. It emits eventual-consistency POIs;
    it never blocks Project-first or Chat-first authoring and never updates cursors.
    """
    depot_path = Path(depot).expanduser().resolve()
    if not depot_path.is_dir():
        raise CliError(f"Project.Index depot is not a directory: {depot_path}")
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    registry_path = depot_path / SUPPORT_CHAT_REGISTRY
    identities = project_support_chat_identities(depot_path)
    findings: list[dict[str, object]] = []
    project_lines = _project_lines(depot_path)

    if not registry_path.is_file():
        _finding(
            findings,
            "Project.Chat.Registry.Missing",
            "Project.Index has no maintained 009-SUPPORT-CHATS.md registry",
            path=str(registry_path),
        )
    elif not identities:
        _finding(
            findings,
            "Project.Chat.Registry.Empty",
            "Project support-chat registry contains no exact chat identities",
            path=str(registry_path),
        )

    head_by_statement: dict[str, list[dict[str, object]]] = {}
    delta_by_statement: dict[str, list[dict[str, object]]] = {}
    anchor_statements: dict[str, set[str]] = {}
    chat_results: list[dict[str, object]] = []
    effective_cursor_root = cursor_root or _default_cursor_root(depot_path)

    for identity in identities:
        discovery = chat_index_discovery(identity, chatlas_root=root)
        if not discovery["materialized"]:
            _finding(
                findings,
                "Project.Chat.Index.Unavailable",
                "registered support chat has no materialized Chat.Index",
                identity=identity,
                path=str(discovery["path"]),
            )
            chat_results.append(
                {
                    "identity": identity,
                    "state": "unavailable",
                    "path": str(discovery["path"]),
                    "candidate_line_count": 0,
                }
            )
            continue

        surface = chat_index_surface_path(identity, chatlas_root=root)


        audited = audit_chat_index_surface(
            surface,
            identity_hash=identity,
            session=_session_of(identity, root),
            chatlas_root=root,
            include_line_inventory=True,
        )
        audit_summary = {
            "ok": audited["ok"],
            "finding_count": audited["finding_count"],
            "blocking_finding_count": audited["blocking_finding_count"],
        }
        if audited.get("blocking_finding_count", 0):
            _finding(
                findings,
                "Project.Chat.Index.Invalid",
                "registered Chat.Index has blocking internal audit findings",
                identity=identity,
                path=str(surface),
                blocking_finding_count=audited["blocking_finding_count"],
            )
            chat_results.append(
                {
                    "identity": identity,
                    "state": "invalid",
                    "path": str(surface),
                    "candidate_line_count": 0,
                    "chat_index_audit": audit_summary,
                }
            )
            continue
        inventory = audited.get("line_inventory", {})
        head = inventory.get("head", {}) if isinstance(inventory, dict) else {}
        deltas = inventory.get("deltas", {}) if isinstance(inventory, dict) else {}
        _merge_inventory(head_by_statement, anchor_statements, identity, head)
        _merge_inventory(delta_by_statement, anchor_statements, identity, deltas)

        cursor = _load_cursor(effective_cursor_root, depot_path, identity)
        candidate = _cursor_candidate(surface, identity)
        reconcile_state, changed_paths = _classify_cursor(cursor, candidate)
        candidate_statement_keys = _candidate_statement_keys(deltas, changed_paths)
        chat_results.append(
            {
                "identity": identity,
                "state": reconcile_state,
                "path": str(surface),
                "changed_delta_paths": changed_paths,
                "candidate_statement_keys": candidate_statement_keys,
                "candidate_line_count": len(candidate_statement_keys),
                "cursor_candidate": candidate,
                "chat_index_audit": audit_summary,
            }
        )

    depot_anchors = chatlas_anchory_depot(root)



    for line in project_lines if identities else ():
        statement_key = str(line["statement_key"])
        delta_homes = delta_by_statement.get(statement_key, [])
        head_occurrences = head_by_statement.get(statement_key, [])
        is_issue = line["surface"] == "issues"
        if not delta_homes:
            _finding(
                findings,
                "Project.Line.Home.Missing",
                "Project Index.Line has no exact Delta home in a registered support chat",
                **line,
            )
        elif len({item["identity"] for item in delta_homes}) > 1:
            _finding(
                findings,
                "Project.Line.Home.Ambiguous",
                "Project Index.Line has candidate homes in several support chats",
                candidates=delta_homes,
                **line,
            )
        if not is_issue and not head_occurrences:
            _finding(
                findings,
                "Project.Line.Head.Missing",
                "ordinary Project Index.Line is absent from every supporting Chat.Index.HEAD",
                **line,
            )
        anchors = tuple(str(value) for value in line["anchors"])
        uses_line_record, issue_contexts = _anchor_line_record_context(
            anchors, depot_anchors
        )
        drift_hashes = sorted(
            {
                observed
                for anchor in anchors
                for observed in anchor_statements.get(anchor, set())
                if observed != statement_key
            }
        )
        if drift_hashes:
            _finding(
                findings,
                "Project.Line.Content.Drift",
                "a Project line anchor is attached to different canonical content in a support Chat.Index",
                observed_statement_keys=drift_hashes,
                **line,
            )
        if is_issue:
            issue = str(line["issue"])
            if issue not in issue_contexts:
                _finding(
                    findings,
                    "Project.Issue.Context.Missing",
                    "Issue.Block line record does not carry its Issue identity",
                    **line,
                )
        elif uses_line_record and not issue_contexts:
            _finding(
                findings,
                "Project.Line.Issue.Context.Missing",
                "line-record-backed Project model line has no Issue identity as edition context",
                **line,
            )

    return {
        "status": "ok",
        "command": "chatlas project-index audit",
        "schema": PROJECT_INDEX_AUDIT_SCHEMA,
        "depot": str(depot_path),
        "registry": str(registry_path),
        "chatlas_root": str(root),
        "cursor_root": str(effective_cursor_root),
        "support_chat_identities": list(identities),
        "project_lines": project_lines,
        "chats": chat_results,
        "findings": findings,
        "finding_count": len(findings),
        "ok": True,
        "counts": {
            "project_line_count": len(project_lines),
            "support_chat_count": len(identities),
            "available_chat_index_count": sum(
                chat["state"] not in {"unavailable", "invalid"}
                for chat in chat_results
            ),
            "candidate_line_count": sum(
                int(chat["candidate_line_count"]) for chat in chat_results
            ),
            "finding_count": len(findings),
        },
    }


def project_index_reconcile(
    depot: str | Path,
    *,
    chatlas_root: Path | None = None,
    cursor_root: Path | None = None,
    reset: bool = False,
) -> dict[str, object]:
    """Audit a Project.Index and advance its per-chat inspection cursors."""
    depot_path = Path(depot).expanduser().resolve()
    effective_cursor_root = cursor_root or _default_cursor_root(depot_path)
    if reset:
        _reset_cursors(effective_cursor_root, depot_path)
    result = project_index_audit(
        depot_path,
        chatlas_root=chatlas_root,
        cursor_root=effective_cursor_root,
    )
    written: list[str] = []
    for chat in result["chats"]:
        candidate = chat.get("cursor_candidate")
        if not isinstance(candidate, dict):
            continue
        path = _cursor_path(effective_cursor_root, depot_path, str(chat["identity"]))
        _write_json_atomic(path, candidate)
        written.append(str(path))
    return {
        **result,
        "command": "chatlas project-index reconcile",
        "cursor_reset": reset,
        "written_cursors": written,
        "written_cursor_count": len(written),
    }


def project_index_coverage_check() -> LinterCheck:
    def run(state: Any) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for depot in state.config.depot_paths:
            result = project_index_audit(depot)
            for item in result["findings"]:
                line = item.get("line")
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=str(item["code"]),
                        message=str(item["message"]),
                        path=str(item.get("path", depot)),
                        line=line if isinstance(line, int) else None,
                        details={
                            key: value
                            for key, value in item.items()
                            if key not in {"code", "message", "path", "line"}
                        },
                    )
                )
        return findings

    return LinterCheck(
        code="Project.Chat.Coverage",
        title="Project lines are represented by registered support Chat.Indexes",
        gate=lambda _state: allowed(),
        run=run,
        poi_package_id="tarav-chatlas-pkg",
    )


def _project_lines(depot: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    model = parse_depot(depot)
    for document in model.documents:
        if document.surface_kind in {"router", "unknown"} or document.path is None:
            continue
        if document.path.parent.name == "poi":
            continue
        for line in document.kernel_lines():
            anchors = [
                str(span.parsed["anchor"])
                for span in line.spans
                if span.kind == "anchor"
            ]
            block_path = str(line.parsed.get("block_path", ""))
            issue_match = _ISSUE_ID_RE.match(block_path)
            rows.append(
                {
                    "statement_key": canonical_index_line_statement(line.src),
                    "source": line.src,
                    "surface": document.surface_kind,
                    "block_path": block_path,
                    "issue": issue_match.group("identity") if issue_match else None,
                    "path": str(document.path),
                    "line": line.start_line,
                    "anchors": anchors,
                }
            )
    return rows


def _merge_inventory(
    target: dict[str, list[dict[str, object]]],
    anchor_statements: dict[str, set[str]],
    identity: str,
    inventory: object,
) -> None:
    if not isinstance(inventory, dict):
        return
    for statement_key, occurrences in inventory.items():
        if not isinstance(occurrences, list):
            continue
        for occurrence in occurrences:
            if not isinstance(occurrence, dict):
                continue
            item = {"identity": identity, **occurrence}
            target.setdefault(str(statement_key), []).append(item)
            for anchor in occurrence.get("anchors", []):
                anchor_statements.setdefault(str(anchor), set()).add(str(statement_key))


def _anchor_line_record_context(
    anchors: tuple[str, ...], depot: Any
) -> tuple[bool, set[str]]:
    uses_line_record = False
    contexts: set[str] = set()
    for anchor in anchors:
        resolution = depot.resolve(anchor)
        if (
            resolution is not None
            and isinstance(resolution.record, dict)
            and resolution.record.get("schema") == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
        ):
            uses_line_record = True
            contexts.update(parse_line_issue_context(resolution.record))
    return uses_line_record, contexts


def _finding(
    findings: list[dict[str, object]],
    code: str,
    message: str,
    **details: object,
) -> None:
    findings.append({"code": code, "severity": "advisory", "message": message, **details})


def _session_of(identity: str, root: Path) -> dict[str, Any] | None:
    """The live chat row behind one registered identity, if it is still there."""
    try:
        return select_one_chatlas_index_row(
            command="chatlas project-index audit",
            chatlas_root=root,
            identity_hash=identity,
        )
    except CliError:
        return None


def _default_cursor_root(depot: Path) -> Path:
    project_root = find_agentos_project_root(depot)
    boundary = project_root if project_root is not None else depot
    return boundary / ".tarav" / "state" / "index-reconciliation"


def _depot_key(depot: Path) -> str:
    return sha256(str(depot.resolve()).encode("utf-8")).hexdigest()[:16]


def _cursor_path(root: Path, depot: Path, identity: str) -> Path:
    return root / _depot_key(depot) / f"{identity}.json"


def _load_cursor(root: Path, depot: Path, identity: str) -> dict[str, Any] | None:
    path = _cursor_path(root, depot, identity)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schema") != RECONCILIATION_CURSOR_SCHEMA:
        return None
    return payload


def _cursor_candidate(surface: Path, identity: str) -> dict[str, object]:
    """What the surface holds right now, as bookkeeping for the next pass.

    The cursor is derived from the files themselves; the surface asserts
    nothing about itself for it to read.
    """
    capture, error = load_chat_index_capture(surface, expected_identity_hash=identity)
    if error is not None or capture is None:
        raise CliError(f"Chat.Index surface is not readable: {error}")
    deltas = [
        {
            "path": str(delta["path"]),
            "sha256": sha256((surface / str(delta["path"])).read_bytes()).hexdigest(),
            "horizon": delta["horizon"],
        }
        for delta in capture["deltas"]
    ]
    return {
        "schema": RECONCILIATION_CURSOR_SCHEMA,
        "identity": identity,
        "surface_sha256": sha256(
            (surface / HEAD_FILENAME).read_bytes()
            + b"".join(item["sha256"].encode("ascii") for item in deltas)
        ).hexdigest(),
        "deltas": deltas,
    }


def _classify_cursor(
    previous: dict[str, Any] | None,
    current: dict[str, object],
) -> tuple[str, list[str]]:
    current_deltas = current["deltas"]
    assert isinstance(current_deltas, list)
    if previous is None:
        return "unreconciled", [str(item["path"]) for item in current_deltas]
    old = previous.get("deltas", [])
    if not isinstance(old, list):
        return "revised", [str(item["path"]) for item in current_deltas]
    common = 0
    for before, after in zip(old, current_deltas):
        if before != after:
            break
        common += 1
    if common == len(old) == len(current_deltas):
        return "current", []
    if common == len(old) < len(current_deltas):
        return "append-only", [str(item["path"]) for item in current_deltas[common:]]
    return "revised", [str(item["path"]) for item in current_deltas[common:]]


def _candidate_statement_keys(inventory: object, changed_paths: list[str]) -> list[str]:
    if not isinstance(inventory, dict) or not changed_paths:
        return []
    changed = set(changed_paths)
    return sorted(
        str(statement_key)
        for statement_key, occurrences in inventory.items()
        if isinstance(occurrences, list)
        and any(
            isinstance(occurrence, dict)
            and occurrence.get("relative_path") in changed
            for occurrence in occurrences
        )
    )


def _reset_cursors(root: Path, depot: Path) -> None:
    directory = root / _depot_key(depot)
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        path.unlink()


def _write_json_atomic(path: Path, payload: object) -> None:
    atomic_write_json(path, payload, sort_keys=False)


__all__ = [
    "PROJECT_INDEX_AUDIT_SCHEMA",
    "RECONCILIATION_CURSOR_SCHEMA",
    "project_index_audit",
    "project_index_coverage_check",
    "project_index_reconcile",
    "project_support_chat_identities",
]
