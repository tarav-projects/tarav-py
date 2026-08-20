# $kw: --from Index.Line.Anchor --note [DF] the caret address grammars, asserted against tokens taken from the live corpus
"""The two caret address grammars.

Tokens here are real: every locator name below appears in the maintained surfaces, and the
citations are shapes the Anchory corpus actually holds — including the untagged and
unprefixed keys allocated before the tag convention existed.
"""

from __future__ import annotations

import pytest

from tarav.index_model.label import (
    CITATION,
    LOCATOR,
    classify,
    find_citations,
    is_citation,
    is_locator,
    parse_citation,
    split_trailing_address,
    strip_trailing_addresses,
)


#: Real tokens, with the kind each must classify as. A token classifying as both, or as
#: neither, is the failure this table exists to catch: the two kinds share one sigil, and
#: the whole point of one module owning both is that a caller gets one answer.
TOKENS: tuple[tuple[str, str | None], ...] = (
    ("^c20260820-0u", CITATION),
    ("^c20260510-1u", CITATION),
    ("^d20260101-9a", CITATION),
    ("c20260820-0u", CITATION),
    ("^c20260820-12", CITATION),
    ("^20260820-1", CITATION),
    ("^package-driver-router", LOCATOR),
    ("^defect-owes-a-test", LOCATOR),
    ("^test-e2e-bloberia", LOCATOR),
    ("^chatlas2-normal-model-cache", LOCATOR),
    ("^route-index-search", LOCATOR),
    ("", None),
    ("^", None),
    ("^not a token", None),
    ("plain-word", LOCATOR),
)


@pytest.mark.parametrize(("token", "kind"), TOKENS)
def test_every_caret_token_classifies_as_exactly_one_kind(
    token: str, kind: str | None
) -> None:
    assert classify(token) == kind
    assert is_citation(token) is (kind == CITATION)
    assert is_locator(token) is (kind == LOCATOR)


def test_a_citation_is_never_also_a_locator() -> None:
    """The kinds partition. Overlap would make `classify` an arbitrary preference."""

    for token, _kind in TOKENS:
        assert not (is_citation(token) and is_locator(token)), token


def test_a_citation_parses_into_its_parts_and_reports_completeness() -> None:
    complete = parse_citation("^c20260820-12u")
    assert complete == parse_citation("c20260820-12u"), "the caret is spelling, not identity"
    assert (complete.sigil, complete.date, complete.seq, complete.tag) == (
        "c",
        "20260820",
        12,
        "u",
    )
    assert complete.is_complete
    assert complete.render() == "^c20260820-12u"

    #: An untagged key still resolves — Anchory shards by the untagged base — so parsing
    #: must accept it. Only minting requires the full form.
    partial = parse_citation("^c20260820-12")
    assert partial is not None and not partial.is_complete


def test_find_citations_requires_the_caret() -> None:
    """A bare `20260820-1` in prose is a date range, not a citation.

    Scanning running text is where a caretless grammar does damage: it would strip ordinary
    words out of index line bodies.
    """

    line = "the run on 20260820-1 landed ^c20260820-0u and ^d20260101-9a"
    assert find_citations(line) == ["^c20260820-0u", "^d20260101-9a"]


def test_a_trailing_address_of_either_kind_splits_off() -> None:
    assert split_trailing_address("- [DF] a body ^c20260820-0u") == (
        "- [DF] a body",
        "^c20260820-0u",
    )
    assert split_trailing_address("### Routing.Table ^package-driver-router") == (
        "### Routing.Table",
        "^package-driver-router",
    )
    assert split_trailing_address("no address here") == ("no address here", None)


def test_a_caret_inside_a_word_is_not_a_trailing_address() -> None:
    """It has to be a separate token, or `a^b` would be read as an address."""

    assert split_trailing_address("expression a^b") == ("expression a^b", None)


def test_several_trailing_addresses_all_strip() -> None:
    """An index line carries its citation; a turn quoting one may carry more."""

    assert strip_trailing_addresses("body ^c20260820-0u ^package-router") == "body"
    assert strip_trailing_addresses("body with none") == "body with none"
