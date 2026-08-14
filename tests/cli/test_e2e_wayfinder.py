from __future__ import annotations

import json
from pathlib import Path

from tarav.wayfinder import index_block_reference
from tarav.cli.cli import build_parser, main


def _captured_json(capsys: object) -> dict[str, object]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def _write_depot(root: Path) -> Path:
    design = root / "design"
    design.mkdir(parents=True)
    (root / "000-INDEX.md").write_text(
        "# INDEX\n\n## Routing\n\n- `design/100-design.md` - POI.Example\n",
        encoding="utf-8",
    )
    (design / "100-design.md").write_text(
        "****\n\n## POI.Example\n\n- Example documentation.\n",
        encoding="utf-8",
    )
    return root


def test_wayfinder_register_resolve_and_check_round_trip(
    tmp_path: Path,
    monkeypatch,
    capsys: object,
) -> None:
    home = tmp_path / "home"
    depot = _write_depot(tmp_path / "demo-pkg")
    monkeypatch.setenv("TARAV_HOME", str(home))

    assert "wayfinder" in build_parser().format_help()
    assert (
        main(
            [
                "wayfinder",
                "register",
                "--package",
                "demo-pkg",
                "--path",
                str(depot),
                "--hint",
                "Search for demo-pkg.",
            ]
        )
        == 0
    )
    registration = _captured_json(capsys)
    assert registration["status"] == "registered"
    assert registration["registration"]["root"]["id"] == "demo-pkg"  # type: ignore[index]

    assert main(["wayfinder", "resolve", "index://demo-pkg/POI.Example"]) == 0
    resolved = _captured_json(capsys)
    assert resolved["status"] == "resolved"
    assert "Example documentation." in resolved["target"]["content"]  # type: ignore[index]

    canonical = index_block_reference("demo-pkg", "POI.Example").to_json()
    assert main(["wayfinder", "resolve", "--reference-json", canonical]) == 0
    assert _captured_json(capsys)["reference"]["type"] == "index.block"  # type: ignore[index]

    assert main(["wayfinder", "check"]) == 0
    checked = _captured_json(capsys)
    assert checked["domain"]["status"] == "ok"
    assert checked["pois"] == []


def test_wayfinder_resolve_returns_structured_poi(
    tmp_path: Path,
    monkeypatch,
    capsys: object,
) -> None:
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / "home"))

    assert main(["wayfinder", "resolve", "index://missing-pkg/POI.Example"]) == 1
    payload = _captured_json(capsys)
    assert payload["status"] == "poi"
    assert payload["poi"]["class"]["address"] == (  # type: ignore[index]
        "Wayfinder.Resolution.POI"
    )
    assert payload["poi"]["evidence"]["kind"] == "missing"  # type: ignore[index]
