# $kw: ^test-workspaces-guide --from Run.Workspace --from Skw.Surface.Token --note [DF] boundary tests for the tokened workspaces guide, the surface the init gate reads --supp ^c20260809-92u ^<anchor-on-landing>
from __future__ import annotations

from pathlib import Path

import pytest

from tarav.workspaces.guide import (
    GuideError,
    guide_text,
    guide_token,
    parse_guide_token,
)


def test_the_guide_carries_a_parsable_surface_token() -> None:
    token = guide_token()
    assert token.startswith("aws-unlock:")
    assert len(token) > len("aws-unlock:")


def test_the_token_is_the_last_line_of_the_guide() -> None:
    """An agent that read the output has the receipt; one that skimmed does not."""
    lines = [line for line in guide_text().splitlines() if line.strip()]
    assert guide_token() in lines[-1]


def test_the_guide_states_what_a_workspace_is() -> None:
    text = guide_text().lower()
    for expected in ("agents.md", "git", "status", "extracted", "volatile.surface"):
        assert expected in text


@pytest.mark.parametrize(
    "body",
    [
        "# Guide\n\nno token here\n",
        "surface-token:\n",
        "surface-token: wrong-prefix:abc\n",
    ],
)
def test_a_guide_without_a_well_formed_token_fails_loudly(body: str) -> None:
    """An unreadable token must not read as an empty one, which would gate nothing."""
    with pytest.raises(GuideError):
        parse_guide_token(body)


def test_the_shipped_guide_is_a_package_resource() -> None:
    from tarav.workspaces import guide as module

    assert (Path(module.__file__).parent / "GUIDE.md").is_file()
