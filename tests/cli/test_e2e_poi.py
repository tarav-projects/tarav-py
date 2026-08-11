from __future__ import annotations

import json
from pathlib import Path

from agentos.cli.cli import build_parser, main


def _write_depot(
    root: Path,
    *,
    block: str = "Index.Linter/Block.TooLong",
    description: str = "a separator-anchored block exceeds the hard line limit",
) -> Path:
    (root / "poi").mkdir(parents=True)
    (root / "000-INDEX.md").write_text(
        f"# INDEX\n\n## poi\n\n- `poi/100-poi.md` - {block}\n",
        encoding="utf-8",
    )
    (root / "poi" / "100-poi.md").write_text(
        "****\n\n"
        f"## {block}\n\n"
        f"- [DF] {description}\n",
        encoding="utf-8",
    )
    return root


def _payload(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_poi_explain_resolves_registered_index_class(
    tmp_path: Path,
    monkeypatch,
    capsys: object,
) -> None:
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _write_depot(tmp_path / "agentos-pkg")

    assert "poi" in build_parser().format_help()
    assert (
        main(
            [
                "wayfinder",
                "register",
                "--package",
                "agentos-pkg",
                "--path",
                str(depot),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["poi", "explain", "Index.Linter/Block.TooLong"]) == 0
    text = capsys.readouterr().out
    assert "index://agentos-pkg/Index.Linter/Block.TooLong" in text
    assert "exceeds the hard line limit" in text

    assert (
        main(
            [
                "poi",
                "explain",
                "index://agentos-pkg/Index.Linter/Block.TooLong",
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
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "home"))
    depot = _write_depot(
        tmp_path / "agentos-chatlas-pkg",
        block="Index.Linter/Anchor.Chatlas.Tag",
        description="a Chatlas citation key lacks its user-evidence tag",
    )

    assert (
        main(
            [
                "wayfinder",
                "register",
                "--package",
                "agentos-chatlas-pkg",
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
                "Index.Linter/Anchor.Chatlas.Tag",
                "--json",
            ]
        )
        == 0
    )
    payload = _payload(capsys)

    assert payload["status"] == "resolved"
    assert payload["reference"]["root"]["id"] == "agentos-chatlas-pkg"  # type: ignore[index]
    assert payload["reference"]["address"] == (  # type: ignore[index]
        "Index.Linter/Anchor.Chatlas.Tag"
    )
