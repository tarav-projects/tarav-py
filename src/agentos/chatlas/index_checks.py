# $kw: --from Chat.Touched.Index --from Line.Home --from Index.Linter/Anchor.LineDrift --note [IMPL] Chatlas compares each dossier attachment assertion with the current canonical line triplet --supp ^c20260802-103u
"""Chatlas-powered index-linter checks — the grounding-provenance bridge.

Bridge-shaped per `Dependency.Profile.Split`: this module's dependency profile
(`agentos.index` + `agentos.anchory` + chatlas) is a subset of this package's,
so it lives here and registers into the linter's check socket at the
composition root (`agentos-cli`).
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.index.linter import (
    GateResult,
    LinterCheck,
    LinterFinding,
    LinterState,
    LineSupportStanding,
    bind_floor_check,
    parsed_linter_kernel_lines,
)
from agentos.index.model import (
    IndexDocument,
    canonical_index_line_body,
    index_line_anchor_triplet_hash,
)
from agentos.chatlas.anchory import (
    CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
    ChatlasSupportRuntimeCache,
    USER_TURN_TAG,
    chatlas_anchory_depot,
    parse_line_attachment,
    parse_line_gate_relationships,
    parse_line_anchor_dossier,
    resolve_support_set_record,
)
from agentos.chatlas.index_store import ChatlasSessionIndexCache
from agentos.chatlas.normal_turn import parse_normal_turn_ref, resolve_normal_turn_ref
from agentos.chatlas.normalization.session_model.events import normal_turn_id

CHECK_GROUNDING_PROVENANCE = "Index.Linter/Grounding.Provenance"
ANCHOR_UNRESOLVABLE = "Index.Linter/Anchor.Unresolvable"
ANCHOR_TURN_MISSING = "Index.Linter/Anchor.Turn.Missing"
ANCHOR_CHATLAS_TAG = "Index.Linter/Anchor.Chatlas.Tag"
ANCHOR_PROVENANCE_STALE_MARKER = "Index.Linter/Anchor.Provenance.StaleMarker"
CHECK_ANCHOR_LINE_DRIFT = "Index.Linter/Anchor.LineDrift"
ANCHOR_LINE_DRIFT = "Index.Linter/Anchor.LineDrift"

SEMANTIC_APPROVAL_GATE = "semantic_approval"
TOKENIZED_APPROVAL_GATE = "tokenized_verbatim_approval"


CHECK_LINE_APPROVAL = "Index.Linter/Line.Approval"
LINE_APPROVAL_MISSING = "Index.Linter/Line.Approval.Missing"


CHECK_LINE_VERBATIM_GATE = "Index.Linter/Line.Verbatim.Gate"
LINE_VERBATIM_GATE_UNREVIEWED = "Index.Linter/Line.Verbatim.Gate.Unreviewed"
LINE_VERBATIM_GATE_TOKEN_MISMATCH = "Index.Linter/Line.Verbatim.Gate.TokenMismatch"
LINE_VERBATIM_GATE_NO_PROPOSAL = "Index.Linter/Line.Verbatim.Gate.NoProposal"
LINE_VERBATIM_GATE_MEMBER_MISMATCH = (
    "Index.Linter/Line.Verbatim.Gate.ApprovalMemberMismatch"
)
LINE_VERBATIM_GATE_ROLE_MISMATCH = "Index.Linter/Line.Verbatim.Gate.RoleMismatch"
LINE_VERBATIM_GATE_ORDER_MISMATCH = "Index.Linter/Line.Verbatim.Gate.OrderMismatch"


@dataclass(frozen=True)
class _AnchorProvenance:
    status: str
    message: str | None = None
    details: dict[str, Any] | None = None
    resolved: bool = False


def chatlas_grounding_provenance_check(
    chatlas_root: Path | None = None,
) -> LinterCheck:
    def _gate(state: LinterState) -> GateResult:
        depot = chatlas_anchory_depot(chatlas_root)
        if not depot.root.is_dir():
            return GateResult(
                allowed=False,
                reason=f"chatlas anchory depot unavailable: {depot.root}",
            )
        return GateResult(allowed=True)

    def _run(
        state: LinterState,
        documents: tuple[IndexDocument, ...],
    ) -> list[LinterFinding]:
        return _check_grounding_provenance(
            state,
            documents,
            chatlas_root=chatlas_root,
        )

    return bind_floor_check(
        code=CHECK_GROUNDING_PROVENANCE,
        title="Grounding provenance (chatlas)",
        gate=_gate,
        run=_run,
        surface_kinds=frozenset({"chapter", "appendix", "agendix", "issues"}),
        poi_package_id="agentos-chatlas-pkg",
        structural=True,
    )


def chatlas_support_reference_resolver(
    chatlas_root: Path | None = None,
):
    """Return a cached resolver for the current Chatlas support realization."""
    depot = None
    model_cache: dict[str, dict[str, Any] | None] = {}
    resolution_cache: dict[str, bool] = {}
    index_cache = ChatlasSessionIndexCache()
    support_cache = ChatlasSupportRuntimeCache()

    def load_model(identity_hash: str) -> dict[str, Any]:
        if identity_hash not in model_cache:
            model_cache[identity_hash] = _load_session_model(
                identity_hash,
                chatlas_root=chatlas_root,
                index_cache=index_cache,
            )
        model = model_cache[identity_hash]
        if model is None:
            raise CliError(f"session is unavailable: {identity_hash}")
        return model

    def resolves(anchor: str) -> bool:
        nonlocal depot
        if anchor in resolution_cache:
            return resolution_cache[anchor]
        if depot is None:
            depot = chatlas_anchory_depot(chatlas_root)
        resolution = depot.resolve(anchor)
        record = resolution.record if resolution is not None else None
        grounded = False
        if (
            isinstance(record, dict)
            and record.get("app") == "chatlas"
            and anchor.endswith(USER_TURN_TAG)
        ):
            try:
                grounded = bool(
                    resolve_support_set_record(
                        record,
                        model_loader=load_model,
                        runtime_cache=support_cache,
                    )
                )
            except CliError:
                grounded = False
        resolution_cache[anchor] = grounded
        return grounded

    return resolves


def chatlas_anchor_line_drift_check(
    chatlas_root: Path | None = None,
) -> LinterCheck:
    def _gate(_state: LinterState) -> GateResult:
        depot = chatlas_anchory_depot(chatlas_root)
        if not depot.root.is_dir():
            return GateResult(
                allowed=False,
                reason=f"chatlas anchory depot unavailable: {depot.root}",
            )
        return GateResult(allowed=True)

    def _run(
        state: LinterState,
        documents: tuple[IndexDocument, ...],
    ) -> list[LinterFinding]:
        depot = chatlas_anchory_depot(chatlas_root)
        records: dict[str, dict[str, Any] | None] = {}
        findings: list[LinterFinding] = []
        for _document, line in parsed_linter_kernel_lines(state, documents):
            for span in line.spans:
                if span.kind != "anchor":
                    continue
                anchor = str(span.parsed["anchor"])
                current_hash = index_line_anchor_triplet_hash(line.src, anchor)
                if anchor not in records:
                    resolution = depot.resolve(anchor)
                    record = resolution.record if resolution is not None else None
                    records[anchor] = (
                        record
                        if isinstance(record, dict) and record.get("app") == "chatlas"
                        else None
                    )
                record = records[anchor]
                if record is None:
                    continue
                try:
                    attachment = parse_line_attachment(record)
                except CliError:
                    attachment = None
                if attachment is not None and attachment["triplet_hash"] == current_hash:
                    continue
                rel = state.rel_path(line.path) if line.path else "."
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=ANCHOR_LINE_DRIFT,
                        path=rel,
                        line=line.start_line,
                        message=(
                            f"Anchor ^{anchor} does not assert the current Index line triplet."
                        ),
                        details={
                            "anchor": anchor,
                            "stored_triplet_hash": None if attachment is None else attachment["triplet_hash"],
                            "current_triplet_hash": current_hash,
                        },
                    )
                )
        return findings

    return bind_floor_check(
        code=CHECK_ANCHOR_LINE_DRIFT,
        title="Anchor binding matches current Index line content (chatlas)",
        gate=_gate,
        run=_run,
        surface_kinds=frozenset({"chapter", "appendix", "agendix", "issues"}),
        poi_package_id="agentos-pkg",
    )


def _check_grounding_provenance(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
    *,
    chatlas_root: Path | None,
) -> list[LinterFinding]:
    depot = chatlas_anchory_depot(chatlas_root)
    findings: list[LinterFinding] = []
    model_cache: dict[str, dict[str, Any] | None] = {}
    provenance_cache: dict[str, _AnchorProvenance] = {}
    index_cache = ChatlasSessionIndexCache()
    support_cache = ChatlasSupportRuntimeCache()

    def load_model(identity_hash: str) -> dict[str, Any]:
        if identity_hash not in model_cache:
            model_cache[identity_hash] = _load_session_model(
                identity_hash,
                chatlas_root=chatlas_root,
                index_cache=index_cache,
            )
        model = model_cache[identity_hash]
        if model is None:
            raise CliError(f"session is unavailable: {identity_hash}")
        return model

    for _document, line in parsed_linter_kernel_lines(state, documents):
        rel = state.rel_path(line.path) if line.path else "."
        anchors = tuple(
            str(span.parsed["anchor"]) for span in line.spans if span.kind == "anchor"
        )
        resolved_anchors: list[str] = []
        for anchor in anchors:
            provenance = provenance_cache.get(anchor)
            if provenance is None:
                provenance = _resolve_anchor_provenance(
                    anchor,
                    depot=depot,
                    load_model=load_model,
                    support_cache=support_cache,
                )
                provenance_cache[anchor] = provenance
            if provenance.status == "unresolvable":
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=ANCHOR_UNRESOLVABLE,
                        path=rel,
                        line=line.start_line,
                        message=provenance.message or "",
                        details=provenance.details or {},
                    )
                )
                continue
            if provenance.status == "skip":
                continue
            if provenance.status == "tag":
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=ANCHOR_CHATLAS_TAG,
                        path=rel,
                        line=line.start_line,
                        message=provenance.message or "",
                        details=provenance.details or {},
                    )
                )
                continue
            if provenance.status == "invalid":
                findings.append(
                    LinterFinding(
                        severity="error",
                        code=ANCHOR_TURN_MISSING,
                        path=rel,
                        line=line.start_line,
                        message=provenance.message or "",
                        details=provenance.details or {},
                    )
                )
                continue
            if provenance.resolved:
                resolved_anchors.append(anchor)
            as_marked = line.parsed.get("source") == "AS"
            if provenance.resolved and as_marked:
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=ANCHOR_PROVENANCE_STALE_MARKER,
                        path=rel,
                        line=line.start_line,
                        message=(
                            f"Anchor ^{anchor} lands on a user turn but the line is AS:-marked "
                            "— stale source-axis marker."
                        ),
                        details={"anchor": anchor},
                    )
                )
        state.record_line_support_standing(
            line,
            LineSupportStanding(
                anchors=anchors,
                resolved_anchors=tuple(resolved_anchors),
            ),
        )
    return findings


def _resolve_anchor_provenance(
    anchor: str,
    *,
    depot,
    load_model,
    support_cache: ChatlasSupportRuntimeCache,
) -> _AnchorProvenance:
    resolution = depot.resolve(anchor)
    record = resolution.record if resolution is not None else None
    if record is None:
        return _AnchorProvenance(
            status="unresolvable",
            message=f"Anchor does not resolve in the chatlas anchory depot: ^{anchor}.",
            details={"anchor": anchor},
        )
    if record.get("app") != "chatlas":
        return _AnchorProvenance(status="skip")
    if record.get("schema") != CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA:
        return _AnchorProvenance(
            status="invalid",
            message=(
                f"Anchor ^{anchor} is cited by an Index line but does not resolve "
                "to a Chatlas.Line.Anchor.Dossier."
            ),
            details={"anchor": anchor, "schema": record.get("schema")},
        )
    actual_tag = anchor[-1] if anchor[-1].isalpha() else None
    if actual_tag != USER_TURN_TAG:
        return _AnchorProvenance(
            status="tag",
            message=(
                f"Chatlas anchor ^{anchor} must carry the "
                f"{USER_TURN_TAG!r} user-evidence tag."
            ),
            details={
                "anchor": anchor,
                "expected_tag": USER_TURN_TAG,
                "actual_tag": actual_tag,
            },
        )
    try:
        resolved = resolve_support_set_record(
            record,
            model_loader=load_model,
            runtime_cache=support_cache,
        )
    except CliError as exc:
        return _AnchorProvenance(
            status="invalid",
            message=f"Anchor ^{anchor} has an invalid support set: {exc}.",
            details={"anchor": anchor, "error": str(exc)},
        )
    return _AnchorProvenance(status="valid", resolved=bool(resolved))


def _line_anchor_records(
    state: LinterState,
    documents: tuple[IndexDocument, ...],
    *,
    chatlas_root: Path | None,
):
    """Yield each kernel line with all of its resolvable Chatlas records.

    Approval and review are line-local. A line with several support references
    passes when one of them establishes the protocol; grounding-only references
    must not independently create duplicate review debt.
    """
    depot = chatlas_anchory_depot(chatlas_root)
    for _document, line in parsed_linter_kernel_lines(state, documents):
        rel = state.rel_path(line.path) if line.path else "."
        records: list[tuple[str, dict[str, Any]]] = []
        for span in line.spans:
            if span.kind != "anchor":
                continue
            anchor = str(span.parsed["anchor"])
            resolution = depot.resolve(anchor)
            record = resolution.record if resolution is not None else None
            if not isinstance(record, dict) or record.get("app") != "chatlas":
                continue
            records.append((anchor, record))
        if records:
            yield rel, line, records


def _record_members(record: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        dossier = parse_line_anchor_dossier(record)
    except CliError:
        return []
    return list(dossier["relationships"]["support"]["members"])


def _record_gates(record: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    try:
        return parse_line_gate_relationships(record)
    except CliError:
        return {SEMANTIC_APPROVAL_GATE: [], TOKENIZED_APPROVAL_GATE: []}


def chatlas_review_reference_resolver(chatlas_root: Path | None = None):
    """Resolve a line reference only when its tokenized approval verifies."""
    depot = chatlas_anchory_depot(chatlas_root)
    model_cache: dict[str, dict[str, Any] | None] = {}
    result_cache: dict[tuple[str, str], bool] = {}

    def load_model(identity_hash: str) -> dict[str, Any] | None:
        if identity_hash not in model_cache:
            model_cache[identity_hash] = _load_session_model(
                identity_hash, chatlas_root=chatlas_root
            )
        return model_cache[identity_hash]

    def resolves(anchor: str, line_text: str) -> bool:
        canonical_line = canonical_index_line_body(line_text)
        key = (anchor, canonical_line)
        if key in result_cache:
            return result_cache[key]
        resolution = depot.resolve(anchor)
        record = resolution.record if resolution is not None else None
        reviewed = False
        if isinstance(record, dict) and record.get("app") == "chatlas":
            for cargo in _record_gates(record)[TOKENIZED_APPROVAL_GATE]:
                if _tokenized_cargo_failure(cargo, canonical_line, load_model) is None:
                    reviewed = True
                    break
        result_cache[key] = reviewed
        return reviewed

    return resolves


def chatlas_line_approval_check(chatlas_root: Path | None = None) -> LinterCheck:
    """Check A — each referenced index line has at least one approval turn.

    Realizes the `Index.Line` approval invariant (Impl.Req 598): explicit
    relationships under `relationships.gates` declare semantic or tokenized
    approval. Support members and gates are independent, so an anchor with no
    gate relationship is grounding-only and surfaces as review-debt.
    """

    def _gate(state: LinterState) -> GateResult:
        depot = chatlas_anchory_depot(chatlas_root)
        if not depot.root.is_dir():
            return GateResult(
                allowed=False, reason=f"chatlas anchory depot unavailable: {depot.root}"
            )
        return GateResult(allowed=True)

    def _run(
        state: LinterState,
        documents: tuple[IndexDocument, ...],
    ) -> list[LinterFinding]:
        findings: list[LinterFinding] = []
        for rel, line, records in _line_anchor_records(
            state, documents, chatlas_root=chatlas_root
        ):
            if any(
                _record_gates(record)[SEMANTIC_APPROVAL_GATE]
                or _record_gates(record)[TOKENIZED_APPROVAL_GATE]
                for _anchor, record in records
            ):
                continue
            anchors = [anchor for anchor, _record in records]
            findings.append(
                LinterFinding(
                    severity="warning",
                    code=LINE_APPROVAL_MISSING,
                    path=rel,
                    line=line.start_line,
                    message=(
                        "The line's support references hold no approval turn — "
                        "the line is grounded but not approved (review-debt)."
                    ),
                    details={"anchors": anchors},
                )
            )
        return findings

    return bind_floor_check(
        code=CHECK_LINE_APPROVAL,
        title="Line approval existence (chatlas)",
        gate=_gate,
        run=_run,
        surface_kinds=frozenset({"chapter", "appendix"}),
        poi_package_id="agentos-chatlas-pkg",
        default_on=False,
    )


def chatlas_line_verbatim_gate_check(chatlas_root: Path | None = None) -> LinterCheck:
    """Check B — tokenized material-equivalence gate.

    Hidden by default (`default_on=False`): among reviewed anchors it prefers a
    machine-verifiable `tokenized_verbatim_approval` relationship. A line with no
    tokenized gate is review-debt (warning); a gate whose token/presentation chain
    does not verify is an error. Any one verifying tokenized member satisfies the
    gate (flexible multiturn).
    """

    def _gate(state: LinterState) -> GateResult:
        depot = chatlas_anchory_depot(chatlas_root)
        if not depot.root.is_dir():
            return GateResult(
                allowed=False, reason=f"chatlas anchory depot unavailable: {depot.root}"
            )
        return GateResult(allowed=True)

    def _run(
        state: LinterState,
        documents: tuple[IndexDocument, ...],
    ) -> list[LinterFinding]:
        model_cache: dict[str, dict[str, Any] | None] = {}

        def load_model(identity_hash: str) -> dict[str, Any] | None:
            if identity_hash not in model_cache:
                model_cache[identity_hash] = _load_session_model(
                    identity_hash, chatlas_root=chatlas_root
                )
            return model_cache[identity_hash]

        findings: list[LinterFinding] = []
        for rel, line, records in _line_anchor_records(
            state, documents, chatlas_root=chatlas_root
        ):
            tokenized = [
                (anchor, cargo)
                for anchor, record in records
                for cargo in _record_gates(record)[TOKENIZED_APPROVAL_GATE]
            ]
            if not tokenized:
                anchors = [anchor for anchor, _record in records]
                findings.append(
                    LinterFinding(
                        severity="warning",
                        code=LINE_VERBATIM_GATE_UNREVIEWED,
                        path=rel,
                        line=line.start_line,
                        message=(
                            "The line has no tokenized approval turn — prefer "
                            "re-approving with a copy-pasteable token (review-debt)."
                        ),
                        details={"anchors": anchors},
                    )
                )
                continue
            line_text = canonical_index_line_body(line.src)
            if any(
                _tokenized_cargo_failure(cargo, line_text, load_model) is None
                for _anchor, cargo in tokenized
            ):
                continue

            findings.append(
                _tokenized_failure(rel, line, tokenized, line_text, load_model)
            )
        return findings

    return bind_floor_check(
        code=CHECK_LINE_VERBATIM_GATE,
        title="Line material-equivalence gate — tokenized approval (chatlas)",
        gate=_gate,
        run=_run,
        surface_kinds=frozenset({"chapter", "appendix"}),
        poi_package_id="agentos-chatlas-pkg",
        default_on=False,
    )


def _canonical_review_content(text: str) -> str:
    """Canonical content used only for the review-attention certificate.

    Formatting differences should not spend another user-attention checkpoint.
    Compatibility normalization, case folding, and whitespace removal are
    deterministic; every remaining character stays significant.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(char for char in normalized if not char.isspace())


def _event_text(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list):
        return None
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and isinstance(block.get("text"), str)
    )


def _turn_message_events(
    model: dict[str, Any] | None,
    turn_id: str,
    *,
    role: str,
) -> list[tuple[int, dict[str, Any]]]:
    if not isinstance(model, dict):
        return []
    chat = model.get("chat")
    events = chat.get("events") if isinstance(chat, dict) else None
    if not isinstance(events, list):
        return []
    return [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict)
        and normal_turn_id(event) == turn_id
        and event.get("kind") == "message"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("role") == role
    ]


def _turn_message_text(
    model: dict[str, Any] | None,
    turn_id: str,
    *,
    role: str,
) -> str | None:
    """Join messages with the required role from one `Normal.Turn`.

    A turn spans several events, so a proposal's text may be split across more
    than one message; the gate still verifies the turn's protocol role.
    """
    texts = [
        text
        for _index, event in _turn_message_events(model, turn_id, role=role)
        for text in (_event_text(event),)
        if text
    ]
    return "\n".join(texts) if texts else None


def _explicitly_approves_token(text: str, token: str) -> bool:
    return (
        re.search(
            rf"(?m)^\s*::approve\s+{re.escape(token)}\s*$",
            text,
        )
        is not None
    )


def _tokenized_cargo_failure(
    cargo: dict[str, Any],
    line_text: str,
    load_model,
) -> str | None:
    token = cargo.get("token")
    verbatim_ref = cargo.get("proposal_turn")
    approval_ref = cargo.get("approval_turn")
    if (
        not isinstance(token, str)
        or not isinstance(verbatim_ref, dict)
        or not isinstance(approval_ref, dict)
    ):
        return "token"
    try:
        proposal = parse_normal_turn_ref(verbatim_ref, field="proposal_turn")
        approval = parse_normal_turn_ref(approval_ref, field="approval_turn")
    except CliError:
        return "role"
    proposal_session = proposal["session"]
    proposal_turn = proposal["turn_id"]
    approval_session = approval["session"]
    approval_turn = approval["turn_id"]
    if proposal_session != approval_session:
        return "order"
    model = load_model(proposal_session)
    if model is None:
        return "role"
    try:
        resolve_normal_turn_ref(proposal, model, field="proposal_turn")
        resolve_normal_turn_ref(approval, model, field="approval_turn")
    except CliError:
        return "role"
    verbatim_text = _turn_message_text(model, proposal_turn, role="assistant")
    approval_text = _turn_message_text(model, approval_turn, role="user")
    if approval_text is None or verbatim_text is None:
        return "role"
    if not _explicitly_approves_token(approval_text, token):
        return "token"
    if token not in verbatim_text:
        return "proposal"
    proposal_events = _turn_message_events(model, proposal_turn, role="assistant")
    approval_events = _turn_message_events(model, approval_turn, role="user")
    if not proposal_events or not approval_events:
        return "role"
    if min(index for index, _event in proposal_events) >= min(
        index for index, _event in approval_events
    ):
        return "order"
    if _canonical_review_content(line_text) not in _canonical_review_content(
        verbatim_text
    ):
        return "proposal"
    return None


def _tokenized_failure(rel, line, tokenized, line_text, load_model) -> LinterFinding:
    failures: list[tuple[str, str]] = []
    for anchor, cargo in tokenized:
        failure = _tokenized_cargo_failure(cargo, line_text, load_model)
        if failure is not None:
            failures.append((anchor, failure))
    anchor, failure = failures[0] if failures else (tokenized[0][0], "proposal")
    code, message = {
        "role": (
            LINE_VERBATIM_GATE_ROLE_MISMATCH,
            f"Anchor ^{anchor} proposal and approval references do not resolve to assistant and user messages.",
        ),
        "order": (
            LINE_VERBATIM_GATE_ORDER_MISMATCH,
            f"Anchor ^{anchor} approval does not follow its proposal in one chat.",
        ),
        "token": (
            LINE_VERBATIM_GATE_TOKEN_MISMATCH,
            f"Anchor ^{anchor} approval turn does not explicitly `::approve` its token.",
        ),
        "proposal": (
            LINE_VERBATIM_GATE_NO_PROPOSAL,
            f"Anchor ^{anchor} has no assistant proposal containing its token and materially equivalent line content.",
        ),
    }[failure]
    return LinterFinding(
        severity="error",
        code=code,
        path=rel,
        line=line.start_line,
        message=message,
        details={"anchor": anchor, "failure": failure},
    )


def _load_session_model(
    identity_hash: str,
    *,
    chatlas_root: Path | None,
    index_cache: ChatlasSessionIndexCache | None = None,
) -> dict[str, Any] | None:
    from agentos.chatlas.index_query import (
        select_materialization_row,
        select_one_chatlas_index_row,
    )
    from agentos.chatlas.views import load_chatlas_session_model

    try:
        session = select_one_chatlas_index_row(
            command="chatlas grounding provenance",
            identity_hash=identity_hash,
            chatlas_root=chatlas_root,
            index_cache=index_cache,
        )
        session = select_materialization_row(session)
        return load_chatlas_session_model(session, chatlas_root=chatlas_root)
    except Exception:
        return None


__all__ = [
    "chatlas_grounding_provenance_check",
    "chatlas_support_reference_resolver",
    "CHECK_GROUNDING_PROVENANCE",
    "chatlas_line_approval_check",
    "CHECK_LINE_APPROVAL",
    "chatlas_line_verbatim_gate_check",
    "CHECK_LINE_VERBATIM_GATE",
]
