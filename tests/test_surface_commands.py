# $kw: ^native-surface-cli-tests --from Normalization.Pipeline --from Floor.Model --note [TP] CLI language inference, explicit override, and model serialization ^c20260812-0u
from __future__ import annotations

import json
from pathlib import Path

from agentos.cli.cli import main


def test_normalize_infers_python_and_prints_complete_json(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "module.py"
    path.write_text("value = 1  # noqa\n# prose\n", encoding="utf-8")
    assert main(["surfaces", "normalize", "--file", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "agentos.surface-normal-model.v1"
    assert payload["language"] == "python"
    assert payload["model"]["text"] == path.read_text(encoding="utf-8")
    assert [item["kind"] for item in payload["model"]["directives"]] == ["lint-noqa"]
    assert payload["model"]["comments"][1]["directive"] is None


def test_normalize_explicit_language_overrides_unknown_extension(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "surface.txt"
    path.write_text("# Heading\n", encoding="utf-8")
    assert (
        main(
            [
                "surfaces",
                "normalize",
                "--file",
                str(path),
                "--language",
                "markdown",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["language"] == "markdown"
    assert payload["model"]["headings"][0]["text"] == "Heading"


def test_normalize_errors_when_language_cannot_be_inferred(
    tmp_path: Path,
    capsys,
) -> None:
    path = tmp_path / "surface.txt"
    path.write_text("content\n", encoding="utf-8")
    assert main(["surfaces", "normalize", "--file", str(path)]) == 1
    assert (
        "cannot infer surface language from extension `.txt`; provide --language"
        in capsys.readouterr().err
    )


def test_normalize_has_no_positional_file_argument() -> None:
    from agentos.cli.cli import build_parser

    parser = build_parser()
    try:
        parser.parse_args(["surfaces", "normalize", "module.py"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("positional file argument unexpectedly accepted")
