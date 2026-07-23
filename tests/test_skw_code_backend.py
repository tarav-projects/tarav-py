"""skw-code backend (carrier B): `# $kw:` machinery on code surfaces."""

from __future__ import annotations

from agentos.skillware.model import parse_skw_code


def test_code_annotation_only_note_parses() -> None:
    # the common code case: a pure `--note` attached to a function, self-closing
    src = (
        "# $kw: ^retry --note [CT] broker can double-deliver ^c20260722-21u\n"
        "def send(msg):\n"
        "    return _do(msg)\n"
    )
    parsed = parse_skw_code(src)
    assert not parsed.findings
    assert len(parsed.notes) == 1
    note = parsed.notes[0]
    assert note.flag == "note"
    assert note.type == "CT"
    assert "double-deliver" in note.text
    assert note.anchor == "^c20260722-21u"


def test_code_from_dependency_parses() -> None:
    src = "# $kw: --from Design.Retry\ndef send(msg):\n    ...\n"
    parsed = parse_skw_code(src)
    assert not parsed.findings
    assert len(parsed.dependencies) == 1
    assert parsed.dependencies[0].froms == ("Design.Retry",)


def test_code_materializing_block_parses() -> None:
    src = "# $kw: #gen --derived --from Tmpl.X\nGENERATED = 1\n# $kw. end\n"
    parsed = parse_skw_code(src)
    assert not parsed.findings
    assert [r.verb for r in parsed.recipes] == ["derived"]


def test_code_unclosed_materializing_block_is_parse_error() -> None:
    src = "# $kw: #gen --derived --from Tmpl.X\nGENERATED = 1\n"
    parsed = parse_skw_code(src)
    assert any("left open at EOF" in f.message for f in parsed.findings)


def test_plain_comment_is_not_machinery() -> None:
    src = "# just a normal comment\nx = 1\n"
    parsed = parse_skw_code(src)
    assert not parsed.findings
    assert not parsed.notes
    assert not parsed.dependencies
    assert not parsed.recipes


def test_blockquote_is_not_a_code_carrier() -> None:
    # the markdown carrier must not leak into the code backend
    src = "> $kw: --from Design.Retry\nx = 1\n"
    parsed = parse_skw_code(src)
    assert not parsed.dependencies
