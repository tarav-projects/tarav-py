# $kw: --from Index.Line.Anchor --note [DC] a citation and a locator name share the caret sigil and are different address kinds; one grammar for both would conflate them
"""The `^` address grammars, in one place.

Two of them, not one. A **citation** — `^c20260820-0u` — points at an index record. A
**locator name** — `^package-driver-router` — names a region of a surface. They share the
caret and nothing else, and the corpus holds 2,776 of the first against 93 of the second, so
a single permissive pattern would let a locator name be handed to a record lookup and a
citation be read as a region name.

This module lives in the kernel for the same reason `identity.py` does: it is the only zone
every consumer of the grammar may import. `index`, `chatlas`, `poi` and `skillware` already
depend on `index_model` and gain no new edge by using it.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


#: `^<sigil><YYYYMMDD>-<seq><tag>`. Sigil and tag are optional here because the grammar has
#: to *read* what the corpus holds, including the untagged keys Anchory allocated before the
#: tag convention. Requiring them is a property of a well-formed label, not of parsing one --
#: see `Citation.is_complete`, which is what minting checks.
#: The body alone, caretless, so consumers that must *require* the caret can compose it and
#: consumers that store keys without one can use it directly. One string, two spellings.
CITATION_BODY = r"(?P<sigil>[a-z])?(?P<date>\d{8})-(?P<seq>\d+)(?P<tag>[a-z])?"

CITATION_RE = re.compile(rf"\^?{CITATION_BODY}")

#: Caret required. `^c20260820-0u` in running text is a citation; the bare `c20260820-0u` is
#: a stored key, and a scanner that accepted it would strip ordinary words that happen to
#: look like one.
CITATION_TOKEN_RE = re.compile(rf"\^{CITATION_BODY}")

#: `^kebab-name`. Deliberately excludes anything the citation grammar accepts, so the two
#: kinds partition rather than overlap -- `classify` can then return one answer.
LOCATOR_RE = re.compile(r"\^?[A-Za-z0-9][A-Za-z0-9_-]*")

CITATION = "citation"
LOCATOR = "locator"


@dataclass(frozen=True, slots=True)
class Citation:
    """One parsed citation, by its parts."""

    sigil: str | None
    date: str
    seq: int
    tag: str | None

    @property
    def is_complete(self) -> bool:
        """Whether it carries both the namespace sigil and the producer tag.

        An incomplete citation still resolves -- Anchory keys shard by their untagged base --
        but nothing new should mint one.
        """

        return self.sigil is not None and self.tag is not None

    def render(self) -> str:
        return f"^{self.sigil or ''}{self.date}-{self.seq}{self.tag or ''}"


def parse_citation(token: str) -> Citation | None:
    """The citation this token is, or `None` if it is not one."""

    if not isinstance(token, str):
        return None
    match = CITATION_RE.fullmatch(token.strip())
    if match is None:
        return None
    return Citation(
        sigil=match.group("sigil"),
        date=match.group("date"),
        seq=int(match.group("seq")),
        tag=match.group("tag"),
    )


def is_citation(token: str) -> bool:
    return parse_citation(token) is not None


def is_locator(token: str) -> bool:
    """A caret address that is not a citation.

    Checked in that order on purpose: the locator pattern would otherwise also match
    `^c20260820-0u`, and a token that is both is a token whose kind nobody can state.
    """

    if not isinstance(token, str) or is_citation(token):
        return False
    return LOCATOR_RE.fullmatch(token.strip()) is not None


def classify(token: str) -> str | None:
    """`CITATION`, `LOCATOR`, or `None` for a token that is neither."""

    if is_citation(token):
        return CITATION
    return LOCATOR if is_locator(token) else None


def find_citations(text: str) -> list[str]:
    """Every citation appearing in a line, in order, carets included."""

    return [
        match.group(0)
        for match in re.finditer(rf"{CITATION_TOKEN_RE.pattern}\b", text)
    ]


def split_trailing_address(text: str) -> tuple[str, str | None]:
    """Split a trailing `^address` of either kind off the end of a line.

    Returns the text without it and the address, or the text unchanged and `None`. Both
    kinds, because the callers -- a POI renderer stripping one for display and the skw parser
    lifting one into an annotation -- are handed real lines that carry either.
    """

    stripped = text.rstrip()
    index = stripped.rfind("^")
    if index <= 0 or not stripped[index - 1].isspace():
        return text, None
    candidate = stripped[index:]
    if classify(candidate) is None:
        return text, None
    return stripped[:index].rstrip(), candidate


def strip_trailing_addresses(text: str) -> str:
    """Drop every trailing `^address` from a line.

    A line may end in several -- an index line carries its citation, and a chat turn quoting
    one may carry more -- so this repeats until the tail is clean rather than assuming one.
    """

    current = text
    while True:
        stripped, address = split_trailing_address(current)
        if address is None:
            return current
        current = stripped


__all__ = [
    "CITATION",
    "CITATION_BODY",
    "CITATION_RE",
    "CITATION_TOKEN_RE",
    "Citation",
    "LOCATOR",
    "LOCATOR_RE",
    "classify",
    "find_citations",
    "is_citation",
    "is_locator",
    "parse_citation",
    "split_trailing_address",
    "strip_trailing_addresses",
]
