from __future__ import annotations

import pytest

from agentos._core.errors import CliError
from agentos.refs.ref_path import build_ref_path_uri, parse_ref_path_uri


def test_build_ref_path_uri_and_parse_round_trip() -> None:
    reference = {
        "class": "git_line_span",
        "commit": "949e55ea4eaff8de83952a4da9005bee30feeaed",
        "path": "docs/sample file.md",
        "start": {"line": 7, "column": 1},
        "end": {"line": 9, "column": 13},
    }
    uri = build_ref_path_uri("6ff493af8281d8cbcc0ca5b89b9dc2561115f450", reference)
    assert (
        uri
        == "git-ref://6ff493af8281d8cbcc0ca5b89b9dc2561115f450/"
        "blob/949e55ea4eaff8de83952a4da9005bee30feeaed/docs/sample%20file.md#L7C1-L9C13"
    )

    parsed = parse_ref_path_uri(uri)
    assert parsed["repo_hash"] == "6ff493af8281d8cbcc0ca5b89b9dc2561115f450"
    assert parsed["commit"] == "949e55ea4eaff8de83952a4da9005bee30feeaed"
    assert parsed["path"] == "docs/sample file.md"
    assert parsed["start"] == {"line": 7, "column": 1}
    assert parsed["end"] == {"line": 9, "column": 13}


def test_parse_ref_path_uri_rejects_invalid_scheme() -> None:
    with pytest.raises(CliError, match="scheme"):
        parse_ref_path_uri(
            "https://6ff493af8281d8cbcc0ca5b89b9dc2561115f450/"
            "blob/949e55ea4eaff8de83952a4da9005bee30feeaed/sample.md#L1C1-L1C2"
        )


def test_parse_ref_path_uri_rejects_invalid_fragment() -> None:
    with pytest.raises(CliError, match="fragment"):
        parse_ref_path_uri(
            "git-ref://6ff493af8281d8cbcc0ca5b89b9dc2561115f450/"
            "blob/949e55ea4eaff8de83952a4da9005bee30feeaed/sample.md#L7-L9"
        )


def test_build_ref_path_uri_requires_commit() -> None:
    with pytest.raises(CliError, match="commit"):
        build_ref_path_uri(
            "6ff493af8281d8cbcc0ca5b89b9dc2561115f450",
            {
                "path": "sample.md",
                "start": {"line": 1, "column": 1},
                "end": {"line": 1, "column": 2},
            },
        )
