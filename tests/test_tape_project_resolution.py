from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos._core.errors import CliError
from agentos._core.utils import validate_string_for_path
from agentos.cli import main


def test_validate_string_for_path_rejects_traversal_tokens() -> None:
    assert validate_string_for_path("bla", field_name="tape") == "bla"

    with pytest.raises(CliError, match="path separators"):
        validate_string_for_path("a/b", field_name="tape")

    with pytest.raises(CliError, match="path separators"):
        validate_string_for_path(r"a\b", field_name="tape")

    with pytest.raises(CliError, match="must not be"):
        validate_string_for_path("..", field_name="tape")


def test_init_project_writes_class_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["marker"]["class"] == "agentos.project"
    config_payload = json.loads((tmp_path / ".agentos" / "config.json").read_text(encoding="utf-8"))
    assert config_payload["class"] == "agentos.project.config"


def test_init_global_writes_class_field(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("AGENTOS_HOME", str(tmp_path / "agentos-home"))

    assert main(["init", "--scope", "global"]) == 0
    payload = json.loads(capsys.readouterr().out)

    config_path = Path(payload["config_path"])
    config_payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert config_payload["class"] == "agentos.global.config"


def test_folder_init_with_tape_requires_agentos_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    code = main(["tape", "init", "--tape", "bla"])
    assert code == 1
    stderr = capsys.readouterr().err
    assert "run `agentos init`" in stderr


def test_folder_init_resolves_tape_name_to_project_tapes_folder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    payload = json.loads(capsys.readouterr().out)

    expected_root = (tmp_path / ".agentos" / "tapes" / "bla").resolve()
    assert payload["resolution"] == "project-tape"
    assert payload["tape"] == "bla"
    assert payload["root_path"] == str(expected_root)
    assert (expected_root / "tape.manifest.json").is_file()


def test_append_requires_explicit_init_for_missing_tape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "tape",
            "append",
            "--tape",
            "bla",
            "--writer-id",
            "proc-a",
            "--class",
            "event.alpha",
        ]
    )
    assert code == 1
    assert "pass --init" in capsys.readouterr().err


def test_append_with_init_creates_missing_tape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
                "--init",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tape_created"] is True
    assert set(payload["record"].keys()) == {"class", "writer", "created_at"}


def test_append_warns_on_init_option_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
                "--init",
                "--init-naming",
                "monthly",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    warnings = payload.get("warnings", [])
    assert any("naming_strategy differs" in warning for warning in warnings)


def test_append_warns_for_existing_non_default_tape_without_init_options(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla", "--naming", "monthly"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    warnings = payload.get("warnings", [])
    assert any("non-default config" in warning for warning in warnings)


def test_tape_config_reports_defaults_and_current_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "tape",
                "init",
                "--tape",
                "bla",
                "--naming",
                "monthly",
                "--max-records-per-segment",
                "123",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["tape", "config", "--tape", "bla"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "tape config"
    assert payload["defaults"]["naming_strategy"] == "sequential"
    assert payload["defaults"]["max_records_per_segment"] == 1000
    assert payload["defaults"]["tape.class"] is None
    assert payload["defaults"]["data_schema"] is None
    assert payload["warning_policy"]["missing_tape_on_write_without_init"] == "error"
    assert payload["config"]["naming_strategy"] == "monthly"
    assert payload["config"]["max_records_per_segment"] == 123


def test_tape_doctor_reports_counts_and_staging_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "consolidate",
                "--tape",
                "bla",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-b",
                "--class",
                "event.beta",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["tape", "doctor", "--tape", "bla"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["command"] == "tape doctor"
    assert payload["committed_record_count"] == 1
    assert payload["best_effort_record_count"] == 2
    assert payload["staging_file_count"] == 2
    assert payload["staging_files"] == ["proc-a.jsonl", "proc-b.jsonl"]


def test_tape_query_with_consolidate_processes_staging_before_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["tape", "query", "--tape", "bla", "--count"]) == 0
    initial = json.loads(capsys.readouterr().out)
    assert initial["count"] == 0

    assert main(["tape", "query", "--tape", "bla", "--count", "--consolidate"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "tape query"
    assert payload["count"] == 1
    assert payload["consolidated"]["processed_count"] == 1


def test_append_batch_rejects_unknown_record_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert main(["tape", "init", "--tape", "bla"]) == 0
    capsys.readouterr()

    code = main(
        [
            "tape",
            "append-batch",
            "--tape",
            "bla",
            "--writer-id",
            "proc-a",
            "--entries-json",
            '[{"class":"event.alpha","refs":[{"id":"x"}]}]',
        ]
    )
    assert code == 1
    assert "unsupported fields: refs" in capsys.readouterr().err


def test_init_accepts_tape_class_and_data_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "tape",
                "init",
                "--tape",
                "bla",
                "--tape-class",
                "events.demo",
                "--data-schema-json",
                '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}',
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["config"]["tape.class"] == "events.demo"
    assert payload["config"]["data_schema"]["type"] == "object"
    assert payload["config"]["data_schema"]["required"] == ["k"]


def test_append_validates_record_data_with_data_schema(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["init", "--scope", "project", "--root", str(tmp_path)]) == 0
    capsys.readouterr()

    monkeypatch.chdir(tmp_path)
    assert (
        main(
            [
                "tape",
                "init",
                "--tape",
                "bla",
                "--data-schema-json",
                '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object","required":["k"],"properties":{"k":{"type":"string"}},"additionalProperties":false}',
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "tape",
                "append",
                "--tape",
                "bla",
                "--writer-id",
                "proc-a",
                "--class",
                "event.alpha",
                "--data-json",
                '{"k":"ok"}',
            ]
        )
        == 0
    )
    valid_payload = json.loads(capsys.readouterr().out)
    assert valid_payload["record"]["data"]["k"] == "ok"

    invalid_code = main(
        [
            "tape",
            "append",
            "--tape",
            "bla",
            "--writer-id",
            "proc-a",
            "--class",
            "event.beta",
            "--data-json",
            '{"k":123}',
        ]
    )
    assert invalid_code == 1
    assert "does not match data_schema" in capsys.readouterr().err
