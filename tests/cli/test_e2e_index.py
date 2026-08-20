# $kw: ^test-e2e-index --from Agentos.Index --note [DF] end-to-end coverage for the tarav index command surface
"""End-to-end coverage for `tarav index`.

This surface had none. Two defects lived here undisturbed through a full green suite: a
`--json` flag that skipped work rather than changing rendering, and a point lookup that ran
the whole corpus linter to report one record. Both are the kind a single exercising test
catches, which is the argument for the file existing at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.cli.cli import main


_GATE = ("--session", "s-1", "--token", "t-1", "--user-turn", "u-1", "--agent-turn", "a-1")

#: Every index subcommand that takes a data input, spelled the one supported way. Driven as
#: a table so a subcommand added later with a positional argument fails here rather than
#: shipping a second calling convention beside this one.
INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("session", "--session", "s-1"),
    ("messages", "--session", "s-1"),
    ("record", "--record-id", "ln_absent"),
    ("trace", "--trace-id", "tr_absent"),
    ("remove", "--record-id", "ln_absent"),
    ("revise", "--record-id", "ln_absent", "--body", "a revision"),
    ("gate", "--record-id", "ln_absent", *_GATE),
    ("resolve", "--label", "^c20260101-1u"),
    ("bless", "--poi-id", "poi-absent", *_GATE),
    ("explain", "--poi-class", "Index.Linter/Line.Untyped"),
    ("import", "--depot-root", "/nonexistent"),
    ("linter", "--label", "^c20260101-1u"),
    ("write", "--scope", "d/design#Concept", "--body", "a body", "--type", "DF"),
)


@pytest.fixture
def project(tmp_path: Path, capsys: object) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
    assert main(["index", "--project", str(root), "init", "--depot", "d"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    return root


def _write_line(project: Path, capsys: object, body: str) -> str:
    assert (
        main(
            [
                "index", "--project", str(project), "write",
                "--scope", "d/design#Concept", "--body", body, "--type", "DF",
            ]
        )
        == 0
    )
    return capsys.readouterr().out.split()[0]  # type: ignore[attr-defined]


def _json(project: Path, capsys: object, *argv: str) -> object:
    assert main(["index", "--project", str(project), "--json", *argv]) in (0, 1)
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]


def test_no_index_subcommand_accepts_a_positional_data_argument(
    project: Path, capsys: object
) -> None:
    """Index inputs are named options; a bare value is a parse error, not a second syntax.

    Each command is given its complete valid invocation plus one stray positional, so the
    rejection can only be about the positional -- a command that merely failed for missing
    arguments would pass a weaker version of this test while still accepting the old shape.
    """

    for invocation in INVOCATIONS:
        with pytest.raises(SystemExit) as exc_info:
            main(["index", "--project", str(project), *invocation, "stray-value"])
        assert exc_info.value.code == 2, invocation[0]
        capsys.readouterr()  # type: ignore[attr-defined]


def test_every_index_invocation_parses_under_its_named_options(
    project: Path, capsys: object
) -> None:
    """The named form parses. Whether the target exists is the command's own business."""

    for invocation in INVOCATIONS:
        try:
            main(["index", "--project", str(project), *invocation])
        except SystemExit as exc:  # a parse failure is the thing under test
            pytest.fail(f"{invocation[0]} did not parse: {exc}")
        except Exception:
            pass  # an absent target is a runtime answer, not a calling-convention failure
        capsys.readouterr()  # type: ignore[attr-defined]


def test_json_selects_presentation_and_never_which_work_runs(
    project: Path, capsys: object
) -> None:
    """`--json` renders differently; it must not compute differently.

    The retired behavior returned before deriving standing at all, so the JSON caller and
    the text caller were running two different commands under one name.
    """

    record_id = _write_line(project, capsys, "a line that is written to a surface")
    record = _json(project, capsys, "record", "--record-id", record_id)
    assert record["id"] == record_id  # type: ignore[index]
    assert "standing" in record, "a point lookup still reports standing"  # type: ignore[operator]

    resolved = _json(project, capsys, "resolve", "--label", record["line"]["label"])  # type: ignore[index]
    assert resolved["id"] == record_id  # type: ignore[index]
    assert "standing" in resolved  # type: ignore[operator]

    listing = _json(project, capsys, "record")
    assert [r["id"] for r in listing] == [record_id]  # type: ignore[index,union-attr]
    assert "open_signals" in listing[0], (  # type: ignore[index,operator]
        "the corpus listing reports error bars in both renderings"
    )


def test_targeted_lint_agrees_with_the_corpus_run_filtered_to_the_same_record(
    project: Path, capsys: object
) -> None:
    """The fast path is only safe if it answers what the slow path answers.

    Targeted linting exists to avoid running every check over every record for a point
    lookup. That is a claim about a *subset of checks*, and the way it goes wrong is
    silently: a check that needed corpus context returns fewer findings when handed one
    record. Asserting equality against the full run is what makes selecting checks safe.

    Several records, not one, and each asserted separately -- a selection mechanism that
    ignored its argument would pass a single-record version of this test.
    """

    ids = [
        _write_line(project, capsys, body)
        for body in (
            "an ungrounded line the linter will notice",
            "a second ungrounded line in the same scope",
            "a third line so the corpus is not one record",
        )
    ]
    # One record carries a gate. Without it the fixture exercises no gate check, and the
    # first version of this test passed while every `Gate.Contradicted` finding was
    # silently missing from targeted runs -- the checks that verify gates reach the
    # records through a shared helper, which a shallower scope derivation could not see.
    assert (
        main(
            [
                "index", "--project", str(project), "gate",
                "--record-id", ids[0], *_GATE,
            ]
        )
        == 0
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    corpus = _json(project, capsys, "linter")
    for record_id in ids:
        expected = sorted(
            (f["class"], f["subject"])  # type: ignore[index]
            for f in corpus["findings"]  # type: ignore[index]
            if f["subject"] == record_id
        )
        targeted = _json(project, capsys, "linter", "--record-id", record_id)
        assert sorted(
            (f["class"], f["subject"]) for f in targeted["findings"]  # type: ignore[index]
        ) == expected, record_id
        assert expected, "the fixture must actually produce findings to compare"


def test_a_selector_matching_no_record_fails_rather_than_reporting_a_clean_run(
    project: Path, capsys: object
) -> None:
    """A targeted run that silently examined nothing would report success for a line it
    never looked at, which is the one outcome worse than being slow."""

    assert main(
        ["index", "--project", str(project), "linter", "--label", "^c20260101-99u"]
    ) != 0
