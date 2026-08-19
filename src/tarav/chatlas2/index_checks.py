from __future__ import annotations

from pathlib import Path
from typing import Any

from tarav._core.errors import CliError
from tarav.chatlas.index_checks import (
    ANCHOR_LINE_DRIFT,
    ANCHOR_TURN_MISSING,
    CHECK_ANCHOR_LINE_DRIFT,
    CHECK_GROUNDING_PROVENANCE,
    CHECK_LINE_APPROVAL,
    CHECK_LINE_VERBATIM_GATE,
    LINE_APPROVAL_MISSING,
    LINE_VERBATIM_GATE_NO_PROPOSAL,
    LINE_VERBATIM_GATE_ORDER_MISMATCH,
    LINE_VERBATIM_GATE_ROLE_MISMATCH,
    LINE_VERBATIM_GATE_TOKEN_MISMATCH,
    LINE_VERBATIM_GATE_UNREVIEWED,
    TOKENIZED_APPROVAL_GATE,
    _load_session_model,
    _record_gates,
    _tokenized_cargo_failure,
    chatlas_anchor_line_drift_check,
    chatlas_grounding_provenance_check,
)
from tarav.chatlas.index_check_model import (
    GateResult,
    LineSupportStanding,
    LinterCheck,
    LinterFinding,
    LinterState,
    bind_floor_check,
    parsed_linter_kernel_lines,
)
from tarav.index_model import (
    IndexDocument,
    canonical_index_line_body,
    index_line_anchor_triplet_hash,
)

from .anchory import chatlas2_anchory_depot, parse_line_anchor_dossier
from .grounding import support_record_resolves, tokenized_gate_failure
from .normal_model import provide_normal_model


def _gate(chatlas_root: Path | None) -> GateResult:
    depot = chatlas2_anchory_depot(chatlas_root)
    if not depot.root.is_dir():
        return GateResult(allowed=False, reason=f"anchory depot unavailable: {depot.root}")
    return GateResult(allowed=True)


def _combine(old: LinterCheck, new: LinterCheck) -> LinterCheck:
    return LinterCheck(
        code=old.code,
        title=old.title,
        gate=old.gate,
        run=lambda state: [*old.run(state), *new.run(state)],
        binding=old.binding,
        poi_package_id=old.poi_package_id,
    )


def _chatlas2_grounding_check(chatlas_root: Path | None = None) -> LinterCheck:
    depot = chatlas2_anchory_depot(chatlas_root)

    def load(identity: str):
        return provide_normal_model(identity_hash=identity, chatlas_root=chatlas_root)

    def run(
        state: LinterState, documents: tuple[IndexDocument, ...]
    ) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for _document, line in parsed_linter_kernel_lines(state, documents):
            anchors = tuple(
                str(span.parsed["anchor"])
                for span in line.spans
                if span.kind == "anchor"
            )
            previous = state.line_support_standing(line)
            resolved = set(previous.resolved_anchors if previous else ())
            for anchor in anchors:
                resolution = depot.resolve(anchor)
                record = resolution.record if resolution is not None else None
                if not isinstance(record, dict) or record.get("app") != "chatlas2":
                    continue
                try:
                    if support_record_resolves(record, loader=load):
                        resolved.add(anchor)
                    else:
                        raise CliError("one or more support messages do not resolve")
                except (CliError, OSError) as exc:
                    findings.append(
                        LinterFinding(
                            severity="error",
                            code=ANCHOR_TURN_MISSING,
                            path=state.rel_path(line.path) if line.path else ".",
                            line=line.start_line,
                            message=f"Anchor ^{anchor} has invalid Chatlas2 support: {exc}.",
                            details={"anchor": anchor, "error": str(exc)},
                        )
                    )
            state.record_line_support_standing(
                line,
                LineSupportStanding(
                    anchors=anchors, resolved_anchors=tuple(sorted(resolved))
                ),
            )
        return findings

    return bind_floor_check(
        code=CHECK_GROUNDING_PROVENANCE,
        title="Grounding provenance (chatlas2)",
        gate=lambda _state: _gate(chatlas_root),
        run=run,
        surface_kinds=frozenset({"chapter", "appendix", "agendix", "issues"}),
        poi_package_id="tarav-chatlas-pkg",
        structural=True,
    )


def grounding_provenance_check(chatlas_root: Path | None = None) -> LinterCheck:
    return _combine(
        chatlas_grounding_provenance_check(chatlas_root),
        _chatlas2_grounding_check(chatlas_root),
    )


def _chatlas2_line_drift_check(chatlas_root: Path | None = None) -> LinterCheck:
    depot = chatlas2_anchory_depot(chatlas_root)

    def run(
        state: LinterState, documents: tuple[IndexDocument, ...]
    ) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for _document, line in parsed_linter_kernel_lines(state, documents):
            for span in line.spans:
                if span.kind != "anchor":
                    continue
                anchor = str(span.parsed["anchor"])
                resolution = depot.resolve(anchor)
                record = resolution.record if resolution is not None else None
                if not isinstance(record, dict) or record.get("app") != "chatlas2":
                    continue
                try:
                    dossier = parse_line_anchor_dossier(record)
                except CliError:
                    continue
                asserted = dossier["attachment"]["triplet_hash"]
                observed = index_line_anchor_triplet_hash(line.src, anchor)
                if asserted != observed:
                    findings.append(
                        LinterFinding(
                            severity="error",
                            code=ANCHOR_LINE_DRIFT,
                            path=state.rel_path(line.path) if line.path else ".",
                            line=line.start_line,
                            message=f"Anchor ^{anchor} attachment differs from the current line.",
                            details={
                                "anchor": anchor,
                                "asserted_triplet_hash": asserted,
                                "observed_triplet_hash": observed,
                            },
                        )
                    )
        return findings

    return bind_floor_check(
        code=CHECK_ANCHOR_LINE_DRIFT,
        title="Anchor binding matches current Index line content (chatlas2)",
        gate=lambda _state: _gate(chatlas_root),
        run=run,
        surface_kinds=frozenset({"chapter", "appendix", "agendix", "issues"}),
    )


def grounding_line_drift_check(chatlas_root: Path | None = None) -> LinterCheck:
    return _combine(
        chatlas_anchor_line_drift_check(chatlas_root),
        _chatlas2_line_drift_check(chatlas_root),
    )


def _line_records(state: LinterState, documents, *, chatlas_root: Path | None):
    depot = chatlas2_anchory_depot(chatlas_root)
    for _document, line in parsed_linter_kernel_lines(state, documents):
        records: list[tuple[str, dict[str, Any]]] = []
        for span in line.spans:
            if span.kind != "anchor":
                continue
            anchor = str(span.parsed["anchor"])
            resolution = depot.resolve(anchor)
            if resolution is not None and isinstance(resolution.record, dict):
                record = dict(resolution.record)
                if record.get("app") in {"chatlas", "chatlas2"}:
                    records.append((anchor, record))
        if records:
            yield state.rel_path(line.path) if line.path else ".", line, records


def _gates(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    if record.get("app") == "chatlas":
        return _record_gates(record)
    try:
        return parse_line_anchor_dossier(record)["relationships"]["gates"]
    except CliError:
        return {"semantic_approval": [], TOKENIZED_APPROVAL_GATE: []}


def grounding_line_approval_check(chatlas_root: Path | None = None) -> LinterCheck:
    def run(state: LinterState, documents) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for rel, line, records in _line_records(
            state, documents, chatlas_root=chatlas_root
        ):
            if any(any(_gates(record).values()) for _anchor, record in records):
                continue
            anchors = [anchor for anchor, _record in records]
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=LINE_APPROVAL_MISSING,
                    path=rel,
                    line=line.start_line,
                    message="The line is grounded but has no approval relationship.",
                    details={"anchors": anchors},
                )
            )
        return findings

    return bind_floor_check(
        code=CHECK_LINE_APPROVAL,
        title="Line approval existence (chat grounding)",
        gate=lambda _state: _gate(chatlas_root),
        run=run,
        surface_kinds=frozenset({"chapter", "appendix"}),
        poi_package_id="tarav-chatlas-pkg",
        default_on=False,
    )


def grounding_line_verbatim_gate_check(chatlas_root: Path | None = None) -> LinterCheck:
    old_models: dict[str, dict[str, Any] | None] = {}

    def load_old(identity: str):
        if identity not in old_models:
            old_models[identity] = _load_session_model(
                identity, chatlas_root=chatlas_root
            )
        return old_models[identity]

    def load_new(identity: str):
        return provide_normal_model(identity_hash=identity, chatlas_root=chatlas_root)

    def run(state: LinterState, documents) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for rel, line, records in _line_records(
            state, documents, chatlas_root=chatlas_root
        ):
            gates = [
                (anchor, record, gate)
                for anchor, record in records
                for gate in _gates(record)[TOKENIZED_APPROVAL_GATE]
            ]
            if not gates:
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=LINE_VERBATIM_GATE_UNREVIEWED,
                        path=rel,
                        line=line.start_line,
                        message="The line has no tokenized approval relationship.",
                        details={"anchors": [anchor for anchor, _record in records]},
                    )
                )
                continue
            failures: list[tuple[str, str]] = []
            for anchor, record, gate in gates:
                failure = (
                    _tokenized_cargo_failure(
                        gate, canonical_index_line_body(line.src), load_old
                    )
                    if record.get("app") == "chatlas"
                    else tokenized_gate_failure(gate, line.src, loader=load_new)
                )
                if failure is None:
                    break
                failures.append((anchor, failure))
            else:
                anchor, failure = failures[0]
                code, message = {
                    "role": (
                        LINE_VERBATIM_GATE_ROLE_MISMATCH,
                        f"Anchor ^{anchor} proposal or approval has the wrong message side.",
                    ),
                    "order": (
                        LINE_VERBATIM_GATE_ORDER_MISMATCH,
                        f"Anchor ^{anchor} approval does not follow its proposal.",
                    ),
                    "token": (
                        LINE_VERBATIM_GATE_TOKEN_MISMATCH,
                        f"Anchor ^{anchor} approval does not explicitly approve its token.",
                    ),
                    "proposal": (
                        LINE_VERBATIM_GATE_NO_PROPOSAL,
                        f"Anchor ^{anchor} proposal does not contain the approved line and token.",
                    ),
                }[failure]
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=code,
                        path=rel,
                        line=line.start_line,
                        message=message,
                        details={"anchor": anchor, "failure": failure},
                    )
                )
        return findings

    return bind_floor_check(
        code=CHECK_LINE_VERBATIM_GATE,
        title="Line material-equivalence gate (chat grounding)",
        gate=lambda _state: _gate(chatlas_root),
        run=run,
        surface_kinds=frozenset({"chapter", "appendix"}),
        poi_package_id="tarav-chatlas-pkg",
        default_on=False,
    )


__all__ = [
    "grounding_line_approval_check",
    "grounding_line_drift_check",
    "grounding_line_verbatim_gate_check",
    "grounding_provenance_check",
]
