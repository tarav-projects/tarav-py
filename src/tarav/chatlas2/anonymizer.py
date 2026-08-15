# $kw: ^chatlas2-text-anonymizer --from Raw.Archive --note [CT] corpus anonymization is deterministic best-effort text transformation with no provider or raw-model knowledge --supp ^c20260815-30u ^c20260815-31u
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
from typing import Callable


ANONYMIZER_VERSION = 1

_EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_MAC_HOME = re.compile(r"/Users/[^/\s\"']+")
_LINUX_HOME = re.compile(r"/home/[^/\s\"']+")
_WINDOWS_HOME = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+", re.IGNORECASE)
_UUID = re.compile(
    r"(?<![0-9a-f])([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-"
    r"([0-9a-f]{4})-([0-9a-f]{12})(?![0-9a-f])",
    re.IGNORECASE,
)
_SECRET = re.compile(
    r"(?i)(\b(?:api[_-]?key|access[_-]?token|authorization|password|secret)"
    r"\b[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)"
)


@dataclass(frozen=True, slots=True)
class AnonymizedText:
    text: str
    replacements: dict[str, int]
    warnings: tuple[str, ...]


def anonymize_text(text: str) -> AnonymizedText:
    replacements: dict[str, int] = {}
    transformed = text
    transformed = _substitute(
        transformed,
        pattern=_SECRET,
        kind="secret",
        replacement=lambda match: match.group(1) + _token("secret", match.group(2)),
        counts=replacements,
    )
    for kind, pattern, prefix in (
        ("mac_home", _MAC_HOME, "/Users/corpus-user-"),
        ("linux_home", _LINUX_HOME, "/home/corpus-user-"),
        ("windows_home", _WINDOWS_HOME, r"C:\\Users\\corpus-user-"),
    ):
        transformed = _substitute(
            transformed,
            pattern=pattern,
            kind=kind,
            replacement=lambda match, kind=kind, prefix=prefix: (
                prefix + _digest(kind, match.group(0))[:10]
            ),
            counts=replacements,
        )
    transformed = _substitute(
        transformed,
        pattern=_EMAIL,
        kind="email",
        replacement=lambda match: (
            f"corpus-email-{_digest('email', match.group(0))[:12]}"
        ),
        counts=replacements,
    )
    transformed = _substitute(
        transformed,
        pattern=_UUID,
        kind="uuid",
        replacement=lambda match: _uuid_token(match.group(0)),
        counts=replacements,
    )
    warnings = tuple(
        name
        for name, pattern in (
            ("email-like text remains", _EMAIL),
            ("macOS home path remains", _MAC_HOME),
            ("Linux home path remains", _LINUX_HOME),
            ("Windows home path remains", _WINDOWS_HOME),
            ("credential-shaped text remains", _SECRET),
        )
        if _has_unreplaced_match(pattern, transformed)
    )
    return AnonymizedText(
        text=transformed,
        replacements=dict(sorted(replacements.items())),
        warnings=warnings,
    )


def _has_unreplaced_match(pattern: re.Pattern[str], text: str) -> bool:
    return any("corpus-" not in match.group(0) for match in pattern.finditer(text))


def _substitute(
    text: str,
    *,
    pattern: re.Pattern[str],
    kind: str,
    replacement: Callable[[re.Match[str]], str],
    counts: dict[str, int],
) -> str:
    def replace(match: re.Match[str]) -> str:
        counts[kind] = counts.get(kind, 0) + 1
        return replacement(match)

    return pattern.sub(replace, text)


def _digest(kind: str, value: str) -> str:
    return sha256(f"{kind}\0{value}".encode("utf-8")).hexdigest()


def _token(kind: str, value: str) -> str:
    return f"corpus-{kind}-{_digest(kind, value)[:16]}"


def _uuid_token(value: str) -> str:
    digest = _digest("uuid", value)
    return (
        f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"
    )


__all__ = ["ANONYMIZER_VERSION", "AnonymizedText", "anonymize_text"]
