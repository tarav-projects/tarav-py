from __future__ import annotations

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
