# $kw: --from Capture --note [CT] chat normalization is unchanged by the new model, so the existing Chatlas2 supplies it
"""Chat evidence — a thin layer over `tarav.chatlas2`.

Almost nothing here is new. Normalization, provider drift handling, the git-backed archive,
and stable message addressing already exist in `tarav.chatlas2` and the new model does not touch any
of them, so they are **used**, not reimplemented:

- `tarav chatlas` is already the git-backed archive, which is what the chat manifest's
  git-backing criterion requires;
- `tarav.chatlas2.build_normal_model` normalizes a session across both providers;
- each normalized message already carries a `message_address` — a stable coordinate derived
  from event identity rather than from position, so it survives a machine change *and*
  further appends to a live session.

The one genuinely new thing is **qualification**: reading a message's touch standing through
the registered `Touch.Authority.Manifest` rather than assuming it. That is the layer below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tarav.chatlas2.messages import chat_message_at, list_chat_messages
from tarav.chatlas2.pipeline import build_normal_model

from .authority import ManifestRegistry
from .config import Geography, TaravIndexError

ARCHIVE_NAME = "chat"


class ChatError(TaravIndexError):
    """Raised when chat evidence cannot be resolved."""


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One provider-neutral message with its qualification verdict.

    ``carries_touch`` is the manifest predicate's verdict, not a role rename: an agent turn
    never carries touch, so a fully agentic chat contains no `User.Touch` at all.
    """

    session_id: str
    address: str
    side: str
    text: str
    at: str | None
    carries_touch: bool

    @property
    def message_id(self) -> str:
        """Stable coordinate. Derived by Chatlas from event identity, not from position."""

        return self.address


@dataclass(frozen=True, slots=True)
class ChatSession:
    session_id: str
    messages: tuple[ChatMessage, ...]

    def touched(self) -> tuple[ChatMessage, ...]:
        """Only the messages qualifying as `Touch.Authority.Surface` editions."""

        return tuple(m for m in self.messages if m.carries_touch)

    def message(self, address: str) -> ChatMessage | None:
        return next((m for m in self.messages if m.address == address), None)


def _text_of(message: dict[str, Any]) -> str:
    text = message.get("text")
    return text if isinstance(text, str) else ""


def load_session(scopes: Geography, session_id: str) -> ChatSession:
    """Normalize one session and apply the chat manifest's qualification predicate."""

    registry = ManifestRegistry(scopes)
    if not registry.is_registered(ARCHIVE_NAME):
        raise ChatError(
            "surface type 'chat' is not registered in this project; "
            "run `tarav index init` before reading chat evidence"
        )
    manifest = registry.get(ARCHIVE_NAME)

    # A `SupportRef` may name a session either way: the provider's session id, or the
    # provider-neutral identity hash. The identity hash is the better coordinate to store
    # -- it survives a provider changing how it names sessions -- so both resolve here
    # rather than forcing the record to know which kind it holds.
    model = None
    errors: list[str] = []
    for selector in ("session_id", "identity_hash"):
        try:
            model = build_normal_model(**{selector: session_id})
            break
        except Exception as exc:  # chatlas2 raises CliError subclasses we do not re-export
            errors.append(f"{selector}: {exc}")
    if model is None:
        raise ChatError(
            f"cannot normalize session {session_id!r}: " + "; ".join(errors)
        )

    messages: list[ChatMessage] = []
    for raw in list_chat_messages(model):
        side = str(raw.get("side") or "")
        # The predicate for a Commit.Records.Edition surface: attribution comes from the
        # role inside the committed content, never from the commit author.
        carries_touch = (
            side == "user" and manifest.attribution.value == "message_role"
        )
        messages.append(
            ChatMessage(
                session_id=session_id,
                address=str(raw.get("message_address") or ""),
                side=side,
                text=_text_of(raw),
                at=chat_message_at(model, raw),
                carries_touch=carries_touch,
            )
        )

    return ChatSession(session_id=session_id, messages=tuple(messages))


def resolve_message(scopes: Geography, session_id: str, address: str) -> ChatMessage | None:
    return load_session(scopes, session_id).message(address)


__all__ = [
    "ARCHIVE_NAME",
    "ChatError",
    "ChatMessage",
    "ChatSession",
    "load_session",
    "resolve_message",
]
