# $kw: --from Typed.Agent.State --note [DF] a Gate is a token round-trip through a qualifying User.Turn, checkable against an immutable chat
"""`Gate` — the only way an assertion about a line becomes state.

The system will not carry a value that is merely agent-based. Where something must be
asserted *about* a line — that the user reviewed it, that the user approved landing it, that
a POI was accepted — the assertion is not a field anyone can set. It is a **token round
trip**, and it looks the same every time:

```text
the record names a gate            archive, session, token, user turn, agent turn
the user turn carries the token    and qualifies as touch under the manifest
the agent turn carries the token   and contains the line verbatim
```

Nothing here trusts a summary. The user turn is the authority; the agent turn is what the
user was looking at when they wrote it. Both are in an immutable, git-backed archive, so a
fabricated gate is detectable rather than merely improbable.

Verification is three-valued on purpose. The archive is user-scoped, so *absent* is the
normal case on any other machine and must not read as *failed*.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .chatlas import ChatError, load_session
from .config import Geography


class GateVerdict(StrEnum):
    #: Both turns carry the token and the agent turn carries the line.
    VERIFIED = "verified"
    #: The archive was readable and says otherwise. A defect.
    CONTRADICTED = "contradicted"
    #: The archive is not on this machine. Not a defect.
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True, slots=True)
class GateRef:
    """One user gate: the turns and the token that prove it happened.

    The same shape carries every gate in the system, because they are the same mechanism
    asking different questions — did you read this, do you approve landing it, do you accept
    this finding.
    """

    archive: str
    session_id: str
    token: str
    user_turn_id: str
    agent_turn_id: str

    def to_json(self) -> dict[str, object]:
        return {
            "archive": self.archive,
            "session_id": self.session_id,
            "token": self.token,
            "user_turn_id": self.user_turn_id,
            "agent_turn_id": self.agent_turn_id,
        }

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> GateRef:
        return cls(
            archive=str(payload["archive"]),
            session_id=str(payload["session_id"]),
            token=str(payload["token"]),
            user_turn_id=str(payload["user_turn_id"]),
            agent_turn_id=str(payload["agent_turn_id"]),
        )


@dataclass(frozen=True, slots=True)
class GateCheck:
    verdict: GateVerdict
    detail: str

    @property
    def failed(self) -> bool:
        return self.verdict is GateVerdict.CONTRADICTED


def verify_gate(geo: Geography, gate: GateRef, verbatim: str | None = None) -> GateCheck:
    """Check one gate against the archive.

    ``verbatim`` is the text the agent turn must contain — the line the user was approving.
    Omit it for a gate whose subject is not a line, such as an accepted POI.
    """

    try:
        session = load_session(geo, gate.session_id)
    except ChatError as exc:
        return GateCheck(GateVerdict.UNVERIFIABLE, f"archive unavailable: {exc}")

    turns = {m.address: m for m in session.messages}

    user_turn = turns.get(gate.user_turn_id)
    if user_turn is None:
        return GateCheck(
            GateVerdict.CONTRADICTED,
            f"user turn {gate.user_turn_id[:16]}… is not in the session",
        )
    if not user_turn.carries_touch:
        return GateCheck(
            GateVerdict.CONTRADICTED,
            "the turn named as the gate does not qualify as User.Touch",
        )
    if gate.token not in user_turn.text:
        return GateCheck(
            GateVerdict.CONTRADICTED, "the user turn does not carry the gate token"
        )

    agent_turn = turns.get(gate.agent_turn_id)
    if agent_turn is None:
        return GateCheck(
            GateVerdict.CONTRADICTED,
            f"agent turn {gate.agent_turn_id[:16]}… is not in the session",
        )
    if gate.token not in agent_turn.text:
        return GateCheck(
            GateVerdict.CONTRADICTED, "the agent turn does not carry the gate token"
        )
    if verbatim is not None and verbatim not in agent_turn.text:
        return GateCheck(
            GateVerdict.CONTRADICTED,
            "the gated line does not appear verbatim in its agent turn",
        )

    return GateCheck(GateVerdict.VERIFIED, "token round-trip holds")


__all__ = ["GateCheck", "GateRef", "GateVerdict", "verify_gate"]
