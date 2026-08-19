# $kw: --from Touch.Authority --note [CT] git-backing is a qualification criterion, not an implementation note
"""`Touch.Authority` — what counts as user touch, and who may write where.

New in this design. The old one hardcoded "a qualifying user `Chat.Message`" as the only authority
surface; here that fact becomes a **declaration** a project registers, so a second surface
type can be added without redefining touch.

Two rules carry the model:

1. **Git-backing is a qualification criterion.** A surface that cannot be git-backed cannot
   carry `Touch.Authority`. Every predicate therefore has one shape — which commits on this
   repo/path qualify. Tarav1's Chatlas archive already satisfies this for chat.

2. **The commit's relation to the edition differs by surface type.** For a journal or vault
   the user authored the commit, so its git author attributes touch. For chat, capture
   commits on the user's behalf, so the attributable unit lives inside the content.

The `homes/` guard is the other half: `homes/<user>/` carries user authority, and an agent
write there is a violation detectable by **path alone**, with no line semantics involved.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path

from .config import Geography, TaravIndexError

MANIFEST_SCHEMA = "tarav.touch-authority-manifest.v1"

HOMES_DIR_NAME = "homes"
AGENT_HOME_NAME = "agent"
DEFAULT_USER_HOME = "ceo"


class ManifestError(TaravIndexError):
    """Raised when a manifest is invalid or not registered."""


class AuthorityGuardError(TaravIndexError):
    """Raised when a write would cross the user-authority boundary."""


class EditionRelation(StrEnum):
    """How a git commit relates to the touched edition it carries."""

    #: The user authored the commit. Git author attributes touch.
    COMMIT_IS_EDITION = "commit_is_edition"
    #: Capture committed on the user's behalf. Git author attributes nothing.
    COMMIT_RECORDS_EDITION = "commit_records_edition"


class Attribution(StrEnum):
    """How the attributable user is derived from a qualifying edition."""

    GIT_AUTHOR = "git_author"
    MESSAGE_ROLE = "message_role"


@dataclass(frozen=True, slots=True)
class TouchAuthorityManifest:
    """One surface type's declaration that it carries `Touch.Authority`."""

    surface_type: str
    git_backed: bool
    edition_relation: EditionRelation
    attribution: Attribution
    predicate: str

    def __post_init__(self) -> None:
        if not self.surface_type or not self.surface_type.replace("-", "").isalnum():
            raise ManifestError(f"invalid surface type: {self.surface_type!r}")
        if not self.git_backed:
            raise ManifestError(
                f"surface type {self.surface_type!r} is not git-backed and therefore "
                "cannot carry Touch.Authority"
            )
        if not self.predicate.strip():
            raise ManifestError(
                f"surface type {self.surface_type!r} declares no qualification predicate"
            )

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["edition_relation"] = str(self.edition_relation)
        payload["attribution"] = str(self.attribution)
        payload["schema"] = MANIFEST_SCHEMA
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> TouchAuthorityManifest:
        try:
            return cls(
                surface_type=str(payload["surface_type"]),
                git_backed=bool(payload["git_backed"]),
                edition_relation=EditionRelation(str(payload["edition_relation"])),
                attribution=Attribution(str(payload["attribution"])),
                predicate=str(payload["predicate"]),
            )
        except (KeyError, ValueError) as exc:
            raise ManifestError(f"malformed manifest payload: {exc}") from exc


#: Chat is the surface capture reads from; journal and vault are declared so their
#: predicates are written down rather than implicit, with nothing reading them yet.
BUILTIN_MANIFESTS: tuple[TouchAuthorityManifest, ...] = (
    TouchAuthorityManifest(
        surface_type="chat",
        git_backed=True,
        edition_relation=EditionRelation.COMMIT_RECORDS_EDITION,
        attribution=Attribution.MESSAGE_ROLE,
        predicate=(
            "a user-side Chat.Message in the git-backed Chatlas archive; "
            "agent turns carry no touch"
        ),
    ),
    TouchAuthorityManifest(
        surface_type="journal",
        git_backed=True,
        edition_relation=EditionRelation.COMMIT_IS_EDITION,
        attribution=Attribution.GIT_AUTHOR,
        predicate="a commit touching a journal path whose git author is the user",
    ),
    TouchAuthorityManifest(
        surface_type="vault",
        git_backed=True,
        edition_relation=EditionRelation.COMMIT_IS_EDITION,
        attribution=Attribution.GIT_AUTHOR,
        predicate=(
            "a commit touching a vault path whose git author is the user; "
            "agent-authored commits in the same vault do not qualify"
        ),
    ),
)


class ManifestRegistry:
    """Project-scoped registry of the surface types enabled here.

    The manifest belongs to the *surface type*, defined once and centrally. The project
    records which types are enabled — otherwise every project could redefine what a user
    turn is.
    """

    def __init__(self, scopes: Geography) -> None:
        self._scopes = scopes

    @property
    def directory(self) -> Path:
        return self._scopes.manifest_dir

    def _path(self, surface_type: str) -> Path:
        return self.directory / f"{surface_type}.json"

    def register(self, manifest: TouchAuthorityManifest) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(manifest.surface_type)
        path.write_text(
            json.dumps(manifest.to_json(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return path

    def get(self, surface_type: str) -> TouchAuthorityManifest:
        path = self._path(surface_type)
        if not path.exists():
            raise ManifestError(
                f"surface type {surface_type!r} is not registered in this project; "
                "it cannot be a source of Touched.Data"
            )
        return TouchAuthorityManifest.from_json(json.loads(path.read_text("utf-8")))

    def is_registered(self, surface_type: str) -> bool:
        return self._path(surface_type).exists()

    def list(self) -> list[TouchAuthorityManifest]:
        if not self.directory.exists():
            return []
        return [
            TouchAuthorityManifest.from_json(json.loads(p.read_text("utf-8")))
            for p in sorted(self.directory.glob("*.json"))
        ]

    def bootstrap(self) -> list[TouchAuthorityManifest]:
        """Register the built-in surface types. Idempotent."""

        for manifest in BUILTIN_MANIFESTS:
            self.register(manifest)
        return list(BUILTIN_MANIFESTS)


def home_owner(path: Path) -> str | None:
    """The home owner governing ``path``, or ``None`` if it is outside any home."""

    parts = path.parts
    for index, part in enumerate(parts):
        if part == HOMES_DIR_NAME and index + 1 < len(parts):
            return parts[index + 1]
    return None


def is_agent_writable(path: Path) -> bool:
    owner = home_owner(path)
    return owner is None or owner == AGENT_HOME_NAME


def assert_agent_writable(path: Path) -> None:
    """Raise unless an agent may write to ``path``."""

    owner = home_owner(path)
    if owner is not None and owner != AGENT_HOME_NAME:
        raise AuthorityGuardError(
            f"refusing agent write into homes/{owner}/: that home carries {owner} "
            f"authority and only {owner} may mutate it ({path})"
        )


__all__ = [
    "AGENT_HOME_NAME",
    "BUILTIN_MANIFESTS",
    "DEFAULT_USER_HOME",
    "HOMES_DIR_NAME",
    "MANIFEST_SCHEMA",
    "Attribution",
    "AuthorityGuardError",
    "EditionRelation",
    "ManifestError",
    "ManifestRegistry",
    "TouchAuthorityManifest",
    "assert_agent_writable",
    "home_owner",
    "is_agent_writable",
]
