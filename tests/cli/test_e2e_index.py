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


_GATE = (
    "--session",
    "s-1",
    "--token",
    "t-1",
    "--user-turn",
    "u-1",
    "--agent-turn",
    "a-1",
)

#: Every index subcommand that takes a data input, spelled the one supported way. Driven as
#: a table so a subcommand added later with a positional argument fails here rather than
#: shipping a second calling convention beside this one.
INVOCATIONS: tuple[tuple[str, ...], ...] = (
    ("session", "--session", "s-1"),
    ("messages", "--session", "s-1"),
    ("lines", "--surface", "d/design"),
    ("record", "--record-id", "ln_absent"),
    ("trace", "--trace-id", "tr_absent"),
    ("remove", "--record-id", "ln_absent"),
    ("revise", "--record-id", "ln_absent", "--body", "a revision"),
    ("gate", "--record-id", "ln_absent", *_GATE),
    ("resolve", "--label", "^c20260101-1u"),
    ("bless", "--poi-id", "poi-absent", "--body", "a claim", "--type", "DC"),
    ("blessings", "--poi-id", "poi-absent"),
    ("explain", "--poi-class", "Index.Linter/Line.Untyped"),
    ("import", "--depot-root", "/nonexistent"),
    ("linter", "--label", "^c20260101-1u"),
    ("write", "--scope", "d/design#Concept", "--body", "a body", "--type", "DF"),
)


#: Subcommands whose answer or write target depends on the project, so they name it
#: themselves. Every other subcommand reads only the shared depot or the chat archive.
PROJECT_COMMANDS = frozenset(
    {"lines", "record", "revise", "trace", "resolve", "import", "linter"}
)


def _argv(
    project: Path, invocation: tuple[str, ...], *, json_flag: bool = False
) -> list[str]:
    """The invocation as a caller writes it, with --project wherever that command wants it."""

    head = ["index", "--json"] if json_flag else ["index"]
    if invocation[0] in PROJECT_COMMANDS:
        return [*head, invocation[0], "--project", str(project), *invocation[1:]]
    return [*head, "--project", str(project), *invocation]


@pytest.fixture
def project(tmp_path: Path, capsys: object) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "AGENTS.md").write_text("# test project\n", encoding="utf-8")
    marker = root / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "11111111-1111-4111-8111-111111111111",
            }
        ),
        encoding="utf-8",
    )
    assert main(["index", "--project", str(root), "init", "--depot", "d"]) == 0
    capsys.readouterr()  # type: ignore[attr-defined]
    return root


def _write_line(project: Path, capsys: object, body: str) -> str:
    assert (
        main(
            [
                "index",
                "--project",
                str(project),
                "write",
                "--scope",
                "d/design#Concept",
                "--body",
                body,
                "--type",
                "DF",
            ]
        )
        == 0
    )
    return capsys.readouterr().out.split()[0]  # type: ignore[attr-defined]


def _json(project: Path, capsys: object, *argv: str) -> object:
    assert main(_argv(project, argv, json_flag=True)) in (0, 1)
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
        command = _argv(project, invocation)
        with pytest.raises(SystemExit) as exc_info:
            main([*command, "stray-value"])
        assert exc_info.value.code == 2, invocation[0]
        capsys.readouterr()  # type: ignore[attr-defined]


def test_every_index_invocation_parses_under_its_named_options(
    project: Path, capsys: object
) -> None:
    """The named form parses. Whether the target exists is the command's own business."""

    for invocation in INVOCATIONS:
        command = _argv(project, invocation)
        try:
            main(command)
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
    # first version of this test passed while every `Gate.Evidence.Invalid` finding was
    # silently missing from targeted runs -- the checks that verify gates reach the
    # records through a shared helper, which a shallower scope derivation could not see.
    assert (
        main(
            [
                "index",
                "--project",
                str(project),
                "gate",
                "--record-id",
                ids[0],
                *_GATE,
            ]
        )
        == 0
    )
    capsys.readouterr()  # type: ignore[attr-defined]

    corpus = _json(project, capsys, "linter", "--limit", "1000")
    for record_id in ids:
        expected = sorted(
            (f["class_address"], f["subject"])  # type: ignore[index]
            for f in corpus["poi_instances"]["items"]  # type: ignore[index]
            if f["subject"] == record_id
        )
        targeted = _json(
            project,
            capsys,
            "linter",
            "--record-id",
            record_id,
            "--limit",
            "1000",
        )
        assert (
            sorted(
                (f["class_address"], f["subject"])
                for f in targeted["poi_instances"]["items"]  # type: ignore[index]
            )
            == expected
        ), record_id
        assert expected, "the fixture must actually produce findings to compare"


def test_linter_text_and_json_share_one_bounded_agent_report(
    project: Path, capsys: object
) -> None:
    for body in ("first migration line", "second migration line"):
        _write_line(project, capsys, body)

    payload = _json(project, capsys, "linter", "--limit", "1")
    window = payload["poi_instances"]  # type: ignore[index]
    assert payload["class"] == "Index.Linter.Run"  # type: ignore[index]
    assert payload["execution"]["project_id"] == "11111111-1111-4111-8111-111111111111"  # type: ignore[index]
    assert payload["execution"]["project_root"] == str(project.resolve())  # type: ignore[index]
    assert window["shown"] == 1
    assert window["matching"] == window["total"]
    assert window["truncated"] is True
    assert (
        sum(row["counts"]["total"] for row in payload["poi_classes"])
        == window[  # type: ignore[index]
            "total"
        ]
    )

    assert (
        main(
            [
                "index",
                "linter",
                "--project",
                str(project),
                "--limit",
                "1",
            ]
        )
        == 1
    )
    rendered = capsys.readouterr().out  # type: ignore[attr-defined]
    assert (
        f"showing 1 of {window['matching']} matching POI instances "
        f"({window['total']} total)" in rendered
    )
    assert "Concentration" not in rendered
    assert "11111111-1111-4111-8111-111111111111" in rendered


def test_linter_requires_project_and_bare_project_uses_pwd(
    project: Path, capsys: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["index", "linter"])
    assert exc_info.value.code == 2
    capsys.readouterr()

    monkeypatch.chdir(project)
    assert main(["index", "linter", "--project", "--limit", "0"]) in (0, 1)
    assert "11111111-1111-4111-8111-111111111111" in capsys.readouterr().out


def test_explicit_project_makes_linter_results_cwd_invariant(
    project: Path, capsys: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_line(project, capsys, "cwd cannot alter this verdict")
    first = _json(project, capsys, "linter", "--limit", "1000")

    outside = project.parent / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    second = _json(project, capsys, "linter", "--limit", "1000")

    first["execution"].pop("elapsed_ms")  # type: ignore[index]
    second["execution"].pop("elapsed_ms")  # type: ignore[index]
    assert second == first


def test_every_project_command_requires_a_named_project(
    project: Path, capsys: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A project-scoped command must not fall back to the working directory.

    This is the defect, stated exactly. `resolve` carried no --project at all, so it derived
    geography from wherever it was called; standing is computed by scanning the project's
    surfaces, so the same stored record read `head` inside the project and `tail` outside it.
    Requiring the flag is what removes the fallback -- honouring it was never the problem.
    """

    monkeypatch.chdir(project)
    covered = set()
    for invocation in INVOCATIONS:
        if invocation[0] not in PROJECT_COMMANDS:
            continue
        covered.add(invocation[0])
        # The complete invocation minus the project, so the only thing missing is the one
        # thing under test -- a command failing for some other absent argument would pass
        # a weaker version of this while still falling back to the working directory.
        with pytest.raises(SystemExit) as exc_info:
            main(["index", *invocation])
        assert exc_info.value.code == 2, invocation[0]
        capsys.readouterr()  # type: ignore[attr-defined]

    assert covered == PROJECT_COMMANDS


def test_a_named_project_answers_the_same_from_any_directory(
    project: Path, capsys: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Given the project, the answer is the project's -- not the caller's."""

    record_id = _write_line(
        project, capsys, "standing cannot depend on the caller's pwd"
    )
    label = _json(project, capsys, "record", "--record-id", record_id)["line"]["label"]  # type: ignore[index,call-overload]

    def _text(*argv: str) -> str:
        assert main(_argv(project, argv)) in (0, 1)
        return capsys.readouterr().out  # type: ignore[attr-defined]

    probes = (("record", "--record-id", record_id), ("resolve", "--label", label))
    inside = {probe[0]: _json(project, capsys, *probe) for probe in probes}
    inside["lines"] = _text("lines")

    # A sibling project, not a bare directory: an unmarked one resolves upward and finds
    # this project anyway, which would pass the assertion without proving anything.
    outside = project.parent / "elsewhere"
    outside.mkdir()
    (outside / "AGENTS.md").write_text("# another project\n", encoding="utf-8")
    monkeypatch.chdir(outside)

    for probe in probes:
        assert _json(project, capsys, *probe) == inside[probe[0]], probe[0]
    assert _text("lines") == inside["lines"]


def test_capture_uses_the_same_required_project_contract(
    project: Path, capsys: object
) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["index", "capture", "preview"])
    assert exc_info.value.code == 2
    capsys.readouterr()

    manifest = project / "capture.json"
    manifest.write_text("{}\n", encoding="utf-8")
    assert (
        main(
            [
                "index",
                "--json",
                "capture",
                "preview",
                "--project",
                str(project),
                "--manifest",
                str(manifest),
            ]
        )
        == 1
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert "Capture.Manifest" in captured.err


def test_linter_poi_selectors_filter_instances_without_hiding_class_totals(
    project: Path, capsys: object
) -> None:
    _write_line(project, capsys, "one migration line")
    corpus = _json(project, capsys, "linter", "--limit", "100")
    selected = corpus["poi_instances"]["items"][0]  # type: ignore[index]

    narrowed = _json(
        project,
        capsys,
        "linter",
        "--poi-class",
        selected["class_address"],
        "--poi-id",
        selected["instance_id"],
        "--status",
        selected["status"],
        "--limit",
        "20",
    )

    assert narrowed["poi_instances"]["matching"] == 1  # type: ignore[index]
    assert (
        narrowed["poi_instances"]["items"][0]["instance_id"]
        == selected[  # type: ignore[index]
            "instance_id"
        ]
    )
    assert narrowed["poi_classes"] == corpus["poi_classes"]  # type: ignore[index]

    assert (
        main(
            [
                "index",
                "linter",
                "--project",
                str(project),
                "--poi-id",
                "poi-does-not-exist",
            ]
        )
        == 1
    )
    assert "matched no occurrence" in capsys.readouterr().err  # type: ignore[attr-defined]


def test_explain_accepts_the_exact_class_emitted_by_the_linter(
    project: Path, capsys: object
) -> None:
    assert (
        main(
            [
                "index",
                "--project",
                str(project),
                "explain",
                "--poi-class",
                "Index.Linter/Line.Unrecorded",
            ]
        )
        == 0
    )
    rendered = capsys.readouterr().out  # type: ignore[attr-defined]
    assert "anchor-has-record" in rendered
    assert "block://" in rendered
    assert "Index.Linter/Line.Unrecorded" in rendered


def test_a_selector_matching_no_record_fails_rather_than_reporting_a_clean_run(
    project: Path, capsys: object
) -> None:
    """A targeted run that silently examined nothing would report success for a line it
    never looked at, which is the one outcome worse than being slow."""

    assert (
        main(
            ["index", "linter", "--project", str(project), "--label", "^c20260101-99u"]
        )
        != 0
    )
