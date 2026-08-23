from __future__ import annotations

import json
from pathlib import Path

from tarav.cli.cli import build_parser, main


def _write_depot(
    root: Path,
    *,
    block: str = "Index.Linter/Block.TooLong",
    description: str = "a separator-anchored block exceeds the hard line limit",
) -> Path:
    """A project whose Index records hold one POI class block."""
    import sys

    sys.path.insert(0, str(Path(__file__).parents[1]))
    from _skillware_helpers import write_index

    root.mkdir(parents=True, exist_ok=True)
    write_index(root, ((f"{root.name}/poi#{block}", (("DF", description),), ()),))
    return root


def _payload(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_poi_explain_resolves_explicit_registered_index_class(
    tmp_path: Path,
    monkeypatch,
    capsys: object,
) -> None:
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / "home"))
    depot = _write_depot(tmp_path / "tarav-pkg")

    assert "poi" in build_parser().format_help()
    assert (
        main(
            [
                "wayfinder",
                "register",
                "--package",
                "tarav-pkg",
                "--path",
                str(depot),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "poi",
                "explain",
                "--class",
                "index://tarav-pkg/Index.Linter/Block.TooLong",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "index://tarav-pkg/Index.Linter/Block.TooLong" in text
    assert "exceeds the hard line limit" in text

    assert (
        main(
            [
                "poi",
                "explain",
                "--class",
                "index://tarav-pkg/Index.Linter/Block.TooLong",
                "--json",
            ]
        )
        == 0
    )
    assert _payload(capsys)["status"] == "resolved"


def test_poi_explain_resolves_chatlas_owned_class_from_its_package(
    tmp_path: Path,
    monkeypatch,
    capsys: object,
) -> None:
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / "home"))
    depot = _write_depot(
        tmp_path / "tarav-chatlas-pkg",
        block="Index.Linter/Anchor.Chatlas.Tag",
        description="a Chatlas citation key lacks its user-evidence tag",
    )

    assert (
        main(
            [
                "wayfinder",
                "register",
                "--package",
                "tarav-chatlas-pkg",
                "--path",
                str(depot),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "poi",
                "explain",
                "--class",
                "index://tarav-chatlas-pkg/Index.Linter/Anchor.Chatlas.Tag",
                "--json",
            ]
        )
        == 0
    )
    payload = _payload(capsys)

    assert payload["status"] == "resolved"
    assert payload["reference"]["root"]["id"] == "tarav-chatlas-pkg"  # type: ignore[index]
    assert payload["reference"]["address"] == (  # type: ignore[index]
        "Index.Linter/Anchor.Chatlas.Tag"
    )
